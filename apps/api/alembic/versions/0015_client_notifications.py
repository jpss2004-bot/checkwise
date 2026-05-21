"""Client notification inbox.

Revision ID: 0015_client_notifications
Revises: 0014_wise_events
Create Date: 2026-05-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0015_client_notifications"
down_revision = "0014_wise_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_notifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "client_id",
            sa.String(length=36),
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        sa.Column(
            "vendor_id",
            sa.String(length=36),
            sa.ForeignKey("vendors.id"),
            nullable=True,
        ),
        sa.Column(
            "submission_id",
            sa.String(length=36),
            sa.ForeignKey("submissions.id"),
            nullable=True,
        ),
        sa.Column("notification_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("action_url", sa.String(length=512), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_client_notifications_client_id", "client_notifications", ["client_id"])
    op.create_index("ix_client_notifications_vendor_id", "client_notifications", ["vendor_id"])
    op.create_index(
        "ix_client_notifications_submission_id",
        "client_notifications",
        ["submission_id"],
    )
    op.create_index(
        "ix_client_notifications_notification_type",
        "client_notifications",
        ["notification_type"],
    )
    op.create_index("ix_client_notifications_read_at", "client_notifications", ["read_at"])
    op.create_index(
        "ix_client_notifications_created_at",
        "client_notifications",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_client_notifications_created_at", table_name="client_notifications")
    op.drop_index("ix_client_notifications_read_at", table_name="client_notifications")
    op.drop_index(
        "ix_client_notifications_notification_type",
        table_name="client_notifications",
    )
    op.drop_index("ix_client_notifications_submission_id", table_name="client_notifications")
    op.drop_index("ix_client_notifications_vendor_id", table_name="client_notifications")
    op.drop_index("ix_client_notifications_client_id", table_name="client_notifications")
    op.drop_table("client_notifications")
