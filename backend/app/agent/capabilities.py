"""What this computer can do: FFmpeg, transcription device, Ollama and its models.

Shown in the dashboard next to the worker and printed by ``doctor``. The server
never bases a security decision on this self-reported information.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import Settings
from app.services.ai import ollama_models
from app.services.system_status import SystemStatusService
from openclip_processing.errors import AIProviderError


def system_components(settings: Settings) -> list[dict[str, Any]]:
    """Component checks without the database (a worker has none)."""
    status = asyncio.run(SystemStatusService(settings, cache_seconds=0).get_status())
    return [
        component.model_dump()
        for component in status.components
        if component.key not in {"database", "jobs"}
    ]


def installed_models(settings: Settings) -> list[str]:
    try:
        _, models = ollama_models(settings.ollama_base_url)
    except AIProviderError:
        return []
    names = [str(m.get("name")) for m in models if m.get("name")]
    return [name for name in names if "embed" not in name.lower()][:100]


def gpu_name() -> str | None:
    try:
        import ctranslate2

        return "NVIDIA GPU (CUDA)" if ctranslate2.get_cuda_device_count() else None
    except Exception:
        return None


def collect_capabilities(settings: Settings) -> dict[str, Any]:
    components = [
        {key: item.get(key) for key in ("key", "name", "status", "version", "detail")}
        for item in system_components(settings)
    ]
    return {
        "components": components,
        "ollama_models": installed_models(settings),
        "ai_provider": settings.agent_ai_provider,
        "gpu": gpu_name(),
    }
