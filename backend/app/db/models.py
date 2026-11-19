"""ORM models. Every user-owned row carries ``owner_id`` so queries can enforce isolation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Index, Integer, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, new_id, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    #: When the person confirmed being 18 or older (never assumed: NULL until they do).
    age_confirmed_at: Mapped[datetime | None] = mapped_column(default=None)
    #: When the email address was verified with a one-time code (NULL = not verified).
    email_verified_at: Mapped[datetime | None] = mapped_column(default=None)
    #: The latest code sent, and wrong guesses against it (for expiry, cooldown, limits).
    email_code_sent_at: Mapped[datetime | None] = mapped_column(default=None)
    email_code_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)
    #: Per-user preferences (for example ``retention_days``). Validated by the settings API.
    preferences: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")


class AuthSession(Base):
    """A login session. Only a SHA-256 hash of the cookie token is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    user_agent: Mapped[str | None] = mapped_column(String(200), default=None)

    user: Mapped[User] = relationship(lazy="joined")


class Project(Base):
    __tablename__ = "projects"
    # The project list: one user's projects, newest first.
    __table_args__ = (Index("ix_projects_owner_created", "owner_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), index=True, default="awaiting_upload")
    source_type: Mapped[str] = mapped_column(String(10), default="upload")
    source_url: Mapped[str | None] = mapped_column(String(2048), default=None)
    #: Public metadata about the source (for example a YouTube title and channel).
    source_meta: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    #: Hybrid mode: the paired worker that holds this project's video files.
    worker_id: Mapped[str | None] = mapped_column(
        ForeignKey("workers.id", ondelete="SET NULL"), index=True, default=None
    )
    original_filename: Mapped[str | None] = mapped_column(String(255), default=None)
    media_key: Mapped[str | None] = mapped_column(String(500), default=None)
    media_size_bytes: Mapped[int | None] = mapped_column(BigInteger, default=None)
    duration_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    width: Mapped[int | None] = mapped_column(Integer, default=None)
    height: Mapped[int | None] = mapped_column(Integer, default=None)
    fps: Mapped[float | None] = mapped_column(Float, default=None)
    video_codec: Mapped[str | None] = mapped_column(String(40), default=None)
    audio_codec: Mapped[str | None] = mapped_column(String(40), default=None)
    thumbnail_key: Mapped[str | None] = mapped_column(String(500), default=None)
    language: Mapped[str] = mapped_column(String(10), default="en")
    whisper_model: Mapped[str] = mapped_column(String(40), default="small")
    clip_count: Mapped[int] = mapped_column(Integer, default=8)
    #: Default output aspect ratio for this project's clips: 9:16, 4:5, 1:1 or 16:9.
    aspect_ratio: Mapped[str] = mapped_column(String(5), default="9:16", server_default="9:16")
    min_clip_seconds: Mapped[int] = mapped_column(Integer, default=20)
    max_clip_seconds: Mapped[int] = mapped_column(Integer, default=60)
    auto_process: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_provider: Mapped[str | None] = mapped_column(String(20), default=None)
    ai_model: Mapped[str | None] = mapped_column(String(120), default=None)
    error_message: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    transcript: Mapped[Transcript | None] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )
    clips: Mapped[list[Clip]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Clip.rank"
    )


class Transcript(Base):
    __tablename__ = "transcripts"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    language: Mapped[str] = mapped_column(String(10))
    language_probability: Mapped[float | None] = mapped_column(Float, default=None)
    model: Mapped[str] = mapped_column(String(40))
    device: Mapped[str] = mapped_column(String(10))
    duration: Mapped[float] = mapped_column(Float)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    segments: Mapped[list[Any]] = mapped_column(default=list)
    warnings: Mapped[list[Any]] = mapped_column(default=list)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    project: Mapped[Project] = relationship(back_populates="transcript")


class Clip(Base):
    __tablename__ = "clips"
    __table_args__ = (Index("ix_clips_owner_status", "owner_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[int | None] = mapped_column(Integer, default=None)
    source: Mapped[str] = mapped_column(String(10), default="ai")
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    suggested_start: Mapped[float | None] = mapped_column(Float, default=None)
    suggested_end: Mapped[float | None] = mapped_column(Float, default=None)
    status: Mapped[str] = mapped_column(String(20), index=True, default="suggested")
    layout: Mapped[str] = mapped_column(String(10), default="crop")
    #: Per-clip aspect ratio. ``None`` follows the project's default.
    aspect_ratio: Mapped[str | None] = mapped_column(String(5), default=None)
    crop_position: Mapped[float] = mapped_column(Float, default=0.5)
    #: When true, the crop position is computed from the video (subject detection) at export.
    auto_frame: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    captions_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    caption_style: Mapped[dict[str, Any]] = mapped_column(default=dict)
    caption_edits: Mapped[dict[str, Any]] = mapped_column(default=dict)
    output_key: Mapped[str | None] = mapped_column(String(500), default=None)
    output_size_bytes: Mapped[int | None] = mapped_column(BigInteger, default=None)
    rendered_at: Mapped[datetime | None] = mapped_column(default=None)
    error_message: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="clips")


class Job(Base):
    __tablename__ = "jobs"
    # Per-user limits and the queue (oldest waiting job first).
    __table_args__ = (
        Index("ix_jobs_owner_status", "owner_id", "status"),
        Index("ix_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, default=None
    )
    clip_id: Mapped[str | None] = mapped_column(
        ForeignKey("clips.id", ondelete="CASCADE"), index=True, default=None
    )
    type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), index=True, default="queued")
    stage: Mapped[str | None] = mapped_column(String(200), default=None)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str | None] = mapped_column(String(500), default=None)
    error_message: Mapped[str | None] = mapped_column(String(500), default=None)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    #: Hybrid mode: the worker this job is pinned to (it holds the files) and its lease.
    worker_id: Mapped[str | None] = mapped_column(
        ForeignKey("workers.id", ondelete="SET NULL"), index=True, default=None
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(default=None)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Worker(Base):
    """A user's own computer, paired to their account to process their videos (hybrid mode).

    Only a SHA-256 hash of the worker's bearer token is stored. Revoking a worker
    clears nothing on that computer but makes its token useless immediately.
    """

    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    platform: Mapped[str] = mapped_column(String(40), default="")
    app_version: Mapped[str] = mapped_column(String(20), default="")
    bridge_port: Mapped[int] = mapped_column(Integer, default=8787)
    #: Self-reported component status (FFmpeg, GPU, Ollama models). Display only.
    capabilities: Mapped[dict[str, Any]] = mapped_column(default=dict)
    preferred_model: Mapped[str | None] = mapped_column(String(120), default=None)
    status: Mapped[str] = mapped_column(String(10), index=True, default="active")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)


class PairingCode(Base):
    """Short-lived, single-use code that links a new worker to the user who created it."""

    __tablename__ = "pairing_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None] = mapped_column(default=None)


class TransferToken(Base):
    """Short-lived permission for the owner's browser to send or read files on one worker."""

    __tablename__ = "transfer_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("workers.id", ondelete="CASCADE"), index=True)
    #: "read" covers every file of the owner on that worker; "upload" is tied to one project.
    scope: Mapped[str] = mapped_column(String(10))
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]


class AppSetting(Base):
    """Installation-wide settings stored as JSON (local mode: this computer's AI setup)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(default=dict)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
