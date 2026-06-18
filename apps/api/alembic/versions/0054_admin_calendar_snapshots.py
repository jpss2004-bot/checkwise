"""Add admin_calendar_snapshots — precomputed admin calendar overview cache.

Revision ID: 0054_admin_calendar_snapshots
Revises: 0053_perf_indexes_validation_events
Create Date: 2026-06-18

The admin calendar overview (GET /admin/calendar/grid, no client_id) is an
O(clients) compliance scan at ~90 ms/client — seconds per load once the
portfolio is large. This table caches each client's contribution (its 12-month
cells + the rollup the overview needs) as JSON, one row per (year, client_id),
so the endpoint reads + sums rows instead of re-scanning. It is refreshed
stale-while-revalidate on read and by the ``checkwise-calendar-snapshot`` cron;
the per-client DRILL stays live, so obligation detail is never stale.

Plain CREATE TABLE — no ACCESS EXCLUSIVE on any live table, no data migration,
trivially reversible (DROP TABLE). Auto-runs via the Render preDeployCommand;
snapshot Neon before deploying per the standing convention.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0054_admin_calendar_snapshots"
down_revision = "0053_perf_indexes_validation_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_calendar_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column("client_name", sa.String(length=255), nullable=False),
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
        sa.UniqueConstraint(
            "year", "client_id", name="uq_admin_calendar_snapshots_year_client"
        ),
    )
    op.create_index(
        "ix_admin_calendar_snapshots_year",
        "admin_calendar_snapshots",
        ["year"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_calendar_snapshots_year",
        table_name="admin_calendar_snapshots",
    )
    op.drop_table("admin_calendar_snapshots")
