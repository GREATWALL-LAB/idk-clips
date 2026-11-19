"""Data isolation between users, checked against *every* route that takes an ID.

Alice owns a project with media, a transcript, a clip, a job and a paired worker. Bob is
logged in and replays every API route with Alice's IDs and every HTTP method the route
accepts. None of those requests may succeed or reveal Alice's data. The route list is
read from the application itself, so a new endpoint is covered automatically.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.conftest import CSRF_HEADERS, PASSWORD, make_settings, register
from tests.hybrid import PROJECTS, FakeWorker, clips_payload, transcript_payload

SECRET_TITLE = "Alice private talk 7f3a"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path, mode="hybrid")


@pytest.fixture
def alice_world(app, user_client: TestClient) -> dict[str, str]:  # type: ignore[no-untyped-def]
    worker = FakeWorker(app, user_client)
    project = user_client.post(PROJECTS, json={"name": SECRET_TITLE, "auto_process": True}).json()
    pid = project["id"]
    assert worker.register_media(pid).status_code == 204
    job = worker.claim()
    assert job is not None
    assert worker.event(job["job_id"], "transcript", transcript_payload(pid)).status_code == 204
    assert worker.event(job["job_id"], "clips", clips_payload(pid)).status_code == 204
    assert worker.finish(job["job_id"]).status_code == 204
    clip_id = user_client.get(f"{PROJECTS}/{pid}/clips").json()["items"][0]["id"]
    return {
        "project_id": pid,
        "clip_id": clip_id,
        "job_id": job["job_id"],
        "worker_id": worker.id,
        "id": pid,
    }


def _bob(app) -> TestClient:  # type: ignore[no-untyped-def]
    bob = TestClient(app, headers=CSRF_HEADERS)
    register(bob, "bob@example.com", PASSWORD, "Bob")
    return bob


PARAM = re.compile(r"{(\w+)}")


def test_no_route_lets_another_user_reach_alices_data(app, alice_world: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
    bob = _bob(app)
    checked = 0
    # The OpenAPI document lists every route, including ones in nested routers.
    for template, operations in app.openapi()["paths"].items():
        names = PARAM.findall(template)
        if not template.startswith("/api/v1/") or not names:
            continue
        if template.startswith("/api/v1/agent"):
            continue  # agent routes need a worker token, checked separately below
        path = template
        for name in names:
            path = path.replace("{" + name + "}", alice_world.get(name, alice_world["id"]))
        for method in sorted(m.upper() for m in operations):
            body = {} if method in {"POST", "PUT", "PATCH"} else None
            response = bob.request(method, path, json=body)
            checked += 1
            assert response.status_code not in range(200, 300), (method, path, response.text)
            assert response.status_code in {404, 403, 409, 422}, (
                method,
                path,
                response.status_code,
            )
            assert SECRET_TITLE not in response.text, (method, path)
    assert checked >= 20


def test_lists_and_dashboards_never_include_other_users_data(
    app, alice_world: dict[str, str]
) -> None:  # type: ignore[no-untyped-def]
    bob = _bob(app)
    for path in (
        "/api/v1/projects",
        "/api/v1/clips",
        "/api/v1/jobs",
        "/api/v1/workers",
        "/api/v1/dashboard",
        "/api/v1/account",
    ):
        response = bob.get(path)
        assert response.status_code == 200, path
        assert SECRET_TITLE not in response.text, path
        assert alice_world["project_id"] not in response.text, path
        assert alice_world["worker_id"] not in response.text, path


def test_a_worker_cannot_act_on_another_users_jobs_or_projects(
    app, user_client: TestClient, alice_world: dict[str, str]
) -> None:  # type: ignore[no-untyped-def]
    bob = _bob(app)
    bobs_worker = FakeWorker(app, bob, name="Bob PC")
    job, pid = alice_world["job_id"], alice_world["project_id"]
    attempts = [
        bobs_worker.post(f"/jobs/{job}/progress", {"progress": 0.5, "stage": "x"}),
        bobs_worker.event(job, "transcript", transcript_payload(pid)),
        bobs_worker.finish(job),
        bobs_worker.register_media(pid),
    ]
    for response in attempts:
        assert response.status_code in {403, 404, 409, 422}, response.text
    assert bobs_worker.claim() is None  # Alice's jobs are never handed to Bob's worker
    assert user_client.get(f"{PROJECTS}/{pid}").json()["name"] == SECRET_TITLE


def test_requests_without_login_are_refused(app, alice_world: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
    anonymous = TestClient(app, headers=CSRF_HEADERS)
    for path in (
        f"{PROJECTS}/{alice_world['project_id']}",
        f"/api/v1/clips/{alice_world['clip_id']}",
        f"/api/v1/clips/{alice_world['clip_id']}/file",
        f"{PROJECTS}/{alice_world['project_id']}/transcript",
        f"/api/v1/jobs/{alice_world['job_id']}",
    ):
        assert anonymous.get(path).status_code == 401, path
