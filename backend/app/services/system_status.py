"""Checks the external components IDK Clips depends on.

Results are cached for a few seconds because the dashboard polls this endpoint.
Responses describe *whether* something works and how to fix it; they never
include file-system paths, internal URLs or credentials.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

import httpx

from app.core.config import Settings
from app.db.session import Database
from app.schemas.system import ComponentStatus, SystemStatusResponse
from openclip_processing.binaries import inspect_binary

FFMPEG_HINT = (
    "Install FFmpeg. On Windows run scripts\\windows\\install-ffmpeg.cmd (portable copy in "
    "tools/ffmpeg) or see docs/INSTALLATION.md. On Linux: sudo apt install ffmpeg."
)
OLLAMA_HINT = (
    "Start Ollama (open the Ollama app or run 'ollama serve') and check "
    "OPENCLIP_OLLAMA_BASE_URL. Install it from https://ollama.com if needed."
)


class SystemStatusService:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        cache_seconds: float = 5.0,
        database: Database | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._cache_seconds = cache_seconds
        self._database = database
        self._cached: tuple[float, SystemStatusResponse] | None = None
        self._lock = asyncio.Lock()

    async def get_status(self) -> SystemStatusResponse:
        async with self._lock:
            now = time.monotonic()
            if self._cached and now - self._cached[0] < self._cache_seconds:
                return self._cached[1]
            status = await self._collect()
            self._cached = (now, status)
            return status

    async def _collect(self) -> SystemStatusResponse:
        ffmpeg, ffprobe, ollama, database, jobs, gpu = await asyncio.gather(
            asyncio.to_thread(self._binary_status, "ffmpeg", "FFmpeg", self._settings.ffmpeg_path),
            asyncio.to_thread(
                self._binary_status, "ffprobe", "FFprobe", self._settings.ffprobe_path
            ),
            self._ollama_status(),
            asyncio.to_thread(self._database_status),
            asyncio.to_thread(self._jobs_status),
            asyncio.to_thread(self._gpu_status),
        )
        components = [database, jobs, ffmpeg, ffprobe, gpu, ollama]
        degraded = any(c.required and c.status != "ok" for c in components)
        return SystemStatusResponse(
            status="degraded" if degraded else "ok",
            components=components,
            checked_at=datetime.now(UTC),
        )

    def _database_status(self) -> ComponentStatus:
        kind = "PostgreSQL" if self._settings.sqlalchemy_url.startswith("postgresql") else "SQLite"
        if self._database is None:
            return ComponentStatus(
                key="database", name="Database", status="not_configured", required=True, detail=kind
            )
        ok = self._database.ping()
        return ComponentStatus(
            key="database",
            name="Database",
            status="ok" if ok else "unavailable",
            required=True,
            detail=kind,
            hint=None
            if ok
            else "Check OPENCLIP_DATABASE_URL and that the database server is running.",
        )

    def _jobs_status(self) -> ComponentStatus:
        if self._settings.jobs_mode == "remote":
            return ComponentStatus(
                key="jobs",
                name="Background jobs",
                status="ok",
                required=True,
                detail="Processed by each user's paired worker",
            )
        if self._settings.jobs_mode == "local":
            return ComponentStatus(
                key="jobs",
                name="Background jobs",
                status="ok",
                required=True,
                detail="Built-in worker (one job at a time)",
            )
        try:
            import redis

            client = redis.Redis.from_url(
                self._settings.redis_url.get_secret_value(),
                socket_timeout=2,
                socket_connect_timeout=2,
            )
            client.ping()
        except Exception:
            return ComponentStatus(
                key="jobs",
                name="Background jobs",
                status="unavailable",
                required=True,
                detail="Celery + Redis: Redis is not reachable",
                hint="Start Redis and a worker (scripts\\windows\\start-worker.cmd), "
                "or set OPENCLIP_JOB_BACKEND=local.",
            )
        return ComponentStatus(
            key="jobs", name="Background jobs", status="ok", required=True, detail="Celery + Redis"
        )

    def _gpu_status(self) -> ComponentStatus:
        try:
            import ctranslate2

            gpus = ctranslate2.get_cuda_device_count()
        except Exception:
            gpus = 0
        if self._settings.whisper_device == "cpu":
            detail = "CPU (configured)"
        elif gpus:
            detail = "NVIDIA GPU detected; the CPU is used if CUDA libraries are missing"
        else:
            detail = "CPU (no NVIDIA GPU detected)"
        return ComponentStatus(
            key="transcription",
            name="Speech transcription",
            status="ok",
            required=True,
            detail=detail,
        )

    def _binary_status(self, key: str, label: str, explicit: str | None) -> ComponentStatus:
        search_dirs = [self._settings.tools_dir / "ffmpeg" / "bin"]
        info = inspect_binary(key, explicit=explicit, search_dirs=search_dirs)
        if info is None:
            if explicit:
                return ComponentStatus(
                    key=key,
                    name=label,
                    status="misconfigured",
                    required=True,
                    detail=f"The configured {label} path does not exist.",
                    hint=f"Fix OPENCLIP_{key.upper()}_PATH or remove it to auto-detect {label}.",
                )
            return ComponentStatus(
                key=key,
                name=label,
                status="unavailable",
                required=True,
                detail=f"{label} was not found.",
                hint=FFMPEG_HINT,
            )
        if info.version is None:
            return ComponentStatus(
                key=key,
                name=label,
                status="misconfigured",
                required=True,
                source=info.source,
                detail=f"{label} was found but did not run correctly.",
                hint=FFMPEG_HINT,
            )
        return ComponentStatus(
            key=key,
            name=label,
            status="ok",
            required=True,
            version=info.version,
            source=info.source,
        )

    async def _ollama_status(self) -> ComponentStatus:
        base = self._settings.ollama_base_url
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=httpx.Timeout(3.0)
            ) as client:
                version_resp = await client.get(f"{base}/api/version")
                version_resp.raise_for_status()
                tags_resp = await client.get(f"{base}/api/tags")
                tags_resp.raise_for_status()
            version = str(version_resp.json().get("version") or "") or None
            models = tags_resp.json().get("models") or []
        except (httpx.HTTPError, ValueError):
            return ComponentStatus(
                key="ollama",
                name="Ollama (local AI)",
                status="unavailable",
                required=False,
                detail="Ollama is not reachable.",
                hint=OLLAMA_HINT,
            )
        count = len(models)
        return ComponentStatus(
            key="ollama",
            name="Ollama (local AI)",
            status="ok",
            required=False,
            version=version,
            detail=f"{count} model{'s' if count != 1 else ''} installed",
            hint=None if count else "Pull a model, for example: ollama pull gemma3:4b",
        )
