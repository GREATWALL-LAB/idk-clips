"""Endpoints called by a paired worker (hybrid mode). Machine-to-machine, bearer token.

Everything a worker can do is listed here: pair once, announce itself, claim its
owner's jobs, report progress and results, check a transfer token, and register a
video the owner sent it directly. There is no endpoint that runs commands, and the
server never connects *to* a worker; the worker only makes outbound HTTPS requests.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app import __version__
from app.api.deps import DbSession, SettingsDep
from app.core.errors import (
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnprocessableError,
)
from app.core.rate_limit import route_limit
from app.db.models import Job, Project, User, Worker
from app.jobs.events import EventError, MediaReadyIn, apply_event, register_media
from app.jobs.lifecycle import finish_job
from app.services.auth import access_problem
from app.services.files import display_filename, video_extension
from app.services.workers import (
    claim_next_job,
    pair_worker,
    revoke_worker,
    running_job_for_worker,
    touch_worker,
    verify_transfer_token,
    worker_for_token,
)

router = APIRouter(prefix="/agent", tags=["worker agent"])


# --------------------------------------------------------------------- auth
def require_hybrid(settings: SettingsDep) -> None:
    if settings.mode != "hybrid":
        raise NotFoundError("Workers are only used when the server runs in hybrid mode.")


def get_current_worker(request: Request, db: DbSession) -> Worker:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    worker = worker_for_token(db, token.strip()) if scheme.lower() == "bearer" else None
    if worker is None:
        raise AuthenticationError(
            "This worker is not connected to an account (it may have been removed). "
            "Pair it again from the dashboard.",
            code="worker_not_authorized",
        )
    owner = db.get(User, worker.owner_id)
    problem = access_problem(request.app.state.settings, owner) if owner else ("gone", "")
    if problem:
        raise ForbiddenError(
            "The account this worker belongs to must confirm its age and verify its email "
            "address before the worker can be used.",
            code="owner_not_verified",
        )
    touch_worker(db, worker)
    request.state.user_id = worker.owner_id
    return worker


CurrentWorker = Annotated[Worker, Depends(get_current_worker)]
Hybrid = Depends(require_hybrid)


# ------------------------------------------------------------------ schemas
class Capabilities(BaseModel):
    """Self-reported by the worker and shown in the dashboard. Never trusted for decisions."""

    components: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    ollama_models: list[str] = Field(default_factory=list, max_length=100)
    ai_provider: str | None = Field(default=None, max_length=20)
    gpu: str | None = Field(default=None, max_length=120)


class PairRequest(BaseModel):
    code: str = Field(min_length=4, max_length=32)
    name: str = Field(default="", max_length=80)
    platform: str = Field(default="", max_length=40)
    app_version: str = Field(default="", max_length=20)
    bridge_port: int = Field(default=8787, ge=1024, le=65535)
    capabilities: Capabilities = Field(default_factory=Capabilities)


class ServerInfo(BaseModel):
    server_version: str
    owner_id: str
    owner_name: str
    allowed_origins: list[str]
    long_poll_seconds: int
    lease_seconds: int


class PairResponse(ServerInfo):
    worker_id: str
    worker_name: str
    token: str = Field(description="Shown once. Store it only on the worker.")


class HeartbeatRequest(BaseModel):
    bridge_port: int = Field(default=8787, ge=1024, le=65535)
    app_version: str = Field(default="", max_length=20)
    capabilities: Capabilities = Field(default_factory=Capabilities)


class HeartbeatResponse(ServerInfo):
    worker_id: str
    worker_name: str
    preferred_model: str | None


class ClaimRequest(BaseModel):
    wait_seconds: int = Field(default=0, ge=0, le=55)


class ClaimResponse(BaseModel):
    job: dict[str, Any] | None = Field(description="A job spec, or null when nothing is waiting.")


class ProgressRequest(BaseModel):
    progress: float = Field(ge=0, le=1)
    stage: str | None = Field(default=None, max_length=200)


class ProgressResponse(BaseModel):
    cancel_requested: bool
    lease_seconds: int


class EventRequest(BaseModel):
    name: str = Field(max_length=40)
    payload: dict[str, Any]


class FinishRequest(BaseModel):
    outcome: Literal["succeeded", "failed", "cancelled"]
    message: str | None = Field(default=None, max_length=500)


class VerifyTokenRequest(BaseModel):
    token: str = Field(max_length=200)


class VerifyTokenResponse(BaseModel):
    scope: Literal["read", "upload"]
    owner_id: str
    project_id: str | None
    expires_in: int
    max_upload_bytes: int
    max_video_seconds: int


class RegisterMediaRequest(MediaReadyIn):
    project_id: str = ""


def _server_info(settings, owner: User) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {
        "server_version": __version__,
        "owner_id": owner.id,
        "owner_name": owner.display_name,
        "allowed_origins": list(settings.cors_origins),
        "long_poll_seconds": settings.worker_long_poll_seconds,
        "lease_seconds": settings.worker_lease_seconds,
    }


# ------------------------------------------------------------------ pairing
@router.post(
    "/pair",
    response_model=PairResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Hybrid, Depends(route_limit("pair"))],
    summary="Exchange a pairing code for worker credentials",
)
def pair(body: PairRequest, db: DbSession, settings: SettingsDep) -> PairResponse:
    worker, token = pair_worker(
        db,
        settings,
        code=body.code,
        name=body.name,
        platform=body.platform,
        app_version=body.app_version,
        bridge_port=body.bridge_port,
        capabilities=body.capabilities.model_dump(),
    )
    owner = db.get(User, worker.owner_id)
    assert owner is not None  # noqa: S101 - the foreign key guarantees it
    return PairResponse(
        worker_id=worker.id, worker_name=worker.name, token=token, **_server_info(settings, owner)
    )


@router.post(
    "/heartbeat",
    response_model=HeartbeatResponse,
    dependencies=[Hybrid],
    summary="Announce that the worker is online and what it can do",
)
def heartbeat(
    body: HeartbeatRequest, worker: CurrentWorker, db: DbSession, settings: SettingsDep
) -> HeartbeatResponse:
    worker.bridge_port = body.bridge_port
    if body.app_version:
        worker.app_version = body.app_version
    worker.capabilities = body.capabilities.model_dump()
    db.commit()
    owner = db.get(User, worker.owner_id)
    assert owner is not None  # noqa: S101
    return HeartbeatResponse(
        worker_id=worker.id,
        worker_name=worker.name,
        preferred_model=worker.preferred_model,
        **_server_info(settings, owner),
    )


@router.delete(
    "/self",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Hybrid],
    summary="Disconnect this worker from the account",
)
def unpair(worker: CurrentWorker, request: Request, db: DbSession) -> Response:
    revoke_worker(db, request.app.state.database, request.app.state.storage, worker)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------- jobs
@router.post(
    "/jobs/claim",
    response_model=ClaimResponse,
    dependencies=[Hybrid],
    summary="Take the next waiting job (long poll)",
)
async def claim(body: ClaimRequest, worker: CurrentWorker, request: Request) -> ClaimResponse:
    """Returns at once when a job is waiting, otherwise holds the request briefly.

    Long polling keeps the worker responsive without a permanent connection, so the
    server can run on small, inexpensive hosting.
    """
    settings = request.app.state.settings
    database, storage = request.app.state.database, request.app.state.storage
    worker_id = worker.id
    deadline = time.monotonic() + min(body.wait_seconds, settings.worker_long_poll_seconds)
    while True:
        claimed = await run_in_threadpool(claim_next_job, database, storage, settings, worker_id)
        if claimed is not None:
            return ClaimResponse(job=claimed[1])
        if time.monotonic() >= deadline or await request.is_disconnected():
            return ClaimResponse(job=None)
        await asyncio.sleep(1.5)


@router.post(
    "/jobs/{job_id}/progress",
    response_model=ProgressResponse,
    dependencies=[Hybrid],
    summary="Report progress and keep the job's lease alive",
)
def progress(
    job_id: uuid.UUID,
    body: ProgressRequest,
    worker: CurrentWorker,
    db: DbSession,
    settings: SettingsDep,
) -> ProgressResponse:
    job = running_job_for_worker(db, settings, worker, str(job_id))
    job.progress = round(body.progress, 4)
    if body.stage:
        job.stage = body.stage
    db.commit()
    return ProgressResponse(
        cancel_requested=job.cancel_requested, lease_seconds=settings.worker_lease_seconds
    )


@router.post(
    "/jobs/{job_id}/events",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Hybrid],
    summary="Report a processing result (validated before it is stored)",
)
def event(
    job_id: uuid.UUID,
    body: EventRequest,
    worker: CurrentWorker,
    request: Request,
    db: DbSession,
    settings: SettingsDep,
) -> Response:
    job = running_job_for_worker(db, settings, worker, str(job_id))
    try:
        apply_event(db, job, body.name, body.payload, request.app.state.job_runner)
    except EventError as exc:
        db.rollback()
        raise UnprocessableError(str(exc), code="invalid_event") from exc
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/jobs/{job_id}/finish",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Hybrid],
    summary="Report that a job succeeded, failed or was cancelled",
)
def finish(
    job_id: uuid.UUID,
    body: FinishRequest,
    worker: CurrentWorker,
    request: Request,
    db: DbSession,
) -> Response:
    job = db.get(Job, str(job_id))
    if job is None or job.owner_id != worker.owner_id or job.worker_id != worker.id:
        raise NotFoundError("Job not found.")
    if job.status not in ("running", "queued"):
        return Response(status_code=status.HTTP_204_NO_CONTENT)  # already settled; idempotent
    outcome = body.outcome
    if outcome == "succeeded" and job.cancel_requested and job.type != "purge_files":
        outcome = "cancelled"
    db.commit()
    finish_job(request.app.state.database, request.app.state.storage, job.id, outcome, body.message)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- transfers
@router.post(
    "/transfer-tokens/verify",
    response_model=VerifyTokenResponse,
    dependencies=[Hybrid],
    summary="Check a transfer token that a browser presented to this worker's bridge",
)
def verify_token(
    body: VerifyTokenRequest, worker: CurrentWorker, db: DbSession, settings: SettingsDep
) -> VerifyTokenResponse:
    from app.db.base import utcnow

    row = verify_transfer_token(db, worker, body.token)
    return VerifyTokenResponse(
        scope=row.scope,  # type: ignore[arg-type]
        owner_id=row.owner_id,
        project_id=row.project_id,
        expires_in=max(0, int((row.expires_at - utcnow()).total_seconds())),
        max_upload_bytes=settings.max_upload_bytes,
        max_video_seconds=settings.max_video_minutes * 60,
    )


@router.post(
    "/projects/{project_id}/media",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Hybrid],
    summary="Register a video the owner sent straight to this worker",
)
def register_project_media(
    project_id: uuid.UUID,
    body: RegisterMediaRequest,
    worker: CurrentWorker,
    request: Request,
    db: DbSession,
) -> Response:
    project = db.get(Project, str(project_id))
    if project is None or project.owner_id != worker.owner_id or project.status == "deleting":
        raise NotFoundError("Project not found.")
    if project.source_type == "url":
        raise ConflictError("This project gets its video from a link.")
    if project.status not in ("awaiting_upload", "failed") or project.media_key:
        raise ConflictError("This project already has a video.", code="media_exists")
    if video_extension(body.media_key) is None:
        raise UnprocessableError("Unsupported file type.", code="unsupported_media_type")
    body.project_id = project.id
    if body.original_filename:
        body.original_filename = display_filename(body.original_filename)
    try:
        register_media(db, project, body, request.app.state.job_runner, worker_id=worker.id)
    except EventError as exc:
        db.rollback()
        raise UnprocessableError(str(exc), code="invalid_event") from exc
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
