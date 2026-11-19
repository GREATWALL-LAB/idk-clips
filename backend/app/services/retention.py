"""User-controlled retention: remove source videos after a number of days.

Only the large source video is removed. The transcript, the clip list and any clips
that were already exported stay, so the project remains useful. In hybrid mode the
file is on the owner's worker, so the worker is asked to delete it.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select

from app.core.config import Settings
from app.db.base import utcnow
from app.db.models import Job, Project, User
from app.db.session import Database
from app.services.storage import LocalStorage, StorageError

logger = logging.getLogger("app.retention")

MAX_RETENTION_DAYS = 3650
SOURCE_REMOVED = "source_removed_at"


def retention_days(user: User, settings: Settings) -> int:
    value = (user.preferences or {}).get("retention_days")
    if isinstance(value, int) and 0 <= value <= MAX_RETENTION_DAYS:
        return value
    return settings.default_retention_days


def sweep_expired_sources(database: Database, storage: LocalStorage, settings: Settings) -> int:
    """Delete source videos that are older than their owner's retention period."""
    removed = 0
    now = utcnow()
    with database.session_scope() as db:
        users = db.scalars(select(User)).all()
        for user in users:
            days = retention_days(user, settings)
            if days <= 0:
                continue
            cutoff = now - timedelta(days=days)
            projects = db.scalars(
                select(Project).where(
                    Project.owner_id == user.id,
                    Project.media_key.is_not(None),
                    Project.created_at < cutoff,
                    Project.status.in_(("uploaded", "transcribed", "ready", "failed")),
                )
            ).all()
            for project in projects:
                busy = db.scalar(
                    select(Job.id).where(
                        Job.project_id == project.id, Job.status.in_(("queued", "running"))
                    )
                )
                if busy:
                    continue
                key = project.media_key
                if storage.remote:
                    if project.worker_id:
                        db.add(
                            Job(
                                owner_id=user.id,
                                worker_id=project.worker_id,
                                type="purge_files",
                                params={"keys": [key]},
                                stage="Waiting for your worker",
                            )
                        )
                else:
                    try:
                        storage.delete(key)
                    except (StorageError, OSError):
                        logger.exception("Could not delete an expired source video")
                        continue
                project.media_key = None
                project.media_size_bytes = None
                project.source_meta = {
                    **dict(project.source_meta or {}),
                    SOURCE_REMOVED: now.isoformat(),
                }
                removed += 1
    if removed:
        logger.info("Retention removed source videos", extra={"count": removed})
    return removed
