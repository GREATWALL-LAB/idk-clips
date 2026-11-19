from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.models import Project, Transcript
from tests.conftest import requires_ffmpeg

PROJECTS = "/api/v1/projects"


def _words(start: float, text: str) -> list[dict[str, Any]]:
    return [
        {"start": start + i * 0.5, "end": start + i * 0.5 + 0.4, "text": word, "probability": 0.9}
        for i, word in enumerate(text.split())
    ]


FAKE_SEGMENTS = [
    {"id": i, "start": i * 3.0, "end": i * 3.0 + 2.5, "text": text, "words": _words(i * 3.0, text)}
    for i, text in enumerate(["Hello and welcome", "this is a test", "of the clip editor"])
]


def wait_for_job(client: TestClient, job_id: str, timeout: float = 300) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(0.25)
    raise AssertionError("job did not finish")


@pytest.fixture
def project_with_video(user_client: TestClient, sample_video: Path, app) -> dict:  # type: ignore[no-untyped-def]
    project = user_client.post(PROJECTS, json={"name": "Clips", "auto_process": False}).json()
    response = user_client.put(
        f"{PROJECTS}/{project['id']}/media",
        params={"filename": "sample.mp4"},
        content=sample_video.read_bytes(),
    )
    assert response.status_code == 200, response.text
    # Store a small transcript directly (transcription itself is covered elsewhere).
    with app.state.database.session_scope() as db:
        db.add(
            Transcript(
                project_id=project["id"], language="en", language_probability=1.0, model="test",
                device="cpu", duration=12.0, word_count=10, segments=FAKE_SEGMENTS, warnings=[],
            )
        )  # fmt: skip
        db.get(Project, project["id"]).status = "transcribed"
    return project


@requires_ffmpeg
def test_manual_clip_edit_captions_and_delete(
    user_client: TestClient, project_with_video: dict
) -> None:
    pid = project_with_video["id"]
    created = user_client.post(
        f"{PROJECTS}/{pid}/clips", json={"title": "Intro", "start_seconds": 0, "end_seconds": 8}
    )
    assert created.status_code == 201, created.text
    clip = created.json()
    assert clip["source"] == "manual" and clip["status"] == "suggested"

    captions = user_client.get(f"/api/v1/clips/{clip['id']}/captions").json()
    assert captions["edited"] is False
    assert [line["text"] for line in captions["lines"]][:2] == [
        "Hello and welcome this",
        "is a test of",
    ]

    edited = user_client.patch(
        f"/api/v1/clips/{clip['id']}",
        json={
            "caption_lines": [{"start": 0.0, "end": 2.0, "text": "Hello, and welcome!"}],
            "layout": "fit",
        },
    )
    assert edited.status_code == 200
    assert edited.json()["has_caption_edits"] is True
    assert edited.json()["layout"] == "fit"
    # Moving the clip keeps edits aligned to the video (they are stored in video time).
    moved = user_client.patch(
        f"/api/v1/clips/{clip['id']}", json={"start_seconds": 1.0, "end_seconds": 9.0}
    )
    assert moved.status_code == 200
    lines = user_client.get(f"/api/v1/clips/{clip['id']}/captions").json()["lines"]
    assert lines == [{"start": 0.0, "end": 1.0, "text": "Hello, and welcome!"}]

    for bad in (
        {"start_seconds": 5, "end_seconds": 4},
        {"start_seconds": 0, "end_seconds": 1},
        {"end_seconds": 999},
    ):
        assert user_client.patch(f"/api/v1/clips/{clip['id']}", json=bad).status_code == 422, bad
    assert (
        user_client.patch(f"/api/v1/clips/{clip['id']}", json={"crop_position": 2}).status_code
        == 422
    )
    style = {"font": "Comic Sans"}
    assert (
        user_client.patch(f"/api/v1/clips/{clip['id']}", json={"caption_style": style}).status_code
        == 422
    )

    assert user_client.delete(f"/api/v1/clips/{clip['id']}").status_code == 204
    assert user_client.get(f"/api/v1/clips/{clip['id']}").status_code == 404


@requires_ffmpeg
def test_clips_are_isolated_between_users(
    user_client: TestClient, second_client: TestClient, project_with_video: dict
) -> None:
    pid = project_with_video["id"]
    clip = user_client.post(
        f"{PROJECTS}/{pid}/clips", json={"start_seconds": 0, "end_seconds": 6}
    ).json()
    assert second_client.get("/api/v1/clips").json()["total"] == 0
    for method, path in [
        ("GET", f"/api/v1/clips/{clip['id']}"),
        ("PATCH", f"/api/v1/clips/{clip['id']}"),
        ("DELETE", f"/api/v1/clips/{clip['id']}"),
        ("GET", f"/api/v1/clips/{clip['id']}/captions"),
        ("POST", f"/api/v1/clips/{clip['id']}/render"),
        ("GET", f"/api/v1/clips/{clip['id']}/file"),
        ("GET", f"{PROJECTS}/{pid}/clips"),
        ("POST", f"{PROJECTS}/{pid}/clips"),
        ("POST", f"{PROJECTS}/{pid}/detect"),
    ]:
        kwargs = (
            {"json": {"start_seconds": 0, "end_seconds": 6}} if method in ("PATCH", "POST") else {}
        )
        assert second_client.request(method, path, **kwargs).status_code == 404, (method, path)


@requires_ffmpeg
def test_detection_job_stores_suggestions(
    user_client: TestClient, project_with_video: dict, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from app.jobs import compute

    class FakeProvider:
        name, model = "ollama", "fake-model"

        def generate_json(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return {"clips": [{"start_segment": 0, "end_segment": 2, "title": "Welcome to the test",
                               "description": "d", "reason": "Strong opening", "score": 77}]}  # fmt: skip

    monkeypatch.setattr(compute, "provider_from_config", lambda config, settings: FakeProvider())
    pid = project_with_video["id"]
    job = user_client.post(f"{PROJECTS}/{pid}/detect").json()
    finished = wait_for_job(user_client, job["id"])
    assert finished["status"] == "succeeded", finished
    clips = user_client.get(f"{PROJECTS}/{pid}/clips").json()["items"]
    assert len(clips) == 1
    suggestion = clips[0]
    assert suggestion["title"] == "Welcome to the test" and suggestion["score"] == 77
    assert suggestion["source"] == "ai"
    # Times come from the transcript segments (0.0 -> 8.5 plus padding), not from the model.
    assert suggestion["start_seconds"] == 0.0 and 8.5 <= suggestion["end_seconds"] <= 9.0
    project = user_client.get(f"{PROJECTS}/{pid}").json()
    assert project["status"] == "ready" and project["ai_model"] == "fake-model"


@requires_ffmpeg
def test_detection_failure_is_reported_not_hidden(
    user_client: TestClient, project_with_video: dict, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from app.jobs import compute
    from openclip_processing.errors import AIProviderError

    def unavailable(config, settings):  # type: ignore[no-untyped-def]
        raise AIProviderError("Ollama is not reachable. Start the Ollama app.")

    monkeypatch.setattr(compute, "provider_from_config", unavailable)
    pid = project_with_video["id"]
    finished = wait_for_job(user_client, user_client.post(f"{PROJECTS}/{pid}/detect").json()["id"])
    assert finished["status"] == "failed"
    assert "Ollama is not reachable" in finished["error_message"]
    project = user_client.get(f"{PROJECTS}/{pid}").json()
    assert project["status"] == "transcribed"  # the transcript is still usable
    assert "Ollama" in project["error_message"]


@requires_ffmpeg
def test_render_job_exports_vertical_mp4(
    user_client: TestClient, project_with_video: dict, settings
) -> None:  # type: ignore[no-untyped-def]
    pid = project_with_video["id"]
    clip = user_client.post(
        f"{PROJECTS}/{pid}/clips", json={"title": "My clip", "start_seconds": 1, "end_seconds": 7}
    ).json()
    job = user_client.post(f"/api/v1/clips/{clip['id']}/render")
    assert job.status_code == 202
    finished = wait_for_job(user_client, job.json()["id"])
    assert finished["status"] == "succeeded", finished
    ready = user_client.get(f"/api/v1/clips/{clip['id']}").json()
    assert ready["status"] == "ready"
    assert ready["output_size_bytes"] > 10_000
    download = user_client.get(f"/api/v1/clips/{clip['id']}/file?download=true")
    assert download.status_code == 200
    assert download.headers["content-type"] == "video/mp4"
    assert 'filename="My-clip.mp4"' in download.headers["content-disposition"]
    assert user_client.get(f"/api/v1/clips/{clip['id']}/thumbnail").status_code == 200
    # The dashboard lists the finished clip.
    dashboard = user_client.get("/api/v1/dashboard").json()
    assert dashboard["stats"]["clips_ready"] == 1
    assert dashboard["recent_clips"][0]["id"] == clip["id"]
    # Changing the layout marks the export as outdated until it is rendered again.
    changed = user_client.patch(f"/api/v1/clips/{clip['id']}", json={"layout": "fit"}).json()
    assert changed["status"] == "suggested" and changed["preview_url"]


# --------------------------------------------------------------- aspect ratios
def test_aspect_ratio_defaults_and_validation(user_client: TestClient) -> None:
    default = user_client.post(PROJECTS, json={"name": "Default", "auto_process": False}).json()
    assert default["aspect_ratio"] == "9:16"
    square = user_client.post(
        PROJECTS, json={"name": "Square", "auto_process": False, "aspect_ratio": "1:1"}
    ).json()
    assert square["aspect_ratio"] == "1:1"
    bad = user_client.post(PROJECTS, json={"name": "Bad", "aspect_ratio": "3:2"})
    assert bad.status_code == 422
    updated = user_client.patch(f"{PROJECTS}/{square['id']}", json={"aspect_ratio": "16:9"})
    assert updated.json()["aspect_ratio"] == "16:9"
    assert user_client.get(f"{PROJECTS}/{square['id']}").json()["aspect_ratio"] == "16:9"


@requires_ffmpeg
def test_ratio_is_applied_to_exports_and_changing_it_marks_them_outdated(
    user_client: TestClient, project_with_video: dict, settings
) -> None:  # type: ignore[no-untyped-def]
    from openclip_processing.ffmpeg import FFmpegTools

    pid = project_with_video["id"]
    user_client.patch(f"{PROJECTS}/{pid}", json={"aspect_ratio": "4:5"})
    clip = user_client.post(
        f"{PROJECTS}/{pid}/clips", json={"title": "Portrait", "start_seconds": 1, "end_seconds": 6}
    ).json()
    assert clip["aspect_ratio"] == "4:5" and clip["auto_frame"] is True
    finished = wait_for_job(
        user_client, user_client.post(f"/api/v1/clips/{clip['id']}/render").json()["id"]
    )
    assert finished["status"] == "succeeded", finished
    exported = user_client.get(f"/api/v1/clips/{clip['id']}/file")
    out = settings.tmp_dir / "portrait.mp4"
    out.write_bytes(exported.content)
    tools = FFmpegTools.locate(search_dirs=[settings.tools_dir / "ffmpeg" / "bin"])
    info = tools.probe(out)
    assert (info.width, info.height) == (1080, 1350)

    # Switching the project to 1:1 keeps the old file but marks the export as outdated.
    user_client.patch(f"{PROJECTS}/{pid}", json={"aspect_ratio": "1:1"})
    outdated = user_client.get(f"/api/v1/clips/{clip['id']}").json()
    assert outdated["status"] == "suggested" and outdated["preview_url"]
    assert outdated["aspect_ratio"] == "1:1"

    # "Export all" regenerates it in the new shape; the source video is untouched.
    jobs = user_client.post(f"{PROJECTS}/{pid}/render-all")
    assert jobs.status_code == 202 and len(jobs.json()) == 1
    assert wait_for_job(user_client, jobs.json()[0]["id"])["status"] == "succeeded"
    out.write_bytes(user_client.get(f"/api/v1/clips/{clip['id']}/file").content)
    assert (tools.probe(out).width, tools.probe(out).height) == (1080, 1080)
    assert user_client.get(f"{PROJECTS}/{pid}").json()["has_media"] is True
    nothing_left = user_client.post(f"{PROJECTS}/{pid}/render-all")
    assert nothing_left.status_code == 409


@requires_ffmpeg
def test_auto_frame_endpoint_and_manual_override(
    user_client: TestClient, project_with_video: dict
) -> None:
    pid = project_with_video["id"]
    clip = user_client.post(
        f"{PROJECTS}/{pid}/clips", json={"start_seconds": 0, "end_seconds": 8}
    ).json()
    framed = user_client.post(f"/api/v1/clips/{clip['id']}/autoframe")
    assert framed.status_code == 200, framed.text
    assert framed.json()["auto_frame"] is True
    assert 0.0 <= framed.json()["crop_position"] <= 1.0
    manual = user_client.patch(f"/api/v1/clips/{clip['id']}", json={"crop_position": 0.2}).json()
    assert manual["crop_position"] == 0.2 and manual["auto_frame"] is False
    again = user_client.patch(f"/api/v1/clips/{clip['id']}", json={"auto_frame": True}).json()
    assert again["auto_frame"] is True
    assert (
        user_client.patch(f"/api/v1/clips/{clip['id']}", json={"layout": "original"}).status_code
        == 422
    )


@requires_ffmpeg
def test_new_ratio_endpoints_are_isolated(
    user_client: TestClient, second_client: TestClient, project_with_video: dict
) -> None:
    pid = project_with_video["id"]
    clip = user_client.post(
        f"{PROJECTS}/{pid}/clips", json={"start_seconds": 0, "end_seconds": 6}
    ).json()
    assert second_client.post(f"/api/v1/clips/{clip['id']}/autoframe").status_code == 404
    assert second_client.post(f"{PROJECTS}/{pid}/render-all").status_code == 404
    assert second_client.patch(f"{PROJECTS}/{pid}", json={"aspect_ratio": "1:1"}).status_code == 404
    assert user_client.get(f"{PROJECTS}/{pid}").json()["aspect_ratio"] == "9:16"
