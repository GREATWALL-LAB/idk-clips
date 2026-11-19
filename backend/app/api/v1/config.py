"""Server limits and options the UI needs (signed-in users only)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentUser, SettingsDep
from app.core.config import ALLOWED_VIDEO_EXTENSIONS
from openclip_processing.transcription import LANGUAGES, WHISPER_MODELS

router = APIRouter(tags=["system"])


class LanguageOption(BaseModel):
    code: str
    name: str


class WhisperModelOption(BaseModel):
    id: str
    label: str
    size_mb: int
    multilingual: bool
    note: str


class ClientConfig(BaseModel):
    max_upload_mb: int
    max_video_minutes: int
    allowed_extensions: list[str]
    url_import_enabled: bool
    storage_quota_mb: int | None
    default_whisper_model: str
    languages: list[LanguageOption]
    whisper_models: list[WhisperModelOption]


@router.get("/config", response_model=ClientConfig, summary="Limits and options for the UI")
def client_config(_user: CurrentUser, settings: SettingsDep) -> ClientConfig:
    return ClientConfig(
        max_upload_mb=settings.max_upload_mb,
        max_video_minutes=settings.max_video_minutes,
        allowed_extensions=list(ALLOWED_VIDEO_EXTENSIONS),
        url_import_enabled=settings.url_import_enabled,
        storage_quota_mb=settings.user_storage_quota_mb or None,
        default_whisper_model=settings.whisper_default_model,
        languages=[LanguageOption(code=code, name=name) for code, name in LANGUAGES.items()],
        whisper_models=[
            WhisperModelOption(
                id=key,
                label=str(meta["label"]),
                size_mb=int(meta["size_mb"]),
                multilingual=bool(meta["multilingual"]),
                note=str(meta["note"]),
            )
            for key, meta in WHISPER_MODELS.items()
        ],
    )
