"""AI provider configuration and provider construction for jobs.

Who changes what (there are no roles):

- Local mode: the person using this computer edits the whole setup (provider, Ollama
  endpoint, model). It is stored once for the installation.
- Server mode: each user chooses their *own* provider and model, stored on their account.
  The Ollama endpoint and any external provider come only from the server's environment,
  so no user can make the server send requests to an address they choose (SSRF).
- Hybrid mode: AI runs on each user's own worker with its own settings.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import UnprocessableError
from app.db.models import AppSetting, User
from openclip_processing.errors import AIProviderError
from openclip_processing.llm import LLMProvider, OllamaProvider, OpenAICompatibleProvider

AI_SETTINGS_KEY = "ai"
MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")
NO_MODEL_MESSAGE = (
    "No Ollama model is installed. Install one, for example 'ollama pull gemma3:4b', "
    "then choose it in Settings > AI."
)


PERSONAL_KEYS = ("provider", "ollama_model")


def load_ai_settings(db: Session, settings: Settings, user: User | None = None) -> dict[str, Any]:
    """The AI setup used for ``user`` (or the installation default without a user)."""
    row = db.get(AppSetting, AI_SETTINGS_KEY)
    stored = dict(row.value) if row else {}
    config = {
        "provider": stored.get("provider") or "ollama",
        "ollama_base_url": stored.get("ollama_base_url") or settings.ollama_base_url,
        "ollama_model": stored.get("ollama_model") or settings.ollama_model,
    }
    if settings.accounts_enabled and user is not None:
        personal = dict((user.preferences or {}).get("ai") or {})
        if personal.get("provider") in {"ollama", "external"}:
            config["provider"] = personal["provider"]
        if personal.get("ollama_model"):
            config["ollama_model"] = personal["ollama_model"]
    return config


def endpoint_editable(settings: Settings) -> bool:
    """Only in local mode, where the user owns the machine, may the endpoint change."""
    return not settings.accounts_enabled


def save_ai_settings(db: Session, settings: Settings, user: User, values: dict[str, Any]) -> None:
    if not settings.accounts_enabled:
        row = db.get(AppSetting, AI_SETTINGS_KEY)
        if row is None:
            db.add(AppSetting(key=AI_SETTINGS_KEY, value=values))
        else:
            row.value = {**dict(row.value), **values}
        db.commit()
        return
    current = load_ai_settings(db, settings, user)
    url = values.get("ollama_base_url")
    if url and url != current["ollama_base_url"]:
        raise UnprocessableError(
            "The Ollama endpoint is part of the server's configuration "
            "(OPENCLIP_OLLAMA_BASE_URL) and cannot be changed from the website.",
            code="endpoint_server_only",
        )
    personal = dict((user.preferences or {}).get("ai") or {})
    personal.update({key: values[key] for key in PERSONAL_KEYS if values.get(key)})
    user.preferences = {**dict(user.preferences or {}), "ai": personal}
    db.commit()


def validate_ollama_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise ValueError("Use an http(s) URL such as http://127.0.0.1:11434 (no credentials).")
    return value.strip().rstrip("/")


def validate_model_name(value: str) -> str:
    if not MODEL_NAME_RE.match(value):
        raise ValueError("That does not look like a valid model name.")
    return value


def ollama_models(
    base_url: str, transport: httpx.BaseTransport | None = None
) -> tuple[str | None, list[dict[str, Any]]]:
    """Return (version, models). Raises AIProviderError when Ollama is unreachable."""
    provider = OllamaProvider(base_url, "-", transport=transport)
    try:
        return provider.version(), provider.list_models()
    except httpx.HTTPError as exc:
        raise AIProviderError("Ollama is not reachable.", detail=str(exc)) from exc


def pick_default_model(models: list[dict[str, Any]]) -> str | None:
    """Prefer chat models; embedding models cannot answer prompts."""
    names = [str(m.get("name")) for m in models if m.get("name")]
    chat = [n for n in names if "embed" not in n.lower()]
    return (chat or [None])[0]


def build_provider(db: Session, settings: Settings) -> LLMProvider:
    return provider_from_config(load_ai_settings(db, settings), settings)


def provider_from_config(config: dict[str, Any], settings: Settings) -> LLMProvider:
    """Build the AI provider for one job.

    ``config`` comes from the job spec. A paired worker receives ``provider="worker"``:
    it always uses its *own* endpoint and keys (from its local settings); only the
    model name may be suggested by the server, and it is validated first.
    """
    if config.get("provider") == "worker":
        requested = config.get("ollama_model")
        config = {
            "provider": settings.agent_ai_provider,
            "ollama_base_url": settings.ollama_base_url,
            "ollama_model": validate_model_name(requested) if requested else settings.ollama_model,
        }
    config = {
        "provider": config.get("provider") or "ollama",
        "ollama_base_url": config.get("ollama_base_url") or settings.ollama_base_url,
        "ollama_model": config.get("ollama_model") or settings.ollama_model,
    }
    if config["provider"] == "external":
        if not settings.external_ai_configured:
            raise AIProviderError(
                "The external AI provider is not configured on the server. Set "
                "OPENCLIP_EXTERNAL_AI_BASE_URL and OPENCLIP_EXTERNAL_AI_MODEL, or switch to Ollama."
            )
        key = (
            settings.external_ai_api_key.get_secret_value()
            if settings.external_ai_api_key
            else None
        )
        return OpenAICompatibleProvider(
            settings.external_ai_base_url,  # type: ignore[arg-type]
            settings.external_ai_model,  # type: ignore[arg-type]
            key,
        )
    model = config["ollama_model"]
    if not model:
        try:
            _, models = ollama_models(config["ollama_base_url"])
        except AIProviderError as exc:
            raise AIProviderError(
                "Ollama is not reachable. Start the Ollama app (or run 'ollama serve') and check the "
                "endpoint in Settings > AI.",
                detail=exc.detail,
            ) from exc
        model = pick_default_model(models)
        if not model:
            raise AIProviderError(NO_MODEL_MESSAGE)
    return OllamaProvider(
        config["ollama_base_url"],
        model,
        timeout=settings.ollama_timeout_seconds,
        num_ctx=settings.ollama_num_ctx,
    )
