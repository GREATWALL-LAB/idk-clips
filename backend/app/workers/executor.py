"""Runs one job inside this process (local and server mode).

The executor builds the job's spec from the database, runs the shared compute code
and applies the resulting events. A paired worker does the same middle step on the
user's own computer in hybrid mode (see ``app.agent``).
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from app.core.errors import AppError
from app.db.base import utcnow
from app.db.models import Job
from app.db.session import Database
from app.jobs import compute
from app.jobs.events import EventError, apply_event
from app.jobs.lifecycle import UNEXPECTED_ERROR, Outcome, finish_job
from app.jobs.specs import build_spec
from app.services.jobs import JobSubmitter
from app.services.media import get_ffmpeg
from app.services.storage import LocalStorage
from app.workers.context import JobContext
from openclip_processing.errors import JobCancelled, ProcessingError
from openclip_processing.ffmpeg import FFmpegTools
from openclip_processing.transcription import WhisperTranscriber

logger = logging.getLogger("app.worker")

__all__ = ["UNEXPECTED_ERROR", "JobExecutor"]


class JobExecutor:
    def __init__(self, settings: Settings, database: Database, storage: LocalStorage) -> None:
        self.settings = settings
        self.database = database
        self.storage = storage
        self.submitter: JobSubmitter | None = None
        self._transcriber: WhisperTranscriber | None = None
        self.env = compute.ComputeEnv(
            settings=settings, storage=storage, get_transcriber=lambda: self.transcriber
        )

    # ----------------------------------------------------------- resources
    @property
    def transcriber(self) -> WhisperTranscriber:
        if self._transcriber is None:
            self._transcriber = WhisperTranscriber(self.settings.models_dir / "whisper")
        return self._transcriber

    def ffmpeg(self) -> FFmpegTools:
        return get_ffmpeg(self.settings)

    def _apply_event(self, job_id: str, name: str, payload: dict[str, Any]) -> None:
        with self.database.session_scope() as db:
            job = db.get(Job, job_id)
            if job is None:
                raise JobCancelled()  # the job row was deleted (for example with its project)
            apply_event(db, job, name, payload, self.submitter)

    # ----------------------------------------------------------------- run
    def run(self, job_id: str) -> None:
        outcome: Outcome = "succeeded"
        message: str | None = None
        spec: dict[str, Any] | None = None
        with self.database.session_scope() as db:
            job = db.get(Job, job_id)
            if job is None or job.status != "queued":
                return
            if job.cancel_requested:
                job.status = "cancelled"
                job.finished_at = utcnow()
                return
            job.status = "running"
            job.started_at = utcnow()
            job.stage = "Starting"
            job.attempts += 1
            job_type = job.type

        logger.info("Job started", extra={"job_id": job_id, "job_type": job_type})
        context = JobContext(self.database, job_id, on_event=self._apply_event)
        try:
            with self.database.session_scope() as db:
                job = db.get(Job, job_id)
                if job is None:
                    return
                spec = build_spec(db, self.settings, self.storage, job)
            compute.run(spec, self.env, context)
        except JobCancelled:
            outcome = "cancelled"
        except ProcessingError as exc:
            outcome, message = "failed", exc.user_message
            logger.warning(
                "Job failed",
                extra={"job_id": job_id, "error": exc.user_message, "detail": exc.detail},
            )
        except (AppError, EventError) as exc:
            outcome, message = "failed", str(getattr(exc, "message", exc))
            logger.warning("Job failed", extra={"job_id": job_id, "error": message})
        except Exception:
            outcome, message = "failed", UNEXPECTED_ERROR
            logger.exception("Job crashed", extra={"job_id": job_id})
        finally:
            finish_job(self.database, self.storage, job_id, outcome, message)
