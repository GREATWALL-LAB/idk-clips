"""Background job status and cancellation."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.db.models import Job
from app.schemas.job import JobOut
from app.services.jobs import ACTIVE_JOB_STATUSES, get_owned_job, request_cancel

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut], summary="Your recent or active jobs")
def list_jobs(
    user: CurrentUser,
    db: DbSession,
    active: Annotated[bool, Query()] = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[JobOut]:
    query = select(Job).where(Job.owner_id == user.id)
    if active:
        query = query.where(Job.status.in_(ACTIVE_JOB_STATUSES))
    jobs = db.scalars(query.order_by(Job.created_at.desc()).limit(limit)).all()
    return [JobOut.model_validate(job) for job in jobs]


@router.get("/{job_id}", response_model=JobOut, summary="Job status and progress")
def get_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> JobOut:
    return JobOut.model_validate(get_owned_job(db, user.id, str(job_id)))


@router.post("/{job_id}/cancel", response_model=JobOut, summary="Cancel a queued or running job")
def cancel_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> JobOut:
    job = request_cancel(db, get_owned_job(db, user.id, str(job_id)))
    return JobOut.model_validate(job)
