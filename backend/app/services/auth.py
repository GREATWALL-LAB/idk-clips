"""Accounts and sessions."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    RateLimitError,
    ServiceUnavailableError,
    UnprocessableError,
)
from app.core.security import (
    hash_password,
    hash_token,
    new_session_token,
    password_needs_rehash,
    password_problem,
    verify_password,
)
from app.db.base import utcnow
from app.db.models import AuthSession, User

SESSION_TOUCH_INTERVAL = timedelta(minutes=5)


LOCAL_USER_EMAIL = "local-user@openclip.invalid"


def ensure_local_user(db: Session) -> User:
    """The single user of local mode.

    An installation that was used with accounts before keeps working: its oldest active
    account becomes the local user, so earlier projects stay visible. Otherwise an
    implicit user is created that has no usable password and cannot log in.
    """
    existing = db.scalar(
        select(User)
        .where(User.is_active.is_(True), User.email != LOCAL_USER_EMAIL)
        .order_by(User.created_at)
        .limit(1)
    )
    if existing is not None:
        return existing
    user = db.scalar(select(User).where(User.email == LOCAL_USER_EMAIL))
    if user is None:
        user = User(
            email=LOCAL_USER_EMAIL,
            display_name="This computer",
            password_hash=hash_password(new_session_token()),
        )
        db.add(user)
        db.commit()
    return user


def normalize_email(email: str) -> str:
    return email.strip().lower()


def user_count(db: Session) -> int:
    """Number of real accounts (the implicit local-mode user is not an account)."""
    return int(
        db.scalar(select(func.count()).select_from(User).where(User.email != LOCAL_USER_EMAIL)) or 0
    )


AGE_REQUIRED_MESSAGE = "You must be 18 or older to use IDK Clips."


def register_user(
    db: Session,
    settings: Settings,
    *,
    email: str,
    password: str,
    display_name: str,
    age_confirmed: bool = False,
) -> User:
    """Public sign-up. IDK Clips has no roles: every account is an ordinary user who can
    reach only their own projects, clips, workers and data.

    The person must have confirmed being 18 or older (never assumed). When email
    verification is on, the account cannot be used until the address is verified.
    """
    if not settings.allow_registration:
        raise ForbiddenError("This server is not accepting new accounts.")
    if settings.email_verification_required and not settings.email_verification_ready:
        raise ServiceUnavailableError(
            "Email verification is not set up on this server yet, so new accounts cannot "
            "be created. Please try again later.",
            code="verification_unavailable",
        )
    if age_confirmed is not True:
        raise ForbiddenError(AGE_REQUIRED_MESSAGE, code="age_required")
    email = normalize_email(email)
    if email == LOCAL_USER_EMAIL or email.endswith(".invalid"):
        raise UnprocessableError("Use a real email address.")
    problem = password_problem(password, email)
    if problem:
        raise UnprocessableError(problem, code="weak_password")
    if db.scalar(select(User.id).where(User.email == email)):
        raise ConflictError("An account with this email address already exists.")
    user = User(
        email=email,
        display_name=display_name.strip() or email.split("@", 1)[0],
        password_hash=hash_password(password),
        age_confirmed_at=utcnow(),
        email_verified_at=None if settings.email_verification_required else utcnow(),
    )
    db.add(user)
    db.commit()
    return user


# ---------------------------------------------------------------- access rules
def access_problem(settings: Settings, user: User) -> tuple[str, str] | None:
    """Why this account may not use IDK Clips yet, or None. Checked on every request."""
    if not settings.accounts_enabled:
        return None
    if user.age_confirmed_at is None:
        return (
            "age_confirmation_required",
            "Please confirm that you are 18 or older before using IDK Clips.",
        )
    if settings.email_verification_required and user.email_verified_at is None:
        return ("email_not_verified", "Verify your email address to continue.")
    return None


def confirm_age(db: Session, user: User) -> None:
    if user.age_confirmed_at is None:
        user.age_confirmed_at = utcnow()
        db.commit()


# ---------------------------------------------------------------- email codes
def _aware(value):  # type: ignore[no-untyped-def]
    return value if value is None or value.tzinfo else value.replace(tzinfo=utcnow().tzinfo)


def resend_wait_seconds(settings: Settings, user: User) -> int:
    sent = _aware(user.email_code_sent_at)
    if sent is None:
        return 0
    elapsed = (utcnow() - sent).total_seconds()
    return max(0, int(settings.email_otp_resend_seconds - elapsed + 0.999))


def send_email_code(
    db: Session, settings: Settings, codes, user: User, purpose: str = "verify"
) -> None:  # type: ignore[no-untyped-def]
    """Email a new one-time code (at most one per ``email_otp_resend_seconds``).

    ``verify`` codes are for unverified accounts; ``reset`` codes (password reset) only for
    verified ones. One code is active per account at a time, so the same expiry, cooldown
    and attempt counters protect both.
    """
    if (purpose == "verify") != (user.email_verified_at is None):
        return
    if codes is None:
        raise ServiceUnavailableError(
            "Email verification is not set up on this server yet.",
            code="verification_unavailable",
        )
    wait = resend_wait_seconds(settings, user)
    if wait > 0:
        raise RateLimitError(
            f"A code was sent recently. You can ask for a new one in {wait} seconds.",
            code="resend_cooldown",
            headers={"Retry-After": str(wait)},
        )
    codes.send(user.email, purpose)
    user.email_code_sent_at = utcnow()
    user.email_code_failures = 0
    db.commit()


def verify_email_code(db: Session, settings: Settings, codes, user: User, code: str) -> None:  # type: ignore[no-untyped-def]
    """Raises unless ``code`` is a valid, unexpired verification code for ``user``.

    Never returns early: callers log the person in afterwards, so an already verified
    account must not get a session from this path (that would skip the password).
    """
    if user.email_verified_at is not None:
        raise UnprocessableError("That code is not correct.", code="invalid_code")
    _check_code(db, settings, codes, user, code, "verify")
    user.email_verified_at = utcnow()
    user.email_code_sent_at = None
    user.email_code_failures = 0
    db.commit()


def reset_password_with_code(  # type: ignore[no-untyped-def]
    db: Session, settings: Settings, codes, user: User, code: str, new_password: str
) -> None:
    """Set a new password after the emailed reset code was confirmed; ends every session."""
    problem = password_problem(new_password, user.email)
    if problem:
        raise UnprocessableError(problem, code="weak_password")
    if user.email_verified_at is None:
        raise UnprocessableError("That code is not correct.", code="invalid_code")
    _check_code(db, settings, codes, user, code, "reset")
    user.password_hash = hash_password(new_password)
    user.email_code_sent_at = None
    user.email_code_failures = 0
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.commit()


def _check_code(
    db: Session, settings: Settings, codes, user: User, code: str, purpose: str
) -> None:  # type: ignore[no-untyped-def]
    if codes is None:
        raise ServiceUnavailableError(
            "Email verification is not set up on this server yet.",
            code="verification_unavailable",
        )
    sent = _aware(user.email_code_sent_at)
    if sent is None:
        raise UnprocessableError("Ask for a code first.", code="code_not_sent")
    if (utcnow() - sent) > timedelta(minutes=settings.email_otp_ttl_minutes):
        raise UnprocessableError("This code has expired. Ask for a new one.", code="code_expired")
    if user.email_code_failures >= settings.email_otp_max_attempts:
        raise RateLimitError("Too many wrong codes. Ask for a new code.", code="too_many_attempts")
    if not codes.verify(user.email, code, purpose):
        user.email_code_failures += 1
        db.commit()
        left = settings.email_otp_max_attempts - user.email_code_failures
        if left <= 0:
            raise RateLimitError(
                "Too many wrong codes. Ask for a new code.", code="too_many_attempts"
            )
        raise UnprocessableError(
            f"That code is not correct. {left} attempt(s) left.", code="invalid_code"
        )


def authenticate(db: Session, *, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    # verify_password always runs (against a dummy hash for unknown emails).
    valid = verify_password(user.password_hash if user else None, password)
    if not user or not valid or not user.is_active or user.email == LOCAL_USER_EMAIL:
        return None
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = utcnow()
    db.commit()
    return user


def create_session(db: Session, user: User, settings: Settings, user_agent: str | None) -> str:
    token = new_session_token()
    db.add(
        AuthSession(
            token_hash=hash_token(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(days=settings.session_days),
            user_agent=(user_agent or "")[:200] or None,
        )
    )
    # Housekeeping: drop this user's expired sessions.
    db.execute(
        delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.expires_at < utcnow())
    )
    db.commit()
    return token


def user_for_token(db: Session, token: str) -> User | None:
    if not token or len(token) > 200:
        return None
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if session is None:
        return None
    now = utcnow()
    if session.expires_at <= now:
        db.delete(session)
        db.commit()
        return None
    if not session.user.is_active:
        return None
    if now - session.last_seen_at > SESSION_TOUCH_INTERVAL:
        session.last_seen_at = now
        db.commit()
    return session.user


def revoke_session(db: Session, token: str) -> None:
    db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    db.commit()


def change_password(
    db: Session, user: User, *, current_password: str, new_password: str, keep_token: str | None
) -> None:
    if not verify_password(user.password_hash, current_password):
        raise UnprocessableError("Your current password is incorrect.", code="invalid_password")
    problem = password_problem(new_password, user.email)
    if problem:
        raise UnprocessableError(problem, code="weak_password")
    user.password_hash = hash_password(new_password)
    # Sign out every other session after a password change.
    keep_hash = hash_token(keep_token) if keep_token else ""
    db.execute(
        delete(AuthSession).where(
            AuthSession.user_id == user.id, AuthSession.token_hash != keep_hash
        )
    )
    db.commit()
