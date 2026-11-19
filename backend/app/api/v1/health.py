"""Liveness and readiness endpoints (safe for uptime monitors; no authentication)."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app import __version__
from app.api.deps import get_app_settings
from app.core.config import Settings
from app.schemas.system import HealthResponse, ReadinessResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
async def health(
    request: Request, settings: Annotated[Settings, Depends(get_app_settings)]
) -> HealthResponse:
    """Returns 200 while the API process is running. Safe to poll."""
    return HealthResponse(
        service="openclip-ai-backend",
        version=__version__,
        environment=settings.environment,
        time=datetime.now(UTC),
        uptime_seconds=round(time.monotonic() - request.app.state.started_at, 1),
    )


def _storage_writable(request: Request) -> bool:
    probe = request.app.state.settings.tmp_dir / f".ready-{uuid.uuid4().hex}"
    try:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError:
        return False
    return True


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
    summary="Readiness check (database and storage)",
)
async def readiness(request: Request) -> JSONResponse:
    database_ok = await run_in_threadpool(request.app.state.database.ping)
    storage_ok = await run_in_threadpool(_storage_writable, request)
    ready = database_ok and storage_ok
    body = ReadinessResponse(
        status="ready" if ready else "not_ready",
        checks={"database": database_ok, "storage": storage_ok},
    )
    return JSONResponse(body.model_dump(), status_code=200 if ready else 503)
