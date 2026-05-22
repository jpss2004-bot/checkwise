"""Provider notification inbox.

Phase 4 / Slice 4B — provider-facing analogue of
``client_notifications``. Keyed on ``workspace_id`` (the natural
tenant boundary on the portal side) instead of
``client_id`` + ``vendor_id``. Ships with ``severity`` from day 1
so the surface inherits the same semáforo treatment the client
inbox got in Slice 4A — no follow-up evolution step.

Emit-site (this slice): the reviewer-decision branch of
``submission_workflow.apply_reviewer_decision``. Other event sources
(scheduled expiry, "due soon") will land alongside their respective
runners.

Revision ID: 0020_provider_notifications
Revises: 0019_client_notif_severity
Create Date: 2026-05-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0020_provider_notifications"
down_revision = "0019_client_notif_severity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_notifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("provider_workspaces.id"),
            nullable=False,
        ),
        sa.Column(
            "submission_id",
            sa.String(length=36),
            sa.ForeignKey("submissions.id"),
            nullable=True,
        ),
        sa.Column(
            "notification_type", sa.String(length=80), nullable=False
        ),
        sa.Column(
            "severity",
            sa.String(length=20),
            nullable=False,
            server_default="info",
        ),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("action_url", sa.String(length=512), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "read_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Two indexes serve the two hot paths: the unread-count query
    # (workspace_id + read_at IS NULL) and the list-by-recency query
    # (workspace_id + ORDER BY created_at DESC).
    op.create_index(
        "ix_provider_notifications_workspace_read_at",
        "provider_notifications",
        ["workspace_id", "read_at"],
    )
    op.create_index(
        "ix_provider_notifications_workspace_created_at",
        "provider_notifications",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "ix_provider_notifications_notification_type",
        "provider_notifications",
        ["notification_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_notifications_notification_type",
        table_name="provider_notifications",
    )
    op.drop_index(
        "ix_provider_notifications_workspace_created_at",
        table_name="provider_notifications",
    )
    op.drop_index(
        "ix_provider_notifications_workspace_read_at",
        table_name="provider_notifications",
    )
    op.drop_table("provider_notifications")
