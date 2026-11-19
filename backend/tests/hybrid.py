"""Helpers for hybrid-mode tests: a paired worker driven through the real HTTP API."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import CSRF_HEADERS

AGENT = "/api/v1/agent"
WORKERS = "/api/v1/workers"
PROJECTS = "/api/v1/projects"

MEDIA_INFO = {
    "duration": 12.0,
    "size_bytes": 1_000_000,
    "width": 1280,
    "height": 720,
    "fps": 25.0,
    "video_codec": "h264",
    "audio_codec": "aac",
}


def new_code(user: TestClient) -> str:
    response = user.post(f"{WORKERS}/pairing-codes")
    assert response.status_code == 201, response.text
    return response.json()["code"]


class FakeWorker:
    """Speaks the worker protocol over HTTP without doing any video work."""

    def __init__(self, app, user: TestClient, name: str = "Test PC") -> None:  # type: ignore[no-untyped-def]
        self.http = TestClient(app, headers=CSRF_HEADERS)
        answer = self.http.post(f"{AGENT}/pair", json={"code": new_code(user), "name": name})
        assert answer.status_code == 201, answer.text
        body = answer.json()
        self.id: str = body["worker_id"]
        self.owner_id: str = body["owner_id"]
        self.token: str = body["token"]
        self.auth = {"Authorization": f"Bearer {self.token}"}

    def post(self, path: str, json: Any = None):  # type: ignore[no-untyped-def]
        return self.http.post(f"{AGENT}{path}", json=json, headers=self.auth)

    def claim(self) -> dict[str, Any] | None:
        response = self.post("/jobs/claim", {"wait_seconds": 0})
        assert response.status_code == 200, response.text
        return response.json()["job"]

    def event(self, job_id: str, name: str, payload: dict[str, Any]):  # type: ignore[no-untyped-def]
        return self.post(f"/jobs/{job_id}/events", {"name": name, "payload": payload})

    def finish(self, job_id: str, outcome: str = "succeeded", message: str | None = None):  # type: ignore[no-untyped-def]
        return self.post(f"/jobs/{job_id}/finish", {"outcome": outcome, "message": message})

    def register_media(self, project_id: str, **overrides: Any):  # type: ignore[no-untyped-def]
        prefix = f"users/{self.owner_id}/projects/{project_id}"
        payload = {
            "media_key": f"{prefix}/source.mp4",
            "thumbnail_key": f"{prefix}/thumbnail.jpg",
            "info": dict(MEDIA_INFO),
            "original_filename": "talk.mp4",
        }
        payload.update(overrides)
        return self.post(f"/projects/{project_id}/media", payload)


def words(start: float, text: str) -> list[dict[str, Any]]:
    return [
        {"start": start + i * 0.5, "end": start + i * 0.5 + 0.4, "text": word, "probability": 0.9}
        for i, word in enumerate(text.split())
    ]


SEGMENTS = [
    {"id": i, "start": i * 3.0, "end": i * 3.0 + 2.5, "text": text, "words": words(i * 3.0, text)}
    for i, text in enumerate(["Hello and welcome", "this is a test", "of the hybrid worker"])
]


def transcript_payload(project_id: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "language": "en",
        "language_probability": 0.99,
        "model": "tiny.en",
        "device": "cpu",
        "duration": 12.0,
        "word_count": 11,
        "segments": SEGMENTS,
        "warnings": [],
    }


def clips_payload(project_id: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "suggestions": [
            {
                "start": 0.0,
                "end": 8.5,
                "title": "Welcome to the test",
                "description": "An introduction.",
                "reason": "Strong opening.",
                "score": 80,
            }
        ],
    }
