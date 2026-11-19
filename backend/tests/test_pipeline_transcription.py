"""Integration: real upload -> real FFmpeg audio extraction -> real faster-whisper transcription.

Uses the sample made by scripts/windows/make-sample-video.cmd (original script, Windows
text-to-speech). Skipped automatically when the sample or FFmpeg is missing.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import PROJECT_ROOT
from app.main import create_app
from tests.conftest import CSRF_HEADERS, make_settings, register, requires_ffmpeg

SAMPLE = PROJECT_ROOT / "data" / "samples" / "curious-minds-sample.mp4"
SHARED_MODELS = PROJECT_ROOT / "data" / "models"

pytestmark = [
    pytest.mark.integration,
    requires_ffmpeg,
    pytest.mark.skipif(
        not SAMPLE.is_file(), reason="Run scripts/windows/make-sample-video.cmd first"
    ),
]


def wait_for_job(client: TestClient, job_id: str, timeout: float = 600) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(0.5)
    raise AssertionError(f"Job {job_id} did not finish in {timeout} seconds")


def test_upload_and_transcribe_real_speech(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path, models_path=SHARED_MODELS))
    with TestClient(app, headers=CSRF_HEADERS) as client:
        register(client)
        project = client.post(
            "/api/v1/projects",
            json={"name": "Curious Minds", "auto_process": False, "whisper_model": "tiny.en"},
        ).json()
        uploaded = client.put(
            f"/api/v1/projects/{project['id']}/media",
            params={"filename": SAMPLE.name},
            content=SAMPLE.read_bytes(),
        )
        assert uploaded.status_code == 200, uploaded.text

        started = client.post(f"/api/v1/projects/{project['id']}/transcribe", json={})
        assert started.status_code == 202, started.text
        progress_seen: set[float] = set()
        job_id = started.json()["id"]
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            job = client.get(f"/api/v1/jobs/{job_id}").json()
            progress_seen.add(job["progress"])
            if job["status"] in ("succeeded", "failed", "cancelled"):
                break
            time.sleep(0.3)
        assert job["status"] == "succeeded", job
        assert len(progress_seen) > 2  # real, incremental progress was reported

        detail = client.get(f"/api/v1/projects/{project['id']}").json()
        assert detail["status"] == "transcribed"
        assert detail["has_transcript"] is True

        transcript = client.get(f"/api/v1/projects/{project['id']}/transcript").json()
        text = " ".join(s["text"] for s in transcript["segments"]).lower()
        assert transcript["language"] == "en"
        assert transcript["word_count"] > 400
        for phrase in ("curious minds", "forgetting curve", "spaced repetition", "octopus"):
            assert phrase in text, phrase
        # Word timestamps are ordered and inside the video.
        words = [w for s in transcript["segments"] for w in s["words"]]
        assert all(0 <= w["start"] <= w["end"] <= detail["duration_seconds"] + 0.5 for w in words)

        srt = client.get(f"/api/v1/projects/{project['id']}/transcript/download?format=srt")
        assert srt.status_code == 200
        assert "-->" in srt.text and "attachment" in srt.headers["content-disposition"]
