"""paired workers, hybrid-mode job leases, per-clip aspect ratio, source metadata

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-13 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.base

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("app_version", sa.String(length=20), nullable=False),
        sa.Column("bridge_port", sa.Integer(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("preferred_model", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", app.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", app.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", app.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_workers_owner_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workers")),
    )
    with op.batch_alter_table("workers", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_workers_owner_id"), ["owner_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_workers_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_workers_token_hash"), ["token_hash"], unique=True)

    op.create_table(
        "pairing_codes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", app.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("expires_at", app.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("used_at", app.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_pairing_codes_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pairing_codes")),
    )
    with op.batch_alter_table("pairing_codes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pairing_codes_code_hash"), ["code_hash"], unique=True)
        batch_op.create_index(batch_op.f("ix_pairing_codes_owner_id"), ["owner_id"], unique=False)

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("preferences", sa.JSON(), nullable=False, server_default="{}")
        )

    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("source_meta", sa.JSON(), nullable=False, server_default="{}")
        )
        batch_op.add_column(sa.Column("worker_id", sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f("ix_projects_worker_id"), ["worker_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_projects_worker_id_workers"),
            "workers",
            ["worker_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("clips", schema=None) as batch_op:
        batch_op.add_column(sa.Column("aspect_ratio", sa.String(length=5), nullable=True))

    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("worker_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column("lease_expires_at", app.db.base.UTCDateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_index(batch_op.f("ix_jobs_worker_id"), ["worker_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_jobs_worker_id_workers"),
            "workers",
            ["worker_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "transfer_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("worker_id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", app.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("expires_at", app.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_transfer_tokens_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_transfer_tokens_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["workers.id"],
            name=op.f("fk_transfer_tokens_worker_id_workers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transfer_tokens")),
    )
    with op.batch_alter_table("transfer_tokens", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_transfer_tokens_owner_id"), ["owner_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_transfer_tokens_token_hash"), ["token_hash"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_transfer_tokens_worker_id"), ["worker_id"], unique=False
        )


def downgrade() -> None:
    op.drop_table("transfer_tokens")
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_jobs_worker_id_workers"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_jobs_worker_id"))
        batch_op.drop_column("attempts")
        batch_op.drop_column("lease_expires_at")
        batch_op.drop_column("worker_id")
    with op.batch_alter_table("clips", schema=None) as batch_op:
        batch_op.drop_column("aspect_ratio")
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_projects_worker_id_workers"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_projects_worker_id"))
        batch_op.drop_column("worker_id")
        batch_op.drop_column("source_meta")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("preferences")
    op.drop_table("pairing_codes")
    op.drop_table("workers")
