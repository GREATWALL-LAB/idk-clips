"""Application settings.

Values come from (highest priority first):
1. Real environment variables (prefix ``OPENCLIP_``).
2. ``<project root>/.env`` and then ``backend/.env`` if they exist.
3. The defaults below, which are safe for local, single-machine use.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent

DEFAULT_CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
ALLOWED_VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")


class Settings(BaseSettings):
    """Typed configuration for the backend."""

    model_config = SettingsConfigDict(
        env_prefix="OPENCLIP_",
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Run mode ----------------------------------------------------
    mode: Literal["local", "server", "hybrid"] = Field(
        default="local",
        description=(
            "local: single user, no account, loopback only, processing in this process. "
            "server: accounts, processing on this server. "
            "hybrid: accounts here, all video processing on each user's paired worker."
        ),
    )
    local_allow_remote: bool = Field(
        default=False,
        description="Local mode normally refuses non-loopback clients. Only enable this behind "
        "a container port that is published on 127.0.0.1.",
    )
    public_app_url: str | None = Field(
        default=None, description="Public URL of the web app (used in links and documentation)."
    )
    public_api_url: str | None = Field(
        default=None,
        description="Public URL of this API, shown in worker pairing instructions. "
        "Defaults to the URL the request arrived on.",
    )
    web_dist_dir: Path | None = Field(
        default=None,
        description="Static web build served by the API. Defaults to frontend/out when it exists.",
    )

    # --- Service -----------------------------------------------------
    app_name: str = "IDK Clips"
    forwarded_allow_ips: str | None = Field(
        default=None,
        description="Proxy addresses whose X-Forwarded-For headers are trusted (uvicorn). "
        "Default: 127.0.0.1 only.",
    )
    environment: Literal["development", "test", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    api_docs_enabled: bool | None = Field(
        default=None,
        description="Serve /docs and /openapi.json. Defaults to on, except in production.",
    )

    # --- Security ------------------------------------------------------
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_CORS_ORIGINS),
        description="Comma-separated list of frontend origins allowed to call the API.",
    )
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = Field(default=600, ge=1)
    login_rate_limit_per_minute: int = Field(default=10, ge=1)
    upload_rate_limit_per_hour: int = Field(default=30, ge=1)
    job_rate_limit_per_hour: int = Field(default=120, ge=1)
    register_rate_limit_per_hour: int = Field(
        default=5, ge=1, description="New accounts per client IP per hour."
    )
    failed_request_limit_per_minute: int = Field(
        default=60,
        ge=1,
        description="401/403/404 answers per client IP per minute before further requests "
        "from that address are refused for a while (slows down probing and guessing).",
    )
    max_active_jobs_per_user: int = Field(
        default=10,
        ge=0,
        description="Queued plus running jobs one user may have at a time (0 = no limit), so "
        "nobody can fill the processing queue for everyone else.",
    )
    daily_processing_minutes_per_user: int = Field(
        default=0,
        ge=0,
        description="Minutes of video one user may send for processing per 24 hours "
        "(0 = no limit). Useful for public servers in server mode.",
    )
    max_request_body_mb: int = Field(
        default=2, ge=1, description="Largest request body for ordinary API calls."
    )
    max_worker_payload_mb: int = Field(
        default=32, ge=1, description="Largest request body from a worker (transcripts)."
    )
    client_ip_header: str | None = Field(
        default=None,
        description="Header that carries the real client address when the API runs behind "
        "a proxy that overwrites it (for example 'x-real-ip' on Vercel). Leave unset "
        "otherwise: a client could send the header itself.",
    )

    # --- Account verification -------------------------------------------
    email_verification: Literal["supabase", "off"] = Field(
        default="supabase",
        description="How new accounts prove they own their email address. 'supabase' "
        "sends a one-time code through Supabase Auth. 'off' is for development and tests "
        "only and is refused in production.",
    )
    supabase_url: str | None = Field(
        default=None,
        description="Supabase project URL, for example https://abcd1234.supabase.co.",
    )
    supabase_anon_key: SecretStr | None = Field(
        default=None,
        description="The project's public anon (publishable) key. Never the service-role key.",
    )
    email_otp_ttl_minutes: int = Field(
        default=10,
        ge=1,
        le=60,
        description="How long a code is accepted. Set the same value as 'Email OTP "
        "Expiration' in Supabase (Authentication > Providers > Email).",
    )
    email_otp_resend_seconds: int = Field(default=60, ge=30, le=600)
    email_otp_max_attempts: int = Field(default=5, ge=1, le=10)

    # --- Accounts ------------------------------------------------------
    allow_registration: bool = Field(
        default=True,
        description="Allow public sign-ups. Every account is an ordinary user; there are "
        "no administrator roles.",
    )
    session_days: int = Field(default=14, ge=1, le=365)
    cookie_secure: bool | None = Field(
        default=None, description="Send cookies only over HTTPS. Defaults to on in production."
    )
    session_cookie_name: str = "openclip_session"

    # --- Logging -------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["console", "json"] = "console"

    # --- Storage & database ---------------------------------------------
    data_dir: Path = Field(default=PROJECT_ROOT / "data")
    tools_dir: Path = Field(default=PROJECT_ROOT / "tools")
    models_path: Path | None = Field(
        default=None, description="Where AI models are cached. Defaults to <data_dir>/models."
    )
    database_url: SecretStr | None = Field(
        default=None,
        description="SQLAlchemy URL. Defaults to SQLite in the data folder. "
        "Example: postgresql+psycopg://user:password@127.0.0.1:5432/openclip",
    )
    database_url_env: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{0,63}$",
        description="Name of another environment variable holding the database URL, for "
        "hosts that set their own (for example DATABASE_URL from Neon on Vercel). Used "
        "only when OPENCLIP_DATABASE_URL is not set.",
    )
    serverless: bool = Field(
        default=False,
        description="Run as short-lived serverless functions (for example on Vercel): "
        "migrations run when a function starts and housekeeping runs during requests "
        "instead of in a background loop. Hybrid mode with PostgreSQL only.",
    )
    ffmpeg_path: str | None = None
    ffprobe_path: str | None = None

    # --- Uploads & imports ------------------------------------------------
    max_upload_mb: int = Field(default=4096, ge=1)
    max_video_minutes: int = Field(default=240, ge=1)
    user_storage_quota_mb: int = Field(default=0, ge=0, description="0 means unlimited.")
    url_import_enabled: bool = True
    youtube_lookup_enabled: bool = Field(
        default=True,
        description="Look up public YouTube titles through YouTube's official oEmbed API. "
        "IDK Clips never downloads video from YouTube.",
    )
    url_import_allow_private_networks: bool = Field(
        default=False,
        description="Allow URL imports from private/LAN addresses (SSRF risk on shared servers).",
    )

    # --- Transcription -------------------------------------------------
    whisper_default_model: str = "small"
    whisper_device: Literal["auto", "cpu", "cuda"] = "auto"
    whisper_compute_type: str = "auto"

    # --- Video export ---------------------------------------------------
    video_encoder: Literal["auto", "libx264", "h264_nvenc"] = Field(
        default="auto", description="auto uses NVIDIA NVENC when it works, otherwise libx264."
    )

    # --- Background jobs ------------------------------------------------
    job_backend: Literal["local", "celery"] = Field(
        default="local", description="Where jobs run in local/server mode. Ignored in hybrid mode."
    )
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:6379/0")

    # --- Hybrid mode: paired workers --------------------------------------
    pairing_code_minutes: int = Field(default=10, ge=1, le=60)
    worker_lease_seconds: int = Field(
        default=90,
        ge=20,
        le=3600,
        description="A running job is re-queued when its worker is silent this long.",
    )
    worker_offline_seconds: int = Field(default=60, ge=10, le=3600)
    worker_job_max_attempts: int = Field(default=3, ge=1, le=10)
    worker_long_poll_seconds: int = Field(default=20, ge=0, le=55)
    transfer_token_minutes: int = Field(default=30, ge=1, le=240)
    max_workers_per_user: int = Field(default=5, ge=1, le=50)

    # --- Worker agent (runs on the user's computer in hybrid mode) ---------
    agent_bridge_port: int = Field(default=8787, ge=1024, le=65535)
    agent_ai_provider: Literal["ollama", "external"] = Field(
        default="ollama", description="Which AI provider this worker uses for clip detection."
    )
    agent_allow_http: bool = Field(
        default=False,
        description="Let the worker talk to a non-loopback server over plain HTTP (LAN testing only).",
    )

    # --- Retention --------------------------------------------------------
    default_retention_days: int = Field(
        default=0,
        ge=0,
        le=3650,
        description="Delete source videos this many days after upload. 0 keeps them until the user deletes them.",
    )

    # --- Local AI (Ollama) -------------------------------------------------
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str | None = None
    ollama_timeout_seconds: int = Field(default=600, ge=10)
    ollama_num_ctx: int = Field(default=8192, ge=2048)

    # --- Optional external AI (OpenAI-compatible) ----------------------
    external_ai_base_url: str | None = None
    external_ai_api_key: SecretStr | None = None
    external_ai_model: str | None = None
    external_ai_name: str = "External provider"

    # ------------------------------------------------------------------
    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _validate_origins(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for origin in value:
            if origin == "*":
                raise ValueError(
                    "Wildcard CORS origins are not allowed. List the frontend origins explicitly."
                )
            parts = urlsplit(origin)
            if (
                parts.scheme not in {"http", "https"}
                or not parts.netloc
                or parts.path not in {"", "/"}
                or parts.query
                or parts.fragment
            ):
                raise ValueError(
                    f"Invalid CORS origin {origin!r}. Use scheme://host[:port] without a path."
                )
            cleaned.append(f"{parts.scheme}://{parts.netloc}")
        return cleaned

    @field_validator("public_app_url", "public_api_url")
    @classmethod
    def _validate_public_url(cls, value: str | None) -> str | None:
        if not value:
            return None
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("Public URLs must be http(s) URLs such as https://app.example.com")
        return value.rstrip("/")

    @field_validator("data_dir", "tools_dir", "models_path", "web_dist_dir")
    @classmethod
    def _resolve_relative_paths(cls, value: Path | None) -> Path | None:
        # Relative paths are interpreted from the project root, never from the
        # current working directory, so scripts behave the same everywhere.
        if value is None:
            return None
        return value if value.is_absolute() else (PROJECT_ROOT / value).resolve()

    @field_validator("ollama_base_url", "external_ai_base_url")
    @classmethod
    def _validate_http_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("AI endpoints must be http(s) URLs such as http://127.0.0.1:11434")
        return value.rstrip("/")

    @field_validator("whisper_default_model")
    @classmethod
    def _validate_whisper_model(cls, value: str) -> str:
        from openclip_processing.transcription import WHISPER_MODELS

        if value not in WHISPER_MODELS:
            raise ValueError(
                f"Unknown Whisper model {value!r}. Options: {', '.join(WHISPER_MODELS)}"
            )
        return value

    # ------------------------------------------------------------------
    @property
    def docs_enabled(self) -> bool:
        if self.api_docs_enabled is not None:
            return self.api_docs_enabled
        return self.environment != "production"

    @property
    def accounts_enabled(self) -> bool:
        """Local mode has one implicit user; the other modes require sign-in."""
        return self.mode != "local"

    @property
    def jobs_mode(self) -> Literal["local", "celery", "remote"]:
        """Who executes jobs: this process, a Celery worker, or the users' paired workers."""
        return "remote" if self.mode == "hybrid" else self.job_backend

    @property
    def media_on_workers(self) -> bool:
        """In hybrid mode the server never stores video; files live on the user's worker."""
        return self.mode == "hybrid"

    @property
    def agent_dir(self) -> Path:
        return self.data_dir / "agent"

    @property
    def web_dist(self) -> Path | None:
        candidate = self.web_dist_dir or (PROJECT_ROOT / "frontend" / "out")
        return candidate if (candidate / "index.html").is_file() else None

    @property
    def secure_cookies(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.environment == "production"

    @property
    def sqlalchemy_url(self) -> str:
        raw = self._raw_database_url()
        if raw:
            return normalize_database_url(raw)
        return f"sqlite:///{(self.data_dir / 'openclip.db').as_posix()}"

    def _raw_database_url(self) -> str | None:
        if self.database_url is not None and self.database_url.get_secret_value():
            return self.database_url.get_secret_value()
        if self.database_url_env:
            return os.environ.get(self.database_url_env) or None
        return None

    @field_validator("supabase_url")
    @classmethod
    def _supabase_https(cls, value: str | None) -> str | None:
        if not value:
            return None
        parts = urlsplit(value.strip())
        # Plain http only for Supabase's local development stack (`supabase start`) on
        # this computer; production additionally requires https (see below).
        local = parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost"}
        if (
            not (parts.scheme == "https" or local)
            or not parts.hostname
            or parts.username
            or parts.password
        ):
            raise ValueError("OPENCLIP_SUPABASE_URL must be an https:// URL without credentials.")
        return value.strip().rstrip("/")

    @property
    def email_verification_required(self) -> bool:
        return self.accounts_enabled and self.email_verification == "supabase"

    @property
    def email_verification_ready(self) -> bool:
        return bool(
            self.email_verification_required
            and self.supabase_url
            and self.supabase_anon_key
            and self.supabase_anon_key.get_secret_value()
        )

    @property
    def registration_available(self) -> bool:
        """Open for sign-ups, and able to verify the addresses of new accounts."""
        return self.allow_registration and (
            not self.email_verification_required or self.email_verification_ready
        )

    @model_validator(mode="after")
    def _production_verifies_email(self) -> Settings:
        if self.environment == "production" and (self.supabase_url or "").startswith("http:"):
            raise ValueError("OPENCLIP_SUPABASE_URL must use https:// in production.")
        if (
            self.environment == "production"
            and self.accounts_enabled
            and (self.email_verification == "off")
        ):
            raise ValueError(
                "Production servers must verify email addresses: set "
                "OPENCLIP_EMAIL_VERIFICATION=supabase (see docs/CONFIGURATION.md)."
            )
        return self

    @model_validator(mode="after")
    def _serverless_needs_hybrid_and_postgres(self) -> Settings:
        if self.serverless:
            if self.mode != "hybrid":
                raise ValueError(
                    "OPENCLIP_SERVERLESS needs OPENCLIP_MODE=hybrid (no video on the server)."
                )
            if not (self._raw_database_url() or "").startswith(("postgres", "postgresql")):
                raise ValueError("OPENCLIP_SERVERLESS needs a PostgreSQL database URL.")
        return self

    @property
    def storage_dir(self) -> Path:
        return self.data_dir / "storage"

    @property
    def models_dir(self) -> Path:
        return self.models_path or self.data_dir / "models"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def external_ai_configured(self) -> bool:
        return bool(self.external_ai_base_url and self.external_ai_model)

    def secret_values(self) -> list[str]:
        """Secrets that must never appear in logs."""
        values = []
        if self.database_url_env and os.environ.get(self.database_url_env):
            raw = os.environ[self.database_url_env]
            values.append(raw)
            password = urlsplit(raw).password if "://" in raw else None
            if password:
                values.append(password)
        for secret in (
            self.external_ai_api_key,
            self.database_url,
            self.redis_url,
            self.supabase_anon_key,
        ):
            if secret is not None:
                raw = secret.get_secret_value()
                values.append(raw)
                # Also mask the password part of connection URLs.
                password = urlsplit(raw).password if "://" in raw else None
                if password:
                    values.append(password)
        return [v for v in values if v]


def normalize_database_url(url: str) -> str:
    """Accept the plain ``postgres://`` URLs hosting providers hand out."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings (cached)."""
    return Settings()
