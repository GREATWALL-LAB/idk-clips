from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

JobType = Literal[
    "import_url", "transcribe", "process", "detect_clips", "render_clip", "purge_files"
]
JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    clip_id: str | None
    type: str
    status: str
    stage: str | None
    progress: float
    message: str | None
    error_message: str | None
    cancel_requested: bool
    worker_id: str | None = None
    attempts: int = 0
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
