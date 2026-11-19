"""One request with everything the dashboard needs."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, SettingsDep, StorageDep
from app.db.models import Clip, Job, Project
from app.schemas.dashboard import ActiveJob, DashboardOut, DashboardStats
from app.services.clips import clips_out
from app.services.jobs import ACTIVE_JOB_STATUSES
from app.services.projects import HIDDEN_STATUSES, list_projects, user_storage_bytes

router = APIRouter(tags=["dashboard"])


@router.get(
    "/dashboard", response_model=DashboardOut, summary="Dashboard summary for the signed-in user"
)
def dashboard(
    user: CurrentUser, db: DbSession, storage: StorageDep, settings: SettingsDep
) -> DashboardOut:
    project_total = db.scalar(
        select(func.count()).where(
            Project.owner_id == user.id, Project.status.not_in(HIDDEN_STATUSES)
        )
    )
    jobs = db.scalars(
        select(Job)
        .where(Job.owner_id == user.id, Job.status.in_(ACTIVE_JOB_STATUSES))
        .order_by(Job.created_at.desc())
        .limit(20)
    ).all()
    names = dict(
        db.execute(
            select(Project.id, Project.name).where(
                Project.id.in_({j.project_id for j in jobs if j.project_id})
            )
        ).all()
    )
    ready_clips = db.scalars(
        select(Clip)
        .join(Project, Project.id == Clip.project_id)
        .where(
            Clip.owner_id == user.id, Clip.status == "ready", Project.status.not_in(HIDDEN_STATUSES)
        )
        .order_by(Clip.rendered_at.desc())
        .limit(8)
    ).all()
    clips_ready = db.scalar(
        select(func.count()).where(Clip.owner_id == user.id, Clip.status == "ready")
    )
    quota = settings.user_storage_quota_mb * 1024 * 1024 if settings.user_storage_quota_mb else None
    return DashboardOut(
        stats=DashboardStats(
            projects=int(project_total or 0),
            processing=len({j.project_id for j in jobs}),
            clips_ready=int(clips_ready or 0),
            storage_used_bytes=user_storage_bytes(db, user.id),
            storage_quota_bytes=quota,
        ),
        recent_projects=list_projects(db, user.id, storage, limit=6, offset=0).items,
        active_jobs=[
            ActiveJob.model_validate({**job.__dict__, "project_name": names.get(job.project_id)})
            for job in jobs
        ],
        recent_clips=clips_out(db, list(ready_clips), storage, with_project=True),
    )
