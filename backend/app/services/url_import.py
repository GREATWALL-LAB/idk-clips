"""Import a video from a direct file URL, with server-side request forgery (SSRF) protection.

What is supported: direct links to video files (``https://example.com/talk.mp4``)
that you have permission to use, for example your own server, cloud bucket or
a public-domain archive.

What is refused: video platforms such as YouTube. Their terms of service do not
allow downloading and they use technical protection measures; IDK Clips does
not bypass those. Users are told to upload a file they have the rights to use
(YouTube creators can download their own uploads from YouTube Studio).

SSRF defenses:
- only http(s), no credentials in the URL;
- every resolved address must be public (no loopback, private, link-local,
  multicast or reserved ranges) unless the server's configuration allows private networks;
- the address actually connected to is re-checked after connecting, which
  defeats DNS-rebinding tricks;
- redirects are followed manually and every hop is re-validated;
- size limits are enforced while streaming, and HTML pages are rejected.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from openclip_processing.errors import JobCancelled, ProcessingError

MAX_REDIRECTS = 5
USER_AGENT = "IDKClips/0.1 (self-hosted video importer)"

_PLATFORMS = {
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "youtube-nocookie.com": "YouTube",
    "tiktok.com": "TikTok",
    "instagram.com": "Instagram",
    "facebook.com": "Facebook",
    "fb.watch": "Facebook",
    "x.com": "X (Twitter)",
    "twitter.com": "X (Twitter)",
    "twitch.tv": "Twitch",
    "vimeo.com": "Vimeo",
    "dailymotion.com": "Dailymotion",
    "netflix.com": "Netflix",
    "primevideo.com": "Prime Video",
    "disneyplus.com": "Disney+",
    "hulu.com": "Hulu",
}


class UrlImportError(ProcessingError):
    """A user-facing reason why a URL cannot be imported."""


def platform_for(host: str) -> str | None:
    host = host.lower().rstrip(".")
    for domain, name in _PLATFORMS.items():
        if host == domain or host.endswith(f".{domain}"):
            return name
    return None


def platform_message(name: str) -> str:
    return (
        f"IDK Clips does not download videos from {name}. {name}'s terms do not allow it and the "
        "videos are technically protected, which this app will not bypass. If you own the video or "
        "have permission to use it, download the original file (YouTube creators can use YouTube "
        "Studio > Content > Download) and upload it here."
    )


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return bool(ip.is_global) and not ip.is_multicast


def validate_url(url: str, *, allow_private: bool = False) -> str:
    """Check scheme, credentials, platform and resolved addresses. Returns the URL."""
    if len(url) > 2048:
        raise UrlImportError("The URL is too long.")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise UrlImportError("Only http:// and https:// links can be imported.")
    if parts.username or parts.password:
        raise UrlImportError("Links that contain a username or password are not accepted.")
    host = parts.hostname
    if not host:
        raise UrlImportError("The URL has no host name.")
    platform = platform_for(host)
    if platform:
        raise UrlImportError(platform_message(platform))
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise UrlImportError("The URL has an invalid port.") from exc
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UrlImportError("The host name in this link could not be found.") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise UrlImportError("The host name in this link could not be resolved.")
    if not allow_private and not all(_is_public(a) for a in addresses):
        raise UrlImportError(
            "This link points to a private or local network address, which is not allowed."
        )
    return url


def _check_peer(response: httpx.Response, allow_private: bool) -> None:
    stream = response.extensions.get("network_stream")
    server_addr = stream.get_extra_info("server_addr") if stream is not None else None
    if server_addr is None:
        raise UrlImportError("Could not verify the server address for this link.")
    if not allow_private and not _is_public(server_addr[0]):
        raise UrlImportError(
            "This link resolved to a private or local network address, which is not allowed."
        )


def download_video(
    url: str,
    destination: Path,
    *,
    max_bytes: int,
    allow_private: bool = False,
    progress: Callable[[float, str | None], None] = lambda _f, _s=None: None,
    should_cancel: Callable[[], bool] = lambda: False,
    transport: httpx.BaseTransport | None = None,
) -> int:
    """Stream a direct video link to ``destination``. Returns the number of bytes written."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    current = url
    timeout = httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0)
    with httpx.Client(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,  # never route through environment proxies
        headers={"User-Agent": USER_AGENT, "Accept": "video/*,application/octet-stream;q=0.9"},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            validate_url(current, allow_private=allow_private)
            with client.stream("GET", current) as response:
                if transport is None:
                    _check_peer(response, allow_private)
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise UrlImportError("The server sent a redirect without a target.")
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    raise UrlImportError(
                        f"The server responded with HTTP {response.status_code}. Check that the "
                        "link is a direct, public link to a video file."
                    )
                content_type = (
                    response.headers.get("content-type", "").split(";")[0].strip().lower()
                )
                if content_type.startswith("text/") or content_type in {
                    "application/json",
                    "application/xml",
                    "application/xhtml+xml",
                }:
                    raise UrlImportError(
                        "This link opens a web page, not a video file. Use a direct link to the "
                        "video (it usually ends in .mp4), or download the file and upload it."
                    )
                declared = response.headers.get("content-length")
                total = int(declared) if declared and declared.isdigit() else None
                if total is not None and total > max_bytes:
                    raise UrlImportError(
                        f"The video is larger than the {max_bytes // (1024 * 1024)} MB upload limit."
                    )
                written = 0
                with destination.open("wb") as handle:
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        if should_cancel():
                            raise JobCancelled()
                        written += len(chunk)
                        if written > max_bytes:
                            raise UrlImportError(
                                f"The video is larger than the {max_bytes // (1024 * 1024)} MB limit."
                            )
                        handle.write(chunk)
                        if total:
                            progress(min(written / total, 1.0), "Downloading video")
                if written == 0:
                    raise UrlImportError("The link returned an empty file.")
                return written
    raise UrlImportError("The link redirected too many times.")
