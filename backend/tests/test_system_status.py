from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.services.system_status import SystemStatusService
from tests.conftest import make_settings


def _ollama_transport(models: list[dict]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.40.16"})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": models})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_status_requires_sign_in(client: TestClient) -> None:
    assert client.get("/api/v1/system/status").status_code == 401


def test_status_endpoint_reports_components_without_paths(
    user_client: TestClient, settings
) -> None:  # type: ignore[no-untyped-def]
    response = user_client.get("/api/v1/system/status")
    assert response.status_code == 200
    body = response.json()
    keys = {component["key"] for component in body["components"]}
    assert keys == {"database", "jobs", "ffmpeg", "ffprobe", "transcription", "ollama"}
    components = {c["key"]: c for c in body["components"]}
    assert components["database"]["status"] == "ok"
    assert components["ollama"]["status"] == "unavailable"
    assert components["ollama"]["hint"]
    # No absolute paths, configured URLs or database URLs leak to clients.
    assert str(settings.data_dir) not in response.text
    assert str(settings.tools_dir) not in response.text
    assert "127.0.0.1:9" not in response.text
    assert "sqlite:" not in response.text


def test_readiness_probe_is_public(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": True, "storage": True}}


def test_ollama_reachable_with_models(tmp_path: Path) -> None:
    service = SystemStatusService(
        make_settings(tmp_path), transport=_ollama_transport([{"name": "gemma4:12b"}])
    )
    status = asyncio.run(service.get_status())
    ollama = next(c for c in status.components if c.key == "ollama")
    assert ollama.status == "ok"
    assert ollama.version == "0.40.16"
    assert ollama.detail == "1 model installed"


def test_ollama_without_models_suggests_pull(tmp_path: Path) -> None:
    service = SystemStatusService(make_settings(tmp_path), transport=_ollama_transport([]))
    ollama = next(c for c in asyncio.run(service.get_status()).components if c.key == "ollama")
    assert ollama.status == "ok"
    assert ollama.hint and "ollama pull" in ollama.hint


def test_missing_ffmpeg_degrades_status(tmp_path: Path) -> None:
    service = SystemStatusService(
        make_settings(tmp_path, ffmpeg_path=str(tmp_path / "missing" / "ffmpeg.exe")),
        transport=_ollama_transport([]),
    )
    status = asyncio.run(service.get_status())
    ffmpeg = next(c for c in status.components if c.key == "ffmpeg")
    assert ffmpeg.status == "misconfigured"
    assert status.status == "degraded"
