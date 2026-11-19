"""Celery application for running jobs in a separate worker process.

Used when OPENCLIP_JOB_BACKEND=celery. Start a worker with:

    celery -A app.workers.celery_app worker --pool=solo --loglevel=INFO

``--pool=solo`` is required on Windows and keeps one job at a time, which is
what a single GPU can handle anyway.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings
from app.core.logging import configure_logging, redactor

_settings = get_settings()

celery_app = Celery("openclip", broker=_settings.redis_url.get_secret_value())
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
)

_executor = None


def _get_executor():  # type: ignore[no-untyped-def]
    """Build the executor lazily inside the worker process."""
    global _executor
    if _executor is None:
        from app.db.migrate import upgrade_to_head
        from app.db.session import Database
        from app.services.storage import LocalStorage
        from app.workers.executor import JobExecutor
        from app.workers.runner import CeleryJobRunner

        configure_logging(_settings.log_level, _settings.log_format)
        for secret in _settings.secret_values():
            redactor.register(secret)
        upgrade_to_head(_settings.sqlalchemy_url)
        _executor = JobExecutor(
            _settings, Database(_settings.sqlalchemy_url), LocalStorage(_settings.storage_dir)
        )
        _executor.submitter = CeleryJobRunner()
    return _executor


@celery_app.task(name="openclip.run_job")
def run_job(job_id: str) -> None:
    _get_executor().run(job_id)
