"""Client notification severity column.

Phase 4 / Slice 4A — adds a ``severity`` discriminator on
``client_notifications`` so the client portal can render the
semáforo (green = approved/complete, yellow = pending/in-review,
red = rejected) the meeting-notes Phase 4 spec calls for. The
column is decoupled from ``notification_type`` so future types can
pick their own severity without retrofitting a mapping.

Additive: defaults to ``info`` on existing rows so the migration
runs without backfill on prod (no notifications written yet) and on
dev (small, ephemeral fixture set).

Revision ID: 0019_client_notif_severity
Revises: 0018_provider_legal_consent
Create Date: 2026-05-22

The revision identifier is intentionally abbreviated — the
``alembic_version.version_num`` column is ``VARCHAR(32)``, so any
identifier longer than 32 characters fails to stamp at the end of
``upgrade()``. ``client_notif_severity`` keeps the meaning while
fitting the constraint.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0019_client_notif_severity"
down_revision = "0018_provider_legal_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_notifications",
        sa.Column(
            "severity",
            sa.String(length=20),
            nullable=False,
            server_default="info",
        ),
    )


def downgrade() -> None:
    op.drop_column("client_notifications", "severity")
