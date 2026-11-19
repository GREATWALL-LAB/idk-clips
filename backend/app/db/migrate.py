"""Run Alembic migrations programmatically (used at startup and by the CLI)."""

from __future__ import annotations

from alembic import command
from alembic.config import Config

from app.core.config import BACKEND_DIR


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    # Percent signs must be escaped for ConfigParser interpolation.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


def upgrade_to_head(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")
