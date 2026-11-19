"""Settings for serverless hosting (for example the API on Vercel with Neon PostgreSQL)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, normalize_database_url
from app.db.session import Database
from tests.conftest import make_settings

PG = "postgres://user:s3cret-pass@db.example.com/idk?sslmode=require"


def test_provider_urls_are_normalised_for_psycopg() -> None:
    assert normalize_database_url(PG).startswith("postgresql+psycopg://user:")
    assert normalize_database_url("postgresql://u@h/d") == "postgresql+psycopg://u@h/d"
    assert normalize_database_url("postgresql+psycopg://u@h/d") == "postgresql+psycopg://u@h/d"
    assert normalize_database_url("sqlite:///x.db") == "sqlite:///x.db"


def test_database_url_can_come_from_the_hosts_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", PG)
    settings = make_settings(tmp_path, mode="hybrid", database_url_env="DATABASE_URL")
    assert settings.sqlalchemy_url.startswith("postgresql+psycopg://")
    # The URL and its password are masked in logs.
    assert PG in settings.secret_values() and "s3cret-pass" in settings.secret_values()


def test_the_explicit_setting_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", PG)
    settings = make_settings(
        tmp_path, database_url="sqlite:///explicit.db", database_url_env="DATABASE_URL"
    )
    assert settings.sqlalchemy_url == "sqlite:///explicit.db"


@pytest.mark.parametrize(
    "overrides",
    [
        {"mode": "server", "database_url": PG},  # the server would need to store videos
        {"mode": "local", "database_url": PG},
        {"mode": "hybrid"},  # SQLite cannot live in a serverless function
    ],
)
def test_serverless_needs_hybrid_mode_and_postgres(tmp_path: Path, overrides: dict) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path, serverless=True, **overrides)


def test_serverless_hybrid_with_postgres_is_accepted(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, serverless=True, mode="hybrid", database_url=PG)
    assert isinstance(settings, Settings) and settings.serverless


def test_postgres_connections_avoid_prepared_statements() -> None:
    database = Database("postgresql+psycopg://u:p@127.0.0.1:1/x", small_pool=True)
    try:
        assert database.engine.pool.size() == 1
        assert database.engine.dialect.dbapi is not None
        # Connection arguments are what transaction-mode poolers need.
        args = database.engine.url.translate_connect_args()
        assert args["database"] == "x"
    finally:
        database.dispose()
