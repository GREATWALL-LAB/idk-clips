from __future__ import annotations

from pydantic import BaseModel

from app.schemas.clip import ClipOut
from app.schemas.job import JobOut
from app.schemas.project import ProjectOut


class DashboardStats(BaseModel):
    projects: int
    processing: int
    clips_ready: int
    storage_used_bytes: int
    storage_quota_bytes: int | None


class ActiveJob(JobOut):
    project_name: str | None = None


class DashboardOut(BaseModel):
    stats: DashboardStats
    recent_projects: list[ProjectOut]
    active_jobs: list[ActiveJob]
    recent_clips: list[ClipOut]
