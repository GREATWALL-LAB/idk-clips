"""18+ confirmation and email verification (one-time codes through Supabase Auth).

The account rules are tested against the real API with a stand-in for Supabase
(``FakeCodes``) that records sent codes. ``SupabaseEmailCodes`` itself is tested against
recorded HTTP exchanges in the format of Supabase's Auth API. Real email delivery needs a
Supabase project and is checked separately on the deployed site.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.core.errors import RateLimitError, ServiceUnavailableError
from app.db.models import User
from app.main import create_app
from app.services import auth as auth_service
from app.services.email_codes import SupabaseEmailCodes
from tests.conftest import CSRF_HEADERS, PASSWORD, make_settings

REGISTER = "/api/v1/auth/register"
VERIFY = "/api/v1/auth/verify-email"
RESEND = "/api/v1/auth/resend-code"
LOGIN = "/api/v1/auth/login"
EMAIL = "new@example.com"


class FakeCodes:
    """Stands in for Supabase: remembers the last code per address."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.purposes: list[str] = []
        self.valid = "123456"

    def send(self, email: str, purpose: str = "verify") -> None:
        self.sent.append(email)
        self.purposes.append(purpose)

    def verify(self, email: str, code: str, purpose: str = "verify") -> bool:
        # Like Supabase: a code only works for the kind of email it was sent in.
        return email in self.sent and self.purposes[-1] == purpose and code == self.valid


@pytest.fixture
def settings(tmp_path: Path):  # type: ignore[no-untyped-def]
    return make_settings(
        tmp_path,
        email_verification="supabase",
        supabase_url="https://example-project.supabase.co",
        supabase_anon_key="public-anon-key-for-tests",
    )


@pytest.fixture
def codes(app) -> FakeCodes:  # type: ignore[no-untyped-def]
    fake = FakeCodes()
    app.state.email_codes = fake
    return fake


def sign_up(client: TestClient, **overrides: object):  # type: ignore[no-untyped-def]
    body = {"email": EMAIL, "password": PASSWORD, "display_name": "New", "age_confirmed": True}
    body.update(overrides)
    return client.post(REGISTER, json=body)


def user_row(app, email: str = EMAIL) -> User:  # type: ignore[no-untyped-def]
    with app.state.database.session_scope() as db:
        user = db.scalar(sa.select(User).where(User.email == email))
        db.expunge(user)
        return user


def shift_code_age(app, seconds: float) -> None:  # type: ignore[no-untyped-def]
    """Pretend the last code was sent ``seconds`` earlier."""
    with app.state.database.session_scope() as db:
        user = db.scalar(sa.select(User).where(User.email == EMAIL))
        user.email_code_sent_at = user.email_code_sent_at - timedelta(seconds=seconds)


# ------------------------------------------------------------ age gate
@pytest.mark.parametrize("answer", [None, False, "yes", 1])
def test_sign_up_requires_an_explicit_yes_to_the_age_question(
    app, client: TestClient, codes: FakeCodes, answer: object
) -> None:  # type: ignore[no-untyped-def]
    body = {"email": EMAIL, "password": PASSWORD}
    if answer is not None:
        body["age_confirmed"] = answer
    response = client.post(REGISTER, json=body)
    assert response.status_code in {403, 422}
    if response.status_code == 403:
        assert response.json()["error"]["code"] == "age_required"
    with app.state.database.session_scope() as db:
        assert db.scalar(sa.select(User).where(User.email == EMAIL)) is None
    assert codes.sent == []


def test_the_age_confirmation_is_stored_with_a_timestamp(
    app, client: TestClient, codes: FakeCodes
) -> None:  # type: ignore[no-untyped-def]
    assert sign_up(client).status_code == 201
    assert user_row(app).age_confirmed_at is not None


# ---------------------------------------------------------- email codes
def test_sign_up_sends_a_code_and_gives_no_session_yet(
    app, client: TestClient, codes: FakeCodes
) -> None:  # type: ignore[no-untyped-def]
    response = sign_up(client)
    assert response.status_code == 201
    body = response.json()
    assert body["verification_required"] is True and body["code_sent"] is True
    assert body["user"]["email_verified"] is False
    assert 55 <= body["resend_after_seconds"] <= 60 and body["code_ttl_minutes"] == 10
    assert "set-cookie" not in response.headers
    assert codes.sent == [EMAIL]
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/projects").status_code == 401


def test_the_right_code_verifies_and_logs_in(app, client: TestClient, codes: FakeCodes) -> None:  # type: ignore[no-untyped-def]
    sign_up(client)
    response = client.post(VERIFY, json={"email": EMAIL, "code": "123456"})
    assert response.status_code == 200, response.text
    assert response.json()["email_verified"] is True
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.get("/api/v1/auth/me").json()["email_verified"] is True
    assert client.get("/api/v1/projects").status_code == 200
    assert user_row(app).email_verified_at is not None


def test_wrong_codes_are_limited(app, client: TestClient, codes: FakeCodes) -> None:  # type: ignore[no-untyped-def]
    sign_up(client)
    for left in (4, 3, 2, 1):
        wrong = client.post(VERIFY, json={"email": EMAIL, "code": "000000"})
        assert wrong.status_code == 422
        assert wrong.json()["error"]["code"] == "invalid_code"
        assert f"{left} attempt" in wrong.json()["error"]["message"]
    fifth = client.post(VERIFY, json={"email": EMAIL, "code": "000000"})
    assert fifth.status_code == 429 and fifth.json()["error"]["code"] == "too_many_attempts"
    # Even the right code is refused now; a new code must be requested.
    right = client.post(VERIFY, json={"email": EMAIL, "code": "123456"})
    assert right.status_code == 429
    shift_code_age(app, 61)
    assert client.post(RESEND, json={"email": EMAIL}).status_code == 202
    assert client.post(VERIFY, json={"email": EMAIL, "code": "123456"}).status_code == 200


def test_codes_expire(app, client: TestClient, codes: FakeCodes) -> None:  # type: ignore[no-untyped-def]
    sign_up(client)
    shift_code_age(app, 10 * 60 + 1)
    expired = client.post(VERIFY, json={"email": EMAIL, "code": "123456"})
    assert expired.status_code == 422 and expired.json()["error"]["code"] == "code_expired"
    assert user_row(app).email_verified_at is None


def test_resend_has_a_60_second_cooldown(app, client: TestClient, codes: FakeCodes) -> None:  # type: ignore[no-untyped-def]
    sign_up(client)
    early = client.post(RESEND, json={"email": EMAIL})
    assert early.status_code == 429
    assert early.json()["error"]["code"] == "resend_cooldown"
    assert 1 <= int(early.headers["Retry-After"]) <= 60
    assert codes.sent == [EMAIL]
    shift_code_age(app, 60)
    later = client.post(RESEND, json={"email": EMAIL})
    assert later.status_code == 202 and later.json()["resend_after_seconds"] >= 55
    assert codes.sent == [EMAIL, EMAIL]


def test_resend_and_verify_do_not_reveal_unknown_addresses(
    client: TestClient, codes: FakeCodes
) -> None:
    unknown = client.post(RESEND, json={"email": "nobody@example.com"})
    assert unknown.status_code == 202
    guess = client.post(VERIFY, json={"email": "nobody@example.com", "code": "123456"})
    assert guess.status_code == 422 and guess.json()["error"]["code"] == "invalid_code"
    assert codes.sent == []


def test_codes_must_look_like_codes(client: TestClient, codes: FakeCodes) -> None:
    sign_up(client)
    for code in ("12345", "abcdef", "1234567890123", "' OR 1=1 --"):
        assert client.post(VERIFY, json={"email": EMAIL, "code": code}).status_code == 422


# ------------------------------------------------------------- logging in
def test_unverified_accounts_cannot_log_in(app, client: TestClient, codes: FakeCodes) -> None:  # type: ignore[no-untyped-def]
    sign_up(client)
    shift_code_age(app, 61)
    login = client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})
    assert login.status_code == 403
    assert login.json()["error"]["code"] == "email_not_verified"
    assert "set-cookie" not in login.headers
    assert codes.sent == [EMAIL, EMAIL]  # a fresh code was sent for the login
    # A wrong password reveals nothing about verification.
    wrong = client.post(LOGIN, json={"email": EMAIL, "password": "not-the-password"})
    assert wrong.status_code == 401
    # After verifying, logging in works.
    assert client.post(VERIFY, json={"email": EMAIL, "code": "123456"}).status_code == 200
    client.post("/api/v1/auth/logout")
    assert client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD}).status_code == 200


def test_older_accounts_confirm_their_age_when_logging_in(
    app, client: TestClient, codes: FakeCodes
) -> None:  # type: ignore[no-untyped-def]
    sign_up(client)
    assert client.post(VERIFY, json={"email": EMAIL, "code": "123456"}).status_code == 200
    client.post("/api/v1/auth/logout")
    with app.state.database.session_scope() as db:  # as after the upgrade to migration 0006
        db.scalar(sa.select(User).where(User.email == EMAIL)).age_confirmed_at = None
    refused = client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "age_confirmation_required"
    confirmed = client.post(
        LOGIN, json={"email": EMAIL, "password": PASSWORD, "age_confirmed": True}
    )
    assert confirmed.status_code == 200
    assert user_row(app).age_confirmed_at is not None


# ---------------------------------------------------- protected endpoints
def test_protected_endpoints_recheck_the_account_on_every_request(
    app, client: TestClient, codes: FakeCodes
) -> None:  # type: ignore[no-untyped-def]
    sign_up(client)
    client.post(VERIFY, json={"email": EMAIL, "code": "123456"})
    assert client.get("/api/v1/projects").status_code == 200
    for column, code in (
        ("email_verified_at", "email_not_verified"),
        ("age_confirmed_at", "age_confirmation_required"),
    ):
        with app.state.database.session_scope() as db:
            user = db.scalar(sa.select(User).where(User.email == EMAIL))
            saved = getattr(user, column)
            setattr(user, column, None)
        for path in ("/api/v1/projects", "/api/v1/dashboard", "/api/v1/account", "/api/v1/auth/me"):
            response = client.get(path)
            assert response.status_code == 403, path
            assert response.json()["error"]["code"] == code
        assert client.post("/api/v1/projects", json={"name": "x"}).status_code == 403
        with app.state.database.session_scope() as db:
            setattr(db.scalar(sa.select(User).where(User.email == EMAIL)), column, saved)
    assert client.get("/api/v1/projects").status_code == 200


def test_workers_of_unverified_accounts_are_refused(tmp_path: Path) -> None:
    from tests.hybrid import FakeWorker

    settings = make_settings(
        tmp_path,
        mode="hybrid",
        email_verification="supabase",
        supabase_url="https://example-project.supabase.co",
        supabase_anon_key="public-anon-key-for-tests",
    )
    app = create_app(settings)
    with TestClient(app, headers=CSRF_HEADERS) as client:
        fake = FakeCodes()
        app.state.email_codes = fake
        sign_up(client)
        client.post(VERIFY, json={"email": EMAIL, "code": "123456"})
        worker = FakeWorker(app, client)
        assert worker.post("/heartbeat", {}).status_code in {200, 204}
        with app.state.database.session_scope() as db:
            db.scalar(sa.select(User).where(User.email == EMAIL)).email_verified_at = None
        refused = worker.post("/heartbeat", {})
        assert refused.status_code == 403
        assert refused.json()["error"]["code"] == "owner_not_verified"


# --------------------------------------------------------- configuration
def test_without_supabase_new_accounts_are_refused_honestly(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path, email_verification="supabase"))
    with TestClient(app, headers=CSRF_HEADERS) as client:
        status = client.get("/api/v1/auth/status").json()
        assert status["registration_open"] is False and status["email_verification"] is True
        response = sign_up(client)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "verification_unavailable"


def test_production_cannot_switch_verification_off(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="verify email"):
        make_settings(tmp_path, environment="production", email_verification="off")


def test_supabase_url_must_be_https(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        make_settings(tmp_path, supabase_url="http://example.supabase.co")
    # Supabase's local development stack on this computer is the only http exception,
    assert make_settings(tmp_path, supabase_url="http://127.0.0.1:54321").supabase_url
    # and never in production.
    with pytest.raises(ValueError):
        make_settings(tmp_path, environment="production", supabase_url="http://127.0.0.1:54321")


def test_the_anon_key_is_masked_in_logs(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, supabase_anon_key="anon-key-value-123")
    assert "anon-key-value-123" in settings.secret_values()


# ------------------------------------------- the Supabase Auth API client
def recorder(responses: list[httpx.Response]):  # type: ignore[no-untyped-def]
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responses.pop(0)

    return seen, httpx.MockTransport(handler)


def test_supabase_send_request_format() -> None:
    seen, transport = recorder([httpx.Response(200, json={})])
    SupabaseEmailCodes("https://abc.supabase.co/", "anon", transport).send(EMAIL)
    request = seen[0]
    assert str(request.url) == "https://abc.supabase.co/auth/v1/otp"
    assert request.headers["apikey"] == "anon"
    assert json.loads(request.content) == {"email": EMAIL, "create_user": True}


def test_supabase_verify_accepts_only_a_session_for_the_same_address() -> None:
    session = {"access_token": "tok", "user": {"email": EMAIL}}
    seen, transport = recorder([httpx.Response(200, json=session), httpx.Response(204)])
    assert SupabaseEmailCodes("https://abc.supabase.co", "anon", transport).verify(EMAIL, "123456")
    assert json.loads(seen[0].content) == {"type": "email", "email": EMAIL, "token": "123456"}
    assert seen[1].url.path == "/auth/v1/logout"  # the Supabase session is revoked
    other = {"access_token": "tok", "user": {"email": "someone-else@example.com"}}
    _, transport = recorder([httpx.Response(200, json=other)])
    assert not SupabaseEmailCodes("https://abc.supabase.co", "anon", transport).verify(EMAIL, "1")


@pytest.mark.parametrize("status", [400, 401, 403, 422])
def test_supabase_wrong_or_expired_codes(status: int) -> None:
    body = {"code": status, "error_code": "otp_expired", "msg": "Token has expired or is invalid"}
    _, transport = recorder([httpx.Response(status, json=body)])
    assert (
        SupabaseEmailCodes("https://abc.supabase.co", "anon", transport).verify(EMAIL, "1") is False
    )


def test_supabase_errors_become_clear_messages() -> None:
    _, transport = recorder([httpx.Response(429, headers={"Retry-After": "42"})])
    with pytest.raises(RateLimitError) as limited:
        SupabaseEmailCodes("https://abc.supabase.co", "anon", transport).send(EMAIL)
    assert limited.value.headers == {"Retry-After": "42"}
    _, transport = recorder([httpx.Response(500, text="boom")])
    with pytest.raises(ServiceUnavailableError):
        SupabaseEmailCodes("https://abc.supabase.co", "anon", transport).send(EMAIL)

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(ServiceUnavailableError):
        SupabaseEmailCodes(
            "https://abc.supabase.co", "anon", httpx.MockTransport(unreachable)
        ).verify(EMAIL, "123456")


def test_services_module_uses_timezone_aware_times() -> None:
    assert auth_service.utcnow().tzinfo is not None


# ----------------------------------------------- no login without a password
def test_a_verified_account_cannot_be_entered_through_the_code_endpoint(
    app, client: TestClient, codes: FakeCodes
) -> None:  # type: ignore[no-untyped-def]
    """Regression: verify-email used to log in already verified accounts with any code."""
    sign_up(client)
    assert client.post(VERIFY, json={"email": EMAIL, "code": "123456"}).status_code == 200
    attacker = TestClient(app, headers=CSRF_HEADERS)
    for code in ("000000", "123456", "999999"):
        response = attacker.post(VERIFY, json={"email": EMAIL, "code": code})
        assert response.status_code == 422, code
        assert response.json()["error"]["code"] == "invalid_code"
        assert "set-cookie" not in response.headers
    assert attacker.get("/api/v1/auth/me").status_code == 401


# ------------------------------------------------------------ password reset
RESET = "/api/v1/auth/password-reset/request"
CONFIRM = "/api/v1/auth/password-reset/confirm"
NEW_PASSWORD = "a-brand-new-password-42"


def verified_account(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    sign_up(client)
    assert client.post(VERIFY, json={"email": EMAIL, "code": "123456"}).status_code == 200
    client.post("/api/v1/auth/logout")


def test_password_reset_with_an_emailed_code(app, client: TestClient, codes: FakeCodes) -> None:  # type: ignore[no-untyped-def]
    verified_account(app, client)
    phone = TestClient(app, headers=CSRF_HEADERS)  # another device, still logged in
    assert phone.post(LOGIN, json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    asked = client.post(RESET, json={"email": EMAIL})
    assert asked.status_code == 202 and codes.purposes[-1] == "reset"
    # A verification-type code is not accepted for a reset, and vice versa.
    codes.purposes[-1] = "verify"
    wrong_kind = client.post(
        CONFIRM, json={"email": EMAIL, "code": "123456", "new_password": NEW_PASSWORD}
    )
    assert wrong_kind.status_code == 422
    codes.purposes[-1] = "reset"
    done = client.post(
        CONFIRM, json={"email": EMAIL, "code": "123456", "new_password": NEW_PASSWORD}
    )
    assert done.status_code == 204, done.text
    assert client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD}).status_code == 401
    assert client.post(LOGIN, json={"email": EMAIL, "password": NEW_PASSWORD}).status_code == 200
    assert phone.get("/api/v1/auth/me").status_code == 401  # every old session ended


def test_password_reset_rules(app, client: TestClient, codes: FakeCodes) -> None:  # type: ignore[no-untyped-def]
    verified_account(app, client)
    client.post(RESET, json={"email": EMAIL})
    early = client.post(RESET, json={"email": EMAIL})
    assert early.status_code == 429 and early.json()["error"]["code"] == "resend_cooldown"
    weak = client.post(CONFIRM, json={"email": EMAIL, "code": "123456", "new_password": "short"})
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "weak_password"
    for _ in range(4):
        bad = client.post(
            CONFIRM, json={"email": EMAIL, "code": "000000", "new_password": NEW_PASSWORD}
        )
        assert bad.status_code == 422
    locked = client.post(
        CONFIRM, json={"email": EMAIL, "code": "000000", "new_password": NEW_PASSWORD}
    )
    assert locked.status_code == 429 and locked.json()["error"]["code"] == "too_many_attempts"
    shift_code_age(app, 10 * 60 + 1)
    expired = client.post(
        CONFIRM, json={"email": EMAIL, "code": "123456", "new_password": NEW_PASSWORD}
    )
    assert expired.status_code in {422, 429}
    assert client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD}).status_code == 200


def test_password_reset_reveals_nothing_about_addresses(
    client: TestClient, codes: FakeCodes
) -> None:
    sign_up(client)  # exists but not verified: verification, not reset, is the way in
    for email in (EMAIL, "nobody@example.com"):
        assert client.post(RESET, json={"email": email}).status_code == 202
        guess = client.post(
            CONFIRM, json={"email": email, "code": "123456", "new_password": NEW_PASSWORD}
        )
        assert guess.status_code == 422
    assert codes.purposes == ["verify"]  # only the sign-up code was ever sent


def test_supabase_reset_uses_the_recovery_email(tmp_path: Path) -> None:
    seen, transport = recorder(
        [
            httpx.Response(200, json={}),
            httpx.Response(200, json={"access_token": "t", "user": {"email": EMAIL}}),
            httpx.Response(204),
        ]
    )
    client = SupabaseEmailCodes("https://abc.supabase.co", "anon", transport)
    client.send(EMAIL, "reset")
    assert client.verify(EMAIL, "123456", "reset")
    assert seen[0].url.path == "/auth/v1/recover" and json.loads(seen[0].content) == {
        "email": EMAIL
    }
    assert json.loads(seen[1].content)["type"] == "recovery"


def test_publishable_keys_are_sent_only_as_apikey() -> None:
    seen, transport = recorder([httpx.Response(200, json={}), httpx.Response(200, json={})])
    SupabaseEmailCodes("https://abc.supabase.co", "sb_publishable_example", transport).send(EMAIL)
    assert seen[0].headers["apikey"] == "sb_publishable_example"
    assert "authorization" not in seen[0].headers
    legacy = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.signature"
    SupabaseEmailCodes("https://abc.supabase.co", legacy, transport).send(EMAIL)
    assert seen[1].headers["authorization"] == f"Bearer {legacy}"
