"""Clips: list, create (manual), edit timing/captions/layout, render, preview, download, delete."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, JobCapacity, RunnerDep, SettingsDep, StorageDep
from app.core.errors import ConflictError, NotFoundError, ServiceUnavailableError
from app.core.rate_limit import route_limit
from app.db.models import Clip, Job, Project
from app.jobs.compute import auto_frame_position
from app.schemas.clip import CaptionStyle, ClipCaptions, ClipCreate, ClipList, ClipOut, ClipUpdate
from app.schemas.job import JobOut
from app.services.clips import (
    ACTIVE,
    clip_out,
    clips_out,
    edited_lines,
    generated_caption_lines,
    get_owned_clip,
    store_edited_lines,
    validate_clip_range,
)
from app.services.files import safe_download_name
from app.services.jobs import enqueue_job, request_cancel
from app.services.media import get_ffmpeg
from app.services.projects import HIDDEN_STATUSES, get_owned_project
from app.services.storage import LocalStorage
from openclip_processing.errors import ProcessingError

router = APIRouter(tags=["clips"])

ClipId = Annotated[uuid.UUID, "Clip ID"]
ProjectId = Annotated[uuid.UUID, "Project ID"]

# Changing any of these makes an existing export outdated.
RENDER_FIELDS = {
    "aspect_ratio",
    "start_seconds",
    "end_seconds",
    "layout",
    "crop_position",
    "auto_frame",
    "captions_enabled",
    "caption_style",
    "caption_lines",
}


def _active_render(db, clip_id: str) -> Job | None:  # type: ignore[no-untyped-def]
    return db.scalar(select(Job).where(Job.clip_id == clip_id, Job.status.in_(ACTIVE)))


def _on_worker(storage: LocalStorage) -> None:
    """Hybrid mode: the server holds no video. The browser reads files from the worker."""
    if storage.remote:
        raise NotFoundError(
            "This file is stored on your worker. Open IDK Clips on that computer to play "
            "or download it.",
            code="media_on_worker",
        )


@router.get("/projects/{project_id}/clips", response_model=ClipList, summary="Clips of a project")
def project_clips(
    project_id: ProjectId, user: CurrentUser, db: DbSession, storage: StorageDep
) -> ClipList:
    project = get_owned_project(db, user.id, str(project_id))
    clips = list(project.clips)
    return ClipList(items=clips_out(db, clips, storage), total=len(clips))


@router.post(
    "/projects/{project_id}/clips",
    response_model=ClipOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a clip manually",
)
def create_clip(
    project_id: ProjectId, body: ClipCreate, user: CurrentUser, db: DbSession, storage: StorageDep
) -> ClipOut:
    project = get_owned_project(db, user.id, str(project_id))
    if not storage.has(project.media_key):
        raise ConflictError("Upload a video before adding clips.", code="no_media")
    start, end = validate_clip_range(body.start_seconds, body.end_seconds, project.duration_seconds)
    rank = (db.scalar(select(func.max(Clip.rank)).where(Clip.project_id == project.id)) or 0) + 1
    clip = Clip(
        project_id=project.id,
        owner_id=user.id,
        rank=rank,
        title=" ".join(body.title.split()),
        source="manual",
        start_seconds=start,
        end_seconds=end,
        status="suggested",
        caption_style=CaptionStyle().model_dump(),
    )
    db.add(clip)
    if project.status == "transcribed":
        project.status = "ready"
    db.commit()
    return clip_out(clip, storage)


@router.post(
    "/projects/{project_id}/detect",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run AI clip detection again (keeps clips you edited or exported)",
)
def detect_again(
    project_id: ProjectId,
    user: CurrentUser,
    db: DbSession,
    runner: RunnerDep,
    _limit: Annotated[None, Depends(route_limit("jobs", key="user"))] = None,
    _capacity: JobCapacity = None,
) -> JobOut:
    project = get_owned_project(db, user.id, str(project_id))
    if project.transcript is None:
        raise ConflictError("Transcribe the video before looking for clips.", code="no_transcript")
    project.status = "queued"
    project.error_message = None
    job = enqueue_job(db, runner, owner_id=user.id, job_type="detect_clips", project_id=project.id)  # type: ignore[arg-type]
    return JobOut.model_validate(job)


@router.get("/clips", response_model=ClipList, summary="All your clips")
def list_clips(
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    status_filter: Annotated[
        Literal["suggested", "rendering", "ready", "failed"] | None, Query(alias="status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClipList:
    query = (
        select(Clip)
        .join(Project, Project.id == Clip.project_id)
        .where(Clip.owner_id == user.id, Project.status.not_in(HIDDEN_STATUSES))
    )
    if status_filter:
        query = query.where(Clip.status == status_filter)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    clips = db.scalars(query.order_by(Clip.updated_at.desc()).limit(limit).offset(offset)).all()
    return ClipList(items=clips_out(db, list(clips), storage, with_project=True), total=int(total))


@router.get("/clips/{clip_id}", response_model=ClipOut, summary="Get a clip")
def get_clip(clip_id: ClipId, user: CurrentUser, db: DbSession, storage: StorageDep) -> ClipOut:
    clip = get_owned_clip(db, user.id, str(clip_id))
    return clips_out(db, [clip], storage, with_project=True)[0]


@router.patch(
    "/clips/{clip_id}", response_model=ClipOut, summary="Edit timing, layout, captions or text"
)
def update_clip(
    clip_id: ClipId, body: ClipUpdate, user: CurrentUser, db: DbSession, storage: StorageDep
) -> ClipOut:
    clip = get_owned_clip(db, user.id, str(clip_id))
    if _active_render(db, clip.id):
        raise ConflictError("This clip is being exported. Wait for it to finish.", code="clip_busy")
    changes = body.model_dump(exclude_unset=True)
    if "start_seconds" in changes or "end_seconds" in changes:
        start, end = validate_clip_range(
            changes.get("start_seconds", clip.start_seconds),
            changes.get("end_seconds", clip.end_seconds),
            clip.project.duration_seconds,
        )
        clip.start_seconds, clip.end_seconds = start, end
    for field in ("title", "description", "layout", "crop_position", "captions_enabled"):
        if field in changes and changes[field] is not None:
            value = changes[field]
            setattr(clip, field, " ".join(value.split()) if field == "title" else value)
    if changes.get("auto_frame") is not None:
        clip.auto_frame = bool(changes["auto_frame"])
    elif changes.get("crop_position") is not None:
        clip.auto_frame = False  # a manual position overrides automatic framing
    if changes.get("aspect_ratio") is not None:
        # Following the project default is stored as "no override".
        chosen = changes["aspect_ratio"]
        clip.aspect_ratio = None if chosen == clip.project.aspect_ratio else chosen
    if changes.get("caption_style") is not None:
        clip.caption_style = body.caption_style.model_dump()  # type: ignore[union-attr]
    if body.caption_lines is not None:
        store_edited_lines(clip, body.caption_lines)
    if RENDER_FIELDS & changes.keys() and clip.status in ("ready", "failed"):
        clip.status = "suggested"  # the previous export no longer matches the settings
    db.commit()
    return clips_out(db, [clip], storage, with_project=True)[0]


@router.delete(
    "/clips/{clip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a clip and its files",
)
def delete_clip(clip_id: ClipId, user: CurrentUser, db: DbSession, storage: StorageDep) -> Response:
    clip = get_owned_clip(db, user.id, str(clip_id))
    job = _active_render(db, clip.id)
    if job is not None:
        request_cancel(db, job)
        if job.status == "running":
            raise ConflictError(
                "The clip is being exported. It was cancelled; try again in a moment.",
                code="clip_busy",
            )
    output = clip.output_key
    owner_id, worker_id = clip.owner_id, clip.project.worker_id
    db.delete(clip)
    if output and storage.remote and worker_id:
        # The files are on the owner's worker: leave it a clean-up job.
        db.add(
            Job(
                owner_id=owner_id,
                worker_id=worker_id,
                type="purge_files",
                params={"keys": [output, output.rsplit(".", 1)[0] + ".jpg"]},
                stage="Waiting for your worker",
            )
        )
    db.commit()
    if output and not storage.remote:
        storage.delete(output)
        storage.delete(output.rsplit(".", 1)[0] + ".jpg")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/clips/{clip_id}/captions", response_model=ClipCaptions, summary="Caption lines for this clip"
)
def get_captions(clip_id: ClipId, user: CurrentUser, db: DbSession) -> ClipCaptions:
    clip = get_owned_clip(db, user.id, str(clip_id))
    edited = edited_lines(clip)
    if edited is not None:
        return ClipCaptions(clip_id=clip.id, edited=True, lines=edited)
    transcript = clip.project.transcript
    if transcript is None:
        return ClipCaptions(clip_id=clip.id, edited=False, lines=[])
    style = CaptionStyle.model_validate(clip.caption_style or {})
    lines = generated_caption_lines(
        transcript.segments or [], clip.start_seconds, clip.end_seconds, style.words_per_line
    )
    return ClipCaptions(clip_id=clip.id, edited=False, lines=lines)


@router.post(
    "/clips/{clip_id}/autoframe",
    response_model=ClipOut,
    summary="Detect the main subject and set the crop position for the project's aspect ratio",
)
def autoframe(
    clip_id: ClipId,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    settings: SettingsDep,
    _limit: Annotated[None, Depends(route_limit("jobs", key="user"))] = None,
    _capacity: JobCapacity = None,
) -> ClipOut:
    clip = get_owned_clip(db, user.id, str(clip_id))
    project = clip.project
    if storage.remote:
        # The worker finds the subject while exporting; there is no video here to analyse.
        clip.auto_frame = True
        if clip.status in ("ready", "failed"):
            clip.status = "suggested"
        db.commit()
        return clips_out(db, [clip], storage, with_project=True)[0]
    if not storage.exists(project.media_key):
        raise ConflictError("The source video is missing.", code="no_media")
    try:
        ffmpeg = get_ffmpeg(settings)
    except ProcessingError as exc:
        raise ServiceUnavailableError(exc.user_message, code="ffmpeg_missing") from exc
    position = auto_frame_position(
        ffmpeg,
        storage.path(project.media_key),  # type: ignore[arg-type]
        {
            "start": clip.start_seconds,
            "end": clip.end_seconds,
            "aspect_ratio": clip.aspect_ratio or project.aspect_ratio,
            "source_width": project.width,
            "source_height": project.height,
        },
    )
    if position is not None:
        clip.crop_position = position
    clip.auto_frame = True
    if clip.status in ("ready", "failed"):
        clip.status = "suggested"
    db.commit()
    return clips_out(db, [clip], storage, with_project=True)[0]


@router.post(
    "/projects/{project_id}/render-all",
    response_model=list[JobOut],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Export (or re-export) every clip of a project in its current aspect ratio",
)
def render_all(
    project_id: ProjectId,
    user: CurrentUser,
    db: DbSession,
    runner: RunnerDep,
    only_outdated: Annotated[bool, Query()] = True,
    _limit: Annotated[None, Depends(route_limit("jobs", key="user"))] = None,
    _capacity: JobCapacity = None,
) -> list[JobOut]:
    project = get_owned_project(db, user.id, str(project_id))
    jobs: list[JobOut] = []
    for clip in project.clips:
        if _active_render(db, clip.id) or (only_outdated and clip.status == "ready"):
            continue
        clip.status = "rendering"
        clip.error_message = None
        job = enqueue_job(
            db,
            runner,
            owner_id=user.id,
            job_type="render_clip",
            project_id=project.id,
            clip_id=clip.id,
            allow_parallel=True,
        )
        jobs.append(JobOut.model_validate(job))
    if not jobs:
        raise ConflictError(
            "All clips are already exported in the current format.", code="nothing_to_export"
        )
    return jobs


@router.post(
    "/clips/{clip_id}/render",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Export the clip as an MP4 in the project's aspect ratio",
)
def render(
    clip_id: ClipId,
    user: CurrentUser,
    db: DbSession,
    runner: RunnerDep,
    _limit: Annotated[None, Depends(route_limit("jobs", key="user"))] = None,
    _capacity: JobCapacity = None,
) -> JobOut:
    clip = get_owned_clip(db, user.id, str(clip_id))
    if _active_render(db, clip.id):
        raise ConflictError("This clip is already being exported.", code="clip_busy")
    clip.status = "rendering"
    clip.error_message = None
    job = enqueue_job(
        db,
        runner,
        owner_id=user.id,
        job_type="render_clip",
        project_id=clip.project_id,
        clip_id=clip.id,
        allow_parallel=True,
    )
    return JobOut.model_validate(job)


@router.get("/clips/{clip_id}/file", summary="Stream (preview) or download the exported MP4")
def clip_file(
    clip_id: ClipId,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    download: Annotated[bool, Query()] = False,
) -> FileResponse:
    clip = get_owned_clip(db, user.id, str(clip_id))
    _on_worker(storage)
    if not storage.exists(clip.output_key):
        raise NotFoundError("This clip has not been exported yet.")
    return FileResponse(
        storage.path(clip.output_key),  # type: ignore[arg-type]
        media_type="video/mp4",
        filename=safe_download_name(clip.title, ".mp4") if download else None,
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.get("/clips/{clip_id}/thumbnail", summary="Thumbnail of the exported clip")
def clip_thumbnail(
    clip_id: ClipId, user: CurrentUser, db: DbSession, storage: StorageDep
) -> FileResponse:
    clip = get_owned_clip(db, user.id, str(clip_id))
    _on_worker(storage)
    key = clip.output_key.rsplit(".", 1)[0] + ".jpg" if clip.output_key else None
    if not storage.exists(key):
        raise NotFoundError("No thumbnail yet.")
    return FileResponse(
        storage.path(key), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=60"}
    )  # type: ignore[arg-type]
