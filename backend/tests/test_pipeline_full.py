"""End-to-end integration: upload -> transcribe -> real Ollama clip detection -> vertical export.

Needs FFmpeg, the generated sample video and a running Ollama with at least one chat model.
Skipped automatically when any of these is missing. Run explicitly with:
    pytest -m integration tests/test_pipeline_full.py -s
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import PROJECT_ROOT
from app.main import create_app
from tests.conftest import CSRF_HEADERS, make_settings, register, requires_ffmpeg

SAMPLE = PROJECT_ROOT / "data" / "samples" / "curious-minds-sample.mp4"
SHARED_MODELS = PROJECT_ROOT / "data" / "models"
OLLAMA = "http://127.0.0.1:11434"


def _ollama_models() -> list[str]:
    try:
        response = httpx.get(f"{OLLAMA}/api/tags", timeout=3)
        return [m["name"] for m in response.json().get("models", []) if "embed" not in m["name"]]
    except (httpx.HTTPError, ValueError):
        return []


pytestmark = [
    pytest.mark.integration,
    requires_ffmpeg,
    pytest.mark.skipif(
        not SAMPLE.is_file(), reason="Run scripts/windows/make-sample-video.cmd first"
    ),
    pytest.mark.skipif(not _ollama_models(), reason="Ollama with a chat model is not available"),
]


def _wait(client: TestClient, job_id: str, timeout: float = 1800) -> dict:
    deadline = time.monotonic() + timeout
    last_stage = None
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["stage"] != last_stage:
            print(f"  [{job['progress']:.0%}] {job['stage']}")
            last_stage = job["stage"]
        if job["status"] in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(1)
    raise AssertionError("job timed out")


def test_full_pipeline_with_local_ai(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, models_path=SHARED_MODELS, ollama_base_url=OLLAMA)
    with TestClient(create_app(settings), headers=CSRF_HEADERS) as client:
        register(client)
        project = client.post(
            "/api/v1/projects",
            json={
                "name": "Curious Minds E2E",
                "whisper_model": "small.en",
                "clip_count": 6,
                "min_clip_seconds": 15,
                "max_clip_seconds": 60,
                "auto_process": True,
            },
        ).json()
        started = time.monotonic()
        uploaded = client.put(
            f"/api/v1/projects/{project['id']}/media",
            params={"filename": SAMPLE.name},
            content=SAMPLE.read_bytes(),
        ).json()
        assert uploaded["active_job"] is not None  # processing started automatically
        job = _wait(client, uploaded["active_job"]["id"])
        assert job["status"] == "succeeded", job
        process_seconds = time.monotonic() - started

        detail = client.get(f"/api/v1/projects/{project['id']}").json()
        assert detail["status"] == "ready"
        clips = client.get(f"/api/v1/projects/{project['id']}/clips").json()["items"]
        print(
            f"\n  processing took {process_seconds:.0f}s with {detail['ai_model']}; {len(clips)} clips:"
        )
        transcript = client.get(f"/api/v1/projects/{project['id']}/transcript").json()
        segment_bounds = {round(s["start"], 1) for s in transcript["segments"]}
        for clip in clips:
            print(f"   {clip['start_seconds']:7.2f}-{clip['end_seconds']:7.2f} ({clip['duration_seconds']:4.1f}s) "
                  f"score={clip['score']} {clip['title']!r}")  # fmt: skip
            assert (
                0
                <= clip["start_seconds"]
                < clip["end_seconds"]
                <= detail["duration_seconds"] + 0.01
            )
            assert clip["title"] and clip["reason"]
            # Starts are anchored on real speech (a segment start, minus at most the padding).
            assert any(0 <= b - clip["start_seconds"] <= 0.3 for b in segment_bounds), clip
        assert 1 <= len(clips) <= 6

        best = clips[0]
        render = client.post(f"/api/v1/clips/{best['id']}/render").json()
        rendered = _wait(client, render["id"])
        assert rendered["status"] == "succeeded", rendered
        exported = client.get(f"/api/v1/clips/{best['id']}").json()
        assert exported["status"] == "ready"
        video = client.get(f"/api/v1/clips/{best['id']}/file")
        out = tmp_path / "export.mp4"
        out.write_bytes(video.content)
        print(f"  exported {len(video.content) / 1e6:.1f} MB")

    from openclip_processing.ffmpeg import FFmpegTools

    info = FFmpegTools.locate(search_dirs=[PROJECT_ROOT / "tools" / "ffmpeg" / "bin"]).probe(out)
    assert (info.width, info.height) == (1080, 1920)
    assert info.has_audio
    assert abs(info.duration - best["duration_seconds"]) < 0.5
