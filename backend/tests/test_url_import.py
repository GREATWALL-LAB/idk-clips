from __future__ import annotations

import socket
from pathlib import Path

import httpx
import pytest

from app.services import url_import
from app.services.url_import import UrlImportError, download_video, validate_url


def _fake_dns(mapping: dict[str, str]):  # type: ignore[no-untyped-def]
    def getaddrinfo(host, port, *args, **kwargs):  # type: ignore[no-untyped-def]
        if host not in mapping:
            raise socket.gaierror("unknown host")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (mapping[host], port))]

    return getaddrinfo


@pytest.fixture
def dns(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    mapping = {
        "videos.example.com": "93.184.215.14",
        "internal.example.com": "10.0.0.5",
        "metadata.example.com": "169.254.169.254",
        "loop.example.com": "127.0.0.1",
    }
    monkeypatch.setattr(url_import.socket, "getaddrinfo", _fake_dns(mapping))
    return mapping


@pytest.mark.parametrize(
    ("url", "fragment"),
    [
        ("ftp://videos.example.com/a.mp4", "http"),
        ("https://user:pass@videos.example.com/a.mp4", "username"),
        ("https://youtu.be/abc", "YouTube"),
        ("https://m.youtube.com/watch?v=abc", "YouTube"),
        ("https://www.tiktok.com/@x/video/1", "TikTok"),
        ("https://internal.example.com/a.mp4", "private"),
        ("https://metadata.example.com/a.mp4", "private"),
        ("https://loop.example.com/a.mp4", "private"),
        ("https://unknown-host.invalid/a.mp4", "could not be found"),
    ],
)
def test_validate_url_rejections(dns, url: str, fragment: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(UrlImportError) as error:
        validate_url(url)
    assert fragment.lower() in error.value.user_message.lower()


def test_validate_url_accepts_public_direct_links(dns) -> None:  # type: ignore[no-untyped-def]
    assert validate_url("https://videos.example.com/talk.mp4")
    # Admins can explicitly allow private networks (for example a NAS on the LAN).
    assert validate_url("https://internal.example.com/a.mp4", allow_private=True)


def _transport(routes: dict[str, httpx.Response]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404))

    return httpx.MockTransport(handler)


def test_download_writes_file(dns, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    data = b"\x00\x00\x00\x18ftypmp42" + b"x" * 5000
    transport = _transport(
        {
            "https://videos.example.com/a.mp4": httpx.Response(
                200, content=data, headers={"content-type": "video/mp4"}
            )
        }
    )
    written = download_video(
        "https://videos.example.com/a.mp4",
        tmp_path / "a.mp4",
        max_bytes=10_000,
        transport=transport,
    )
    assert written == len(data)
    assert (tmp_path / "a.mp4").read_bytes() == data


def test_download_rejects_web_pages(dns, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    transport = _transport(
        {
            "https://videos.example.com/page": httpx.Response(
                200, text="<html></html>", headers={"content-type": "text/html"}
            )
        }
    )
    with pytest.raises(UrlImportError, match="web page"):
        download_video(
            "https://videos.example.com/page", tmp_path / "x", max_bytes=10_000, transport=transport
        )


def test_download_enforces_size_limits(dns, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    declared = _transport(
        {
            "https://videos.example.com/big.mp4": httpx.Response(
                200, content=b"x" * 20, headers={"content-length": "999999"}
            )
        }
    )
    with pytest.raises(UrlImportError, match="larger"):
        download_video(
            "https://videos.example.com/big.mp4", tmp_path / "x", max_bytes=1000, transport=declared
        )

    streamed = _transport(
        {"https://videos.example.com/big.mp4": httpx.Response(200, content=b"x" * 5000)}
    )
    with pytest.raises(UrlImportError, match="larger"):
        download_video(
            "https://videos.example.com/big.mp4", tmp_path / "y", max_bytes=1000, transport=streamed
        )


def test_redirects_to_private_hosts_are_blocked(dns, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    transport = _transport(
        {
            "https://videos.example.com/a.mp4": httpx.Response(
                302, headers={"location": "https://metadata.example.com/latest"}
            )
        }
    )
    with pytest.raises(UrlImportError, match="private"):
        download_video(
            "https://videos.example.com/a.mp4", tmp_path / "x", max_bytes=1000, transport=transport
        )
