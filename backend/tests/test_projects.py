from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import CSRF_HEADERS, make_settings, register, requires_ffmpeg

PROJECTS = "/api/v1/projects"


def create(client: TestClient, **overrides: object) -> dict:
    body = {"name": "My talk", "auto_process": False, **overrides}
    response = client.post(PROJECTS, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def upload(client: TestClient, project_id: str, path: Path, filename: str | None = None):  # type: ignore[no-untyped-def]
    return client.put(
        f"{PROJECTS}/{project_id}/media",
        params={"filename": filename or path.name},
        content=path.read_bytes(),
        headers={"Content-Type": "video/mp4"},
    )


def test_create_list_get_update_project(user_client: TestClient) -> None:
    project = create(user_client, clip_count=6, language="auto")
    assert project["status"] == "awaiting_upload"
    assert project["clip_count"] == 6
    assert project["has_media"] is False
    listed = user_client.get(PROJECTS).json()
    assert listed["total"] == 1
    updated = user_client.patch(f"{PROJECTS}/{project['id']}", json={"name": "  Renamed   talk "})
    assert updated.json()["name"] == "Renamed talk"
    assert user_client.get(f"{PROJECTS}/{project['id']}").json()["name"] == "Renamed talk"


@pytest.mark.parametrize(
    "body",
    [
        {"name": "x", "clip_count": 11},
        {"name": "x", "clip_count": 4},
        {"name": "x", "language": "klingon"},
        {"name": "x", "whisper_model": "giant"},
        {"name": "x", "whisper_model": "small.en", "language": "es"},
        {"name": "x", "min_clip_seconds": 60, "max_clip_seconds": 30},
        {"name": "   "},
    ],
)
def test_invalid_project_options_are_rejected(user_client: TestClient, body: dict) -> None:
    assert user_client.post(PROJECTS, json=body).status_code == 422


def test_invalid_ids_are_rejected_before_any_lookup(user_client: TestClient) -> None:
    assert user_client.get(f"{PROJECTS}/not-a-uuid").status_code == 422
    assert user_client.get(f"{PROJECTS}/..%2F..%2Fetc").status_code in (404, 422)


@requires_ffmpeg
def test_users_cannot_see_or_touch_each_others_projects(
    user_client: TestClient, second_client: TestClient, sample_video: Path
) -> None:
    project = create(user_client)
    assert upload(user_client, project["id"], sample_video).status_code == 200
    pid = project["id"]

    assert second_client.get(PROJECTS).json()["total"] == 0
    for method, path in [
        ("GET", f"{PROJECTS}/{pid}"),
        ("PATCH", f"{PROJECTS}/{pid}"),
        ("DELETE", f"{PROJECTS}/{pid}"),
        ("GET", f"{PROJECTS}/{pid}/media"),
        ("GET", f"{PROJECTS}/{pid}/thumbnail"),
        ("GET", f"{PROJECTS}/{pid}/transcript"),
        ("POST", f"{PROJECTS}/{pid}/process"),
        ("PUT", f"{PROJECTS}/{pid}/media?filename=x.mp4"),
    ]:
        kwargs = {"json": {}} if method in ("PATCH", "POST") else {}
        if method == "PUT":
            kwargs = {"content": b"0" * 10}
        response = second_client.request(method, path, **kwargs)
        assert response.status_code == 404, (method, path, response.status_code)
    # Alice still has her project and file.
    assert user_client.get(f"{PROJECTS}/{pid}").json()["has_media"] is True


@requires_ffmpeg
def test_upload_validates_and_stores_video(
    user_client: TestClient, sample_video: Path, settings
) -> None:  # type: ignore[no-untyped-def]
    project = create(user_client)
    response = upload(user_client, project["id"], sample_video, "My Video (final).MP4")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "uploaded"
    assert body["has_media"] is True
    assert body["original_filename"] == "My Video (final).MP4"
    assert 11.5 < body["duration_seconds"] < 12.5
    assert (body["width"], body["height"]) == (640, 360)
    assert body["thumbnail_url"] == f"/projects/{project['id']}/thumbnail"
    # Server paths are never exposed.
    assert str(settings.data_dir) not in response.text
    assert "media_key" not in body

    # Files are stored under the owner's folder.
    user_id = user_client.get("/api/v1/auth/me").json()["id"]
    folder = settings.storage_dir / "users" / user_id / "projects" / project["id"]
    assert (folder / "source.mp4").is_file()
    assert not (folder / "source.upload").exists()

    # Streaming supports HTTP Range requests (needed for video seeking).
    ranged = user_client.get(f"{PROJECTS}/{project['id']}/media", headers={"Range": "bytes=0-99"})
    assert ranged.status_code == 206
    assert len(ranged.content) == 100
    assert (
        user_client.get(f"{PROJECTS}/{project['id']}/thumbnail").headers["content-type"]
        == "image/jpeg"
    )

    second = upload(user_client, project["id"], sample_video)
    assert second.status_code == 409


@requires_ffmpeg
def test_upload_rejects_unsupported_and_invalid_files(
    user_client: TestClient, silent_video: Path, tmp_path: Path
) -> None:
    project = create(user_client)
    assert upload(user_client, project["id"], silent_video, "clip.exe").status_code == 415
    assert upload(user_client, project["id"], silent_video, "../../evil.txt").status_code == 415

    no_audio = upload(user_client, project["id"], silent_video)
    assert no_audio.status_code == 422
    assert "no audio" in no_audio.json()["error"]["message"].lower()

    garbage = tmp_path / "fake.mp4"
    garbage.write_bytes(b"this is not really a video" * 200)
    response = upload(user_client, project["id"], garbage)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_media"

    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    assert upload(user_client, project["id"], empty).status_code == 400
    # Nothing invalid was kept, so a valid upload is still possible afterwards.
    assert user_client.get(f"{PROJECTS}/{project['id']}").json()["has_media"] is False


@requires_ffmpeg
def test_upload_size_limit_and_quota(tmp_path: Path, sample_video: Path) -> None:
    app = create_app(make_settings(tmp_path, max_upload_mb=1, user_storage_quota_mb=1))
    big = tmp_path / "big.mp4"
    big.write_bytes(b"\0" * (2 * 1024 * 1024))
    with TestClient(app, headers=CSRF_HEADERS) as client:
        register(client)
        project = create(client)
        too_big = upload(client, project["id"], big)
        assert too_big.status_code == 413
        assert too_big.json()["error"]["code"] == "payload_too_large"

    app = create_app(make_settings(tmp_path / "q", user_storage_quota_mb=1))
    with TestClient(app, headers=CSRF_HEADERS) as client:
        register(client)
        project = create(client)
        over_quota = upload(client, project["id"], big)
        assert over_quota.status_code == 413
        assert over_quota.json()["error"]["code"] == "quota_exceeded"


@requires_ffmpeg
def test_delete_project_removes_rows_and_files(
    user_client: TestClient, sample_video: Path, settings
) -> None:  # type: ignore[no-untyped-def]
    project = create(user_client)
    upload(user_client, project["id"], sample_video)
    user_id = user_client.get("/api/v1/auth/me").json()["id"]
    folder = settings.storage_dir / "users" / user_id / "projects" / project["id"]
    assert folder.is_dir()
    assert user_client.delete(f"{PROJECTS}/{project['id']}").status_code == 204
    assert not folder.exists()
    assert user_client.get(f"{PROJECTS}/{project['id']}").status_code == 404


def test_processing_requires_media(user_client: TestClient) -> None:
    project = create(user_client)
    response = user_client.post(f"{PROJECTS}/{project['id']}/process", json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_media"


def test_youtube_links_are_refused_with_an_explanation(user_client: TestClient) -> None:
    response = user_client.post(
        f"{PROJECTS}/import-url", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "url_not_allowed"
    assert "YouTube" in error["message"] and "upload" in error["message"].lower()


def test_private_network_links_are_refused(user_client: TestClient) -> None:
    for url in (
        "http://127.0.0.1:8000/x.mp4",
        "http://169.254.169.254/latest/meta-data",
        "http://localhost/a.mp4",
    ):
        response = user_client.post(f"{PROJECTS}/import-url", json={"url": url})
        assert response.status_code == 422, url
