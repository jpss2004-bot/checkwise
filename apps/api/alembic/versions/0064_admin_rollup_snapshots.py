"""Add admin_rollup_snapshots — precomputed admin ops-dashboard rollup cache.

Revision ID: 0064_admin_rollup_snapshots
Revises: 0057_user_session_epoch
Create Date: 2026-06-29

GET /admin/rollup scans every client's per-vendor compliance into memory on each
load — O(clients × vendors), seconds per hit at portfolio scale. This table
caches the heavy part (per-client rollup rows + the worst-8 at-risk vendors) as
JSON, one row per year, served stale-while-revalidate on read. The cheap
"now"-anchored counters (review-queue ageing, 7-day throughput, triage inbox)
stay LIVE on every request, so only the per-client portfolio map can lag minutes.

Plain CREATE TABLE — no ACCESS EXCLUSIVE on any live table, no data migration,
trivially reversible (DROP TABLE). Mirrors 0054_admin_calendar_snapshots.
Auto-runs via the Render preDeployCommand; snapshot Neon before deploying per
the standing convention.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0064_admin_rollup_snapshots"
down_revision = "0057_user_session_epoch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_rollup_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("year", name="uq_admin_rollup_snapshots_year"),
    )
    op.create_index(
        "ix_admin_rollup_snapshots_year",
        "admin_rollup_snapshots",
        ["year"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_rollup_snapshots_year",
        table_name="admin_rollup_snapshots",
    )
    op.drop_table("admin_rollup_snapshots")
