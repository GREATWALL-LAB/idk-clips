"""Account controls: retention, deleting data, deleting the account, per-clip aspect ratios."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.base import utcnow
from app.db.models import Job, Project, Transcript
from app.main import create_app
from app.services.retention import sweep_expired_sources
from tests.conftest import CSRF_HEADERS, PASSWORD, make_settings, register, requires_ffmpeg
from tests.hybrid import FakeWorker

PROJECTS = "/api/v1/projects"
ACCOUNT = "/api/v1/account"


def upload(client: TestClient, video: Path, **options: object) -> dict:
    project = client.post(PROJECTS, json={"name": "Talk", "auto_process": False, **options}).json()
    response = client.put(
        f"{PROJECTS}/{project['id']}/media",
        params={"filename": "talk.mp4"},
        content=video.read_bytes(),
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- account
def test_account_settings(user_client: TestClient) -> None:
    account = user_client.get(ACCOUNT).json()
    assert account["user"]["email"] == "alice@example.com"
    assert account["retention_days"] == 0 and account["can_delete_account"] is True
    updated = user_client.patch(
        ACCOUNT, json={"retention_days": 30, "display_name": "  Alice   B "}
    ).json()
    assert updated["retention_days"] == 30 and updated["user"]["display_name"] == "Alice B"
    assert user_client.patch(ACCOUNT, json={"retention_days": -1}).status_code == 422
    assert user_client.patch(ACCOUNT, json={"retention_days": 99999}).status_code == 422
    assert user_client.patch(ACCOUNT, json={"display_name": "   "}).status_code == 422


def test_account_requires_sign_in(client: TestClient) -> None:
    assert client.get(ACCOUNT).status_code == 401
    assert client.delete(f"{ACCOUNT}/projects").status_code == 401
    assert client.post(f"{ACCOUNT}/delete", json={"password": PASSWORD}).status_code == 401


def test_delete_all_projects_only_touches_your_own(
    user_client: TestClient, second_client: TestClient
) -> None:
    for name in ("A", "B"):
        user_client.post(PROJECTS, json={"name": name, "auto_process": False})
    second_client.post(PROJECTS, json={"name": "Bob's", "auto_process": False})
    assert user_client.delete(f"{ACCOUNT}/projects").json() == {"deleted_projects": 2}
    assert user_client.get(PROJECTS).json()["total"] == 0
    assert second_client.get(PROJECTS).json()["total"] == 1


@requires_ffmpeg
def test_deleting_the_account_removes_everything(
    app, user_client: TestClient, second_client: TestClient, sample_video: Path, settings
) -> None:  # type: ignore[no-untyped-def]
    project = upload(user_client, sample_video)
    bob_project = upload(second_client, sample_video)
    wrong = user_client.post(f"{ACCOUNT}/delete", json={"password": "not-my-password"})
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "invalid_password"

    deleted = user_client.post(f"{ACCOUNT}/delete", json={"password": PASSWORD})
    assert deleted.status_code == 204
    assert "openclip_session=" in deleted.headers.get("set-cookie", "")
    assert user_client.get("/api/v1/auth/me").status_code == 401
    login = user_client.post(
        "/api/v1/auth/login", json={"email": "alice@example.com", "password": PASSWORD}
    )
    assert login.status_code == 401
    with app.state.database.session_scope() as db:
        assert db.get(Project, project["id"]) is None
    alice_files = [p for p in settings.storage_dir.rglob("*") if project["id"] in str(p)]
    assert alice_files == []
    # Bob is unaffected.
    assert second_client.get(f"{PROJECTS}/{bob_project['id']}").json()["has_media"] is True


def test_local_user_address_cannot_be_registered(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "age_confirmed": True,
            "email": "local-user@openclip.invalid",
            "password": PASSWORD,
            "display_name": "x",
        },
    )
    assert response.status_code == 422


# -------------------------------------------------------------- retention
@requires_ffmpeg
def test_retention_removes_only_old_source_videos(
    app, user_client: TestClient, sample_video: Path, settings
) -> None:  # type: ignore[no-untyped-def]
    old = upload(user_client, sample_video)
    recent = upload(user_client, sample_video)
    with app.state.database.session_scope() as db:
        db.get(Project, old["id"]).created_at = utcnow() - timedelta(days=10)
        db.add(
            Transcript(
                project_id=old["id"], language="en", language_probability=1.0, model="t",
                device="cpu", duration=12.0, word_count=0, segments=[], warnings=[],
            )
        )  # fmt: skip
    # Retention is off by default: nothing happens.
    assert sweep_expired_sources(app.state.database, app.state.storage, settings) == 0
    user_client.patch(ACCOUNT, json={"retention_days": 7})
    assert sweep_expired_sources(app.state.database, app.state.storage, settings) == 1

    gone = user_client.get(f"{PROJECTS}/{old['id']}").json()
    assert gone["has_media"] is False and gone["has_transcript"] is True
    assert "source_removed_at" in gone["source_meta"]
    assert user_client.get(f"{PROJECTS}/{recent['id']}").json()["has_media"] is True
    remaining = [p.parent.name for p in settings.storage_dir.rglob("source.mp4")]
    assert remaining == [recent["id"]]


def test_retention_in_hybrid_mode_asks_the_worker_to_delete(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, mode="hybrid")
    app = create_app(settings)
    with TestClient(app, headers=CSRF_HEADERS) as user:
        register(user)
        worker = FakeWorker(app, user)
        pid = user.post(PROJECTS, json={"name": "Old", "auto_process": False}).json()["id"]
        worker.register_media(pid)
        with app.state.database.session_scope() as db:
            db.get(Project, pid).created_at = utcnow() - timedelta(days=40)
        user.patch(ACCOUNT, json={"retention_days": 30})
        assert sweep_expired_sources(app.state.database, app.state.storage, settings) == 1
        spec = worker.claim()
        assert spec["type"] == "purge_files"
        assert spec["keys"] == [f"users/{worker.owner_id}/projects/{pid}/source.mp4"]
        assert user.get(f"{PROJECTS}/{pid}").json()["has_media"] is False
        with app.state.database.session_scope() as db:
            assert db.scalar(select(Job).where(Job.status == "queued")) is None


# ------------------------------------------------------- per-clip aspect ratio
@requires_ffmpeg
def test_each_clip_can_have_its_own_aspect_ratio(
    app, user_client: TestClient, sample_video: Path, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    from openclip_processing.ffmpeg import FFmpegTools
    from tests.clips_util import wait_for_job
    from tests.conftest import REAL_TOOLS

    project = upload(user_client, sample_video, aspect_ratio="9:16")
    clip = user_client.post(
        f"{PROJECTS}/{project['id']}/clips",
        json={"title": "Wide", "start_seconds": 1, "end_seconds": 5},
    ).json()
    assert clip["aspect_ratio"] == "9:16" and clip["aspect_ratio_overridden"] is False
    wide = user_client.patch(f"/api/v1/clips/{clip['id']}", json={"aspect_ratio": "16:9"}).json()
    assert wide["aspect_ratio"] == "16:9" and wide["aspect_ratio_overridden"] is True
    assert (
        user_client.patch(f"/api/v1/clips/{clip['id']}", json={"aspect_ratio": "2:1"}).status_code
        == 422
    )

    job = user_client.post(f"/api/v1/clips/{clip['id']}/render").json()
    assert wait_for_job(user_client, job["id"])["status"] == "succeeded"
    out = tmp_path / "wide.mp4"
    out.write_bytes(user_client.get(f"/api/v1/clips/{clip['id']}/file").content)
    info = FFmpegTools.locate(search_dirs=[REAL_TOOLS / "ffmpeg" / "bin"]).probe(out)
    assert (info.width, info.height) == (1920, 1080)

    # Changing the ratio marks the export as outdated; choosing the project default clears the override.
    back = user_client.patch(f"/api/v1/clips/{clip['id']}", json={"aspect_ratio": "9:16"}).json()
    assert back["aspect_ratio_overridden"] is False and back["status"] == "suggested"
