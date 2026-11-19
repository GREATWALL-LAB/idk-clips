"""Per-job helpers: throttled progress updates and cancellation checks."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import select, update

from app.db.base import utcnow
from app.db.models import Job
from app.db.session import Database
from openclip_processing.errors import JobCancelled
from openclip_processing.types import ProgressCallback


class JobContext:
    PROGRESS_INTERVAL = 0.5  # seconds between progress writes
    CANCEL_INTERVAL = 1.0  # seconds between cancellation checks

    def __init__(
        self,
        database: Database,
        job_id: str,
        on_event: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.database = database
        self.job_id = job_id
        self._on_event = on_event
        self._last_write = 0.0
        self._last_stage: str | None = None
        self._last_cancel_check = 0.0
        self._cancelled = False

    def progress(self, fraction: float, stage: str | None = None) -> None:
        """Record real progress (0..1). Writes are throttled except on stage changes."""
        fraction = max(0.0, min(1.0, float(fraction)))
        now = time.monotonic()
        stage_changed = stage is not None and stage != self._last_stage
        if not stage_changed and now - self._last_write < self.PROGRESS_INTERVAL and fraction < 1.0:
            return
        self._last_write = now
        if stage is not None:
            self._last_stage = stage
        values: dict[str, object] = {"progress": round(fraction, 4), "updated_at": utcnow()}
        if stage is not None:
            values["stage"] = stage[:200]
        with self.database.session_scope() as db:
            db.execute(update(Job).where(Job.id == self.job_id).values(**values))

    def scaled(self, start: float, end: float) -> ProgressCallback:
        """Map a sub-step's 0..1 progress into [start, end] of the whole job."""

        def report(fraction: float, stage: str | None = None) -> None:
            self.progress(start + (end - start) * max(0.0, min(1.0, fraction)), stage)

        return report

    def should_cancel(self) -> bool:
        if self._cancelled:
            return True
        now = time.monotonic()
        if now - self._last_cancel_check < self.CANCEL_INTERVAL:
            return False
        self._last_cancel_check = now
        with self.database.session_scope() as db:
            row = db.execute(select(Job.cancel_requested).where(Job.id == self.job_id)).first()
        # A deleted job row counts as cancelled.
        self._cancelled = row is None or bool(row[0])
        return self._cancelled

    def emit(self, name: str, payload: dict[str, Any]) -> None:
        """Report a processing result. It is validated and written to the database."""
        if self._on_event is not None:
            self._on_event(self.job_id, name, payload)

    def check_cancel(self) -> None:
        if self.should_cancel():
            raise JobCancelled()
