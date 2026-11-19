"""YouTube as a reference source: official oEmbed metadata only, never a download."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services import youtube
from tests.conftest import requires_ffmpeg

PROJECTS = "/api/v1/projects"
VIDEO_ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (f"https://www.youtube.com/watch?v={VIDEO_ID}", VIDEO_ID),
        (f"https://youtube.com/watch?v={VIDEO_ID}&t=42s", VIDEO_ID),
        (f"https://m.youtube.com/watch?feature=share&v={VIDEO_ID}", VIDEO_ID),
        (f"https://youtu.be/{VIDEO_ID}?si=abc", VIDEO_ID),
        (f"https://www.youtube.com/shorts/{VIDEO_ID}", VIDEO_ID),
        (f"https://www.youtube.com/embed/{VIDEO_ID}", VIDEO_ID),
        (f"https://www.youtube.com/live/{VIDEO_ID}", VIDEO_ID),
        ("https://www.youtube.com/watch?v=short", None),
        ("https://www.youtube.com/channel/UC123", None),
        (f"https://evil.example.com/watch?v={VIDEO_ID}", None),
        (f"https://youtube.com.evil.example/watch?v={VIDEO_ID}", None),
        (f"https://user:pw@www.youtube.com/watch?v={VIDEO_ID}", None),
        (f"javascript:alert(1)//youtube.com/watch?v={VIDEO_ID}", None),
        ("", None),
    ],
)
def test_video_ids_are_parsed_strictly(url: str, expected: str | None) -> None:
    assert youtube.parse_video_id(url) == expected


def _transport(status: int, body: object = None) -> httpx.MockTransport:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    transport = httpx.MockTransport(handler)
    transport.seen = seen  # type: ignore[attr-defined]
    return transport


def test_lookup_uses_the_official_oembed_endpoint() -> None:
    transport = _transport(
        200,
        {
            "title": "  My   talk  ",
            "author_name": "Alice",
            "author_url": "https://www.youtube.com/@alice",
            "thumbnail_url": "https://i.ytimg.com/vi/x/hqdefault.jpg",
            "html": "<iframe src='https://evil.example.com'></iframe>",
        },
    )
    details = youtube.lookup(VIDEO_ID, transport=transport)
    request = transport.seen[0]  # type: ignore[attr-defined]
    assert request.url.host == "www.youtube.com" and request.url.path == "/oembed"
    assert request.url.params["url"] == f"https://www.youtube.com/watch?v={VIDEO_ID}"
    assert details == {
        "video_id": VIDEO_ID,
        "url": f"https://www.youtube.com/watch?v={VIDEO_ID}",
        "title": "My talk",
        "author_name": "Alice",
        "author_url": "https://www.youtube.com/@alice",
        "thumbnail_url": "https://i.ytimg.com/vi/x/hqdefault.jpg",
    }  # the embed HTML is never passed on


def test_untrusted_links_in_the_answer_are_dropped() -> None:
    transport = _transport(
        200,
        {
            "title": "t",
            "author_url": "https://evil.example.com/@alice",
            "thumbnail_url": "http://i.ytimg.com/vi/x.jpg",  # not https
        },
    )
    details = youtube.lookup(VIDEO_ID, transport=transport)
    assert details["author_url"] is None and details["thumbnail_url"] is None


@pytest.mark.parametrize(
    ("status", "fragment"),
    [(401, "private"), (403, "private"), (404, "does not have"), (500, "unexpected")],
)
def test_lookup_failures_are_explained(status: int, fragment: str) -> None:
    with pytest.raises(youtube.YouTubeError, match=fragment):
        youtube.lookup(VIDEO_ID, transport=_transport(status))


def test_unreachable_youtube_is_explained() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network")

    with pytest.raises(youtube.YouTubeError, match="could not be reached"):
        youtube.lookup(VIDEO_ID, transport=httpx.MockTransport(down))


def test_downloading_from_youtube_is_not_offered(user_client: TestClient) -> None:
    refused = user_client.post(
        f"{PROJECTS}/import-url", json={"url": f"https://www.youtube.com/watch?v={VIDEO_ID}"}
    )
    assert refused.status_code == 422
    assert "YouTube Studio" in refused.json()["error"]["message"]
    # No module in the app knows how to fetch YouTube media streams.
    app_dir = Path(youtube.__file__).resolve().parents[1]
    for module in app_dir.rglob("*.py"):
        source = module.read_text(encoding="utf-8")
        for marker in ("googlevideo", "yt_dlp", "youtube_dl", "pytube", "player_response"):
            assert marker not in source, f"{marker} in {module.name}"


@pytest.fixture
def fake_lookup(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def lookup(video_id: str, transport=None):  # type: ignore[no-untyped-def]
        return {
            "video_id": video_id,
            "url": youtube.canonical_url(video_id),
            "title": "How we built it",
            "author_name": "Alice",
            "author_url": None,
            "thumbnail_url": "https://i.ytimg.com/vi/x/hqdefault.jpg",
        }

    monkeypatch.setattr(youtube, "lookup", lookup)


def test_lookup_endpoint(user_client: TestClient, fake_lookup) -> None:  # type: ignore[no-untyped-def]
    found = user_client.post(
        f"{PROJECTS}/youtube/lookup", json={"url": f"https://youtu.be/{VIDEO_ID}"}
    )
    assert found.status_code == 200
    body = found.json()
    assert body["title"] == "How we built it" and body["notice"] is None
    assert "YouTube Studio" in body["how_to_get_the_file"]
    wrong = user_client.post(f"{PROJECTS}/youtube/lookup", json={"url": "https://vimeo.com/123456"})
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "not_a_youtube_link"


def test_lookup_requires_sign_in(client: TestClient) -> None:
    assert (
        client.post(
            f"{PROJECTS}/youtube/lookup", json={"url": f"https://youtu.be/{VIDEO_ID}"}
        ).status_code
        == 401
    )


def test_private_videos_can_still_be_referenced(
    user_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def private(video_id: str, transport=None):  # type: ignore[no-untyped-def]
        raise youtube.YouTubeError("This video is private or cannot be embedded.")

    monkeypatch.setattr(youtube, "lookup", private)
    project = user_client.post(
        f"{PROJECTS}/from-youtube",
        json={"url": f"https://youtu.be/{VIDEO_ID}", "auto_process": False},
    )
    assert project.status_code == 201
    assert project.json()["name"] == "YouTube video"
    assert project.json()["source_meta"] == {
        "video_id": VIDEO_ID,
        "url": youtube.canonical_url(VIDEO_ID),
    }


@requires_ffmpeg
def test_youtube_project_waits_for_the_creators_own_file(
    user_client: TestClient, fake_lookup, sample_video: Path
) -> None:  # type: ignore[no-untyped-def]
    created = user_client.post(
        f"{PROJECTS}/from-youtube",
        json={
            "url": f"https://www.youtube.com/shorts/{VIDEO_ID}",
            "auto_process": False,
            "aspect_ratio": "1:1",
        },
    )
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["source_type"] == "youtube" and project["status"] == "awaiting_upload"
    assert project["source_url"] == f"https://www.youtube.com/watch?v={VIDEO_ID}"
    assert project["name"] == "How we built it" and project["aspect_ratio"] == "1:1"
    assert project["source_meta"]["author_name"] == "Alice"
    assert project["has_media"] is False
    uploaded = user_client.put(
        f"{PROJECTS}/{project['id']}/media",
        params={"filename": "studio-download.mp4"},
        content=sample_video.read_bytes(),
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["has_media"] is True
    assert uploaded.json()["source_type"] == "youtube"


def test_other_users_cannot_see_youtube_projects(
    user_client: TestClient, second_client: TestClient, fake_lookup
) -> None:  # type: ignore[no-untyped-def]
    pid = user_client.post(
        f"{PROJECTS}/from-youtube", json={"url": f"https://youtu.be/{VIDEO_ID}"}
    ).json()["id"]
    assert second_client.get(f"{PROJECTS}/{pid}").status_code == 404
    assert second_client.get(PROJECTS).json()["total"] == 0
