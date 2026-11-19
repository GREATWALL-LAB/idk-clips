"""The database schema built by the migrations matches the SQLAlchemy models exactly."""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.db.base import Base
from app.db.migrate import upgrade_to_head
from tests.conftest import make_settings


def test_migrations_match_the_models(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upgrade_to_head(settings.sqlalchemy_url)
    engine = sa.create_engine(settings.sqlalchemy_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"compare_type": True, "render_as_batch": True}
            )
            differences = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()
    assert differences == [], differences


def test_migrations_can_be_reversed_to_the_previous_version(tmp_path: Path) -> None:
    from alembic import command

    from app.db.migrate import alembic_config

    settings = make_settings(tmp_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    config = alembic_config(settings.sqlalchemy_url)
    command.upgrade(config, "head")
    command.downgrade(config, "0003")
    command.upgrade(config, "head")
