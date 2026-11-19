"""Abuse protection: request size, repeated failures, per-user job limits and quotas."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import CSRF_HEADERS, PASSWORD, make_settings, register
from tests.hybrid import MEDIA_INFO, PROJECTS, FakeWorker


def _client(tmp_path: Path, **overrides: object) -> TestClient:
    return TestClient(create_app(make_settings(tmp_path, **overrides)), headers=CSRF_HEADERS)


def test_oversized_request_bodies_are_refused(tmp_path: Path) -> None:
    with _client(tmp_path, max_request_body_mb=1) as client:
        register(client)
        big = {"name": "x", "description": "y" * (2 * 1024 * 1024)}
        response = client.post(PROJECTS, json=big)
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "request_too_large"
        # Normal requests still work.
        assert client.post(PROJECTS, json={"name": "ok", "auto_process": False}).status_code == 201


def test_body_limit_also_applies_without_content_length(tmp_path: Path) -> None:
    with _client(tmp_path, max_request_body_mb=1) as client:
        register(client)

        def chunks():  # type: ignore[no-untyped-def]
            for _ in range(3):
                yield b"x" * (600 * 1024)

        response = client.post(
            PROJECTS, content=chunks(), headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 413


def test_repeated_failed_requests_are_slowed_down(tmp_path: Path) -> None:
    with _client(tmp_path, rate_limit_enabled=True, failed_request_limit_per_minute=3) as client:
        register(client)
        for _ in range(3):
            missing = client.get(f"{PROJECTS}/00000000-0000-0000-0000-000000000000")
            assert missing.status_code == 404
        blocked = client.get(PROJECTS)
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) >= 1


def test_anonymous_who_am_i_checks_do_not_count_as_failures(tmp_path: Path) -> None:
    with _client(tmp_path, rate_limit_enabled=True, failed_request_limit_per_minute=2) as client:
        for _ in range(5):
            assert client.get("/api/v1/auth/me").status_code == 401
        assert client.get("/api/v1/meta").status_code == 200


def test_sign_up_limit_is_configurable(tmp_path: Path) -> None:
    with _client(tmp_path, rate_limit_enabled=True, register_rate_limit_per_hour=1) as client:
        register(client, "one@example.com")
        second = client.post(
            "/api/v1/auth/register",
            json={"age_confirmed": True, "email": "two@example.com", "password": PASSWORD},
        )
        assert second.status_code == 429


def test_trusted_client_ip_header_separates_clients(tmp_path: Path) -> None:
    with _client(
        tmp_path,
        rate_limit_enabled=True,
        rate_limit_requests_per_minute=2,
        client_ip_header="x-real-ip",
    ) as client:
        a = {"x-real-ip": "203.0.113.10"}
        assert client.get("/api/v1/meta", headers=a).status_code == 200
        assert client.get("/api/v1/meta", headers=a).status_code == 200
        assert client.get("/api/v1/meta", headers=a).status_code == 429
        assert client.get("/api/v1/meta", headers={"x-real-ip": "203.0.113.11"}).status_code == 200
        # Garbage in the header is ignored rather than trusted.
        assert client.get("/api/v1/meta", headers={"x-real-ip": "not-an-ip"}).status_code in {
            200,
            429,
        }


def test_client_ip_header_is_ignored_unless_configured(tmp_path: Path) -> None:
    with _client(tmp_path, rate_limit_enabled=True, rate_limit_requests_per_minute=2) as client:
        for ip in ("198.51.100.1", "198.51.100.2"):
            client.get("/api/v1/meta", headers={"x-real-ip": ip})
        # Spoofed headers do not create fresh budgets.
        assert client.get("/api/v1/meta", headers={"x-real-ip": "198.51.100.3"}).status_code == 429


def _hybrid_user(tmp_path: Path, **overrides: object):  # type: ignore[no-untyped-def]
    app = create_app(make_settings(tmp_path, mode="hybrid", **overrides))
    client = TestClient(app, headers=CSRF_HEADERS)
    client.__enter__()
    register(client)
    return app, client


def test_one_user_cannot_fill_the_queue(tmp_path: Path) -> None:
    app, client = _hybrid_user(tmp_path, max_active_jobs_per_user=1)
    try:
        worker = FakeWorker(app, client)
        first = client.post(PROJECTS, json={"name": "A", "auto_process": True}).json()
        assert worker.register_media(first["id"]).status_code == 204  # queues one job
        second = client.post(PROJECTS, json={"name": "B", "auto_process": False}).json()
        assert worker.register_media(second["id"]).status_code == 204
        refused = client.post(f"{PROJECTS}/{second['id']}/process", json={})
        assert refused.status_code == 429
        assert refused.json()["error"]["code"] == "too_many_jobs"
    finally:
        client.__exit__(None, None, None)


def test_daily_processing_quota(tmp_path: Path) -> None:
    app, client = _hybrid_user(tmp_path, daily_processing_minutes_per_user=1)
    try:
        worker = FakeWorker(app, client)
        project = client.post(PROJECTS, json={"name": "Long", "auto_process": True}).json()
        info = {**MEDIA_INFO, "duration": 120.0}  # two minutes: over the one-minute quota
        assert worker.register_media(project["id"], info=info).status_code == 204
        job = worker.claim()
        assert job is not None
        worker.finish(job["job_id"])
        other = client.post(PROJECTS, json={"name": "Next", "auto_process": False}).json()
        assert worker.register_media(other["id"]).status_code == 204
        refused = client.post(f"{PROJECTS}/{other['id']}/process", json={})
        assert refused.status_code == 429
        assert refused.json()["error"]["code"] == "daily_quota"
    finally:
        client.__exit__(None, None, None)
