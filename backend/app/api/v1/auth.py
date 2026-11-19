"""Sign-up, sign-in and sessions (HttpOnly cookie)."""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, SettingsDep
from app.core.config import Settings
from app.core.errors import (
    AuthenticationError,
    ForbiddenError,
    RateLimitError,
    ServiceUnavailableError,
    UnprocessableError,
)
from app.core.rate_limit import route_limit
from app.core.security import LoginThrottle
from app.db.models import User
from app.schemas.auth import (
    AuthStatus,
    ChangePasswordRequest,
    CodeSentOut,
    EmailRequest,
    LoginRequest,
    PasswordResetConfirm,
    RegisterOut,
    RegisterRequest,
    UserOut,
    VerifyEmailRequest,
)
from app.services.auth import (
    LOCAL_USER_EMAIL,
    access_problem,
    authenticate,
    change_password,
    confirm_age,
    create_session,
    normalize_email,
    register_user,
    resend_wait_seconds,
    reset_password_with_code,
    revoke_session,
    send_email_code,
    user_count,
    verify_email_code,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
    )


def _require_accounts(settings: Settings) -> None:
    if not settings.accounts_enabled:
        raise ForbiddenError(
            "This copy of IDK Clips runs in local mode: there are no accounts and nothing "
            "to sign in to.",
            code="local_mode",
        )


@router.get("/status", response_model=AuthStatus, summary="Is setup done? Are sign-ups open?")
def auth_status(db: DbSession, settings: SettingsDep) -> AuthStatus:
    if not settings.accounts_enabled:
        return AuthStatus(has_users=True, registration_open=False, mode="local", accounts=False)
    has_users = user_count(db) > 0
    return AuthStatus(
        has_users=has_users,
        registration_open=settings.registration_available,
        email_verification=settings.email_verification_required,
        mode=settings.mode,
        accounts=True,
    )


@router.post(
    "/register",
    response_model=RegisterOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(route_limit("register"))],
    summary="Create an account (18+ confirmation required; then verify the email address)",
)
def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: SettingsDep,
) -> RegisterOut:
    _require_accounts(settings)
    user = register_user(
        db,
        settings,
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        age_confirmed=body.age_confirmed,
    )
    if not settings.email_verification_required:
        token = create_session(db, user, settings, request.headers.get("user-agent"))
        _set_session_cookie(response, token, settings)
        return RegisterOut(
            user=UserOut.of(user),
            verification_required=False,
            code_sent=False,
            resend_after_seconds=0,
            code_ttl_minutes=settings.email_otp_ttl_minutes,
        )
    # No session until the address is verified. If the email could not be sent, the
    # account still exists and the person can ask for a new code on the next screen.
    code_sent = True
    try:
        send_email_code(db, settings, request.app.state.email_codes, user)
    except (RateLimitError, ServiceUnavailableError):
        code_sent = False
    return RegisterOut(
        user=UserOut.of(user),
        verification_required=True,
        code_sent=code_sent,
        resend_after_seconds=resend_wait_seconds(settings, user),
        code_ttl_minutes=settings.email_otp_ttl_minutes,
    )


def _pending_user(db, email: str) -> User | None:  # type: ignore[no-untyped-def]
    address = normalize_email(email)
    if address == LOCAL_USER_EMAIL:
        return None
    return db.scalar(select(User).where(User.email == address, User.is_active.is_(True)))


@router.post(
    "/verify-email",
    response_model=UserOut,
    dependencies=[Depends(route_limit("verify"))],
    summary="Verify the email address with the emailed code, then log in",
)
def verify_email(
    body: VerifyEmailRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: SettingsDep,
) -> UserOut:
    _require_accounts(settings)
    user = _pending_user(db, body.email)
    if user is None or user.age_confirmed_at is None or user.email_verified_at is not None:
        # Same answer as a wrong code, so nobody can probe which addresses exist, and an
        # already verified account can never get a session here without its password.
        raise UnprocessableError("That code is not correct.", code="invalid_code")
    verify_email_code(db, settings, request.app.state.email_codes, user, body.code)
    token = create_session(db, user, settings, request.headers.get("user-agent"))
    _set_session_cookie(response, token, settings)
    return UserOut.of(user)


@router.post(
    "/resend-code",
    response_model=CodeSentOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(route_limit("resend"))],
    summary="Email a new verification code (once a minute at most)",
)
def resend_code(
    body: EmailRequest, request: Request, db: DbSession, settings: SettingsDep
) -> CodeSentOut:
    _require_accounts(settings)
    user = _pending_user(db, body.email)
    if user is not None and user.email_verified_at is None and user.age_confirmed_at:
        send_email_code(db, settings, request.app.state.email_codes, user)
        wait = resend_wait_seconds(settings, user)
    else:
        wait = settings.email_otp_resend_seconds  # same answer for unknown addresses
    return CodeSentOut(resend_after_seconds=wait, code_ttl_minutes=settings.email_otp_ttl_minutes)


@router.post(
    "/login",
    response_model=UserOut,
    dependencies=[Depends(route_limit("login"))],
    summary="Sign in and receive a session cookie",
)
def login(
    body: LoginRequest, request: Request, response: Response, db: DbSession, settings: SettingsDep
) -> UserOut:
    _require_accounts(settings)
    throttle: LoginThrottle = request.app.state.login_throttle
    key = normalize_email(body.email)
    wait = throttle.retry_after(key)
    if wait > 0:
        minutes = max(1, math.ceil(wait / 60))
        raise RateLimitError(
            f"Too many failed sign-in attempts for this account. Try again in {minutes} minute(s).",
            headers={"Retry-After": str(math.ceil(wait))},
        )
    user = authenticate(db, email=body.email, password=body.password)
    if user is None:
        throttle.record_failure(key)
        raise AuthenticationError("Incorrect email or password.", code="invalid_credentials")
    throttle.reset(key)
    # The password is right; the account must also be 18+ confirmed and verified.
    if user.age_confirmed_at is None and body.age_confirmed is True:
        confirm_age(db, user)
    problem = access_problem(settings, user)
    if problem and problem[0] == "age_confirmation_required":
        raise ForbiddenError(problem[1], code=problem[0])
    if problem and problem[0] == "email_not_verified":
        codes = request.app.state.email_codes
        if codes is None:
            raise ServiceUnavailableError(
                "Email verification is not set up on this server yet, so this account "
                "cannot be verified. Please try again later.",
                code="verification_unavailable",
            )
        if resend_wait_seconds(settings, user) == 0:
            send_email_code(db, settings, codes, user)
        raise ForbiddenError(
            "Verify your email address first. We sent a code to your inbox.",
            code="email_not_verified",
            details=[
                {
                    "field": "resend_after_seconds",
                    "message": str(resend_wait_seconds(settings, user)),
                }
            ],
        )
    token = create_session(db, user, settings, request.headers.get("user-agent"))
    _set_session_cookie(response, token, settings)
    return UserOut.of(user)


@router.post(
    "/password-reset/request",
    response_model=CodeSentOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(route_limit("resend"))],
    summary="Email a password reset code (verified accounts only)",
)
def request_password_reset(
    body: EmailRequest, request: Request, db: DbSession, settings: SettingsDep
) -> CodeSentOut:
    _require_accounts(settings)
    codes = request.app.state.email_codes
    if codes is None:
        raise ServiceUnavailableError(
            "Password reset by email is not set up on this server yet.",
            code="verification_unavailable",
        )
    user = _pending_user(db, body.email)
    if user is not None and user.email_verified_at is not None:
        send_email_code(db, settings, codes, user, purpose="reset")
        wait = resend_wait_seconds(settings, user)
    else:
        wait = settings.email_otp_resend_seconds  # same answer for unknown addresses
    return CodeSentOut(resend_after_seconds=wait, code_ttl_minutes=settings.email_otp_ttl_minutes)


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(route_limit("verify"))],
    summary="Set a new password with the emailed code (logs out every session)",
)
def confirm_password_reset(
    body: PasswordResetConfirm, request: Request, db: DbSession, settings: SettingsDep
) -> Response:
    _require_accounts(settings)
    user = _pending_user(db, body.email)
    if user is None:
        raise UnprocessableError("That code is not correct.", code="invalid_code")
    reset_password_with_code(
        db, settings, request.app.state.email_codes, user, body.code, body.new_password
    )
    request.app.state.login_throttle.reset(normalize_email(body.email))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Sign out")
def logout(request: Request, db: DbSession, settings: SettingsDep) -> Response:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        revoke_session(db, token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookie(response, settings)
    return response


@router.get("/me", response_model=UserOut, summary="The signed-in user")
def me(user: CurrentUser) -> UserOut:
    return UserOut.of(user)


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change password (signs out your other sessions)",
)
def update_password(
    body: ChangePasswordRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
) -> Response:
    _require_accounts(settings)
    change_password(
        db,
        user,
        current_password=body.current_password,
        new_password=body.new_password,
        keep_token=request.cookies.get(settings.session_cookie_name),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
