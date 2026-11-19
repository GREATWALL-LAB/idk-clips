"""Clip queries (owner-scoped), serialization and caption lines."""

from __future__ import annotations

from itertools import pairwise
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, UnprocessableError
from app.db.models import Clip, Job, Project
from app.schemas.clip import CaptionLine, CaptionStyle, ClipOut
from app.schemas.job import JobOut
from app.services.storage import LocalStorage

ACTIVE = ("queued", "running")
MIN_CLIP_SECONDS = 3.0
MAX_CLIP_SECONDS = 600.0


def get_owned_clip(db: Session, user_id: str, clip_id: str) -> Clip:
    clip = db.scalar(select(Clip).where(Clip.id == clip_id, Clip.owner_id == user_id))
    if clip is None or clip.project.status == "deleting":
        raise NotFoundError("Clip not found.")
    return clip


def active_render_jobs(db: Session, clip_ids: list[str]) -> dict[str, Job]:
    if not clip_ids:
        return {}
    jobs = db.scalars(
        select(Job)
        .where(Job.clip_id.in_(clip_ids), Job.status.in_(ACTIVE))
        .order_by(Job.created_at.desc())
    ).all()
    result: dict[str, Job] = {}
    for job in jobs:
        if job.clip_id and job.clip_id not in result:
            result[job.clip_id] = job
    return result


def clip_out(
    clip: Clip,
    storage: LocalStorage,
    *,
    project_name: str | None = None,
    active_job: Job | None = None,
) -> ClipOut:
    rendered = storage.has(clip.output_key)
    thumb_key = clip.output_key.rsplit(".", 1)[0] + ".jpg" if clip.output_key else None
    return ClipOut(
        id=clip.id,
        project_id=clip.project_id,
        project_name=project_name,
        rank=clip.rank,
        title=clip.title,
        description=clip.description,
        reason=clip.reason,
        score=clip.score,
        source=clip.source,
        start_seconds=clip.start_seconds,
        end_seconds=clip.end_seconds,
        duration_seconds=round(clip.end_seconds - clip.start_seconds, 3),
        suggested_start=clip.suggested_start,
        suggested_end=clip.suggested_end,
        status=clip.status,
        layout=clip.layout,
        crop_position=clip.crop_position,
        auto_frame=clip.auto_frame,
        aspect_ratio=clip.aspect_ratio or clip.project.aspect_ratio,
        aspect_ratio_overridden=bool(clip.aspect_ratio),
        worker_id=clip.project.worker_id,
        media_host="worker" if storage.remote else "server",
        captions_enabled=clip.captions_enabled,
        caption_style=CaptionStyle.model_validate(clip.caption_style or {}),
        has_caption_edits=bool((clip.caption_edits or {}).get("lines")),
        output_size_bytes=clip.output_size_bytes if rendered else None,
        rendered_at=clip.rendered_at if rendered else None,
        error_message=clip.error_message,
        preview_url=f"/clips/{clip.id}/file" if rendered else None,
        download_url=f"/clips/{clip.id}/file?download=true" if rendered else None,
        thumbnail_url=f"/clips/{clip.id}/thumbnail" if storage.has(thumb_key) else None,
        active_job=JobOut.model_validate(active_job) if active_job else None,
        created_at=clip.created_at,
        updated_at=clip.updated_at,
    )


def clips_out(
    db: Session, clips: list[Clip], storage: LocalStorage, *, with_project: bool = False
) -> list[ClipOut]:
    jobs = active_render_jobs(db, [c.id for c in clips])
    names: dict[str, str] = {}
    if with_project and clips:
        rows = db.execute(
            select(Project.id, Project.name).where(Project.id.in_({c.project_id for c in clips}))
        ).all()
        names = {row[0]: row[1] for row in rows}
    return [
        clip_out(c, storage, project_name=names.get(c.project_id), active_job=jobs.get(c.id))
        for c in clips
    ]


def validate_clip_range(start: float, end: float, duration: float | None) -> tuple[float, float]:
    start, end = round(float(start), 3), round(float(end), 3)
    if end <= start:
        raise UnprocessableError("The clip must end after it starts.")
    if end - start < MIN_CLIP_SECONDS:
        raise UnprocessableError(f"Clips must be at least {MIN_CLIP_SECONDS:.0f} seconds long.")
    if end - start > MAX_CLIP_SECONDS:
        raise UnprocessableError(f"Clips can be at most {MAX_CLIP_SECONDS / 60:.0f} minutes long.")
    if duration is not None and end > duration + 0.05:
        raise UnprocessableError("The clip cannot end after the video ends.")
    return start, min(end, duration) if duration is not None else end


def edited_lines(clip: Clip) -> list[CaptionLine] | None:
    """User-edited captions, stored in source-video time, returned relative to the clip."""
    stored = (clip.caption_edits or {}).get("lines")
    if not stored:
        return None
    duration = clip.end_seconds - clip.start_seconds
    lines: list[CaptionLine] = []
    for line in stored:
        start = float(line["start"]) - clip.start_seconds
        end = float(line["end"]) - clip.start_seconds
        if end <= 0 or start >= duration:
            continue  # outside the current clip range
        lines.append(
            CaptionLine(
                start=round(max(start, 0.0), 3), end=round(min(end, duration), 3), text=line["text"]
            )
        )
    return lines


def store_edited_lines(clip: Clip, lines: list[CaptionLine]) -> None:
    duration = clip.end_seconds - clip.start_seconds
    cleaned = []
    for line in sorted(lines, key=lambda item: item.start):
        if line.end <= line.start:
            raise UnprocessableError("Each caption line must end after it starts.")
        if line.start > duration + 0.05:
            raise UnprocessableError("A caption line starts after the end of the clip.")
        cleaned.append(
            {
                "start": round(clip.start_seconds + line.start, 3),
                "end": round(clip.start_seconds + min(line.end, duration), 3),
                "text": line.text,
            }
        )
    clip.caption_edits = {"lines": cleaned} if cleaned else {}


def caption_cues_for_clip(clip: Clip, transcript: Any, style: dict[str, Any]) -> list[Any]:
    """Caption cues for rendering: user edits (static) or transcript words (highlighted)."""
    from openclip_processing.captions import CaptionCue

    edited = edited_lines(clip)
    if edited is not None:
        return [CaptionCue(start=line.start, end=line.end, text=line.text) for line in edited]
    if transcript is None:
        return []
    words = words_in_range(transcript.segments or [], clip.start_seconds, clip.end_seconds)
    per_line = max(1, int(style.get("words_per_line", 4)))
    cues = []
    for index in range(0, len(words), per_line):
        group = words[index : index + per_line]
        relative = [
            {
                "start": max(w["start"] - clip.start_seconds, 0.0),
                "end": min(w["end"], clip.end_seconds) - clip.start_seconds,
                "text": w["text"],
            }
            for w in group
        ]
        text = " ".join(w["text"].strip() for w in group).strip()
        if text:
            cues.append(
                CaptionCue(
                    start=relative[0]["start"], end=relative[-1]["end"], text=text, words=relative
                )
            )
    # Keep each caption on screen until the next one starts (avoids flicker in short pauses).
    for current, following in pairwise(cues):
        if 0 < following.start - current.end < 0.6:
            current.end = following.start
    return cues


def words_in_range(
    segments: list[dict[str, Any]], start: float, end: float
) -> list[dict[str, Any]]:
    """Transcript words whose midpoint falls inside [start, end)."""
    words: list[dict[str, Any]] = []
    for segment in segments:
        if segment["end"] < start or segment["start"] > end:
            continue
        for word in segment.get("words") or []:
            middle = (word["start"] + word["end"]) / 2
            if start <= middle < end:
                words.append(word)
    return words


def generated_caption_lines(
    segments: list[dict[str, Any]], start: float, end: float, words_per_line: int
) -> list[CaptionLine]:
    """Group the real transcript words into short caption lines (times relative to the clip)."""
    words = words_in_range(segments, start, end)
    lines: list[CaptionLine] = []
    for index in range(0, len(words), max(1, words_per_line)):
        group = words[index : index + words_per_line]
        text = " ".join(w["text"].strip() for w in group).strip()
        if not text:
            continue
        lines.append(
            CaptionLine(
                start=round(max(group[0]["start"] - start, 0.0), 3),
                end=round(min(group[-1]["end"], end) - start, 3),
                text=text,
            )
        )
    return lines
