"""Local mode: no account, this computer only, and the web interface served by the API."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import CSRF_HEADERS, make_settings, requires_ffmpeg

LOCAL = "http://localhost:8000"
LOOPBACK_PEER = ("127.0.0.1", 50000)


def local_client(settings: Settings, **kwargs: object) -> TestClient:
    options: dict[str, object] = {
        "base_url": LOCAL,
        "client": LOOPBACK_PEER,
        "headers": CSRF_HEADERS,
    }
    options.update(kwargs)
    return TestClient(create_app(settings), **options)  # type: ignore[arg-type]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path, mode="local")


@pytest.fixture
def local(settings: Settings) -> Iterator[TestClient]:
    with local_client(settings) as client:
        yield client


def test_everything_works_without_an_account(local: TestClient) -> None:
    status = local.get("/api/v1/auth/status").json()
    assert status == {
        "has_users": True,
        "registration_open": False,
        "email_verification": False,
        "mode": "local",
        "accounts": False,
    }
    meta = local.get("/api/v1/meta").json()
    assert meta["accounts"] is False and meta["processing"] == "this_computer"
    me = local.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["display_name"] == "This computer"
    project = local.post("/api/v1/projects", json={"name": "Mine", "auto_process": False})
    assert project.status_code == 201
    assert local.get("/api/v1/projects").json()["total"] == 1
    assert local.get("/api/v1/dashboard").status_code == 200


def test_projects_from_an_earlier_account_stay_visible(tmp_path: Path) -> None:
    from tests.conftest import register

    data = tmp_path / "shared"
    server_app = create_app(make_settings(data, mode="server"))
    with TestClient(server_app, headers=CSRF_HEADERS) as before:
        register(before)
        before.post(
            "/api/v1/projects", json={"name": "Made with an account", "auto_process": False}
        )
    with local_client(make_settings(data, mode="local")) as after:
        assert after.get("/api/v1/auth/me").json()["email"] == "alice@example.com"
        names = [p["name"] for p in after.get("/api/v1/projects").json()["items"]]
        assert names == ["Made with an account"]


def test_sign_in_and_sign_up_are_disabled(local: TestClient) -> None:
    for path, body in (
        ("/api/v1/auth/register", {"email": "a@example.com", "password": "correct-horse-battery"}),
        ("/api/v1/auth/login", {"email": "local-user@openclip.invalid", "password": "anything"}),
        ("/api/v1/auth/password", {"current_password": "x", "new_password": "y" * 12}),
    ):
        response = local.post(path, json=body)
        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "local_mode"


def test_other_computers_are_refused(settings: Settings) -> None:
    with local_client(settings, client=("192.168.1.40", 40000)) as remote:
        response = remote.get("/api/v1/projects")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "local_only"


def test_dns_rebinding_is_refused(settings: Settings) -> None:
    # A website that resolves its own name to 127.0.0.1 still sends its own Host header.
    with local_client(settings, base_url="http://attacker.example.com") as rebound:
        assert rebound.get("/api/v1/projects").status_code == 403
    with local_client(settings, base_url="http://127.0.0.1:8000") as by_address:
        assert by_address.get("/api/v1/projects").status_code == 200


def test_websites_cannot_send_commands_to_the_local_app(local: TestClient) -> None:
    # Cross-site request without the CSRF header (what a plain HTML form would send).
    bare = local.post(
        "/api/v1/projects",
        json={"name": "x"},
        headers={"X-Requested-With": "", "Origin": "https://evil.example.com"},
    )
    assert bare.status_code == 403
    # The app's own pages (same origin) and the dev server origin are allowed.
    same_origin = local.post(
        "/api/v1/projects",
        json={"name": "Same origin", "auto_process": False},
        headers={"Origin": LOCAL},
    )
    assert same_origin.status_code == 201
    dev = local.post(
        "/api/v1/projects",
        json={"name": "Dev", "auto_process": False},
        headers={"Origin": "http://localhost:3000"},
    )
    assert dev.status_code == 201


def test_account_deletion_is_not_offered_but_data_can_be_erased(local: TestClient) -> None:
    local.post("/api/v1/projects", json={"name": "One", "auto_process": False})
    local.post("/api/v1/projects", json={"name": "Two", "auto_process": False})
    account = local.get("/api/v1/account").json()
    assert account["can_delete_account"] is False and account["projects"] == 2
    assert local.post("/api/v1/account/delete", json={"password": "x"}).status_code == 403
    erased = local.delete("/api/v1/account/projects")
    assert erased.json() == {"deleted_projects": 2}
    assert local.get("/api/v1/projects").json()["total"] == 0


@requires_ffmpeg
def test_local_mode_processes_videos_in_process(
    local: TestClient, sample_video: Path, settings: Settings
) -> None:
    project = local.post("/api/v1/projects", json={"name": "Talk", "auto_process": False}).json()
    uploaded = local.put(
        f"/api/v1/projects/{project['id']}/media",
        params={"filename": "talk.mp4"},
        content=sample_video.read_bytes(),
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["media_host"] == "server"
    media = local.get(f"/api/v1/projects/{project['id']}/media")
    assert media.status_code == 200 and media.headers["content-type"] == "video/mp4"
    # Files are stored inside the local data folder only.
    assert list(settings.storage_dir.rglob("source.mp4"))


def test_api_refuses_to_start_on_a_network_address_in_local_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import app.__main__ as entry

    monkeypatch.setattr(
        entry,
        "get_settings",
        lambda: make_settings(tmp_path, mode="local", host="0.0.0.0"),  # noqa: S104
    )
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: pytest.fail("must not start"))
    assert entry.serve(reload=False) == 2


# ------------------------------------------------------- built web interface
@pytest.fixture
def web_build(tmp_path: Path) -> Path:
    out = tmp_path / "web-out"
    (out / "_next" / "static" / "chunks").mkdir(parents=True)
    (out / "index.html").write_text("<!doctype html><title>IDK Clips</title>", encoding="utf-8")
    (out / "404.html").write_text("<!doctype html><title>Not found</title>", encoding="utf-8")
    (out / "dashboard.html").write_text("<!doctype html><title>Dashboard</title>", encoding="utf-8")
    (out / "_next" / "static" / "chunks" / "app-1234.js").write_text(
        "console.log(1)", encoding="utf-8"
    )
    return out


def test_web_interface_is_served_with_a_strict_policy(tmp_path: Path, web_build: Path) -> None:
    settings = make_settings(tmp_path, mode="local", web_dist_dir=web_build)
    with local_client(settings) as client:
        page = client.get("/")
        assert page.status_code == 200 and "IDK Clips" in page.text
        policy = page.headers["content-security-policy"]
        assert "default-src 'self'" in policy and "frame-ancestors 'none'" in policy
        assert page.headers["cache-control"] == "no-cache"
        asset = client.get("/_next/static/chunks/app-1234.js")
        assert asset.status_code == 200
        assert "immutable" in asset.headers["cache-control"]
        # API routes are not shadowed by the static files.
        assert client.get("/api/v1/health").json()["status"] == "ok"
        assert client.get("/api/docs").status_code == 200
        missing = client.get("/no-such-page")
        assert missing.status_code == 404
        # Static files never leak anything outside the build folder.
        assert client.get("/../pyproject.toml").status_code == 404
