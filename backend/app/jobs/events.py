"""Validate job events and apply them to the database (runs on the server only).

Events are the *only* way processing results reach the database. In hybrid mode they
arrive over the network from a user's worker, so every event is treated as untrusted:

- the payload is validated against a strict schema (sizes, ranges, lengths);
- an event may only touch the project or clip its own job belongs to;
- storage keys must sit inside that project's folder.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import Clip, Job, Project, Transcript
from app.schemas.clip import CaptionStyle
from app.services.jobs import JobSubmitter, enqueue_job
from app.services.media import apply_media_info
from app.services.storage import LocalStorage

logger = logging.getLogger("app.jobs")


class EventError(Exception):
    """The event is malformed or not allowed for this job. Safe to show to the sender."""


# ------------------------------------------------------------------ schemas
class MediaInfoIn(BaseModel):
    duration: float = Field(gt=0, le=7 * 24 * 3600)
    size_bytes: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=1, le=16384)
    height: int | None = Field(default=None, ge=1, le=16384)
    fps: float | None = Field(default=None, ge=0, le=1000)
    video_codec: str | None = Field(default=None, max_length=40)
    audio_codec: str | None = Field(default=None, max_length=40)


class MediaReadyIn(BaseModel):
    project_id: str
    media_key: str = Field(max_length=500)
    thumbnail_key: str | None = Field(default=None, max_length=500)
    info: MediaInfoIn
    original_filename: str | None = Field(default=None, max_length=255)


class ProjectStatusIn(BaseModel):
    project_id: str
    status: Literal["transcribing", "analyzing"]
    ai_provider: str | None = Field(default=None, max_length=20)
    ai_model: str | None = Field(default=None, max_length=120)


class WordIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(max_length=200)
    probability: float | None = None


class SegmentIn(BaseModel):
    id: int = Field(ge=0)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(max_length=5000)
    words: list[WordIn] = Field(default_factory=list, max_length=5000)


class TranscriptIn(BaseModel):
    project_id: str
    language: str = Field(max_length=10)
    language_probability: float | None = None
    model: str = Field(max_length=40)
    device: str = Field(max_length=10)
    duration: float = Field(ge=0)
    word_count: int = Field(ge=0)
    segments: list[SegmentIn] = Field(max_length=200_000)
    warnings: list[str] = Field(default_factory=list, max_length=20)


class SuggestionIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    title: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)
    reason: str = Field(default="", max_length=1000)
    score: int = Field(ge=1, le=100)


class ClipsIn(BaseModel):
    project_id: str
    suggestions: list[SuggestionIn] = Field(max_length=50)


class CropPositionIn(BaseModel):
    clip_id: str
    position: float = Field(ge=0, le=1)


class ClipRenderedIn(BaseModel):
    clip_id: str
    output_key: str = Field(max_length=500)
    size_bytes: int = Field(ge=0)


_SCHEMAS: dict[str, type[BaseModel]] = {
    "media_ready": MediaReadyIn,
    "project_status": ProjectStatusIn,
    "transcript": TranscriptIn,
    "clips": ClipsIn,
    "crop_position": CropPositionIn,
    "clip_rendered": ClipRenderedIn,
}

#: Which events each job type may report.
ALLOWED_EVENTS: dict[str, frozenset[str]] = {
    "import_url": frozenset({"media_ready"}),
    "transcribe": frozenset({"project_status", "transcript"}),
    "process": frozenset({"project_status", "transcript", "clips"}),
    "detect_clips": frozenset({"project_status", "clips"}),
    "render_clip": frozenset({"crop_position", "clip_rendered"}),
    "purge_files": frozenset(),
}


# ------------------------------------------------------------------ helpers
def _project_for(db: Session, job: Job, project_id: str) -> Project:
    if not job.project_id or project_id != job.project_id:
        raise EventError("This event does not belong to the job's project.")
    project = db.get(Project, job.project_id)
    if project is None or project.owner_id != job.owner_id:
        raise EventError("The project no longer exists.")
    return project


def _clip_for(db: Session, job: Job, clip_id: str) -> Clip:
    if not job.clip_id or clip_id != job.clip_id:
        raise EventError("This event does not belong to the job's clip.")
    clip = db.get(Clip, job.clip_id)
    if clip is None or clip.owner_id != job.owner_id:
        raise EventError("The clip no longer exists.")
    return clip


def _check_key(project: Project, key: str | None) -> None:
    prefix = LocalStorage.project_prefix(project.owner_id, project.id) + "/"
    if key is not None and (not key.startswith(prefix) or ".." in key or "\\" in key):
        raise EventError("A file reference points outside the project's folder.")


def untouched_ai_suggestion(clip: Clip) -> bool:
    return (
        clip.source == "ai"
        and clip.status == "suggested"
        and not clip.output_key
        and not (clip.caption_edits or {}).get("lines")
        and clip.start_seconds == clip.suggested_start
        and clip.end_seconds == clip.suggested_end
    )


# ----------------------------------------------------------------- appliers
def register_media(
    db: Session,
    project: Project,
    data: MediaReadyIn,
    submitter: JobSubmitter | None,
    *,
    worker_id: str | None = None,
) -> None:
    """Record that a project's source video is in place and start processing if wanted."""
    _check_key(project, data.media_key)
    _check_key(project, data.thumbnail_key)
    project.media_key = data.media_key
    project.thumbnail_key = data.thumbnail_key
    if data.original_filename:
        project.original_filename = data.original_filename
    if worker_id:
        project.worker_id = worker_id
    apply_media_info(project, data.info.model_dump())
    project.status = "uploaded"
    project.error_message = None
    if project.auto_process and submitter is not None:
        project.status = "queued"
        db.flush()
        enqueue_job(
            db,
            submitter,
            owner_id=project.owner_id,
            job_type="process",
            project_id=project.id,
            allow_parallel=True,
        )


def _media_ready(db: Session, job: Job, data: MediaReadyIn, submitter: JobSubmitter | None) -> None:
    project = _project_for(db, job, data.project_id)
    register_media(db, project, data, submitter, worker_id=job.worker_id)


def _project_status(db: Session, job: Job, data: ProjectStatusIn, _: Any) -> None:
    project = _project_for(db, job, data.project_id)
    if project.status == "deleting":
        return
    project.status = data.status
    project.error_message = None
    if data.status == "analyzing":
        project.ai_provider = data.ai_provider
        project.ai_model = data.ai_model


def _transcript(db: Session, job: Job, data: TranscriptIn, _: Any) -> None:
    project = _project_for(db, job, data.project_id)
    if project.transcript is not None:
        db.delete(project.transcript)
        db.flush()
    db.add(
        Transcript(
            project_id=project.id,
            language=data.language,
            language_probability=data.language_probability,
            model=data.model,
            device=data.device,
            duration=data.duration,
            word_count=data.word_count,
            segments=[segment.model_dump() for segment in data.segments],
            warnings=list(data.warnings),
        )
    )
    if project.status != "deleting":
        project.status = "transcribed"


def _clips(db: Session, job: Job, data: ClipsIn, _: Any) -> None:
    project = _project_for(db, job, data.project_id)
    duration = float(project.duration_seconds or 0)
    # Replace earlier AI suggestions the user has not touched; keep everything else.
    kept = []
    for clip in list(project.clips):
        if untouched_ai_suggestion(clip):
            db.delete(clip)
        else:
            kept.append(clip)
    next_rank = max((c.rank for c in kept), default=-1) + 1
    style = CaptionStyle().model_dump()
    added = 0
    for suggestion in data.suggestions:
        end = min(suggestion.end, duration) if duration else suggestion.end
        if end - suggestion.start < 1:
            continue  # outside the real video; never stored
        db.add(
            Clip(
                project_id=project.id,
                owner_id=project.owner_id,
                rank=next_rank + added,
                title=" ".join(suggestion.title.split()) or "Clip",
                description=suggestion.description,
                reason=suggestion.reason,
                score=suggestion.score,
                source="ai",
                start_seconds=round(suggestion.start, 3),
                end_seconds=round(end, 3),
                suggested_start=round(suggestion.start, 3),
                suggested_end=round(end, 3),
                status="suggested",
                caption_style=style,
            )
        )
        added += 1
    if project.status != "deleting":
        project.status = "ready"


def _crop_position(db: Session, job: Job, data: CropPositionIn, _: Any) -> None:
    _clip_for(db, job, data.clip_id).crop_position = data.position


def _clip_rendered(db: Session, job: Job, data: ClipRenderedIn, _: Any) -> None:
    clip = _clip_for(db, job, data.clip_id)
    _check_key(clip.project, data.output_key)
    if not data.output_key.endswith(f"/clips/{clip.id}.mp4"):
        raise EventError("The exported file does not match this clip.")
    clip.output_key = data.output_key
    clip.output_size_bytes = data.size_bytes
    clip.rendered_at = utcnow()
    clip.status = "ready"
    clip.error_message = None


_APPLIERS = {
    "media_ready": _media_ready,
    "project_status": _project_status,
    "transcript": _transcript,
    "clips": _clips,
    "crop_position": _crop_position,
    "clip_rendered": _clip_rendered,
}


def apply_event(
    db: Session,
    job: Job,
    name: str,
    payload: dict[str, Any],
    submitter: JobSubmitter | None = None,
) -> None:
    """Validate and apply one event for ``job``. The caller commits."""
    if name not in ALLOWED_EVENTS.get(job.type, frozenset()):
        raise EventError(f"Event '{name}' is not allowed for a {job.type} job.")
    try:
        data = _SCHEMAS[name].model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first.get("loc", ()))
        raise EventError(
            f"Invalid '{name}' event ({location}: {first.get('msg', 'invalid')})."
        ) from exc
    _APPLIERS[name](db, job, data, submitter)  # type: ignore[arg-type]
    logger.debug("Job event applied", extra={"job_id": job.id, "event": name})
