"""Video validation and thumbnails on top of the processing library."""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import Settings
from app.db.models import Project
from app.services.storage import LocalStorage
from openclip_processing.errors import MediaValidationError, ProcessingError
from openclip_processing.ffmpeg import FFmpegTools, MediaInfo

logger = logging.getLogger("app.media")

MIN_VIDEO_SECONDS = 10


def get_ffmpeg(settings: Settings) -> FFmpegTools:
    """Locate FFmpeg (raises FFmpegNotFoundError with a user-facing message)."""
    return FFmpegTools.locate(
        ffmpeg_path=settings.ffmpeg_path,
        ffprobe_path=settings.ffprobe_path,
        search_dirs=[settings.tools_dir / "ffmpeg" / "bin"],
    )


def validate_media(
    info: MediaInfo, settings: Settings, *, max_seconds: float | None = None
) -> None:
    limit = settings.max_video_minutes * 60
    if max_seconds:
        limit = min(limit, max_seconds)
    if not info.has_video:
        raise MediaValidationError("This file has no video track. Upload a video file.")
    if not info.has_audio:
        raise MediaValidationError(
            "This video has no audio track, so there is no speech to transcribe."
        )
    if info.duration <= 0:
        raise MediaValidationError("The length of this video could not be determined.")
    if info.duration < MIN_VIDEO_SECONDS:
        raise MediaValidationError(f"The video is too short (minimum {MIN_VIDEO_SECONDS} seconds).")
    if info.duration > limit:
        raise MediaValidationError(
            f"The video is longer than the {round(limit / 60)}-minute limit on this server."
        )


def media_info_dict(info: MediaInfo) -> dict[str, object]:
    """The probe fields stored on a project (also sent by workers in hybrid mode)."""
    return {
        "duration": info.duration,
        "size_bytes": info.size_bytes,
        "width": info.width,
        "height": info.height,
        "fps": info.fps,
        "video_codec": info.video_codec,
        "audio_codec": info.audio_codec,
    }


def apply_media_info(project: Project, info: MediaInfo | dict[str, object]) -> None:
    values = media_info_dict(info) if isinstance(info, MediaInfo) else info
    project.duration_seconds = values["duration"]  # type: ignore[assignment]
    project.media_size_bytes = values.get("size_bytes")  # type: ignore[assignment]
    project.width = values.get("width")  # type: ignore[assignment]
    project.height = values.get("height")  # type: ignore[assignment]
    project.fps = values.get("fps")  # type: ignore[assignment]
    project.video_codec = values.get("video_codec")  # type: ignore[assignment]
    project.audio_codec = values.get("audio_codec")  # type: ignore[assignment]


def create_thumbnail(
    ffmpeg: FFmpegTools, storage: LocalStorage, project: Project, source: Path
) -> str | None:
    """Best effort: a missing thumbnail must never fail an upload."""
    prefix = LocalStorage.project_prefix(project.owner_id, project.id)
    return create_thumbnail_at(ffmpeg, storage, prefix, source, project.duration_seconds or 0)


def create_thumbnail_at(
    ffmpeg: FFmpegTools, storage: LocalStorage, prefix: str, source: Path, duration: float
) -> str | None:
    key = f"{prefix}/thumbnail.jpg"
    at = min(max(duration * 0.1, 1.0), 30.0)
    try:
        ffmpeg.thumbnail(source, storage.ensure_parent(key), at_seconds=at)
    except ProcessingError as exc:
        logger.warning("Thumbnail creation failed", extra={"detail": exc.detail})
        return None
    return key
