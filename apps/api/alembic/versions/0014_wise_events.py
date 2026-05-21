"""Wise copilot analytics events.

Revision ID: 0014_wise_events
Revises: 0013_canonicalize_persona_type
Create Date: 2026-05-21

Adds the ``wise_events`` table that captures every meaningful
interaction with the new Wise copilot dock on the provider portal:

* ``wise.first_render`` — emitted once per session when the dock mounts.
* ``wise.opened``       — user expanded the dock.
* ``wise.collapsed``    — user collapsed the dock.
* ``wise.suggestion_clicked`` — user clicked a Wise suggestion CTA;
  ``payload`` carries the suggestion id and href.

Conventions:
- 36-char string ids matching the rest of the schema.
- ``DateTime(timezone=True)`` timestamps.
- Indexes on ``workspace_id``, ``user_id``, ``event_type``, and
  ``occurred_at`` — the four columns we'll filter on when running
  time-to-first-upload funnels and per-vendor diagnostics.
- No FK to ``users`` is required (the dock may emit events under a
  cookie-only portal session), but when a user id is present we'll
  store it and index it.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0014_wise_events"
down_revision = "0013_canonicalize_persona_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wise_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("provider_workspaces.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_wise_events_workspace_id",
        "wise_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_wise_events_user_id",
        "wise_events",
        ["user_id"],
    )
    op.create_index(
        "ix_wise_events_event_type",
        "wise_events",
        ["event_type"],
    )
    op.create_index(
        "ix_wise_events_occurred_at",
        "wise_events",
        ["occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_wise_events_occurred_at", table_name="wise_events")
    op.drop_index("ix_wise_events_event_type", table_name="wise_events")
    op.drop_index("ix_wise_events_user_id", table_name="wise_events")
    op.drop_index("ix_wise_events_workspace_id", table_name="wise_events")
    op.drop_table("wise_events")
