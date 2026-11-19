"""FastAPI application factory and ASGI entry point (``app.main:app``)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app import __version__
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.csrf import CSRF_HEADER, CSRFMiddleware
from app.core.errors import register_exception_handlers
from app.core.local_guard import LocalOnlyMiddleware
from app.core.logging import configure_logging, redactor
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import (
    BodySizeLimitMiddleware,
    ClientIPMiddleware,
    RateLimitMiddleware,
    TokenBucketLimiter,
    build_route_limiters,
)
from app.core.security import LoginThrottle
from app.core.webapp import WebApp
from app.db.migrate import upgrade_to_head
from app.db.models import Job, Project
from app.db.session import Database
from app.services.auth import ensure_local_user
from app.services.email_codes import build_email_codes
from app.services.jobs import ACTIVE_JOB_STATUSES, recover_interrupted_jobs
from app.services.projects import delete_project_now
from app.services.retention import sweep_expired_sources
from app.services.storage import LocalStorage
from app.services.system_status import SystemStatusService
from app.services.workers import requeue_expired
from app.workers.executor import JobExecutor
from app.workers.runner import CeleryJobRunner, LocalJobRunner, RemoteJobRunner

logger = logging.getLogger("app")

API_DESCRIPTION = (
    "REST API for IDK Clips: import long videos, transcribe them, find clip candidates with "
    "AI and export MP4 clips in 9:16, 4:5, 1:1 or 16:9. All endpoints are under /api/v1. "
    "Signed-in endpoints use the HttpOnly session cookie set by /api/v1/auth/login; "
    f"state-changing requests must send the header `{CSRF_HEADER}: OpenClip`. "
    "Endpoints under /api/v1/agent are for paired workers (hybrid mode) and use a bearer token."
)

TMP_MAX_AGE_SECONDS = 24 * 3600
LEASE_SWEEP_SECONDS = 20
RETENTION_SWEEP_SECONDS = 3600


def _cleanup_tmp(tmp_dir: Path) -> None:
    """Remove temporary files left behind by crashes (older than a day)."""
    if not tmp_dir.is_dir():
        return
    cutoff = time.time() - TMP_MAX_AGE_SECONDS
    for item in tmp_dir.iterdir():
        try:
            if item.is_file() and item.stat().st_mtime < cutoff:
                item.unlink()
        except OSError:
            logger.warning("Could not remove temporary file", extra={"file": item.name})


def _startup_recovery(database: Database, storage: LocalStorage) -> list[str]:
    with database.session_scope() as db:
        requeue = recover_interrupted_jobs(db)
    # Finish deletions that were waiting for a job which will never report back.
    with database.session_scope() as db:
        for project in db.scalars(select(Project).where(Project.status == "deleting")).all():
            busy = db.scalar(
                select(Job.id).where(
                    Job.project_id == project.id, Job.status.in_(ACTIVE_JOB_STATUSES)
                )
            )
            if not busy:
                delete_project_now(db, storage, project)
    return requeue


async def _maintenance(settings: Settings, database: Database, storage: LocalStorage) -> None:
    """Periodic housekeeping: expired worker leases (hybrid) and retention (every mode)."""
    last_retention = 0.0
    while True:
        try:
            if settings.jobs_mode == "remote":
                await run_in_threadpool(requeue_expired, database, storage, settings)
            if time.monotonic() - last_retention >= RETENTION_SWEEP_SECONDS or not last_retention:
                last_retention = time.monotonic()
                await run_in_threadpool(sweep_expired_sources, database, storage, settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Maintenance task failed")
        await asyncio.sleep(LEASE_SWEEP_SECONDS)


class LazyMaintenance:
    """Housekeeping for serverless deployments, run at most every LEASE_SWEEP_SECONDS
    while handling ordinary requests (expired worker leases, retention)."""

    def __init__(self, app, settings: Settings, database: Database, storage: LocalStorage) -> None:  # type: ignore[no-untyped-def]
        self.app = app
        self.settings = settings
        self.database = database
        self.storage = storage
        self.last_sweep = 0.0
        self.last_retention = 0.0

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] == "http":
            now = time.monotonic()
            if now - self.last_sweep >= LEASE_SWEEP_SECONDS:
                self.last_sweep = now
                try:
                    await run_in_threadpool(
                        requeue_expired, self.database, self.storage, self.settings
                    )
                    if (
                        now - self.last_retention >= RETENTION_SWEEP_SECONDS
                        or not self.last_retention
                    ):
                        self.last_retention = now
                        await run_in_threadpool(
                            sweep_expired_sources, self.database, self.storage, self.settings
                        )
                except Exception:
                    logger.exception("Maintenance failed")
        await self.app(scope, receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    for secret in settings.secret_values():
        redactor.register(secret)

    database = Database(settings.sqlalchemy_url, small_pool=settings.serverless)
    if settings.serverless:
        # A serverless platform may never send lifespan events, so prepare everything now.
        for folder in (settings.data_dir, settings.tmp_dir):
            folder.mkdir(parents=True, exist_ok=True)
        upgrade_to_head(settings.sqlalchemy_url)
    # Hybrid mode: the server only tracks file keys; the bytes stay on each user's worker.
    storage = LocalStorage(settings.storage_dir, remote=settings.media_on_workers)
    executor = JobExecutor(settings, database, storage)
    runner: LocalJobRunner | CeleryJobRunner | RemoteJobRunner
    if settings.jobs_mode == "remote":
        runner = RemoteJobRunner()
    elif settings.jobs_mode == "celery":
        runner = CeleryJobRunner()
    else:
        runner = LocalJobRunner(executor)
    executor.submitter = runner

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        for folder in (settings.data_dir, settings.tmp_dir, settings.models_dir):
            folder.mkdir(parents=True, exist_ok=True)
        await run_in_threadpool(upgrade_to_head, settings.sqlalchemy_url)
        _cleanup_tmp(settings.tmp_dir)
        if not settings.accounts_enabled:
            with database.session_scope() as db:
                ensure_local_user(db)
        if settings.jobs_mode == "local":
            requeue = await run_in_threadpool(_startup_recovery, database, storage)
            runner.start()
            for job_id in requeue:
                runner.submit(job_id)
        # Serverless functions are frozen between requests; LazyMaintenance runs instead.
        maintenance = (
            None
            if settings.serverless
            else asyncio.create_task(_maintenance(settings, database, storage))
        )
        logger.info(
            "IDK Clips backend started",
            extra={
                "version": __version__,
                "environment": settings.environment,
                "mode": settings.mode,
                "database": "sqlite" if database.is_sqlite else "postgresql",
                "jobs": settings.jobs_mode,
            },
        )
        yield
        if maintenance is not None:
            maintenance.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await maintenance
        runner.stop()
        database.dispose()
        logger.info("IDK Clips backend stopped")

    app = FastAPI(
        title="IDK Clips API",
        version=__version__,
        description=API_DESCRIPTION,
        # Under /api so the web interface can use /docs for the user documentation.
        docs_url="/api/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.started_at = time.monotonic()
    app.state.database = database
    app.state.storage = storage
    app.state.executor = executor
    app.state.job_runner = runner
    app.state.system_status = SystemStatusService(settings, database=database)
    app.state.route_limiters = build_route_limiters(settings)
    app.state.login_throttle = LoginThrottle()
    app.state.email_codes = build_email_codes(settings)

    register_exception_handlers(app)

    # Starlette runs the most recently added middleware first, so the order is:
    # client IP -> CORS -> request context (IDs, headers, logs) -> local-only guard -> CSRF
    # -> rate limit -> body size limit.
    app.add_middleware(
        BodySizeLimitMiddleware,
        default_bytes=settings.max_request_body_mb * 1024 * 1024,
        worker_bytes=settings.max_worker_payload_mb * 1024 * 1024,
        # Video uploads stream to disk with their own limit (max_upload_mb).
        stream_paths=(re.compile(r"^/api/v1/projects/[^/]+/media$"),),
    )
    app.add_middleware(
        RateLimitMiddleware,
        limiter=TokenBucketLimiter(settings.rate_limit_requests_per_minute, 60),
        enabled=settings.rate_limit_enabled,
        exempt_paths=frozenset({"/api/v1/health", "/api/v1/health/ready"}),
        failure_limiter=TokenBucketLimiter(settings.failed_request_limit_per_minute, 60),
    )
    app.add_middleware(CSRFMiddleware, allowed_origins=settings.cors_origins)
    if settings.mode == "local":
        # No accounts in local mode, so the API must only ever answer this computer.
        app.add_middleware(LocalOnlyMiddleware, enforce_peer=not settings.local_allow_remote)
    app.add_middleware(RequestContextMiddleware, hsts=settings.secure_cookies)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,  # the session cookie; origins are an explicit allow list
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", CSRF_HEADER, "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After", "Content-Disposition"],
        max_age=600,
    )
    if settings.serverless:
        app.add_middleware(LazyMaintenance, settings=settings, database=database, storage=storage)
    if settings.client_ip_header:
        app.add_middleware(ClientIPMiddleware, header=settings.client_ip_header)

    app.include_router(api_router, prefix="/api")

    web_dist = settings.web_dist
    if web_dist is not None:
        # Mounted last so every /api route wins. Unknown paths get the export's 404 page.
        app.mount("/", WebApp(web_dist, hybrid=settings.mode == "hybrid"), name="web")
        logger.info("Serving the web interface from the API process")
    else:

        @app.get("/", include_in_schema=False)
        async def root() -> dict[str, str | None]:
            return {
                "name": settings.app_name,
                "mode": settings.mode,
                "api": "/api/v1",
                "health": "/api/v1/health",
                "docs": "/api/docs" if settings.docs_enabled else None,
            }

    return app


app = create_app()
