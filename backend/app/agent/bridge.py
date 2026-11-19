"""The worker's local bridge: lets the owner's browser hand over and read video files.

In hybrid mode the website never receives video. Instead, the dashboard (running in
the owner's browser) talks to this small HTTP service on **127.0.0.1**:

- ``PUT  /bridge/v1/projects/{id}/media``   send a video to this computer
- ``GET  /bridge/v1/projects/{id}/media``   play the source video
- ``GET  /bridge/v1/projects/{id}/clips/{clip}/file``   play or download a clip
- thumbnails for both

Protections:

- it binds to the loopback interface only and rejects non-loopback peers and
  foreign ``Host`` headers (DNS rebinding);
- only the website's own origins may call it from a browser (CORS allow list
  provided by the server the worker is paired with);
- every file request needs a short-lived **transfer token** created by the signed-in
  owner. The bridge asks the server whether the token is valid for *this* worker
  before it does anything, and remembers the answer only until the token expires;
- file names from the browser are never used as paths: files are addressed by
  project and clip IDs that are validated as UUIDs.
"""

from __future__ import annotations

import inspect
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.requests import ClientDisconnect

from app import __version__
from app.agent import AGENT_NAME
from app.agent.client import ConnectionProblem, NotAuthorized, ServerClient, ServerError
from app.agent.state import Credentials
from app.core.config import ALLOWED_VIDEO_EXTENSIONS, Settings
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
    register_exception_handlers,
)
from app.core.local_guard import LocalOnlyMiddleware
from app.core.middleware import RequestContextMiddleware
from app.core.security import hash_token
from app.services.files import display_filename, safe_download_name, video_extension
from app.services.media import create_thumbnail_at, get_ffmpeg, media_info_dict, validate_media
from app.services.storage import LocalStorage
from openclip_processing.errors import FFmpegNotFoundError, ProcessingError

logger = logging.getLogger("app.bridge")

MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
}
TOKEN_CACHE_SECONDS = 300.0


class TokenVerifier:
    """Asks the server about transfer tokens and briefly remembers valid ones."""

    def __init__(self, client: ServerClient, owner_id: str) -> None:
        self._client = client
        self._owner_id = owner_id
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def verify(self, token: str | None) -> dict[str, Any]:
        denied = ForbiddenError(
            "This transfer link is not valid any more. Reload the page.",
            code="invalid_transfer_token",
        )
        if not token or len(token) > 200:
            raise denied
        key = hash_token(token)
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached and cached[0] > now:
                return cached[1]
            for stale in [k for k, (expires, _) in self._cache.items() if expires <= now]:
                del self._cache[stale]
        try:
            info = self._client.verify_transfer_token(token)
        except (ConnectionProblem, NotAuthorized) as exc:
            raise ServiceUnavailableError(
                "The worker cannot reach the IDK Clips server to check this request. "
                "Check the internet connection and try again.",
                code="server_unreachable",
            ) from exc
        except ServerError as exc:
            raise denied from exc
        if info.get("owner_id") != self._owner_id:
            raise denied
        lifetime = min(float(info.get("expires_in", 0)), TOKEN_CACHE_SECONDS)
        if lifetime <= 0:
            raise denied
        with self._lock:
            self._cache[key] = (now + lifetime, info)
        return info


def _bearer(request: Request, query_token: str | None) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return query_token  # <video> and <img> cannot send headers


def create_bridge(
    settings: Settings,
    credentials: Credentials,
    client: ServerClient,
    storage: LocalStorage,
    allowed_origins: list[str],
) -> FastAPI:
    app = FastAPI(title="IDK Clips worker bridge", docs_url=None, redoc_url=None, openapi_url=None)
    verifier = TokenVerifier(client, credentials.owner_id)
    owner_id = credentials.owner_id
    register_exception_handlers(app)

    cors_options: dict[str, Any] = {
        "allow_origins": allowed_origins,
        "allow_credentials": False,
        "allow_methods": ["GET", "PUT", "OPTIONS"],
        "allow_headers": ["Authorization", "Content-Type"],
        "expose_headers": ["Content-Length", "Content-Range", "Accept-Ranges"],
        "max_age": 600,
    }
    # Browsers ask for this before a public website may call a local service.
    if "allow_private_network" in inspect.signature(CORSMiddleware.__init__).parameters:
        cors_options["allow_private_network"] = True
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(CORSMiddleware, **cors_options)
    app.add_middleware(LocalOnlyMiddleware)  # outermost: runs before everything else

    def authorize(request: Request, token: str | None, scope: str, project_id: uuid.UUID) -> dict:
        info = verifier.verify(_bearer(request, token))
        if info.get("scope") != scope:
            raise ForbiddenError("This link cannot be used for that.", code="wrong_scope")
        if scope == "upload" and info.get("project_id") != str(project_id):
            raise ForbiddenError(
                "This upload link belongs to another project.", code="wrong_project"
            )
        return info

    def project_prefix(project_id: uuid.UUID) -> str:
        return LocalStorage.project_prefix(owner_id, str(project_id))

    def source_file(project_id: uuid.UUID) -> Path:
        folder = storage.path(project_prefix(project_id))
        if folder.is_dir():
            for extension in ALLOWED_VIDEO_EXTENSIONS:
                candidate = folder / f"source{extension}"
                if candidate.is_file():
                    return candidate
        raise NotFoundError("This computer does not have that video.")

    def file_response(
        path: Path, media_type: str, download_name: str | None = None
    ) -> FileResponse:
        if not path.is_file():
            raise NotFoundError("This computer does not have that file.")
        return FileResponse(
            path,
            media_type=media_type,
            filename=download_name,
            content_disposition_type="attachment" if download_name else "inline",
            headers={"Cache-Control": "private, max-age=60", "Referrer-Policy": "no-referrer"},
        )

    @app.get("/bridge/v1/hello")
    async def hello() -> dict[str, str]:
        """Lets the dashboard find out whether this worker runs on the same computer."""
        return {
            "app": AGENT_NAME,
            "version": __version__,
            "worker_id": credentials.worker_id,
            "worker_name": credentials.worker_name,
        }

    @app.put("/bridge/v1/projects/{project_id}/media")
    async def upload(
        project_id: uuid.UUID,
        request: Request,
        filename: Annotated[str, Query(min_length=1, max_length=255)],
    ) -> dict[str, Any]:
        info = await run_in_threadpool(authorize, request, None, "upload", project_id)
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
        limit = min(
            int(info.get("max_upload_bytes") or 0) or settings.max_upload_bytes,
            settings.max_upload_bytes,
        )
        if expected == 0:
            raise BadRequestError("The file is empty.")
        if expected > limit:
            raise PayloadTooLargeError(
                f"The file is larger than the {limit // (1024 * 1024)} MB limit."
            )
        prefix = project_prefix(project_id)
        folder = storage.path(prefix)
        if folder.is_dir() and any(
            (folder / f"source{ext}").is_file() for ext in ALLOWED_VIDEO_EXTENSIONS
        ):
            raise ConflictError("This project already has a video.", code="media_exists")
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

        def finalize() -> dict[str, Any]:
            try:
                ffmpeg = get_ffmpeg(settings)
                media = ffmpeg.probe(final_path)
                validate_media(media, settings, max_seconds=info.get("max_video_seconds"))
                thumbnail_key = create_thumbnail_at(
                    ffmpeg, storage, prefix, final_path, media.duration
                )
                payload = {
                    "media_key": final_key,
                    "thumbnail_key": thumbnail_key,
                    "info": media_info_dict(media),
                    "original_filename": display_filename(filename),
                }
                client.register_media(str(project_id), payload)
            except FFmpegNotFoundError as exc:
                storage.delete_tree(prefix)
                raise ServiceUnavailableError(exc.user_message, code="ffmpeg_missing") from exc
            except ProcessingError as exc:
                storage.delete_tree(prefix)
                raise UnprocessableError(exc.user_message, code="invalid_media") from exc
            except (ConnectionProblem, NotAuthorized) as exc:
                storage.delete_tree(prefix)
                raise ServiceUnavailableError(
                    "The video arrived, but the worker could not reach the IDK Clips server to "
                    "register it. Check the internet connection and try again.",
                    code="server_unreachable",
                ) from exc
            except ServerError as exc:
                storage.delete_tree(prefix)
                raise ConflictError(exc.message, code=exc.code) from exc
            return {"ok": True, "duration": media.duration, "size_bytes": media.size_bytes}

        return await run_in_threadpool(finalize)

    @app.get("/bridge/v1/projects/{project_id}/media")
    def project_media(
        project_id: uuid.UUID, request: Request, token: Annotated[str | None, Query()] = None
    ) -> FileResponse:
        authorize(request, token, "read", project_id)
        path = source_file(project_id)
        return file_response(path, MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"))

    @app.get("/bridge/v1/projects/{project_id}/thumbnail")
    def project_thumbnail(
        project_id: uuid.UUID, request: Request, token: Annotated[str | None, Query()] = None
    ) -> FileResponse:
        authorize(request, token, "read", project_id)
        return file_response(
            storage.path(f"{project_prefix(project_id)}/thumbnail.jpg"), "image/jpeg"
        )

    @app.get("/bridge/v1/projects/{project_id}/clips/{clip_id}/file")
    def clip_file(
        project_id: uuid.UUID,
        clip_id: uuid.UUID,
        request: Request,
        token: Annotated[str | None, Query()] = None,
        download: Annotated[bool, Query()] = False,
        name: Annotated[str, Query(max_length=200)] = "clip",
    ) -> FileResponse:
        authorize(request, token, "read", project_id)
        path = storage.path(f"{project_prefix(project_id)}/clips/{clip_id}.mp4")
        return file_response(
            path, "video/mp4", safe_download_name(name, ".mp4") if download else None
        )

    @app.get("/bridge/v1/projects/{project_id}/clips/{clip_id}/thumbnail")
    def clip_thumbnail(
        project_id: uuid.UUID,
        clip_id: uuid.UUID,
        request: Request,
        token: Annotated[str | None, Query()] = None,
    ) -> FileResponse:
        authorize(request, token, "read", project_id)
        return file_response(
            storage.path(f"{project_prefix(project_id)}/clips/{clip_id}.jpg"), "image/jpeg"
        )

    return app


class BridgeServer:
    """Runs the bridge with uvicorn in a background thread."""

    def __init__(self, app: FastAPI, port: int) -> None:
        import uvicorn

        self.port = port
        config = uvicorn.Config(
            app,
            host="127.0.0.1",  # loopback only, by design; never configurable to 0.0.0.0
            port=port,
            log_config=None,
            access_log=False,
            server_header=False,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, name="openclip-bridge", daemon=True
        )

    def start(self, timeout: float = 10.0) -> bool:
        self._thread.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server.started:
                return True
            if not self._thread.is_alive():
                return False
            time.sleep(0.05)
        return False

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=10)
