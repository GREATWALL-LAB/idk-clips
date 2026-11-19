"""Dependency status endpoint used by the dashboard (signed-in users only)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser
from app.schemas.system import SystemStatusResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse, summary="Check external components")
async def system_status(request: Request, _user: CurrentUser) -> SystemStatusResponse:
    """Database, job queue, FFmpeg, transcription device and Ollama (cached for ~5 s)."""
    return await request.app.state.system_status.get_status()
