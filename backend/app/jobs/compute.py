"""Run one job spec: the actual video and AI work. No database access.

The same functions run in two places:

- inside the API process (local and server mode), driven by ``JobExecutor``;
- on a user's own computer (hybrid mode), driven by the worker agent.

Results are reported as *events* through ``io.emit``; the server validates each one
before it changes anything (see ``app.jobs.events``). A spec can only name files by
storage key, and every key must sit inside the job owner's own folder.
"""

from __future__ import annotations

import contextlib
import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings
from app.schemas.clip import CaptionStyle
from app.services.ai import provider_from_config
from app.services.media import (
    create_thumbnail_at,
    get_ffmpeg,
    media_info_dict,
    validate_media,
)
from app.services.storage import LocalStorage, StorageError
from app.services.url_import import download_video
from openclip_processing.captions import CaptionCue, build_ass, copy_fonts
from openclip_processing.clip_detection import DetectionOptions, detect_clips
from openclip_processing.errors import JobCancelled, ProcessingError
from openclip_processing.ffmpeg import FFmpegTools
from openclip_processing.framing import subject_position
from openclip_processing.render import ASPECT_RATIOS, RenderSpec, render_clip
from openclip_processing.transcription import TranscriptionOptions, WhisperTranscriber
from openclip_processing.types import ProgressCallback

logger = logging.getLogger("app.compute")

_EXTENSION_BY_FORMAT = (
    ("webm", ".webm"),
    ("matroska", ".mkv"),
    ("avi", ".avi"),
    ("mp4", ".mp4"),
    ("mov", ".mov"),
)


class JobIO(Protocol):
    """What a job needs from its surroundings: progress, cancellation and events."""

    job_id: str

    def progress(self, fraction: float, stage: str | None = None) -> None: ...

    def scaled(self, start: float, end: float) -> ProgressCallback: ...

    def should_cancel(self) -> bool: ...

    def emit(self, name: str, payload: dict[str, Any]) -> None: ...


@dataclass
class ComputeEnv:
    """Local resources for processing: settings, a storage folder and lazy AI models."""

    settings: Settings
    storage: LocalStorage
    get_transcriber: Callable[[], WhisperTranscriber]

    def ffmpeg(self) -> FFmpegTools:
        return get_ffmpeg(self.settings)


# ------------------------------------------------------------------ helpers
def _owned_key(spec: dict[str, Any], key: Any) -> str:
    """Refuse any storage key outside the job owner's folder (defense in depth)."""
    owner_id = str(spec.get("owner_id") or "")
    if not owner_id or not isinstance(key, str):
        raise ProcessingError("This job is missing its file reference.")
    prefix = LocalStorage.user_prefix(owner_id)
    inside = key == prefix or key.startswith(prefix + "/")
    if not inside or "\\" in key or any(part in {"", ".", ".."} for part in key.split("/")):
        raise ProcessingError("This job refers to a file outside its owner's folder.")
    return key


def _require(spec: dict[str, Any], field: str) -> Any:
    value = spec.get(field)
    if value in (None, ""):
        raise ProcessingError(f"This job is missing its {field.replace('_', ' ')}.")
    return value


def _extension_for(format_name: str, video_codec: str | None) -> str:
    names = format_name.lower().split(",")
    if "webm" in names and video_codec in {"vp8", "vp9", "av1"}:
        return ".webm"
    for container, extension in _EXTENSION_BY_FORMAT:
        if container in names:
            return ".mkv" if container == "webm" else extension
    return ".mp4"


def auto_frame_position(ffmpeg: FFmpegTools, source: Path, values: dict[str, Any]) -> float | None:
    """Subject-aware crop position for an aspect ratio (None if it cannot be computed)."""
    width, height = values.get("source_width"), values.get("source_height")
    if not width or not height:
        return None
    ratio_w, ratio_h = ASPECT_RATIOS[values["aspect_ratio"]]
    try:
        return subject_position(
            ffmpeg,
            source,
            start=values["start"],
            end=values["end"],
            source_width=width,
            source_height=height,
            ratio_w=ratio_w,
            ratio_h=ratio_h,
        )
    except ProcessingError as exc:
        logger.warning(
            "Automatic framing failed; keeping the current position", extra={"detail": exc.detail}
        )
        return None


# ------------------------------------------------------------------- import
def import_url(spec: dict[str, Any], env: ComputeEnv, io: JobIO) -> None:
    prefix = _owned_key(spec, _require(spec, "prefix"))
    destination = env.storage.ensure_parent(f"{prefix}/source.download")
    ffmpeg = env.ffmpeg()
    try:
        io.progress(0.0, "Connecting to the server")
        download_video(
            str(_require(spec, "url")),
            destination,
            max_bytes=int(_require(spec, "max_bytes")),
            allow_private=env.settings.url_import_allow_private_networks,
            progress=io.scaled(0.0, 0.92),
            should_cancel=io.should_cancel,
        )
        io.progress(0.93, "Checking the video")
        info = ffmpeg.probe(destination)
        validate_media(info, env.settings, max_seconds=spec.get("max_video_seconds"))
        final_key = f"{prefix}/source{_extension_for(info.format_name, info.video_codec)}"
        final_path = env.storage.path(final_key)
        destination.replace(final_path)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    thumbnail_key = create_thumbnail_at(ffmpeg, env.storage, prefix, final_path, info.duration)
    io.emit(
        "media_ready",
        {
            "project_id": spec["project_id"],
            "media_key": final_key,
            "thumbnail_key": thumbnail_key,
            "info": media_info_dict(info),
        },
    )
    io.progress(1.0, "Imported")


# ----------------------------------------------------- transcription + AI
def analysis(spec: dict[str, Any], env: ComputeEnv, io: JobIO) -> None:
    """Transcribe, then find clips. Either step can be switched off by the spec."""
    project_id = _require(spec, "project_id")
    transcribe, detect = bool(spec.get("transcribe")), bool(spec.get("detect"))
    duration = float(spec.get("duration") or 0)
    segments: list[dict[str, Any]] = list(spec.get("segments") or [])
    language = spec.get("transcript_language") or "en"
    transcribe_end = 0.7 if detect else 1.0

    if transcribe:
        media = env.storage.path(_owned_key(spec, spec.get("media_key")))
        if not media.is_file():
            raise ProcessingError("The video file for this project is missing. Upload it again.")
        io.emit("project_status", {"project_id": project_id, "status": "transcribing"})
        wanted = spec.get("language") or "en"
        audio_share = 0.06 * transcribe_end
        wav = env.settings.tmp_dir / f"{io.job_id}.wav"
        try:
            env.ffmpeg().extract_audio(
                media,
                wav,
                duration=duration,
                progress=io.scaled(0.0, audio_share),
                should_cancel=io.should_cancel,
            )
            transcript = env.get_transcriber().transcribe(
                wav,
                TranscriptionOptions(
                    model=str(_require(spec, "whisper_model")),
                    language=None if wanted == "auto" else wanted,
                    device=env.settings.whisper_device,
                    compute_type=env.settings.whisper_compute_type,
                ),
                duration=duration,
                progress=io.scaled(audio_share, transcribe_end),
                should_cancel=io.should_cancel,
            )
        finally:
            wav.unlink(missing_ok=True)
        data = transcript.to_dict()
        io.emit(
            "transcript",
            {
                "project_id": project_id,
                "language": transcript.language,
                "language_probability": transcript.language_probability,
                "model": transcript.model,
                "device": transcript.device,
                "duration": transcript.duration,
                "word_count": transcript.word_count,
                "segments": data["segments"],
                "warnings": data["warnings"],
            },
        )
        segments = data["segments"]
        language = transcript.language or "en"
        duration = duration or transcript.duration
        if not detect:
            io.progress(1.0, "Transcript ready")
            return

    start = transcribe_end if transcribe else 0.0
    options_in = spec.get("detection") or {}
    options = DetectionOptions(
        clip_count=int(options_in.get("clip_count", 8)),
        min_seconds=float(options_in.get("min_seconds", 20)),
        max_seconds=float(options_in.get("max_seconds", 60)),
        language=language,
    )
    provider = provider_from_config(dict(spec.get("ai") or {}), env.settings)
    io.emit(
        "project_status",
        {
            "project_id": project_id,
            "status": "analyzing",
            "ai_provider": provider.name,
            "ai_model": provider.model,
        },
    )
    label = "Ollama" if provider.name == "ollama" else "the external AI provider"
    io.progress(start, f"Asking {label} ({provider.model}) to find the best moments")
    suggestions = detect_clips(
        segments,
        duration,
        options,
        provider,
        progress=io.scaled(start, 1.0),
        should_cancel=io.should_cancel,
    )
    io.emit(
        "clips",
        {
            "project_id": project_id,
            "suggestions": [
                {
                    "start": s.start,
                    "end": s.end,
                    "title": s.title,
                    "description": s.description,
                    "reason": s.reason,
                    "score": s.score,
                }
                for s in suggestions
            ],
        },
    )
    io.progress(1.0, f"Found {len(suggestions)} clip suggestions")


# ------------------------------------------------------------------ render
def render(spec: dict[str, Any], env: ComputeEnv, io: JobIO) -> None:
    clip_id = _require(spec, "clip_id")
    source = env.storage.path(_owned_key(spec, spec.get("media_key")))
    if not source.is_file():
        raise ProcessingError("The source video is missing. Upload it again.")
    output_key = _owned_key(spec, spec.get("output_key"))
    if not output_key.endswith(".mp4"):
        raise ProcessingError("This job has an invalid output file.")
    aspect_ratio = spec.get("aspect_ratio")
    if aspect_ratio not in ASPECT_RATIOS:
        raise ProcessingError("This clip has an unsupported aspect ratio.")
    layout = spec.get("layout")
    if layout not in ("crop", "fit"):
        raise ProcessingError("This clip has an unsupported layout.")
    start = float(spec.get("start") or 0.0)
    end = float(_require(spec, "end"))
    if start < 0 or end - start < 1:
        raise ProcessingError("The clip times are outside the video. Adjust the start and end.")
    # Styles and cues are validated again here, right before they reach FFmpeg/libass.
    style = CaptionStyle.model_validate(spec.get("style") or {}).model_dump()
    cues = [
        CaptionCue(
            start=float(c["start"]), end=float(c["end"]), text=str(c["text"]), words=c.get("words")
        )
        for c in (spec.get("cues") or [])
    ]
    values: dict[str, Any] = {
        "start": start,
        "end": end,
        "layout": layout,
        "crop_position": min(max(float(spec.get("crop_position", 0.5)), 0.0), 1.0),
        "aspect_ratio": aspect_ratio,
        "source_width": spec.get("source_width"),
        "source_height": spec.get("source_height"),
    }

    workdir = env.settings.tmp_dir / f"render-{io.job_id}"
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        ffmpeg = env.ffmpeg()
        if spec.get("auto_frame") and layout == "crop":
            io.progress(0.0, "Finding the main subject")
            position = auto_frame_position(ffmpeg, source, values)
            if position is not None:
                values["crop_position"] = position
                io.emit("crop_position", {"clip_id": clip_id, "position": position})
        render_spec = RenderSpec(
            source=source,
            output=workdir / "clip.mp4",
            workdir=workdir,
            encoder=ffmpeg.pick_encoder(env.settings.video_encoder),
            **values,
        )
        if cues:
            width, height = render_spec.output_size()
            (workdir / "captions.ass").write_text(
                build_ass(cues, style, width=width, height=height), encoding="utf-8"
            )
            copy_fonts(workdir / "fonts")
            render_spec.subtitles, render_spec.fonts_dir = "captions.ass", "fonts"
        io.progress(0.0, "Rendering video")
        render_clip(
            ffmpeg, render_spec, progress=io.scaled(0.0, 0.95), should_cancel=io.should_cancel
        )
        final_path = env.storage.ensure_parent(output_key)
        Path(render_spec.output).replace(final_path)
        io.progress(0.97, "Creating thumbnail")
        thumb_key = output_key.rsplit(".", 1)[0] + ".jpg"
        with contextlib.suppress(ProcessingError):  # a missing thumbnail must not fail the export
            ffmpeg.thumbnail(
                final_path,
                env.storage.ensure_parent(thumb_key),
                at_seconds=min(1.0, render_spec.duration / 2),
                width=360,
            )
        size = final_path.stat().st_size
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    io.emit("clip_rendered", {"clip_id": clip_id, "output_key": output_key, "size_bytes": size})
    io.progress(1.0, "Clip exported")


# ------------------------------------------------------------------- purge
def purge_files(spec: dict[str, Any], env: ComputeEnv, io: JobIO) -> None:
    """Delete a project's folder and/or individual files (the owner asked for it)."""
    io.progress(0.0, "Deleting files")
    prefix = spec.get("prefix")
    targets: list[tuple[str, Any]] = [("tree", prefix)] if prefix else []
    targets += [("file", key) for key in spec.get("keys") or []]
    refused = 0
    for kind, raw in targets:
        try:
            key = _owned_key(spec, raw)
        except ProcessingError:
            refused += 1  # never delete anything outside the owner's folder
            continue
        with contextlib.suppress(StorageError, OSError):
            if kind == "tree":
                env.storage.delete_tree(key)
            else:
                env.storage.delete(key)
    if refused:
        logger.warning(
            "Refused to delete files outside the owner's folder", extra={"count": refused}
        )
    io.progress(1.0, "Files deleted")


HANDLERS: dict[str, Callable[[dict[str, Any], ComputeEnv, JobIO], None]] = {
    "import_url": import_url,
    "transcribe": analysis,
    "process": analysis,
    "detect_clips": analysis,
    "render_clip": render,
    "purge_files": purge_files,
}


def run(spec: dict[str, Any], env: ComputeEnv, io: JobIO) -> None:
    """Execute ``spec``. Raises ``ProcessingError`` (user-facing) or ``JobCancelled``."""
    handler = HANDLERS.get(str(spec.get("type")))
    if handler is None:
        raise ProcessingError(f"Unknown job type '{spec.get('type')}'.")
    if io.should_cancel():
        raise JobCancelled()
    handler(spec, env, io)
