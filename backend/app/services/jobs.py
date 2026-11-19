"""Creating, cancelling and recovering background jobs."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError, RateLimitError
from app.db.base import utcnow
from app.db.models import Clip, Job, Project

logger = logging.getLogger("app.jobs")

ACTIVE_JOB_STATUSES = ("queued", "running")


class JobSubmitter(Protocol):
    def submit(self, job_id: str) -> None: ...


def active_job(db: Session, project_id: str) -> Job | None:
    return db.scalar(
        select(Job)
        .where(Job.project_id == project_id, Job.status.in_(ACTIVE_JOB_STATUSES))
        .order_by(Job.created_at.desc())
    )


def processing_minutes_last_day(db: Session, user_id: str) -> float:
    """Minutes of video this user sent for processing or export in the last 24 hours."""
    since = utcnow() - timedelta(days=1)
    whole = db.scalar(
        select(func.coalesce(func.sum(Project.duration_seconds), 0.0))
        .select_from(Job)
        .join(Project, Project.id == Job.project_id)
        .where(
            Job.owner_id == user_id,
            Job.created_at >= since,
            Job.type.in_(("process", "import_url", "transcribe", "detect_clips")),
        )
    )
    clips = db.scalar(
        select(func.coalesce(func.sum(Clip.end_seconds - Clip.start_seconds), 0.0))
        .select_from(Job)
        .join(Clip, Clip.id == Job.clip_id)
        .where(Job.owner_id == user_id, Job.created_at >= since, Job.type == "render_clip")
    )
    return (float(whole or 0) + float(clips or 0)) / 60


def check_job_capacity(db: Session, settings: Settings, user_id: str) -> None:
    if settings.max_active_jobs_per_user:
        active = db.scalar(
            select(func.count()).where(Job.owner_id == user_id, Job.status.in_(ACTIVE_JOB_STATUSES))
        )
        if (active or 0) >= settings.max_active_jobs_per_user:
            raise RateLimitError(
                f"You already have {active} jobs waiting or running. Wait for some to finish, "
                "or cancel one, before starting more.",
                code="too_many_jobs",
            )
    quota = settings.daily_processing_minutes_per_user
    if quota and processing_minutes_last_day(db, user_id) >= quota:
        raise RateLimitError(
            f"You have used today's processing allowance on this server ({quota} minutes of "
            "video per 24 hours). Try again later, or run IDK Clips on your own computer.",
            code="daily_quota",
        )


def enqueue_job(
    db: Session,
    runner: JobSubmitter,
    *,
    owner_id: str,
    job_type: str,
    project_id: str | None = None,
    clip_id: str | None = None,
    params: dict[str, Any] | None = None,
    allow_parallel: bool = False,
    worker_id: str | None = None,
) -> Job:
    if project_id and not allow_parallel and active_job(db, project_id):
        raise ConflictError(
            "This project is already being processed. Wait for it to finish or cancel it first.",
            code="project_busy",
        )
    # Hybrid mode: a project's files live on one worker, so its jobs are pinned to it.
    project = db.get(Project, project_id) if project_id else None
    pinned = worker_id or (project.worker_id if project is not None else None)
    job = Job(
        owner_id=owner_id,
        project_id=project_id,
        clip_id=clip_id,
        type=job_type,
        params=params or {},
        worker_id=pinned,
        stage="Waiting for your worker" if getattr(runner, "remote", False) else "Waiting in queue",
    )
    db.add(job)
    db.commit()
    runner.submit(job.id)
    logger.info("Job queued", extra={"job_id": job.id, "job_type": job_type})
    return job


def get_owned_job(db: Session, user_id: str, job_id: str) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id, Job.owner_id == user_id))
    if job is None:
        raise NotFoundError("Job not found.")
    return job


def request_cancel(db: Session, job: Job) -> Job:
    if job.status not in ACTIVE_JOB_STATUSES:
        return job
    job.cancel_requested = True
    if job.status == "queued":
        # The worker never started it, so settle the project and clip state here.
        job.status = "cancelled"
        job.finished_at = utcnow()
        job.stage = "Cancelled"
        job.lease_expires_at = None
        clip = db.get(Clip, job.clip_id) if job.clip_id else None
        if clip is not None and clip.status == "rendering":
            clip.status = "ready" if clip.output_key else "suggested"
        project = db.get(Project, job.project_id) if job.project_id else None
        if project is not None and project.status in ("queued", "importing"):
            if project.status == "importing":
                project.status = "failed"
                project.error_message = "Import was cancelled."
            else:
                project.status = "transcribed" if project.transcript is not None else "uploaded"
    db.commit()
    return job


# Project status to fall back to when a job is interrupted.
_RECOVERY_STATUS = {
    "importing": "failed",
    "queued": "uploaded",
    "transcribing": "uploaded",
    "analyzing": "transcribed",
}


def recover_interrupted_jobs(db: Session) -> list[str]:
    """After a restart in local mode: fail jobs that were running, re-queue queued ones.

    Returns the IDs of jobs that should be submitted again.
    """
    requeue: list[str] = []
    for job in db.scalars(select(Job).where(Job.status.in_(ACTIVE_JOB_STATUSES))).all():
        if job.status == "queued" and not job.cancel_requested:
            requeue.append(job.id)
            continue
        job.status = "failed" if not job.cancel_requested else "cancelled"
        job.error_message = (
            "Interrupted because the server stopped. Start it again from the project page."
        )
        job.finished_at = utcnow()
        if job.project_id:
            project = db.get(Project, job.project_id)
            if project and project.status in _RECOVERY_STATUS:
                project.status = _RECOVERY_STATUS[project.status]
                project.error_message = job.error_message
    db.commit()
    return requeue
