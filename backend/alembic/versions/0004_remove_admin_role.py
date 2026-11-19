"""remove the administrator role: IDK Clips has ordinary user accounts only

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-18 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Batch mode rebuilds the table on SQLite, which cannot drop columns in place.
    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_admin")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false())
        )
