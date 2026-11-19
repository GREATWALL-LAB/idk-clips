"""Project queries with ownership checks, serialization and deletion."""

from __future__ import annotations

import logging

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models import Clip, Job, Project
from app.schemas.job import JobOut
from app.schemas.project import ClipCounts, ProjectList, ProjectOut
from app.services.storage import LocalStorage

logger = logging.getLogger("app.projects")

ACTIVE_JOB_STATUSES = ("queued", "running")
HIDDEN_STATUSES = ("deleting",)


def get_owned_project(db: Session, user_id: str, project_id: str) -> Project:
    """Return the project if it exists and belongs to the user; otherwise 404.

    Projects owned by someone else are reported as "not found" so their
    existence is not revealed.
    """
    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user_id,
            Project.status.not_in(HIDDEN_STATUSES),
        )
    )
    if project is None:
        raise NotFoundError("Project not found.")
    return project


def active_jobs_by_project(db: Session, project_ids: list[str]) -> dict[str, Job]:
    if not project_ids:
        return {}
    jobs = db.scalars(
        select(Job)
        .where(Job.project_id.in_(project_ids), Job.status.in_(ACTIVE_JOB_STATUSES))
        .order_by(Job.created_at.desc())
    ).all()
    result: dict[str, Job] = {}
    for job in jobs:
        if job.project_id and job.project_id not in result:
            result[job.project_id] = job
    return result


def clip_counts_by_project(db: Session, project_ids: list[str]) -> dict[str, ClipCounts]:
    if not project_ids:
        return {}
    rows = db.execute(
        select(
            Clip.project_id,
            func.count(Clip.id),
            func.sum(case((Clip.status == "ready", 1), else_=0)),
        )
        .where(Clip.project_id.in_(project_ids))
        .group_by(Clip.project_id)
    ).all()
    return {row[0]: ClipCounts(total=int(row[1]), ready=int(row[2] or 0)) for row in rows}


def to_project_out(
    project: Project,
    storage: LocalStorage,
    *,
    active_job: Job | None,
    clip_counts: ClipCounts | None,
    has_transcript: bool,
) -> ProjectOut:
    has_media = storage.has(project.media_key)
    return ProjectOut(
        id=project.id,
        name=project.name,
        status=project.status,
        source_type=project.source_type,
        source_url=project.source_url,
        source_meta=dict(project.source_meta or {}),
        worker_id=project.worker_id,
        media_host="worker" if storage.remote else "server",
        original_filename=project.original_filename,
        media_size_bytes=project.media_size_bytes,
        duration_seconds=project.duration_seconds,
        width=project.width,
        height=project.height,
        fps=project.fps,
        language=project.language,
        whisper_model=project.whisper_model,
        clip_count=project.clip_count,
        aspect_ratio=project.aspect_ratio,
        min_clip_seconds=project.min_clip_seconds,
        max_clip_seconds=project.max_clip_seconds,
        auto_process=project.auto_process,
        ai_provider=project.ai_provider,
        ai_model=project.ai_model,
        error_message=project.error_message,
        has_media=has_media,
        media_url=f"/projects/{project.id}/media" if has_media else None,
        thumbnail_url=f"/projects/{project.id}/thumbnail"
        if storage.has(project.thumbnail_key)
        else None,
        has_transcript=has_transcript,
        clips=clip_counts or ClipCounts(),
        active_job=JobOut.model_validate(active_job) if active_job else None,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def project_out(db: Session, project: Project, storage: LocalStorage) -> ProjectOut:
    jobs = active_jobs_by_project(db, [project.id])
    counts = clip_counts_by_project(db, [project.id])
    return to_project_out(
        project,
        storage,
        active_job=jobs.get(project.id),
        clip_counts=counts.get(project.id),
        has_transcript=project.transcript is not None,
    )


def list_projects(
    db: Session, user_id: str, storage: LocalStorage, *, limit: int, offset: int
) -> ProjectList:
    base = select(Project).where(
        Project.owner_id == user_id, Project.status.not_in(HIDDEN_STATUSES)
    )
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    projects = db.scalars(
        base.order_by(Project.created_at.desc()).limit(limit).offset(offset)
    ).all()
    ids = [p.id for p in projects]
    jobs = active_jobs_by_project(db, ids)
    counts = clip_counts_by_project(db, ids)
    from app.db.models import Transcript  # local import keeps module dependencies obvious

    with_transcript = (
        set(db.scalars(select(Transcript.project_id).where(Transcript.project_id.in_(ids))).all())
        if ids
        else set()
    )
    items = [
        to_project_out(
            p,
            storage,
            active_job=jobs.get(p.id),
            clip_counts=counts.get(p.id),
            has_transcript=p.id in with_transcript,
        )
        for p in projects
    ]
    return ProjectList(items=items, total=total)


def user_storage_bytes(db: Session, user_id: str) -> int:
    media = db.scalar(
        select(func.coalesce(func.sum(Project.media_size_bytes), 0)).where(
            Project.owner_id == user_id
        )
    )
    clips = db.scalar(
        select(func.coalesce(func.sum(Clip.output_size_bytes), 0)).where(Clip.owner_id == user_id)
    )
    return int(media or 0) + int(clips or 0)


def delete_project_now(db: Session, storage: LocalStorage, project: Project) -> None:
    """Delete the database rows (cascades to clips/jobs/transcript) and every file.

    In hybrid mode the files are on the owner's worker, so a ``purge_files`` job is
    left for it. The job has no project, which is why it survives the cascade.
    """
    prefix = LocalStorage.project_prefix(project.owner_id, project.id)
    purge_on = project.worker_id if storage.remote and project.media_key else None
    owner_id = project.owner_id
    db.delete(project)
    if purge_on:
        db.add(
            Job(
                owner_id=owner_id,
                worker_id=purge_on,
                type="purge_files",
                params={"prefix": prefix},
                stage="Waiting for your worker",
            )
        )
    db.commit()
    try:
        storage.delete_tree(prefix)
    except OSError:
        logger.exception("Could not delete project files", extra={"project_id": project.id})


def request_project_deletion(db: Session, storage: LocalStorage, project: Project) -> bool:
    """Delete now, or mark for deletion after the running job stops.

    Returns True if the project was deleted immediately.
    """
    active = db.scalars(
        select(Job).where(Job.project_id == project.id, Job.status.in_(ACTIVE_JOB_STATUSES))
    ).all()
    if not active:
        delete_project_now(db, storage, project)
        return True
    for job in active:
        job.cancel_requested = True
        if job.status == "queued":
            job.status = "cancelled"
    project.status = "deleting"
    db.commit()
    if all(job.status == "cancelled" for job in active):
        delete_project_now(db, storage, project)
        return True
    return False
