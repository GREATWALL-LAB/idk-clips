from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import AuthSession
from app.main import create_app
from tests.conftest import CSRF_HEADERS, PASSWORD, make_settings, register

LOGIN = "/api/v1/auth/login"


def test_auth_status_is_public_and_reports_setup(client: TestClient) -> None:
    assert client.get("/api/v1/auth/status").json() == {
        "has_users": False,
        "registration_open": True,
        "email_verification": False,
        "mode": "server",
        "accounts": True,
    }
    register(client)
    assert client.get("/api/v1/auth/status").json()["has_users"] is True


def test_accounts_have_no_role(user_client: TestClient, second_client: TestClient) -> None:
    # Not even the very first account on an empty server is special.
    for session in (user_client, second_client):
        me = session.get("/api/v1/auth/me").json()
        assert set(me) == {
            "id",
            "email",
            "display_name",
            "created_at",
            "email_verified",
            "age_confirmed",
        }
        assert not [key for key in me if "admin" in key or "role" in key]


def test_session_cookie_is_httponly_and_samesite(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "age_confirmed": True,
            "email": "a@example.com",
            "password": PASSWORD,
            "display_name": "A",
        },
    )
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    token = client.cookies.get("openclip_session")
    assert token and token not in response.text  # never returned in the body


def test_session_tokens_are_stored_hashed(app, user_client: TestClient) -> None:  # type: ignore[no-untyped-def]
    token = user_client.cookies.get("openclip_session")
    with app.state.database.session_scope() as db:
        stored = db.scalars(select(AuthSession.token_hash)).all()
    assert stored and token not in stored
    assert all(len(value) == 64 for value in stored)


def test_duplicate_email_and_weak_password_are_rejected(client: TestClient) -> None:
    register(client, "dup@example.com")
    response = client.post(
        "/api/v1/auth/register",
        json={"age_confirmed": True, "email": "DUP@example.com", "password": PASSWORD},
    )
    assert response.status_code == 409
    weak = client.post(
        "/api/v1/auth/register",
        json={"age_confirmed": True, "email": "x@example.com", "password": "short"},
    )
    assert weak.status_code == 422
    assert weak.json()["error"]["code"] == "weak_password"
    bad_email = client.post(
        "/api/v1/auth/register",
        json={"age_confirmed": True, "email": "not-an-email", "password": PASSWORD},
    )
    assert bad_email.status_code == 422


def test_login_logout_and_server_side_revocation(client: TestClient) -> None:
    register(client, "carol@example.com")
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401

    response = client.post(LOGIN, json={"email": "Carol@Example.com", "password": PASSWORD})
    assert response.status_code == 200
    token = client.cookies.get("openclip_session")
    assert client.get("/api/v1/auth/me").status_code == 200

    client.post("/api/v1/auth/logout")
    # Re-using the old cookie fails because the session was deleted on the server.
    client.cookies.set("openclip_session", token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_wrong_password_and_unknown_email_get_the_same_answer(client: TestClient) -> None:
    register(client, "dave@example.com")
    client.post("/api/v1/auth/logout")
    wrong = client.post(LOGIN, json={"email": "dave@example.com", "password": "nope-nope-nope"})
    unknown = client.post(LOGIN, json={"email": "nobody@example.com", "password": "nope-nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_account_is_locked_after_repeated_failures(client: TestClient) -> None:
    register(client, "erin@example.com")
    client.post("/api/v1/auth/logout")
    for _ in range(5):
        client.post(LOGIN, json={"email": "erin@example.com", "password": "wrong-password-x"})
    locked = client.post(LOGIN, json={"email": "erin@example.com", "password": PASSWORD})
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0


def test_change_password_revokes_other_sessions(app, user_client: TestClient) -> None:  # type: ignore[no-untyped-def]
    laptop = TestClient(app, headers=CSRF_HEADERS)
    assert (
        laptop.post(LOGIN, json={"email": "alice@example.com", "password": PASSWORD}).status_code
        == 200
    )

    bad = user_client.post(
        "/api/v1/auth/password",
        json={"current_password": "wrong", "new_password": "another-good-pass"},
    )
    assert bad.status_code == 422
    ok = user_client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "another-good-pass"},
    )
    assert ok.status_code == 204
    assert user_client.get("/api/v1/auth/me").status_code == 200  # current session kept
    assert laptop.get("/api/v1/auth/me").status_code == 401  # other session revoked


def test_registration_can_be_closed(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path, allow_registration=False))
    with TestClient(app, headers=CSRF_HEADERS) as client:
        assert client.get("/api/v1/auth/status").json()["registration_open"] is False
        # Closed means closed: an empty server no longer hands out a first account either.
        for email in ("first@example.com", "late@example.com"):
            response = client.post(
                "/api/v1/auth/register",
                json={"age_confirmed": True, "email": email, "password": PASSWORD},
            )
            assert response.status_code == 403


def test_protected_endpoints_require_sign_in(client: TestClient) -> None:
    for path in ("/api/v1/projects", "/api/v1/dashboard", "/api/v1/system/status", "/api/v1/jobs"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "not_authenticated"


def test_csrf_header_is_required_for_state_changes(app) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app) as bare:  # no X-Requested-With header
        response = bare.post(
            "/api/v1/auth/register",
            json={"age_confirmed": True, "email": "z@example.com", "password": PASSWORD},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "csrf_failed"


def test_requests_from_unlisted_origins_are_blocked(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"age_confirmed": True, "email": "y@example.com", "password": PASSWORD},
        headers={"Origin": "https://evil.example.com"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


def test_login_rate_limit_per_ip(tmp_path: Path) -> None:
    app = create_app(
        make_settings(tmp_path, rate_limit_enabled=True, login_rate_limit_per_minute=3)
    )
    with TestClient(app, headers=CSRF_HEADERS) as client:
        codes = [
            client.post(
                LOGIN, json={"email": f"u{i}@example.com", "password": "whatever-123"}
            ).status_code
            for i in range(5)
        ]
    assert codes[:3] == [401, 401, 401]
    assert codes[3:] == [429, 429]
