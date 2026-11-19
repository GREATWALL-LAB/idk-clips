"""The signed-in user's paired workers (hybrid mode): connect, list, rename, disconnect."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, SettingsDep
from app.core.errors import NotFoundError
from app.core.rate_limit import route_limit
from app.db.models import Job, Worker
from app.services.ai import validate_model_name
from app.services.projects import get_owned_project
from app.services.workers import (
    create_pairing_code,
    create_transfer_token,
    get_owned_worker,
    is_online,
    revoke_worker,
)

router = APIRouter(prefix="/workers", tags=["workers"])


def require_hybrid(settings: SettingsDep) -> None:
    if settings.mode != "hybrid":
        raise NotFoundError("Workers are only used when the server runs in hybrid mode.")


Hybrid = Depends(require_hybrid)


class WorkerOut(BaseModel):
    id: str
    name: str
    platform: str
    app_version: str
    bridge_port: int
    online: bool
    last_seen_at: datetime | None
    created_at: datetime
    capabilities: dict[str, Any]
    preferred_model: str | None
    active_jobs: int


class WorkerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    preferred_model: str | None = Field(
        default=None, max_length=120, description="Ollama model to use; empty string resets it."
    )

    @field_validator("preferred_model")
    @classmethod
    def _model(cls, value: str | None) -> str | None:
        return validate_model_name(value) if value else value


class PairingCodeOut(BaseModel):
    code: str = Field(description="Shown once. Valid for a few minutes and for one worker.")
    expires_at: datetime
    server_url: str
    #: Arguments for the worker program: ``scripts/windows/worker.cmd <command>``,
    #: ``scripts/linux/worker.sh <command>`` or ``python -m app.agent <command>``.
    command: str


class TransferTokenRequest(BaseModel):
    scope: Literal["read", "upload"] = "read"
    project_id: uuid.UUID | None = None


class TransferTokenOut(BaseModel):
    token: str
    scope: str
    expires_at: datetime
    worker_id: str
    bridge_port: int


def _worker_out(db, settings, worker: Worker) -> WorkerOut:  # type: ignore[no-untyped-def]
    active = db.scalar(
        select(func.count()).where(
            Job.worker_id == worker.id, Job.status.in_(("queued", "running"))
        )
    )
    return WorkerOut(
        id=worker.id,
        name=worker.name,
        platform=worker.platform,
        app_version=worker.app_version,
        bridge_port=worker.bridge_port,
        online=is_online(worker, settings),
        last_seen_at=worker.last_seen_at,
        created_at=worker.created_at,
        capabilities=dict(worker.capabilities or {}),
        preferred_model=worker.preferred_model,
        active_jobs=int(active or 0),
    )


@router.get("", response_model=list[WorkerOut], dependencies=[Hybrid], summary="Your workers")
def list_workers(user: CurrentUser, db: DbSession, settings: SettingsDep) -> list[WorkerOut]:
    workers = db.scalars(
        select(Worker)
        .where(Worker.owner_id == user.id, Worker.status == "active")
        .order_by(Worker.created_at)
    ).all()
    return [_worker_out(db, settings, worker) for worker in workers]


@router.post(
    "/pairing-codes",
    response_model=PairingCodeOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Hybrid],
    summary="Create a one-time code to connect a new worker",
)
def new_pairing_code(
    request: Request,
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
    _limit: Annotated[None, Depends(route_limit("pair", key="user"))] = None,
) -> PairingCodeOut:
    code, row = create_pairing_code(db, settings, user.id)
    # Behind a proxy the request URL can be internal, so a configured public URL wins.
    server_url = settings.public_api_url or str(request.base_url).rstrip("/")
    return PairingCodeOut(
        code=code,
        expires_at=row.expires_at,
        server_url=server_url,
        command=f"pair --server {server_url} --code {code}",
    )


@router.patch(
    "/{worker_id}", response_model=WorkerOut, dependencies=[Hybrid], summary="Rename a worker"
)
def update_worker(
    worker_id: uuid.UUID,
    body: WorkerUpdate,
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
) -> WorkerOut:
    worker = get_owned_worker(db, user.id, str(worker_id))
    if body.name is not None:
        worker.name = " ".join(body.name.split())[:80]
    if body.preferred_model is not None:
        worker.preferred_model = body.preferred_model or None
    db.commit()
    return _worker_out(db, settings, worker)


@router.delete(
    "/{worker_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Hybrid],
    summary="Disconnect a worker (its credentials stop working immediately)",
)
def delete_worker(
    worker_id: uuid.UUID, request: Request, user: CurrentUser, db: DbSession
) -> Response:
    worker = get_owned_worker(db, user.id, str(worker_id))
    revoke_worker(db, request.app.state.database, request.app.state.storage, worker)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{worker_id}/transfer-tokens",
    response_model=TransferTokenOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Hybrid],
    summary="Short-lived permission for this browser to send or read files on the worker",
)
def new_transfer_token(
    worker_id: uuid.UUID,
    body: TransferTokenRequest,
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
) -> TransferTokenOut:
    worker = get_owned_worker(db, user.id, str(worker_id))
    project = get_owned_project(db, user.id, str(body.project_id)) if body.project_id else None
    token, row = create_transfer_token(
        db, settings, owner_id=user.id, worker=worker, scope=body.scope, project=project
    )
    return TransferTokenOut(
        token=token,
        scope=row.scope,
        expires_at=row.expires_at,
        worker_id=worker.id,
        bridge_port=worker.bridge_port,
    )
