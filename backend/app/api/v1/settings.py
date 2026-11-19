"""AI configuration and live AI status.

Local mode: the computer's setup. Server mode: each user's own provider and model (the
endpoint is fixed by the server). There are no administrator-only settings.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import CurrentUser, DbSession, SettingsDep
from app.core.errors import UnprocessableError
from app.services.ai import (
    endpoint_editable,
    load_ai_settings,
    ollama_models,
    pick_default_model,
    save_ai_settings,
    validate_model_name,
    validate_ollama_url,
)
from openclip_processing.errors import AIProviderError

router = APIRouter(tags=["settings"])


class AISettingsOut(BaseModel):
    provider: Literal["ollama", "external"]
    ollama_base_url: str
    ollama_model: str | None
    external_configured: bool
    external_name: str
    external_model: str | None
    external_base_url_host: str | None
    scope: Literal["computer", "account"] = Field(
        description="computer: this installation's setup (local mode); account: your own choice."
    )
    can_change_endpoint: bool


class AISettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["ollama", "external"] | None = None
    ollama_base_url: str | None = Field(default=None, max_length=300)
    ollama_model: str | None = Field(default=None, max_length=120)

    @field_validator("ollama_base_url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return validate_ollama_url(value) if value else None

    @field_validator("ollama_model")
    @classmethod
    def _model(cls, value: str | None) -> str | None:
        return validate_model_name(value) if value else None


class OllamaModelOut(BaseModel):
    name: str
    size_bytes: int | None
    parameter_size: str | None
    family: str | None


class OllamaStatusOut(BaseModel):
    reachable: bool
    version: str | None
    models: list[OllamaModelOut]
    selected_model: str | None
    selected_model_available: bool
    message: str | None


class ExternalStatusOut(BaseModel):
    configured: bool
    name: str
    model: str | None


class AIStatusOut(BaseModel):
    provider: Literal["ollama", "external"]
    ollama: OllamaStatusOut
    external: ExternalStatusOut


def _settings_out(db, settings, user) -> AISettingsOut:  # type: ignore[no-untyped-def]
    config = load_ai_settings(db, settings, user)
    host = (
        urlsplit(settings.external_ai_base_url).hostname if settings.external_ai_base_url else None
    )
    return AISettingsOut(
        provider=config["provider"],
        ollama_base_url=config["ollama_base_url"],
        ollama_model=config["ollama_model"],
        external_configured=settings.external_ai_configured,
        external_name=settings.external_ai_name,
        external_model=settings.external_ai_model,
        external_base_url_host=host,
        scope="account" if settings.accounts_enabled else "computer",
        can_change_endpoint=endpoint_editable(settings),
    )


@router.get("/settings/ai", response_model=AISettingsOut, summary="Current AI configuration")
def get_ai_settings(user: CurrentUser, db: DbSession, settings: SettingsDep) -> AISettingsOut:
    return _settings_out(db, settings, user)


@router.put(
    "/settings/ai",
    response_model=AISettingsOut,
    summary="Change your AI provider and model (local mode: this computer's whole setup)",
)
def update_ai_settings(
    body: AISettingsUpdate, user: CurrentUser, db: DbSession, settings: SettingsDep
) -> AISettingsOut:
    changes = body.model_dump(exclude_none=True)
    if changes.get("provider") == "external" and not settings.external_ai_configured:
        raise UnprocessableError(
            "The external provider is not configured on the server. Set OPENCLIP_EXTERNAL_AI_BASE_URL, "
            "OPENCLIP_EXTERNAL_AI_MODEL and (if needed) OPENCLIP_EXTERNAL_AI_API_KEY first.",
            code="external_not_configured",
        )
    if changes:
        save_ai_settings(db, settings, user, changes)
    return _settings_out(db, settings, user)


@router.get(
    "/ai/status",
    response_model=AIStatusOut,
    summary="Ollama connection, installed models, provider",
)
def ai_status(user: CurrentUser, db: DbSession, settings: SettingsDep) -> AIStatusOut:
    config = load_ai_settings(db, settings, user)
    try:
        version, models = ollama_models(config["ollama_base_url"])
        reachable, message = True, None
    except AIProviderError:
        version, models, reachable = None, [], False
        message = (
            "Ollama is not reachable. Install it from https://ollama.com, start it (open the app or "
            "run 'ollama serve'), then check the endpoint below."
        )
    names = [str(m.get("name")) for m in models]
    selected = config["ollama_model"] or (pick_default_model(models) if reachable else None)
    if reachable and not models:
        message = (
            "Ollama is running but has no models. Install one, for example: ollama pull gemma3:4b"
        )
    return AIStatusOut(
        provider=config["provider"],
        ollama=OllamaStatusOut(
            reachable=reachable,
            version=version,
            models=[
                OllamaModelOut(
                    name=str(m.get("name")),
                    size_bytes=m.get("size"),
                    parameter_size=(m.get("details") or {}).get("parameter_size"),
                    family=(m.get("details") or {}).get("family"),
                )
                for m in models
            ],
            selected_model=selected,
            selected_model_available=bool(selected and selected in names),
            message=message,
        ),
        external=ExternalStatusOut(
            configured=settings.external_ai_configured,
            name=settings.external_ai_name,
            model=settings.external_ai_model,
        ),
    )
