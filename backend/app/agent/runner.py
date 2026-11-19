"""The worker's main loop: stay connected, claim jobs, run them, report back.

Disconnections are expected (laptops sleep, Wi-Fi drops). The loop therefore never
gives up on network errors: it waits with an increasing delay and tries again. A job
that is running during an outage keeps running; its lease is re-acquired when the
connection returns, and the final result is delivered with retries.
"""

from __future__ import annotations

import logging
import platform
import threading
import time
from pathlib import Path
from typing import Any

from app import __version__
from app.agent.capabilities import collect_capabilities
from app.agent.client import ConnectionProblem, NotAuthorized, ServerClient, ServerError
from app.agent.state import Credentials
from app.core.config import Settings
from app.jobs import JOB_TYPES, compute
from app.services.storage import LocalStorage
from openclip_processing.errors import JobCancelled, ProcessingError
from openclip_processing.transcription import WhisperTranscriber
from openclip_processing.types import ProgressCallback

logger = logging.getLogger("app.agent")

HEARTBEAT_SECONDS = 30.0
KEEPALIVE_SECONDS = 10.0
MAX_BACKOFF_SECONDS = 30.0
DELIVERY_ATTEMPTS = 8
UNEXPECTED_ERROR = "The worker hit an unexpected error. Details are in the worker's log."


class RemoteJobIO:
    """Progress, cancellation and events for one job, sent to the server.

    Progress is kept in memory and posted by a small background thread, so slow
    networks never slow the video work down. The same thread keeps the job's lease
    alive during long quiet steps (for example while a language model is thinking).
    """

    def __init__(
        self, client: ServerClient, job_id: str, keepalive: float = KEEPALIVE_SECONDS
    ) -> None:
        self.client = client
        self.job_id = job_id
        self._keepalive = keepalive
        self._lock = threading.Lock()
        self._fraction = 0.0
        self._stage: str | None = "Starting"
        self._dirty = True
        self._cancelled = False
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = threading.Thread(target=self._pump, name="openclip-progress", daemon=True)

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=15)

    def _pump(self) -> None:
        last_sent = 0.0
        while not self._stop.is_set():
            with self._lock:
                dirty = self._dirty
            # New progress goes out about once a second; otherwise only the keep-alive.
            if dirty or time.monotonic() - last_sent >= self._keepalive:
                self._send()
                last_sent = time.monotonic()
            self._wake.wait(1.0)
            self._wake.clear()

    def _send(self) -> None:
        with self._lock:
            fraction, stage, self._dirty = self._fraction, self._stage, False
        try:
            answer = self.client.progress(self.job_id, fraction, stage)
        except ConnectionProblem:
            return  # the next keep-alive tries again
        except ServerError as exc:
            if exc.status in (404, 409):
                self._cancelled = True  # the job was cancelled, deleted or reassigned
            return
        if answer.get("cancel_requested"):
            self._cancelled = True

    # ------------------------------------------------------------ JobIO API
    def progress(self, fraction: float, stage: str | None = None) -> None:
        fraction = max(0.0, min(1.0, float(fraction)))
        with self._lock:
            stage_changed = stage is not None and stage != self._stage
            self._fraction = fraction
            if stage is not None:
                self._stage = stage[:200]
            self._dirty = True
        if stage_changed or fraction >= 1.0:
            self._wake.set()

    def scaled(self, start: float, end: float) -> ProgressCallback:
        def report(fraction: float, stage: str | None = None) -> None:
            self.progress(start + (end - start) * max(0.0, min(1.0, fraction)), stage)

        return report

    def should_cancel(self) -> bool:
        return self._cancelled

    def emit(self, name: str, payload: dict[str, Any]) -> None:
        """Deliver a result. Retries through short outages; a rejected event fails the job."""
        delay = 1.0
        for attempt in range(DELIVERY_ATTEMPTS):
            try:
                self.client.event(self.job_id, name, payload)
                return
            except ConnectionProblem:
                if attempt == DELIVERY_ATTEMPTS - 1:
                    raise ProcessingError(
                        "The worker lost its connection to the server while saving results. "
                        "Start the job again when the connection is back."
                    ) from None
                time.sleep(delay)
                delay = min(delay * 2, MAX_BACKOFF_SECONDS)
            except ServerError as exc:
                if exc.status in (404, 409):
                    raise JobCancelled() from None
                raise ProcessingError(
                    f"The server did not accept this result: {exc.message}"
                ) from None


class Agent:
    def __init__(
        self,
        settings: Settings,
        credentials: Credentials,
        client: ServerClient | None = None,
    ) -> None:
        self.settings = settings
        self.credentials = credentials
        self.client = client or ServerClient(credentials.server_url, credentials.token)
        self.storage = LocalStorage(settings.storage_dir)
        self._transcriber: WhisperTranscriber | None = None
        self.env = compute.ComputeEnv(
            settings=settings, storage=self.storage, get_transcriber=self._get_transcriber
        )
        self.server_info: dict[str, Any] = {}
        self.jobs_done = 0
        self._last_heartbeat = 0.0

    def _get_transcriber(self) -> WhisperTranscriber:
        if self._transcriber is None:
            self._transcriber = WhisperTranscriber(self.settings.models_dir / "whisper")
        return self._transcriber

    # ------------------------------------------------------------ heartbeat
    def heartbeat(self) -> dict[str, Any]:
        self.server_info = self.client.heartbeat(
            {
                "bridge_port": self.settings.agent_bridge_port,
                "app_version": __version__,
                "capabilities": collect_capabilities(self.settings),
            }
        )
        self._last_heartbeat = time.monotonic()
        return self.server_info

    # ----------------------------------------------------------------- jobs
    def run_job(self, spec: dict[str, Any]) -> str:
        """Run one claimed job and report its outcome. Returns the outcome."""
        job_id = str(spec.get("job_id") or "")
        job_type = str(spec.get("type") or "")
        outcome, message = "succeeded", None
        io = RemoteJobIO(self.client, job_id)
        logger.info("Job started", extra={"job_id": job_id, "job_type": job_type})
        io.start()
        try:
            if job_type not in JOB_TYPES:
                raise ProcessingError(
                    f"This worker does not know the job type '{job_type}'. Update the worker."
                )
            if spec.get("owner_id") != self.credentials.owner_id:
                # Defense in depth: the server only hands out the owner's jobs.
                raise ProcessingError("This job belongs to a different account and was refused.")
            compute.run(spec, self.env, io)
        except JobCancelled:
            outcome = "cancelled"
        except ProcessingError as exc:
            outcome, message = "failed", exc.user_message
            logger.warning(
                "Job failed",
                extra={"job_id": job_id, "error": exc.user_message, "detail": exc.detail},
            )
        except Exception:
            outcome, message = "failed", UNEXPECTED_ERROR
            logger.exception("Job crashed", extra={"job_id": job_id})
        finally:
            io.stop()
            self._cleanup_job_files(job_id)
        self._deliver_finish(job_id, outcome, message)
        self.jobs_done += 1
        logger.info("Job finished", extra={"job_id": job_id, "outcome": outcome})
        return outcome

    def _deliver_finish(self, job_id: str, outcome: str, message: str | None) -> None:
        delay = 1.0
        for _ in range(DELIVERY_ATTEMPTS):
            try:
                self.client.finish(job_id, outcome, message)
                return
            except ConnectionProblem:
                time.sleep(delay)
                delay = min(delay * 2, MAX_BACKOFF_SECONDS)
            except ServerError:
                return  # the job no longer exists on the server; nothing to report
        logger.warning(
            "Could not report the job result; the server will re-queue it", extra={"job_id": job_id}
        )

    def _cleanup_job_files(self, job_id: str) -> None:
        """Remove anything a job left in the temporary folder (crash safety)."""
        if not job_id:
            return
        tmp: Path = self.settings.tmp_dir
        for leftover in (tmp / f"{job_id}.wav", tmp / f"render-{job_id}"):
            try:
                if leftover.is_dir():
                    import shutil

                    shutil.rmtree(leftover, ignore_errors=True)
                elif leftover.is_file():
                    leftover.unlink()
            except OSError:
                logger.warning("Could not remove a temporary file", extra={"file": leftover.name})

    # ----------------------------------------------------------------- loop
    def step(self, wait_seconds: int | None = None) -> str | None:
        """One iteration: heartbeat if due, then claim and run at most one job."""
        if time.monotonic() - self._last_heartbeat >= HEARTBEAT_SECONDS or not self.server_info:
            self.heartbeat()
        wait = (
            int(self.server_info.get("long_poll_seconds", 20))
            if wait_seconds is None
            else wait_seconds
        )
        spec = self.client.claim(wait)
        if spec is None:
            return None
        return self.run_job(spec)

    def run_forever(self, stop: threading.Event) -> int:
        """Run until ``stop`` is set. Returns a process exit code."""
        backoff = 1.0
        connected = False
        while not stop.is_set():
            try:
                self.step()
                if not connected:
                    logger.info(
                        "Connected: waiting for jobs",
                        extra={"server": self.credentials.server_url, "host": platform.node()},
                    )
                connected, backoff = True, 1.0
            except NotAuthorized as exc:
                logger.error("This worker is no longer connected to an account: %s", exc.message)
                return 2
            except ConnectionProblem as exc:
                if connected:
                    logger.warning(
                        "Lost the connection to the server; retrying",
                        extra={"reason": str(exc)[:200]},
                    )
                connected = False
                stop.wait(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            except ServerError as exc:
                logger.warning(
                    "The server reported a problem; retrying", extra={"reason": exc.message}
                )
                stop.wait(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
        return 0
