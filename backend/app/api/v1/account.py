"""The signed-in user's own account: profile, retention, and deleting their data."""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select

from app.api.deps import CurrentUser, DbSession, SettingsDep, StorageDep
from app.core.errors import ForbiddenError, UnprocessableError
from app.core.security import verify_password
from app.db.models import AuthSession, Project, User, Worker
from app.schemas.auth import UserOut
from app.services.projects import delete_project_now, request_project_deletion, user_storage_bytes
from app.services.retention import MAX_RETENTION_DAYS, retention_days
from app.services.workers import revoke_worker

router = APIRouter(prefix="/account", tags=["account"])


class AccountOut(BaseModel):
    user: UserOut
    retention_days: int = Field(description="0 keeps source videos until you delete them.")
    storage_used_bytes: int
    projects: int
    can_delete_account: bool


class AccountUpdate(BaseModel):
    """What users may change about themselves. Roles are not among them."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    retention_days: int | None = Field(default=None, ge=0, le=MAX_RETENTION_DAYS)


class DeleteAccountRequest(BaseModel):
    password: str = Field(max_length=128)


class DeleteDataOut(BaseModel):
    deleted_projects: int


def _account_out(db, settings, user: User) -> AccountOut:  # type: ignore[no-untyped-def]
    projects = db.scalars(
        select(Project.id).where(Project.owner_id == user.id, Project.status != "deleting")
    ).all()
    return AccountOut(
        user=UserOut.of(user),
        retention_days=retention_days(user, settings),
        storage_used_bytes=user_storage_bytes(db, user.id),
        projects=len(projects),
        can_delete_account=settings.accounts_enabled,
    )


@router.get("", response_model=AccountOut, summary="Your account and data settings")
def get_account(user: CurrentUser, db: DbSession, settings: SettingsDep) -> AccountOut:
    return _account_out(db, settings, user)


@router.patch("", response_model=AccountOut, summary="Change your name or retention period")
def update_account(
    body: AccountUpdate, user: CurrentUser, db: DbSession, settings: SettingsDep
) -> AccountOut:
    if body.display_name is not None:
        cleaned = " ".join(body.display_name.split())
        if not cleaned:
            raise UnprocessableError("The name cannot be empty.")
        user.display_name = cleaned
    if body.retention_days is not None:
        user.preferences = {**dict(user.preferences or {}), "retention_days": body.retention_days}
    db.commit()
    return _account_out(db, settings, user)


def _delete_all_projects(db, storage, user_id: str) -> int:  # type: ignore[no-untyped-def]
    projects = db.scalars(select(Project).where(Project.owner_id == user_id)).all()
    for project in projects:
        if project.status == "deleting":
            continue
        request_project_deletion(db, storage, project)
    return len(projects)


@router.delete(
    "/projects",
    response_model=DeleteDataOut,
    summary="Delete every project, transcript and clip you own",
)
def delete_all_projects(user: CurrentUser, db: DbSession, storage: StorageDep) -> DeleteDataOut:
    return DeleteDataOut(deleted_projects=_delete_all_projects(db, storage, user.id))


@router.post(
    "/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your account and all of its data (asks for your password)",
)
def delete_account(
    body: DeleteAccountRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    settings: SettingsDep,
) -> Response:
    if not settings.accounts_enabled:
        raise ForbiddenError(
            "Local mode has no account. Use 'Delete all projects' to erase your data.",
            code="local_mode",
        )
    if not verify_password(user.password_hash, body.password):
        raise UnprocessableError("Your password is incorrect.", code="invalid_password")
    database = request.app.state.database
    # Files first (in hybrid mode this leaves clean-up jobs for workers that are online).
    for project in db.scalars(select(Project).where(Project.owner_id == user.id)).all():
        delete_project_now(db, storage, project)
    for worker in db.scalars(
        select(Worker).where(Worker.owner_id == user.id, Worker.status == "active")
    ).all():
        revoke_worker(db, database, storage, worker)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.delete(user)  # cascades to every remaining row that belongs to the user
    db.commit()
    with contextlib.suppress(Exception):  # the rows are gone; a leftover folder is harmless
        storage.delete_tree(storage.user_prefix(user.id))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
    )
    return response
