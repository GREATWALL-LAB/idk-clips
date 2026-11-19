"""age confirmation and email verification for accounts

Existing accounts get NULL for both: they confirm their age and verify their email
address the next time they log in. Nothing is assumed about anyone's age.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-18 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("age_confirmed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("email_code_sent_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("email_code_failures", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("email_code_failures")
        batch.drop_column("email_code_sent_at")
        batch.drop_column("email_verified_at")
        batch.drop_column("age_confirmed_at")
