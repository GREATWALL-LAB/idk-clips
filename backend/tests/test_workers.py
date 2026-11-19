"""Hybrid mode: pairing, worker credentials, job coordination and isolation between users."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.security import hash_token
from app.db.base import utcnow
from app.db.models import Job, PairingCode, Worker
from app.main import create_app
from app.services.workers import requeue_expired
from tests.conftest import CSRF_HEADERS, make_settings, register
from tests.hybrid import (
    AGENT,
    PROJECTS,
    WORKERS,
    FakeWorker,
    clips_payload,
    new_code,
    transcript_payload,
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path, mode="hybrid")


def make_project(user: TestClient, **options: object) -> dict:
    body = {"name": "Talk", "auto_process": True, **options}
    response = user.post(PROJECTS, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def job_row(app, job_id: str) -> Job:  # type: ignore[no-untyped-def]
    with app.state.database.session_scope() as db:
        job = db.get(Job, job_id)
        db.expunge(job)
        return job


# ----------------------------------------------------------------- modes
def test_worker_endpoints_do_not_exist_outside_hybrid_mode(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path, mode="server"))
    with TestClient(app, headers=CSRF_HEADERS) as client:
        register(client)
        assert client.get(WORKERS).status_code == 404
        assert client.post(f"{WORKERS}/pairing-codes").status_code == 404
        assert client.post(f"{AGENT}/pair", json={"code": "ABCD-EFGH"}).status_code == 404


def test_meta_describes_hybrid_mode(client: TestClient) -> None:
    meta = client.get("/api/v1/meta").json()
    assert meta["mode"] == "hybrid"
    assert meta["accounts"] is True
    assert meta["processing"] == "your_worker"


# --------------------------------------------------------------- pairing
def test_pairing_requires_a_signed_in_user(client: TestClient) -> None:
    assert client.post(f"{WORKERS}/pairing-codes").status_code == 401
    assert client.get(WORKERS).status_code == 401


def test_pairing_code_works_exactly_once(app, user_client: TestClient) -> None:  # type: ignore[no-untyped-def]
    code = new_code(user_client)
    assert len(code) == 9 and code[4] == "-"
    machine = TestClient(app, headers=CSRF_HEADERS)
    first = machine.post(f"{AGENT}/pair", json={"code": code.lower(), "name": "  Studio   PC "})
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["worker_name"] == "Studio PC"
    assert body["token"].startswith("ocw_") and len(body["token"]) > 40
    assert body["allowed_origins"] == ["http://localhost:3000", "http://127.0.0.1:3000"]
    again = machine.post(f"{AGENT}/pair", json={"code": code})
    assert again.status_code == 422
    assert again.json()["error"]["code"] == "invalid_pairing_code"


def test_secrets_are_stored_only_as_hashes(app, user_client: TestClient) -> None:  # type: ignore[no-untyped-def]
    code = new_code(user_client)
    normalized = code.replace("-", "")
    with app.state.database.session_scope() as db:
        row = db.scalar(select(PairingCode))
        assert row.code_hash == hash_token(normalized)
        assert normalized not in (row.code_hash, row.id)
    worker = FakeWorker(app, user_client)
    with app.state.database.session_scope() as db:
        stored = db.get(Worker, worker.id)
        assert stored.token_hash == hash_token(worker.token)
        assert worker.token not in stored.token_hash


def test_wrong_and_expired_codes_are_refused(app, user_client: TestClient) -> None:  # type: ignore[no-untyped-def]
    machine = TestClient(app, headers=CSRF_HEADERS)
    assert machine.post(f"{AGENT}/pair", json={"code": "ZZZZ-ZZZZ"}).status_code == 422
    assert machine.post(f"{AGENT}/pair", json={"code": "short"}).status_code == 422
    code = new_code(user_client)
    with app.state.database.session_scope() as db:
        db.scalar(select(PairingCode)).expires_at = utcnow() - timedelta(seconds=1)
    expired = machine.post(f"{AGENT}/pair", json={"code": code})
    assert expired.status_code == 422
    assert user_client.get(WORKERS).json() == []


def test_pairing_attempts_are_rate_limited(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path, mode="hybrid", rate_limit_enabled=True))
    with TestClient(app, headers=CSRF_HEADERS) as machine:
        statuses = [
            machine.post(f"{AGENT}/pair", json={"code": "ZZZZ-ZZZZ"}).status_code for _ in range(12)
        ]
    assert statuses[:10] == [422] * 10
    assert statuses[10:] == [429, 429]


def test_too_many_unused_codes_are_refused(user_client: TestClient) -> None:
    for _ in range(5):
        new_code(user_client)
    refused = user_client.post(f"{WORKERS}/pairing-codes")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "too_many_codes"


# ------------------------------------------------------ worker credentials
def test_worker_must_authenticate(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    for headers in ({}, {"Authorization": "Bearer ocw_not-a-real-token"}, {"Authorization": "x"}):
        response = client.post(f"{AGENT}/jobs/claim", json={"wait_seconds": 0}, headers=headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "worker_not_authorized"


def test_user_sees_renames_and_revokes_their_worker(app, user_client: TestClient) -> None:  # type: ignore[no-untyped-def]
    worker = FakeWorker(app, user_client, name="Desk")
    heartbeat = worker.post(
        "/heartbeat",
        {
            "bridge_port": 8899,
            "app_version": "0.1.0",
            "capabilities": {"ollama_models": ["gemma3:4b"], "gpu": "NVIDIA GPU (CUDA)"},
        },
    )
    assert heartbeat.status_code == 200, heartbeat.text
    listed = user_client.get(WORKERS).json()
    assert len(listed) == 1
    assert listed[0]["online"] is True and listed[0]["bridge_port"] == 8899
    assert listed[0]["capabilities"]["ollama_models"] == ["gemma3:4b"]
    assert "token" not in listed[0] and "token_hash" not in listed[0]

    renamed = user_client.patch(
        f"{WORKERS}/{worker.id}", json={"name": "Studio", "preferred_model": "gemma3:4b"}
    )
    assert renamed.json()["name"] == "Studio"
    assert renamed.json()["preferred_model"] == "gemma3:4b"
    assert (
        user_client.patch(f"{WORKERS}/{worker.id}", json={"preferred_model": "bad model; rm"})
    ).status_code == 422

    assert user_client.delete(f"{WORKERS}/{worker.id}").status_code == 204
    assert user_client.get(WORKERS).json() == []
    # The credentials stop working at once.
    assert worker.post("/heartbeat", {}).status_code == 401
    assert worker.post("/jobs/claim", {"wait_seconds": 0}).status_code == 401


def test_worker_can_unpair_itself(app, user_client: TestClient) -> None:  # type: ignore[no-untyped-def]
    worker = FakeWorker(app, user_client)
    assert worker.http.delete(f"{AGENT}/self", headers=worker.auth).status_code == 204
    assert worker.post("/heartbeat", {}).status_code == 401
    assert user_client.get(WORKERS).json() == []


# ------------------------------------------------------------ full job flow
def test_job_is_assigned_processed_and_synchronised(app, user_client: TestClient) -> None:  # type: ignore[no-untyped-def]
    worker = FakeWorker(app, user_client)
    project = make_project(user_client)
    pid = project["id"]
    assert project["media_host"] == "worker" and project["has_media"] is False

    # The server itself never accepts video in hybrid mode.
    refused = user_client.put(
        f"{PROJECTS}/{pid}/media", params={"filename": "talk.mp4"}, content=b"x" * 32
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "upload_to_worker"

    # The owner sends the file to the worker, which registers it.
    assert worker.register_media(pid).status_code == 204
    detail = user_client.get(f"{PROJECTS}/{pid}").json()
    assert detail["has_media"] is True and detail["worker_id"] == worker.id
    assert detail["status"] == "queued" and detail["duration_seconds"] == 12.0
    job_id = detail["active_job"]["id"]
    assert detail["active_job"]["stage"] == "Waiting for your worker"

    spec = worker.claim()
    assert spec is not None
    assert spec["job_id"] == job_id and spec["type"] == "process"
    assert spec["owner_id"] == worker.owner_id
    assert spec["media_key"] == f"users/{worker.owner_id}/projects/{pid}/source.mp4"
    assert spec["ai"] == {"provider": "worker", "ollama_model": None}
    assert worker.claim() is None  # one job, handed out once

    running = user_client.get(f"/api/v1/jobs/{job_id}").json()
    assert running["status"] == "running" and running["worker_id"] == worker.id

    progress = worker.post(f"/jobs/{job_id}/progress", {"progress": 0.4, "stage": "Transcribing"})
    assert progress.json() == {"cancel_requested": False, "lease_seconds": 90}
    assert user_client.get(f"/api/v1/jobs/{job_id}").json()["stage"] == "Transcribing"

    assert (
        worker.event(
            job_id, "project_status", {"project_id": pid, "status": "transcribing"}
        ).status_code
        == 204
    )
    assert user_client.get(f"{PROJECTS}/{pid}").json()["status"] == "transcribing"
    assert worker.event(job_id, "transcript", transcript_payload(pid)).status_code == 204
    analyzing = {
        "project_id": pid,
        "status": "analyzing",
        "ai_provider": "ollama",
        "ai_model": "gemma3:4b",
    }
    assert worker.event(job_id, "project_status", analyzing).status_code == 204
    assert worker.event(job_id, "clips", clips_payload(pid)).status_code == 204
    assert worker.finish(job_id).status_code == 204
    assert worker.finish(job_id).status_code == 204  # reporting twice is harmless

    done = user_client.get(f"{PROJECTS}/{pid}").json()
    assert done["status"] == "ready" and done["ai_model"] == "gemma3:4b"
    assert done["has_transcript"] is True and done["clips"] == {"total": 1, "ready": 0}
    transcript = user_client.get(f"{PROJECTS}/{pid}/transcript").json()
    assert transcript["segments"][0]["text"] == "Hello and welcome"
    clip = user_client.get(f"{PROJECTS}/{pid}/clips").json()["items"][0]
    assert clip["title"] == "Welcome to the test" and clip["media_host"] == "worker"

    # Export: the render job goes to the same worker and the result stays there.
    render = user_client.post(f"/api/v1/clips/{clip['id']}/render")
    assert render.status_code == 202
    render_spec = worker.claim()
    assert render_spec["type"] == "render_clip" and render_spec["aspect_ratio"] == "9:16"
    assert render_spec["cues"] and render_spec["output_key"].endswith(f"/clips/{clip['id']}.mp4")
    rid = render_spec["job_id"]
    assert (
        worker.event(rid, "crop_position", {"clip_id": clip["id"], "position": 0.31}).status_code
        == 204
    )
    rendered = {"clip_id": clip["id"], "output_key": render_spec["output_key"], "size_bytes": 4321}
    assert worker.event(rid, "clip_rendered", rendered).status_code == 204
    assert worker.finish(rid).status_code == 204
    ready = user_client.get(f"/api/v1/clips/{clip['id']}").json()
    assert ready["status"] == "ready" and ready["crop_position"] == 0.31
    assert ready["preview_url"] and ready["output_size_bytes"] == 4321
    # The server has no bytes to serve; the browser is pointed at the worker.
    served = user_client.get(f"/api/v1/clips/{clip['id']}/file")
    assert served.status_code == 404 and served.json()["error"]["code"] == "media_on_worker"
    assert user_client.get(f"{PROJECTS}/{pid}/media").json()["error"]["code"] == "media_on_worker"


def test_failed_job_reports_a_meaningful_error_and_can_be_retried(
    app, user_client: TestClient
) -> None:  # type: ignore[no-untyped-def]
    worker = FakeWorker(app, user_client)
    pid = make_project(user_client)["id"]
    worker.register_media(pid)
    spec = worker.claim()
    worker.finish(spec["job_id"], "failed", "Ollama is not reachable. Start the Ollama app.")
    project = user_client.get(f"{PROJECTS}/{pid}").json()
    assert project["status"] == "uploaded"
    assert project["error_message"] == "Ollama is not reachable. Start the Ollama app."
    retry = user_client.post(f"{PROJECTS}/{pid}/process", json={})
    assert retry.status_code == 202
    assert worker.claim()["job_id"] == retry.json()["id"]


def test_cancelling_reaches_the_worker(app, user_client: TestClient) -> None:  # type: ignore[no-untyped-def]
    worker = FakeWorker(app, user_client)
    pid = make_project(user_client)["id"]
    worker.register_media(pid)
    job_id = worker.claim()["job_id"]
    assert user_client.post(f"/api/v1/jobs/{job_id}/cancel").json()["cancel_requested"] is True
    answer = worker.post(f"/jobs/{job_id}/progress", {"progress": 0.5}).json()
    assert answer["cancel_requested"] is True
    worker.finish(job_id, "cancelled")
    assert user_client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "cancelled"
    assert user_client.get(f"{PROJECTS}/{pid}").json()["status"] == "uploaded"
    # A job cancelled while it waits is never handed out.
    waiting = user_client.post(f"{PROJECTS}/{pid}/process", json={}).json()
    user_client.post(f"/api/v1/jobs/{waiting['id']}/cancel")
    assert worker.claim() is None


# -------------------------------------------------- disconnections / leases
def test_job_returns_to_the_queue_when_the_worker_goes_silent(
    app, settings, user_client: TestClient
) -> None:  # type: ignore[no-untyped-def]
    worker = FakeWorker(app, user_client)
    pid = make_project(user_client)["id"]
    worker.register_media(pid)
    job_id = worker.claim()["job_id"]

    def expire() -> None:
        with app.state.database.session_scope() as db:
            db.get(Job, job_id).lease_expires_at = utcnow() - timedelta(seconds=5)

    expire()
    assert requeue_expired(app.state.database, app.state.storage, settings) == 1
    waiting = user_client.get(f"/api/v1/jobs/{job_id}").json()
    assert waiting["status"] == "queued" and "reconnect" in waiting["stage"]

    # The worker was only briefly offline and is still on the job: it keeps it.
    kept = worker.post(f"/jobs/{job_id}/progress", {"progress": 0.6, "stage": "Still working"})
    assert kept.status_code == 200
    assert user_client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "running"

    # A worker that never comes back: the job is offered again, then failed after 3 attempts.
    expire()
    requeue_expired(app.state.database, app.state.storage, settings)
    assert worker.claim()["job_id"] == job_id  # attempt 2
    expire()
    requeue_expired(app.state.database, app.state.storage, settings)
    assert worker.claim()["job_id"] == job_id  # attempt 3
    expire()
    requeue_expired(app.state.database, app.state.storage, settings)
    failed = user_client.get(f"/api/v1/jobs/{job_id}").json()
    assert failed["status"] == "failed" and failed["attempts"] == 3
    assert "stopped responding" in failed["error_message"]
    project = user_client.get(f"{PROJECTS}/{pid}").json()
    assert project["status"] == "uploaded" and "stopped responding" in project["error_message"]
    # A late report from the lost worker is ignored rather than resurrecting the job.
    assert worker.post(f"/jobs/{job_id}/progress", {"progress": 0.9}).status_code == 409
    assert worker.event(job_id, "transcript", transcript_payload(pid)).status_code == 409


def test_revoking_a_worker_settles_its_jobs(app, user_client: TestClient) -> None:  # type: ignore[no-untyped-def]
    worker = FakeWorker(app, user_client)
    pid = make_project(user_client)["id"]
    worker.register_media(pid)
    job_id = worker.claim()["job_id"]
    user_client.delete(f"{WORKERS}/{worker.id}")
    job = user_client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "failed" and "disconnected" in job["error_message"]


# ------------------------------------------------- isolation between users
def test_users_cannot_see_or_control_each_others_workers(
    app, user_client: TestClient, second_client: TestClient
) -> None:  # type: ignore[no-untyped-def]
    alice_worker = FakeWorker(app, user_client)
    assert second_client.get(WORKERS).json() == []
    assert second_client.delete(f"{WORKERS}/{alice_worker.id}").status_code == 404
    assert (
        second_client.patch(f"{WORKERS}/{alice_worker.id}", json={"name": "Mine"}).status_code
        == 404
    )
    token = second_client.post(
        f"{WORKERS}/{alice_worker.id}/transfer-tokens", json={"scope": "read"}
    )
    assert token.status_code == 404
    assert alice_worker.post("/heartbeat", {}).status_code == 200  # untouched


def test_a_worker_only_gets_its_owners_jobs(
    app, user_client: TestClient, second_client: TestClient
) -> None:  # type: ignore[no-untyped-def]
    alice_worker = FakeWorker(app, user_client)
    bob_worker = FakeWorker(app, second_client)
    pid = make_project(user_client)["id"]
    # Bob's worker cannot register media for Alice's project...
    assert bob_worker.register_media(pid).status_code == 404
    assert alice_worker.register_media(pid).status_code == 204
    # ...cannot claim her job...
    assert bob_worker.claim() is None
    job_id = alice_worker.claim()["job_id"]
    # ...and cannot report progress, results or an outcome for it.
    assert bob_worker.post(f"/jobs/{job_id}/progress", {"progress": 0.5}).status_code == 404
    assert bob_worker.event(job_id, "transcript", transcript_payload(pid)).status_code == 404
    assert bob_worker.finish(job_id, "failed", "nope").status_code == 404
    assert user_client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "running"
    assert second_client.get(f"/api/v1/jobs/{job_id}").status_code == 404


def test_events_are_validated_and_confined_to_the_jobs_project(
    app, user_client: TestClient
) -> None:  # type: ignore[no-untyped-def]
    worker = FakeWorker(app, user_client)
    pid = make_project(user_client)["id"]
    other = make_project(user_client, name="Other")["id"]
    worker.register_media(pid)
    worker.register_media(other)
    job_id = worker.claim()["job_id"]
    spec_project = job_row(app, job_id).project_id
    foreign = other if spec_project == pid else pid

    def rejected(name: str, payload: dict) -> str:
        response = worker.event(job_id, name, payload)
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "invalid_event"
        return response.json()["error"]["message"]

    # A result for another project of the same user is still refused.
    assert "does not belong" in rejected("transcript", transcript_payload(foreign))
    # Event types that this kind of job cannot produce.
    assert "not allowed" in rejected(
        "clip_rendered", {"clip_id": "x", "output_key": "y", "size_bytes": 1}
    )
    assert "not allowed" in rejected("run_command", {"cmd": "whoami"})
    # Malformed and out-of-range values.
    assert "Invalid" in rejected("project_status", {"project_id": spec_project, "status": "ready"})
    bad_clips = clips_payload(spec_project)
    bad_clips["suggestions"][0]["score"] = 1000
    assert "Invalid" in rejected("clips", bad_clips)
    huge = clips_payload(spec_project)
    huge["suggestions"] = huge["suggestions"] * 51
    assert "Invalid" in rejected("clips", huge)
    # Nothing was stored by any of the rejected events.
    assert user_client.get(f"{PROJECTS}/{spec_project}").json()["has_transcript"] is False
    assert user_client.get(f"{PROJECTS}/{foreign}").json()["has_transcript"] is False


def test_file_references_must_stay_inside_the_project_folder(app, user_client: TestClient) -> None:  # type: ignore[no-untyped-def]
    worker = FakeWorker(app, user_client)
    pid = make_project(user_client, auto_process=False)["id"]
    for key in (
        "users/someone-else/projects/x/source.mp4",
        f"users/{worker.owner_id}/projects/{pid}/../../../../etc/passwd.mp4",
        "C:\\Windows\\system32\\source.mp4",
        f"users/{worker.owner_id}/projects/{pid}/source.exe",
    ):
        response = worker.register_media(pid, media_key=key)
        assert response.status_code == 422, key
    assert user_client.get(f"{PROJECTS}/{pid}").json()["has_media"] is False
    assert worker.register_media(pid).status_code == 204
    assert worker.register_media(pid).status_code == 409  # a project takes one video


# ---------------------------------------------------------- transfer tokens
def test_transfer_tokens_are_scoped_to_one_worker_and_owner(
    app, user_client: TestClient, second_client: TestClient
) -> None:  # type: ignore[no-untyped-def]
    worker = FakeWorker(app, user_client)
    second_worker = FakeWorker(app, user_client, name="Laptop")
    bob_worker = FakeWorker(app, second_client)
    pid = make_project(user_client)["id"]

    upload = user_client.post(
        f"{WORKERS}/{worker.id}/transfer-tokens", json={"scope": "upload", "project_id": pid}
    )
    assert upload.status_code == 201, upload.text
    token = upload.json()["token"]
    assert token.startswith("oct_") and upload.json()["bridge_port"] == 8787

    checked = worker.post("/transfer-tokens/verify", {"token": token})
    assert checked.status_code == 200
    assert checked.json()["scope"] == "upload" and checked.json()["project_id"] == pid
    assert checked.json()["owner_id"] == worker.owner_id and checked.json()["expires_in"] > 0
    # The same token is worthless on any other worker.
    assert second_worker.post("/transfer-tokens/verify", {"token": token}).status_code == 403
    assert bob_worker.post("/transfer-tokens/verify", {"token": token}).status_code == 403
    assert worker.post("/transfer-tokens/verify", {"token": "oct_guess"}).status_code == 403

    # Bob cannot get a token for Alice's project, even on his own worker.
    theirs = second_client.post(
        f"{WORKERS}/{bob_worker.id}/transfer-tokens", json={"scope": "upload", "project_id": pid}
    )
    assert theirs.status_code == 404

    # Once the project has a video, no further upload tokens are issued.
    worker.register_media(pid)
    again = user_client.post(
        f"{WORKERS}/{worker.id}/transfer-tokens", json={"scope": "upload", "project_id": pid}
    )
    assert again.status_code == 409


def test_expired_transfer_tokens_are_refused(app, user_client: TestClient) -> None:  # type: ignore[no-untyped-def]
    from app.db.models import TransferToken

    worker = FakeWorker(app, user_client)
    token = user_client.post(
        f"{WORKERS}/{worker.id}/transfer-tokens", json={"scope": "read"}
    ).json()["token"]
    with app.state.database.session_scope() as db:
        db.scalar(select(TransferToken)).expires_at = utcnow() - timedelta(seconds=1)
    assert worker.post("/transfer-tokens/verify", {"token": token}).status_code == 403


# ----------------------------------------------------------------- deletion
def test_deleting_a_project_tells_the_worker_to_remove_its_files(
    app, user_client: TestClient
) -> None:  # type: ignore[no-untyped-def]
    worker = FakeWorker(app, user_client)
    pid = make_project(user_client, auto_process=False)["id"]
    worker.register_media(pid)
    assert user_client.delete(f"{PROJECTS}/{pid}").status_code == 204
    assert user_client.get(f"{PROJECTS}/{pid}").status_code == 404
    spec = worker.claim()
    assert spec["type"] == "purge_files"
    assert spec["prefix"] == f"users/{worker.owner_id}/projects/{pid}"
    assert worker.finish(spec["job_id"]).status_code == 204
    assert worker.claim() is None
