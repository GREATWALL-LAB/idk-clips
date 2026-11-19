"""Schemas for health and system status endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = Field(examples=["openclip-ai-backend"])
    version: str = Field(examples=["0.1.0"])
    environment: str = Field(examples=["development"])
    time: datetime
    uptime_seconds: float


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, bool]


ComponentState = Literal["ok", "unavailable", "misconfigured", "not_configured"]


class ComponentStatus(BaseModel):
    """Status of one external dependency. Never contains server paths or secrets."""

    key: str = Field(examples=["ffmpeg"])
    name: str = Field(examples=["FFmpeg"])
    status: ComponentState
    required: bool = Field(description="Whether the core local workflow needs this component.")
    version: str | None = None
    source: str | None = Field(default=None, description="configured, bundled or system")
    detail: str | None = None
    hint: str | None = Field(default=None, description="How to fix the problem, if any.")


class SystemStatusResponse(BaseModel):
    status: Literal["ok", "degraded"]
    components: list[ComponentStatus]
    checked_at: datetime
