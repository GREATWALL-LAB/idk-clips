"""Shared FastAPI dependencies: settings, database sessions, storage and the signed-in user."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AuthenticationError, ForbiddenError
from app.db.models import User
from app.services.auth import access_problem, ensure_local_user, user_for_token
from app.services.storage import LocalStorage


def get_app_settings(request: Request) -> Settings:
    """Settings bound to the running app instance (tests can inject their own)."""
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.database.session()
    try:
        yield session
    finally:
        session.close()


def get_storage(request: Request) -> LocalStorage:
    return request.app.state.storage


def get_runner(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.job_runner


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DbSession = Annotated[Session, Depends(get_db)]
StorageDep = Annotated[LocalStorage, Depends(get_storage)]
RunnerDep = Annotated[object, Depends(get_runner)]


def get_current_user(request: Request, db: DbSession) -> User:
    settings: Settings = request.app.state.settings
    if not settings.accounts_enabled:
        # Local mode: one implicit user, no sign-in. Requests are restricted to this
        # computer by LocalOnlyMiddleware, so there is nobody else to authenticate.
        user = ensure_local_user(db)
        request.state.user_id = user.id
        return user
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise AuthenticationError()
    user = user_for_token(db, token)
    if user is None:
        raise AuthenticationError("Your session has expired. Please log in again.")
    # Re-checked on every request, not only at login: 18+ confirmation and a verified
    # email address are required to use any protected feature.
    problem = access_problem(request.app.state.settings, user)
    if problem:
        raise ForbiddenError(problem[1], code=problem[0])
    db.commit()  # end the read transaction; the user object stays usable
    request.state.user_id = user.id
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_job_capacity(user: CurrentUser, request: Request) -> None:
    """Fair use: refuse new work while a user already has many jobs or used their quota."""
    from app.services.jobs import check_job_capacity

    settings: Settings = request.app.state.settings
    with request.app.state.database.session_scope() as db:
        check_job_capacity(db, settings, user.id)


JobCapacity = Annotated[None, Depends(require_job_capacity)]
