"""Job runners: a local worker thread (default) or Celery with Redis."""

from __future__ import annotations

import logging
import queue
import threading

from app.workers.executor import JobExecutor

logger = logging.getLogger("app.worker")


class LocalJobRunner:
    """Processes jobs one at a time in a background thread inside the API process.

    One job at a time is deliberate: transcription and local AI models share the
    GPU/CPU, and running them in parallel on a typical 8 GB GPU would fail or crawl.
    """

    def __init__(self, executor: JobExecutor) -> None:
        self.executor = executor
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="openclip-worker", daemon=True)
        self._thread.start()

    def submit(self, job_id: str) -> None:
        self._queue.put(job_id)

    def stop(self, timeout: float = 5.0) -> None:
        if self._thread is None:
            return
        self._queue.put(None)
        self._thread.join(timeout=timeout)

    def _loop(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                return
            try:
                self.executor.run(job_id)
            except Exception:  # the executor already records failures; never kill the loop
                logger.exception("Worker loop error", extra={"job_id": job_id})


class RemoteJobRunner:
    """Hybrid mode: jobs wait in the database until the owner's paired worker claims them.

    Nothing is processed on the server, so ``submit`` has nothing to do. Workers pull
    jobs through ``/api/v1/agent/jobs/claim`` (see ``app.services.workers``).
    """

    remote = True

    def start(self) -> None:
        return None

    def submit(self, job_id: str) -> None:
        return None

    def stop(self, timeout: float = 5.0) -> None:
        return None


class CeleryJobRunner:
    """Sends jobs to a Celery worker (start it with scripts\\windows\\start-worker.cmd)."""

    def __init__(self) -> None:
        from app.workers.celery_app import celery_app

        self._celery = celery_app

    def start(self) -> None:  # the worker is a separate process
        return None

    def submit(self, job_id: str) -> None:
        self._celery.send_task("openclip.run_job", args=[job_id])

    def stop(self, timeout: float = 5.0) -> None:
        return None
