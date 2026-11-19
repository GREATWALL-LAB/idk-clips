"""aspect ratio per project and automatic subject framing per clip

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12 22:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("aspect_ratio", sa.String(length=5), nullable=False, server_default="9:16")
        )
    with op.batch_alter_table("clips", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("auto_frame", sa.Boolean(), nullable=False, server_default=sa.true())
        )
    # The old "original" layout is replaced by explicit aspect ratios; "fit" never distorts.
    op.execute("UPDATE clips SET layout = 'fit' WHERE layout = 'original'")


def downgrade() -> None:
    with op.batch_alter_table("clips", schema=None) as batch_op:
        batch_op.drop_column("auto_frame")
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_column("aspect_ratio")
