"""composite indexes for the project list, per-user job limits and the job queue

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-18 15:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES = (
    ("ix_projects_owner_created", "projects", ["owner_id", "created_at"]),
    ("ix_clips_owner_status", "clips", ["owner_id", "status"]),
    ("ix_jobs_owner_status", "jobs", ["owner_id", "status"]),
    ("ix_jobs_status_created", "jobs", ["status", "created_at"]),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
