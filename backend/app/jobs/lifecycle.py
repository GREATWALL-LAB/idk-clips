"""Bookkeeping around a job: finishing it and settling project/clip state afterwards.

Used by the in-process executor and by the agent API (when a paired worker reports
that a job finished, failed or was cancelled).
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from sqlalchemy import select

from app.db.base import utcnow
from app.db.models import Clip, Job, Project
from app.db.session import Database
from app.services.projects import delete_project_now
from app.services.storage import LocalStorage

logger = logging.getLogger("app.jobs")

Outcome = Literal["succeeded", "failed", "cancelled"]

UNEXPECTED_ERROR = "An unexpected error occurred. The details were written to the server log."
_STAGE = {"succeeded": "Done", "failed": "Failed", "cancelled": "Cancelled"}


def settle_project(
    db: Any,
    storage: LocalStorage,
    project: Project,
    job_type: str,
    outcome: str,
    message: str | None,
) -> None:
    """Put a project back into a sensible state after a job did not succeed."""
    has_transcript = project.transcript is not None
    has_media = storage.has(project.media_key)
    has_clips = bool(db.scalar(select(Clip.id).where(Clip.project_id == project.id).limit(1)))
    if has_transcript:
        project.status = "ready" if has_clips else "transcribed"
    elif has_media:
        project.status = "uploaded"
    else:
        project.status = "failed"
    if outcome == "cancelled":
        project.error_message = "Import was cancelled." if job_type == "import_url" else None
    else:
        project.error_message = (message or UNEXPECTED_ERROR)[:500]


def finish_job(
    database: Database,
    storage: LocalStorage,
    job_id: str,
    outcome: Outcome,
    message: str | None = None,
) -> None:
    """Record the final state of a job and repair the project/clip state if it did not succeed."""
    delete_after: str | None = None
    with database.session_scope() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        job_type, project_id, clip_id = job.type, job.project_id, job.clip_id
        job.status = outcome
        job.finished_at = utcnow()
        job.stage = _STAGE[outcome]
        job.lease_expires_at = None
        if outcome == "succeeded":
            job.progress = 1.0
        job.error_message = (message or UNEXPECTED_ERROR)[:500] if outcome == "failed" else None

        project = db.get(Project, project_id) if project_id else None
        if project is not None and project.status == "deleting":
            delete_after = project.id
        elif project is not None and outcome != "succeeded" and job_type != "render_clip":
            settle_project(db, storage, project, job_type, outcome, message)

        if clip_id and outcome != "succeeded":
            clip = db.get(Clip, clip_id)
            if clip is not None:
                clip.status = (
                    "failed"
                    if outcome == "failed"
                    else ("ready" if clip.output_key else "suggested")
                )
                clip.error_message = (
                    (message or UNEXPECTED_ERROR)[:500] if outcome == "failed" else None
                )

    if delete_after:
        with database.session_scope() as db:
            project = db.get(Project, delete_after)
            if project is not None:
                still_busy = db.scalar(
                    select(Job.id).where(
                        Job.project_id == delete_after, Job.status.in_(("queued", "running"))
                    )
                )
                if not still_busy:
                    delete_project_now(db, storage, project)
    logger.info("Job finished", extra={"job_id": job_id, "outcome": outcome})
