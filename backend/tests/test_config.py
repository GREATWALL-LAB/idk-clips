from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, Settings


def test_defaults_are_safe_for_local_use(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENCLIP_HOST", "OPENCLIP_PORT", "OPENCLIP_CORS_ORIGINS", "OPENCLIP_ENVIRONMENT"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.environment == "development"
    assert settings.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]
    assert settings.docs_enabled is True


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCLIP_PORT", "8123")
    monkeypatch.setenv("OPENCLIP_ENVIRONMENT", "production")
    monkeypatch.setenv("OPENCLIP_CORS_ORIGINS", "https://clips.example.com, http://localhost:4000")
    settings = Settings(_env_file=None)
    assert settings.port == 8123
    assert settings.environment == "production"
    assert settings.cors_origins == ["https://clips.example.com", "http://localhost:4000"]
    assert settings.docs_enabled is False  # docs default to off in production


def test_env_file_is_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCLIP_PORT", raising=False)
    env_file = tmp_path / "settings.test.env"
    env_file.write_text("OPENCLIP_PORT=9001\nOPENCLIP_LOG_FORMAT=json\n", encoding="utf-8")
    settings = Settings(_env_file=env_file)
    assert settings.port == 9001
    assert settings.log_format == "json"


def test_wildcard_cors_origin_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Wildcard"):
        Settings(_env_file=None, cors_origins="*")


@pytest.mark.parametrize(
    "origin", ["localhost:3000", "ftp://example.com", "http://example.com/app", "http://x.com?a=1"]
)
def test_malformed_cors_origins_are_rejected(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=origin)


def test_invalid_port_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, port=70000)


def test_relative_data_dir_is_resolved_from_project_root() -> None:
    settings = Settings(_env_file=None, data_dir="custom-data")
    assert settings.data_dir == (PROJECT_ROOT / "custom-data").resolve()


def test_ollama_url_must_be_http() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ollama_base_url="file:///etc/passwd")
    assert Settings(_env_file=None, ollama_base_url="http://host:11434/").ollama_base_url == (
        "http://host:11434"
    )
