"""Build a self-contained job spec from the database (runs on the server only).

A spec is plain JSON. It names files by storage key (never by path), carries typed
values (times, sizes, a validated caption style) and nothing a worker could execute.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Clip, Job, Project, User, Worker
from app.schemas.clip import CaptionStyle
from app.services.ai import load_ai_settings
from app.services.clips import caption_cues_for_clip
from app.services.projects import user_storage_bytes
from app.services.storage import LocalStorage
from openclip_processing.errors import ProcessingError

Builder = Callable[[Session, Settings, LocalStorage, Job], dict[str, Any]]


def _project(db: Session, job: Job) -> Project:
    project = db.get(Project, job.project_id) if job.project_id else None
    if project is None:
        raise ProcessingError("The project no longer exists.")
    return project


def _ai_config(db: Session, settings: Settings, job: Job) -> dict[str, Any]:
    if settings.media_on_workers:
        # The worker uses its own AI endpoint and keys; the server may only suggest a model.
        worker = db.get(Worker, job.worker_id) if job.worker_id else None
        return {"provider": "worker", "ollama_model": worker.preferred_model if worker else None}
    # The project owner's own choice (server mode) or this computer's setup (local mode).
    owner = db.get(User, _project(db, job).owner_id)
    return load_ai_settings(db, settings, owner)


def _import_url(db: Session, settings: Settings, storage: LocalStorage, job: Job) -> dict[str, Any]:
    project = _project(db, job)
    if not project.source_url:
        raise ProcessingError("The project to import into no longer exists.")
    max_bytes = settings.max_upload_bytes
    if settings.user_storage_quota_mb:
        remaining = settings.user_storage_quota_mb * 1024 * 1024 - user_storage_bytes(
            db, project.owner_id
        )
        if remaining <= 0:
            raise ProcessingError("Your storage quota is full. Delete some projects first.")
        max_bytes = min(max_bytes, remaining)
    return {
        "project_id": project.id,
        "prefix": LocalStorage.project_prefix(project.owner_id, project.id),
        "url": project.source_url,
        "max_bytes": max_bytes,
        "max_video_seconds": settings.max_video_minutes * 60,
    }


def _analysis(db: Session, settings: Settings, storage: LocalStorage, job: Job) -> dict[str, Any]:
    """Shared by ``transcribe``, ``detect_clips`` and ``process`` (both steps)."""
    project = _project(db, job)
    params = dict(job.params or {})
    has_transcript = project.transcript is not None
    if job.type == "transcribe":
        transcribe, detect = True, False
    elif job.type == "detect_clips":
        transcribe, detect = False, True
    else:
        transcribe, detect = bool(params.get("transcribe", True)) or not has_transcript, True
    if transcribe and not storage.has(project.media_key):
        raise ProcessingError("The video file for this project is missing. Upload it again.")
    if not transcribe and not has_transcript:
        raise ProcessingError("Transcribe the video before looking for clips.")

    spec: dict[str, Any] = {
        "project_id": project.id,
        "media_key": project.media_key,
        "duration": float(project.duration_seconds or 0),
        "transcribe": transcribe,
        "detect": detect,
        "language": params.get("language") or project.language,
        "whisper_model": params.get("whisper_model") or project.whisper_model,
    }
    if detect:
        spec["detection"] = {
            "clip_count": project.clip_count,
            "min_seconds": float(project.min_clip_seconds),
            "max_seconds": float(project.max_clip_seconds),
        }
        spec["ai"] = _ai_config(db, settings, job)
        if not transcribe and project.transcript is not None:
            spec["segments"] = list(project.transcript.segments or [])
            spec["transcript_language"] = project.transcript.language or "en"
            spec["duration"] = float(project.duration_seconds or project.transcript.duration)
    project.error_message = None
    return spec


def _render(db: Session, settings: Settings, storage: LocalStorage, job: Job) -> dict[str, Any]:
    clip = db.get(Clip, job.clip_id) if job.clip_id else None
    if clip is None:
        raise ProcessingError("The clip no longer exists.")
    project = clip.project
    if not storage.has(project.media_key):
        raise ProcessingError("The source video is missing. Upload it again.")
    duration = float(project.duration_seconds or 0)
    if clip.end_seconds > duration + 0.05 or clip.end_seconds - clip.start_seconds < 1:
        raise ProcessingError("The clip times are outside the video. Adjust the start and end.")
    style = CaptionStyle.model_validate(clip.caption_style or {}).model_dump()
    cues = caption_cues_for_clip(clip, project.transcript, style) if clip.captions_enabled else []
    layout = clip.layout if clip.layout in ("crop", "fit") else "fit"
    prefix = LocalStorage.project_prefix(project.owner_id, project.id)
    clip.status = "rendering"
    clip.error_message = None
    return {
        "project_id": project.id,
        "clip_id": clip.id,
        "media_key": project.media_key,
        "output_key": f"{prefix}/clips/{clip.id}.mp4",
        "start": float(clip.start_seconds),
        "end": float(min(clip.end_seconds, duration)),
        "layout": layout,
        "crop_position": float(clip.crop_position),
        "auto_frame": bool(clip.auto_frame and layout == "crop"),
        "aspect_ratio": clip.aspect_ratio or project.aspect_ratio,
        "source_width": project.width,
        "source_height": project.height,
        "style": style,
        "cues": [asdict(cue) for cue in cues],
    }


def _purge(db: Session, settings: Settings, storage: LocalStorage, job: Job) -> dict[str, Any]:
    params = dict(job.params or {})
    return {"prefix": params.get("prefix"), "keys": list(params.get("keys") or [])}


_BUILDERS: dict[str, Builder] = {
    "import_url": _import_url,
    "transcribe": _analysis,
    "process": _analysis,
    "detect_clips": _analysis,
    "render_clip": _render,
    "purge_files": _purge,
}


def build_spec(db: Session, settings: Settings, storage: LocalStorage, job: Job) -> dict[str, Any]:
    """Spec for ``job``. Also records the state changes that happen when a job starts."""
    builder = _BUILDERS.get(job.type)
    if builder is None:
        raise ProcessingError(f"Unknown job type '{job.type}'.")
    spec = builder(db, settings, storage, job)
    spec.update({"type": job.type, "job_id": job.id, "owner_id": job.owner_id})
    return spec
