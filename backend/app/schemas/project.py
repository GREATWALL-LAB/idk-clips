from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.schemas.job import JobOut
from openclip_processing.transcription import LANGUAGES, WHISPER_MODELS

#: Output aspect ratios (see processing/openclip_processing/render.py for the pixel sizes).
AspectRatio = Literal["9:16", "4:5", "1:1", "16:9"]

ProjectStatus = Literal[
    "awaiting_upload",
    "importing",
    "uploaded",
    "queued",
    "transcribing",
    "transcribed",
    "analyzing",
    "ready",
    "failed",
]


def check_language(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().lower()
    if value != "auto" and value not in LANGUAGES:
        raise ValueError("Unsupported language. Use 'auto' or one of the listed language codes.")
    return value


def check_whisper_model(value: str | None) -> str | None:
    if value is not None and value not in WHISPER_MODELS:
        raise ValueError(f"Unknown speech model. Options: {', '.join(WHISPER_MODELS)}")
    return value


class ProcessingOptions(BaseModel):
    language: str = Field(default="en", description="ISO code, or 'auto' to detect.")
    whisper_model: str | None = Field(default=None, description="Defaults to the server setting.")
    clip_count: int = Field(default=8, ge=5, le=10)
    min_clip_seconds: int = Field(default=20, ge=5, le=120)
    max_clip_seconds: int = Field(default=60, ge=10, le=180)
    auto_process: bool = True
    aspect_ratio: AspectRatio = Field(default="9:16", description="Output shape for every clip.")

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        return check_language(value) or "en"

    @field_validator("whisper_model")
    @classmethod
    def _model(cls, value: str | None) -> str | None:
        return check_whisper_model(value)

    @model_validator(mode="after")
    def _lengths(self) -> ProcessingOptions:
        if self.min_clip_seconds >= self.max_clip_seconds:
            raise ValueError("min_clip_seconds must be smaller than max_clip_seconds.")
        if (
            self.whisper_model
            and self.whisper_model.endswith(".en")
            and self.language not in ("en", "auto")
        ):
            raise ValueError("English-only speech models can only transcribe English.")
        return self


class ProjectCreate(ProcessingOptions):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Name cannot be empty.")
        return cleaned


class ProjectImportUrl(ProcessingOptions):
    url: HttpUrl
    name: str | None = Field(default=None, max_length=200)


class ProjectFromYouTube(ProcessingOptions):
    """A project that references a YouTube video. The file itself is added afterwards."""

    url: str = Field(min_length=10, max_length=2048)
    name: str | None = Field(default=None, max_length=200)


class YouTubeLookupRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2048)


class YouTubeVideoOut(BaseModel):
    video_id: str
    url: str
    title: str | None = None
    author_name: str | None = None
    author_url: str | None = None
    thumbnail_url: str | None = None
    #: Why public details are missing (for example a private video). The link is still usable.
    notice: str | None = None
    how_to_get_the_file: str


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    language: str | None = None
    whisper_model: str | None = None
    clip_count: int | None = Field(default=None, ge=5, le=10)
    min_clip_seconds: int | None = Field(default=None, ge=5, le=120)
    max_clip_seconds: int | None = Field(default=None, ge=10, le=180)
    aspect_ratio: AspectRatio | None = None

    @field_validator("language")
    @classmethod
    def _language(cls, value: str | None) -> str | None:
        return check_language(value)

    @field_validator("whisper_model")
    @classmethod
    def _model(cls, value: str | None) -> str | None:
        return check_whisper_model(value)


class ProcessRequest(BaseModel):
    """Optional overrides when (re)starting processing."""

    language: str | None = None
    whisper_model: str | None = None
    transcribe: bool = Field(
        default=True,
        description="Set to false to keep the existing transcript and only detect clips.",
    )

    @field_validator("language")
    @classmethod
    def _language(cls, value: str | None) -> str | None:
        return check_language(value)

    @field_validator("whisper_model")
    @classmethod
    def _model(cls, value: str | None) -> str | None:
        return check_whisper_model(value)


class ClipCounts(BaseModel):
    total: int = 0
    ready: int = 0


class ProjectOut(BaseModel):
    id: str
    name: str
    status: str
    source_type: str
    source_url: str | None
    source_meta: dict[str, Any] = Field(default_factory=dict)
    #: Hybrid mode: the paired worker holding the files ("media_host" says where to fetch them).
    worker_id: str | None = None
    media_host: Literal["server", "worker"] = "server"
    original_filename: str | None
    media_size_bytes: int | None
    duration_seconds: float | None
    width: int | None
    height: int | None
    fps: float | None
    language: str
    whisper_model: str
    clip_count: int
    aspect_ratio: str
    min_clip_seconds: int
    max_clip_seconds: int
    auto_process: bool
    ai_provider: str | None
    ai_model: str | None
    error_message: str | None
    has_media: bool
    media_url: str | None
    thumbnail_url: str | None
    has_transcript: bool
    clips: ClipCounts
    active_job: JobOut | None
    created_at: datetime
    updated_at: datetime


class ProjectList(BaseModel):
    items: list[ProjectOut]
    total: int
