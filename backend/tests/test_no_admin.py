"""IDK Clips has no administrator system: no roles, no admin endpoints, no admin command.

Every account is an ordinary user who can reach only their own data. Settings that used
to be "administrator only" are either per user (AI provider and model) or fixed by the
server's configuration (the Ollama endpoint), so no user can affect another user.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.__main__ import main as cli_main
from app.db.models import User
from app.main import create_app
from tests.conftest import CSRF_HEADERS, PASSWORD, make_settings, register

AI = "/api/v1/settings/ai"
LOCAL = {"base_url": "http://localhost:8000", "client": ("127.0.0.1", 50000)}


# --------------------------------------------------------------- no roles
@pytest.mark.parametrize(
    "extra",
    [{"role": "admin"}, {"is_admin": True}, {"isAdmin": True}, {"roles": ["admin"]}],
)
def test_sign_up_rejects_role_fields(app, client: TestClient, extra: dict) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "m@example.com", "password": PASSWORD, "display_name": "M", **extra},
    )
    assert response.status_code == 422
    assert client.get("/api/v1/auth/me").status_code == 401
    with app.state.database.session_scope() as db:
        assert db.scalar(sa.select(User).where(User.email == "m@example.com")) is None


def test_users_table_has_no_role_column(app, user_client: TestClient) -> None:  # type: ignore[no-untyped-def]
    with app.state.database.session_scope() as db:
        columns = {c["name"] for c in sa.inspect(db.get_bind()).get_columns("users")}
    assert "is_admin" not in columns
    assert not any("admin" in name or "role" in name for name in columns)
    assert not hasattr(User, "is_admin")


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/admin/users"),
        ("patch", "/api/v1/admin/users/00000000-0000-0000-0000-000000000000"),
        ("get", "/api/v1/admin"),
        ("get", "/api/v1/users"),
    ],
)
def test_there_are_no_admin_endpoints(user_client: TestClient, method: str, path: str) -> None:
    response = getattr(user_client, method)(path, **({"json": {}} if method == "patch" else {}))
    assert response.status_code == 404


def test_openapi_lists_no_admin_operations(client: TestClient) -> None:
    spec = client.app.openapi()  # type: ignore[attr-defined]
    assert not [path for path in spec["paths"] if "admin" in path.lower()]
    for name, schema in spec["components"]["schemas"].items():
        fields = set(schema.get("properties", {}))
        assert not fields & {"is_admin", "role", "roles"}, name


def test_profile_updates_cannot_carry_roles(user_client: TestClient) -> None:
    for body in ({"is_admin": True}, {"role": "admin"}, {"display_name": "A", "is_admin": True}):
        assert user_client.patch("/api/v1/account", json=body).status_code == 422


def test_there_is_no_admin_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli_main(["admin", "create", "--email", "a@example.com"])
    assert "invalid choice" in capsys.readouterr().err


# ------------------------------------------------- AI settings are per user
def test_each_user_chooses_their_own_model(
    user_client: TestClient, second_client: TestClient
) -> None:
    before = second_client.get(AI).json()
    assert before["scope"] == "account" and before["can_change_endpoint"] is False
    changed = user_client.put(AI, json={"ollama_model": "alice-model:7b"})
    assert changed.status_code == 200 and changed.json()["ollama_model"] == "alice-model:7b"
    # Bob is not affected by Alice's choice.
    assert second_client.get(AI).json()["ollama_model"] == before["ollama_model"]
    assert user_client.get(AI).json()["ollama_model"] == "alice-model:7b"


def test_users_cannot_point_the_server_at_another_address(user_client: TestClient) -> None:
    current = user_client.get(AI).json()["ollama_base_url"]
    for url in ("http://169.254.169.254/latest", "http://10.0.0.5:11434", "https://evil.example"):
        response = user_client.put(AI, json={"ollama_base_url": url})
        assert response.status_code == 422, url
        assert response.json()["error"]["code"] == "endpoint_server_only"
    # Sending the unchanged value is harmless.
    assert user_client.put(AI, json={"ollama_base_url": current}).status_code == 200
    assert user_client.get(AI).json()["ollama_base_url"] == current
    # Unknown fields are refused rather than ignored.
    assert user_client.put(AI, json={"api_key": "x"}).status_code == 422


def test_jobs_use_the_project_owners_model(
    app, user_client: TestClient, second_client: TestClient
) -> None:  # type: ignore[no-untyped-def]
    from app.db.models import Job
    from app.jobs.specs import _ai_config

    user_client.put(AI, json={"ollama_model": "alice-model:7b"})
    project = user_client.post(
        "/api/v1/projects", json={"name": "Mine", "auto_process": False}
    ).json()
    with app.state.database.session_scope() as db:
        alice = db.scalar(sa.select(User).where(User.email == "alice@example.com"))
        job = Job(owner_id=alice.id, project_id=project["id"], type="detect_clips")
        config = _ai_config(db, app.state.settings, job)
    assert config["ollama_model"] == "alice-model:7b"


def test_local_mode_owner_edits_the_whole_setup(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path, mode="local"))
    with TestClient(app, headers=CSRF_HEADERS, **LOCAL) as local:  # type: ignore[arg-type]
        settings = local.get(AI).json()
        assert settings["scope"] == "computer" and settings["can_change_endpoint"] is True
        response = local.put(AI, json={"ollama_base_url": "http://127.0.0.1:11500"})
        assert response.status_code == 200
        assert local.get(AI).json()["ollama_base_url"] == "http://127.0.0.1:11500"


# ------------------------------------------------------ existing databases
def test_upgrading_an_old_database_drops_the_role_but_keeps_accounts(tmp_path: Path) -> None:
    """A database created before 0004 (with administrators) keeps its users and data."""
    from alembic import command

    from app.db.migrate import alembic_config

    settings = make_settings(tmp_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_config(settings.sqlalchemy_url), "0003")
    engine = sa.create_engine(settings.sqlalchemy_url)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO users (id, email, display_name, password_hash, is_admin, is_active, "
                "created_at, preferences) VALUES ('u-1', 'old@example.com', 'Old', 'x', 1, 1, "
                "'2026-01-01 00:00:00', '{}')"
            )
        )
    engine.dispose()

    app = create_app(settings)  # upgrades to head on start
    with TestClient(app, headers=CSRF_HEADERS) as client:
        register(client, "new@example.com")
        with app.state.database.session_scope() as db:
            emails = set(db.scalars(sa.select(User.email)).all())
            columns = {c["name"] for c in sa.inspect(db.get_bind()).get_columns("users")}
    assert {"old@example.com", "new@example.com"} <= emails
    assert "is_admin" not in columns
