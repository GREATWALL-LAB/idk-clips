"""YouTube as a *reference* source, using only methods YouTube permits.

What IDK Clips does with a YouTube link:

- recognises the video ID and asks YouTube's public **oEmbed** endpoint for the
  title, channel and thumbnail (an official, documented, unauthenticated API);
- creates a project that remembers the link and that metadata;
- asks the creator to add the video file they downloaded from **YouTube Studio**
  (Content > Download) or Google Takeout, which is how YouTube lets owners get
  their own videos.

What it deliberately does not do: download video or audio streams from YouTube.
YouTube's Terms of Service only allow downloads through features YouTube itself
provides, and stream downloaders work by defeating technical protections. No such
code is shipped, and no cookies, logins or age/region checks are bypassed.

The oEmbed request is built from a validated 11-character video ID, so the user
cannot steer the server to any other host (no SSRF surface).
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from openclip_processing.errors import ProcessingError

OEMBED_URL = "https://www.youtube.com/oembed"
USER_AGENT = "IDKClips/0.1 (oEmbed metadata lookup)"
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
_PATH_PREFIXES = ("/shorts/", "/embed/", "/live/", "/v/")
_THUMBNAIL_HOSTS = {"i.ytimg.com", "i1.ytimg.com", "i2.ytimg.com", "i3.ytimg.com", "i4.ytimg.com"}

HOW_TO_GET_THE_FILE = (
    "Download the original file from YouTube Studio (Content > the video's menu > Download) "
    "or Google Takeout, then add it to this project."
)


class YouTubeError(ProcessingError):
    """A user-facing reason why a YouTube link cannot be used."""


def parse_video_id(url: str) -> str | None:
    """Return the 11-character video ID for a YouTube watch/short/embed link, else None."""
    if not url or len(url) > 2048:
        return None
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or parts.username or parts.password:
        return None
    host = (parts.hostname or "").lower()
    candidate: str | None = None
    if host in _SHORT_HOSTS:
        candidate = parts.path.strip("/").split("/")[0]
    elif host in _HOSTS:
        if parts.path == "/watch":
            candidate = (parse_qs(parts.query).get("v") or [None])[0]
        else:
            for prefix in _PATH_PREFIXES:
                if parts.path.startswith(prefix):
                    candidate = parts.path[len(prefix) :].split("/")[0]
                    break
    return candidate if candidate and _VIDEO_ID_RE.match(candidate) else None


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _safe_thumbnail(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 300:
        return None
    parts = urlsplit(value)
    if parts.scheme == "https" and (parts.hostname or "") in _THUMBNAIL_HOSTS:
        return value
    return None


def lookup(video_id: str, transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    """Public metadata for a video from YouTube's oEmbed API.

    Raises YouTubeError when the video is private, removed or not embeddable.
    """
    if not _VIDEO_ID_RE.match(video_id):
        raise YouTubeError("That does not look like a YouTube video link.")
    try:
        with httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(8.0),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        ) as client:
            response = client.get(
                OEMBED_URL, params={"url": canonical_url(video_id), "format": "json"}
            )
    except httpx.HTTPError as exc:
        raise YouTubeError(
            "YouTube could not be reached to look up this video. You can still create the "
            "project and add your video file.",
            detail=str(exc),
        ) from exc
    if response.status_code in (401, 403):
        raise YouTubeError(
            "This video is private or cannot be embedded, so its details are not public. "
            "If it is your video, you can still create the project and add the file."
        )
    if response.status_code in (400, 404):
        raise YouTubeError("YouTube does not have a public video at this link.")
    if response.status_code != 200:
        raise YouTubeError(
            f"YouTube answered with an unexpected status ({response.status_code}).",
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise YouTubeError("YouTube sent an unreadable answer.") from exc
    if not isinstance(data, dict):
        raise YouTubeError("YouTube sent an unreadable answer.")

    def text(key: str, limit: int) -> str | None:
        value = data.get(key)
        return " ".join(value.split())[:limit] if isinstance(value, str) and value.strip() else None

    author_url = text("author_url", 300)
    if author_url and (urlsplit(author_url).hostname or "").lower() not in _HOSTS:
        author_url = None
    return {
        "video_id": video_id,
        "url": canonical_url(video_id),
        "title": text("title", 200),
        "author_name": text("author_name", 120),
        "author_url": author_url,
        "thumbnail_url": _safe_thumbnail(data.get("thumbnail_url")),
    }
