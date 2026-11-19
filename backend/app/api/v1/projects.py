"""Projects: create, upload (streaming), import from a link, YouTube reference, process, media."""

from __future__ import annotations

import uuid
from pathlib import PurePosixPath
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, Depends, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, PlainTextResponse
from starlette.requests import ClientDisconnect

from app.api.deps import CurrentUser, DbSession, JobCapacity, RunnerDep, SettingsDep, StorageDep
from app.core.config import ALLOWED_VIDEO_EXTENSIONS
from app.core.errors import (
    AppError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PayloadTooLargeError,
    ServiceUnavailableError,
    UnprocessableError,
    UnsupportedMediaTypeError,
)
from app.core.rate_limit import route_limit
from app.db.models import Project
from app.schemas.job import JobOut
from app.schemas.project import (
    ProcessRequest,
    ProjectCreate,
    ProjectFromYouTube,
    ProjectImportUrl,
    ProjectList,
    ProjectOut,
    ProjectUpdate,
    YouTubeLookupRequest,
    YouTubeVideoOut,
)
from app.schemas.transcript import TranscriptOut
from app.services import youtube
from app.services.files import display_filename, safe_download_name, video_extension
from app.services.jobs import enqueue_job
from app.services.media import apply_media_info, create_thumbnail, get_ffmpeg, validate_media
from app.services.projects import (
    get_owned_project,
    list_projects,
    project_out,
    request_project_deletion,
    user_storage_bytes,
)
from app.services.storage import LocalStorage
from app.services.url_import import UrlImportError, validate_url
from openclip_processing.errors import FFmpegNotFoundError, ProcessingError
from openclip_processing.subtitles import to_srt, to_text, to_vtt

router = APIRouter(prefix="/projects", tags=["projects"])

ProjectId = Annotated[uuid.UUID, "Project ID"]

MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
}


def _quota_check(db, settings, user_id: str, incoming: int) -> None:  # type: ignore[no-untyped-def]
    if not settings.user_storage_quota_mb:
        return
    quota = settings.user_storage_quota_mb * 1024 * 1024
    if user_storage_bytes(db, user_id) + incoming > quota:
        raise PayloadTooLargeError(
            f"This would exceed your {settings.user_storage_quota_mb} MB storage quota. "
            "Delete older projects first.",
            code="quota_exceeded",
        )


@router.get("", response_model=ProjectList, summary="List your projects")
def list_my_projects(
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProjectList:
    return list_projects(db, user.id, storage, limit=limit, offset=offset)


@router.post(
    "", response_model=ProjectOut, status_code=status.HTTP_201_CREATED, summary="Create a project"
)
def create_project(
    body: ProjectCreate,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    settings: SettingsDep,
) -> ProjectOut:
    project = Project(
        owner_id=user.id,
        name=body.name,
        status="awaiting_upload",
        source_type="upload",
        language=body.language,
        whisper_model=body.whisper_model or settings.whisper_default_model,
        clip_count=body.clip_count,
        aspect_ratio=body.aspect_ratio,
        min_clip_seconds=body.min_clip_seconds,
        max_clip_seconds=body.max_clip_seconds,
        auto_process=body.auto_process,
    )
    db.add(project)
    db.commit()
    return project_out(db, project, storage)


def _name_from_url(url: str) -> str:
    parts = urlsplit(url)
    stem = PurePosixPath(parts.path).stem
    return (display_filename(stem) if stem else parts.hostname or "Imported video")[:200]


@router.post(
    "/import-url",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project from a direct video link",
)
def import_from_url(
    body: ProjectImportUrl,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    settings: SettingsDep,
    runner: RunnerDep,
    _limit: Annotated[None, Depends(route_limit("upload", key="user"))] = None,
    _capacity: JobCapacity = None,
) -> ProjectOut:
    if not settings.url_import_enabled:
        raise ForbiddenError("Importing from links is disabled on this server.")
    url = str(body.url)
    try:
        validate_url(url, allow_private=settings.url_import_allow_private_networks)
    except UrlImportError as exc:
        raise UnprocessableError(exc.user_message, code="url_not_allowed") from exc
    _quota_check(db, settings, user.id, 0)
    project = Project(
        owner_id=user.id,
        name=" ".join((body.name or _name_from_url(url)).split()) or "Imported video",
        status="importing",
        source_type="url",
        source_url=url,
        language=body.language,
        whisper_model=body.whisper_model or settings.whisper_default_model,
        clip_count=body.clip_count,
        aspect_ratio=body.aspect_ratio,
        min_clip_seconds=body.min_clip_seconds,
        max_clip_seconds=body.max_clip_seconds,
        auto_process=body.auto_process,
    )
    db.add(project)
    db.commit()
    enqueue_job(db, runner, owner_id=user.id, job_type="import_url", project_id=project.id)  # type: ignore[arg-type]
    return project_out(db, project, storage)


def _youtube_video(url: str, enabled: bool) -> YouTubeVideoOut:
    video_id = youtube.parse_video_id(url)
    if video_id is None:
        raise UnprocessableError(
            "That does not look like a YouTube video link. Paste a link such as "
            "https://www.youtube.com/watch?v=... or https://youtu.be/...",
            code="not_a_youtube_link",
        )
    details: dict[str, object] = {"video_id": video_id, "url": youtube.canonical_url(video_id)}
    notice = None
    if enabled:
        try:
            details = youtube.lookup(video_id)
        except youtube.YouTubeError as exc:
            notice = exc.user_message  # the link is still usable as a reference
    return YouTubeVideoOut(
        **details,  # type: ignore[arg-type]
        notice=notice,
        how_to_get_the_file=youtube.HOW_TO_GET_THE_FILE,
    )


@router.post(
    "/youtube/lookup",
    response_model=YouTubeVideoOut,
    summary="Public details of a YouTube video (official oEmbed API; nothing is downloaded)",
)
def youtube_lookup(
    body: YouTubeLookupRequest,
    user: CurrentUser,
    settings: SettingsDep,
    _limit: Annotated[None, Depends(route_limit("upload", key="user"))] = None,
    _capacity: JobCapacity = None,
) -> YouTubeVideoOut:
    return _youtube_video(body.url, settings.youtube_lookup_enabled)


@router.post(
    "/from-youtube",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project that references a YouTube video, then add your own file",
)
def create_from_youtube(
    body: ProjectFromYouTube,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    settings: SettingsDep,
    _limit: Annotated[None, Depends(route_limit("upload", key="user"))] = None,
    _capacity: JobCapacity = None,
) -> ProjectOut:
    """The video itself is never fetched from YouTube.

    The project waits for the file the creator downloaded through YouTube Studio or
    Google Takeout, which is uploaded like any other video.
    """
    video = _youtube_video(body.url, settings.youtube_lookup_enabled)
    name = " ".join((body.name or video.title or "YouTube video").split())[:200]
    project = Project(
        owner_id=user.id,
        name=name or "YouTube video",
        status="awaiting_upload",
        source_type="youtube",
        source_url=video.url,
        source_meta=video.model_dump(exclude={"notice", "how_to_get_the_file"}, exclude_none=True),
        language=body.language,
        whisper_model=body.whisper_model or settings.whisper_default_model,
        clip_count=body.clip_count,
        aspect_ratio=body.aspect_ratio,
        min_clip_seconds=body.min_clip_seconds,
        max_clip_seconds=body.max_clip_seconds,
        auto_process=body.auto_process,
    )
    db.add(project)
    db.commit()
    return project_out(db, project, storage)


@router.get("/{project_id}", response_model=ProjectOut, summary="Get a project")
def get_project(
    project_id: ProjectId, user: CurrentUser, db: DbSession, storage: StorageDep
) -> ProjectOut:
    return project_out(db, get_owned_project(db, user.id, str(project_id)), storage)


@router.patch("/{project_id}", response_model=ProjectOut, summary="Rename or change options")
def update_project(
    project_id: ProjectId,
    body: ProjectUpdate,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
) -> ProjectOut:
    project = get_owned_project(db, user.id, str(project_id))
    changes = body.model_dump(exclude_none=True)
    if "name" in changes:
        changes["name"] = " ".join(changes["name"].split())
    ratio_changed = changes.get("aspect_ratio", project.aspect_ratio) != project.aspect_ratio
    for field, value in changes.items():
        setattr(project, field, value)
    if project.min_clip_seconds >= project.max_clip_seconds:
        raise UnprocessableError("The minimum clip length must be shorter than the maximum.")
    if project.whisper_model.endswith(".en") and project.language not in ("en", "auto"):
        raise UnprocessableError("English-only speech models can only transcribe English.")
    if ratio_changed:
        # Exports in the old shape stay downloadable but are marked as outdated, so they
        # can be regenerated in the new ratio. The original video is never modified.
        for clip in project.clips:
            if clip.status in ("ready", "failed"):
                clip.status = "suggested"
    db.commit()
    return project_out(db, project, storage)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={202: {"description": "Deletion will finish once the running job stops"}},
    summary="Delete a project and all of its files",
)
def delete_project(
    project_id: ProjectId, user: CurrentUser, db: DbSession, storage: StorageDep
) -> Response:
    project = get_owned_project(db, user.id, str(project_id))
    deleted = request_project_deletion(db, storage, project)
    return Response(status_code=status.HTTP_204_NO_CONTENT if deleted else status.HTTP_202_ACCEPTED)


@router.put(
    "/{project_id}/media",
    response_model=ProjectOut,
    summary="Upload the video file (raw request body, streamed to disk)",
)
async def upload_media(
    project_id: ProjectId,
    request: Request,
    user: CurrentUser,
    filename: Annotated[str, Query(min_length=1, max_length=255)],
    _limit: Annotated[None, Depends(route_limit("upload", key="user"))] = None,
    _capacity: JobCapacity = None,
) -> ProjectOut:
    settings = request.app.state.settings
    storage: LocalStorage = request.app.state.storage
    database = request.app.state.database
    runner = request.app.state.job_runner

    if storage.remote:
        raise ConflictError(
            "This server does not store videos. Send the file to your connected worker "
            "from the dashboard instead.",
            code="upload_to_worker",
        )
    extension = video_extension(filename)
    if extension is None:
        raise UnsupportedMediaTypeError(
            f"Unsupported file type. Allowed: {', '.join(ALLOWED_VIDEO_EXTENSIONS)}."
        )
    declared = request.headers.get("content-length", "")
    if not declared.isdigit():
        raise AppError(
            "The upload size must be sent in the Content-Length header.",
            status_code=411,
            code="length_required",
        )
    expected = int(declared)
    if expected == 0:
        raise BadRequestError("The file is empty.")
    if expected > settings.max_upload_bytes:
        raise PayloadTooLargeError(
            f"The file is larger than the {settings.max_upload_mb} MB limit."
        )

    def prepare() -> str:
        with database.session_scope() as db:
            project = get_owned_project(db, user.id, str(project_id))
            if project.source_type == "url":
                raise ConflictError("This project gets its video from a link.")
            if project.status not in ("awaiting_upload", "failed") or storage.exists(
                project.media_key
            ):
                raise ConflictError("This project already has a video.", code="media_exists")
            _quota_check(db, settings, user.id, expected)
            return project.owner_id

    owner_id = await run_in_threadpool(prepare)
    prefix = LocalStorage.project_prefix(owner_id, str(project_id))
    partial = storage.ensure_parent(f"{prefix}/source.upload")
    received = 0
    try:
        with partial.open("wb") as handle:
            async for chunk in request.stream():
                received += len(chunk)
                if received > expected:
                    raise PayloadTooLargeError("The upload is larger than its declared size.")
                handle.write(chunk)
        if received != expected:
            raise BadRequestError("The upload was incomplete. Please try again.")
    except ClientDisconnect as exc:
        partial.unlink(missing_ok=True)
        raise BadRequestError("The upload was interrupted.") from exc
    except BaseException:
        partial.unlink(missing_ok=True)
        raise

    final_key = f"{prefix}/source{extension}"
    final_path = storage.path(final_key)
    partial.replace(final_path)

    def finalize() -> ProjectOut:
        try:
            ffmpeg = get_ffmpeg(settings)
            info = ffmpeg.probe(final_path)
            validate_media(info, settings)
        except FFmpegNotFoundError as exc:
            final_path.unlink(missing_ok=True)
            raise ServiceUnavailableError(exc.user_message, code="ffmpeg_missing") from exc
        except ProcessingError as exc:
            final_path.unlink(missing_ok=True)
            raise UnprocessableError(exc.user_message, code="invalid_media") from exc
        with database.session_scope() as db:
            project = get_owned_project(db, user.id, str(project_id))
            project.media_key = final_key
            project.original_filename = display_filename(filename)
            apply_media_info(project, info)
            project.thumbnail_key = create_thumbnail(ffmpeg, storage, project, final_path)
            project.status = "uploaded"
            project.error_message = None
            if project.auto_process:
                project.status = "queued"
                db.flush()
                enqueue_job(db, runner, owner_id=user.id, job_type="process", project_id=project.id)
            return project_out(db, project, storage)

    return await run_in_threadpool(finalize)


def _media_response(
    storage: LocalStorage, key: str | None, media_type: str | None = None
) -> FileResponse:
    if storage.remote:
        raise NotFoundError(
            "This file is stored on your worker. Open IDK Clips on that computer to play it.",
            code="media_on_worker",
        )
    if not storage.exists(key):
        raise NotFoundError("The file is not available.")
    path = storage.path(key)  # type: ignore[arg-type]
    return FileResponse(
        path,
        media_type=media_type or MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/{project_id}/media", summary="Stream the source video (supports Range requests)")
def project_media(
    project_id: ProjectId, user: CurrentUser, db: DbSession, storage: StorageDep
) -> FileResponse:
    project = get_owned_project(db, user.id, str(project_id))
    return _media_response(storage, project.media_key)


@router.get("/{project_id}/thumbnail", summary="Project thumbnail (JPEG)")
def project_thumbnail(
    project_id: ProjectId, user: CurrentUser, db: DbSession, storage: StorageDep
) -> FileResponse:
    project = get_owned_project(db, user.id, str(project_id))
    return _media_response(storage, project.thumbnail_key, "image/jpeg")


def _start_job(
    job_type: str,
    project_id: str,
    body: ProcessRequest,
    user,
    db,
    storage: LocalStorage,
    runner,  # type: ignore[no-untyped-def]
) -> JobOut:
    project = get_owned_project(db, user.id, project_id)
    if not storage.has(project.media_key):
        raise ConflictError("Upload a video before starting processing.", code="no_media")
    if body.language:
        project.language = body.language
    if body.whisper_model:
        project.whisper_model = body.whisper_model
    if project.whisper_model.endswith(".en") and project.language not in ("en", "auto"):
        raise UnprocessableError("English-only speech models can only transcribe English.")
    if job_type == "process" and not body.transcribe and project.transcript is None:
        raise ConflictError("Transcribe the video before detecting clips.", code="no_transcript")
    params = {"transcribe": body.transcribe} if job_type == "process" else {}
    previous_status = project.status
    # Set the status before the job is submitted so the worker's updates are never overwritten.
    project.status = "queued"
    project.error_message = None
    try:
        job = enqueue_job(
            db, runner, owner_id=user.id, job_type=job_type, project_id=project.id, params=params
        )
    except ConflictError:
        db.rollback()
        project.status = previous_status
        raise
    return JobOut.model_validate(job)


@router.post(
    "/{project_id}/process",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Transcribe (optional) and detect clips",
)
def process_project(
    project_id: ProjectId,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    runner: RunnerDep,
    body: Annotated[ProcessRequest, Body()] = ProcessRequest(),  # noqa: B008
    _limit: Annotated[None, Depends(route_limit("jobs", key="user"))] = None,
    _capacity: JobCapacity = None,
) -> JobOut:
    return _start_job("process", str(project_id), body, user, db, storage, runner)


@router.post(
    "/{project_id}/transcribe",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Transcribe only",
)
def transcribe_project(
    project_id: ProjectId,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    runner: RunnerDep,
    body: Annotated[ProcessRequest, Body()] = ProcessRequest(),  # noqa: B008
    _limit: Annotated[None, Depends(route_limit("jobs", key="user"))] = None,
    _capacity: JobCapacity = None,
) -> JobOut:
    return _start_job("transcribe", str(project_id), body, user, db, storage, runner)


@router.get(
    "/{project_id}/transcript", response_model=TranscriptOut, summary="Timestamped transcript"
)
def get_transcript(project_id: ProjectId, user: CurrentUser, db: DbSession) -> TranscriptOut:
    project = get_owned_project(db, user.id, str(project_id))
    transcript = project.transcript
    if transcript is None:
        raise NotFoundError("This project has no transcript yet.")
    return TranscriptOut(
        project_id=project.id,
        language=transcript.language,
        language_probability=transcript.language_probability,
        model=transcript.model,
        device=transcript.device,
        duration=transcript.duration,
        word_count=transcript.word_count,
        warnings=list(transcript.warnings or []),
        segments=transcript.segments,
        created_at=transcript.created_at,
    )


@router.get(
    "/{project_id}/transcript/download", summary="Download the transcript as TXT, SRT or VTT"
)
def download_transcript(
    project_id: ProjectId,
    user: CurrentUser,
    db: DbSession,
    format: Annotated[Literal["txt", "srt", "vtt"], Query()] = "srt",
) -> PlainTextResponse:
    project = get_owned_project(db, user.id, str(project_id))
    if project.transcript is None:
        raise NotFoundError("This project has no transcript yet.")
    segments = project.transcript.segments
    body = {"txt": to_text, "srt": to_srt, "vtt": to_vtt}[format](segments)
    media = {"txt": "text/plain", "srt": "application/x-subrip", "vtt": "text/vtt"}[format]
    filename = safe_download_name(project.name, f".{format}")
    return PlainTextResponse(
        body,
        media_type=f"{media}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
