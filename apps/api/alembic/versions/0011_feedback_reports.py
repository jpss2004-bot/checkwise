"""Feedback reports — persistence for the in-app Reportar launcher.

Revision ID: 0011_feedback_reports
Revises: 0010_contact_requests
Create Date: 2026-05-20

Adds a ``feedback_reports`` table so bug reports and improvement
suggestions from the floating launcher are stored canonically in our
own DB instead of relying on Slack as the system of record. Slack
delivery becomes a side-effect notifier: the row exists before the
BackgroundTask fires, and the task writes back ``slack_message_ts`` +
``slack_delivery_status`` on completion.

Two source modes share this table:
- ``source='authenticated'`` — JWT-backed staff submissions. User
  identity columns (``user_id``, ``user_email``, ``user_full_name``,
  ``user_roles``) are populated.
- ``source='public'`` — anonymous landing-page submissions. User
  identity columns are NULL; ``contact_email`` (optional) and
  ``ip_hash`` (peppered SHA-256, same algorithm as
  ``contact_requests.ip_hash``) carry the only attribution.

Screenshot bytes live in the standard storage backend (S3/R2 in prod,
local on dev). The row carries the key + size in bytes so list views
can render "PNG · 184 KB" without a HEAD call to the bucket.

Conventions matched to the rest of the schema:
- ``String(36)`` ids.
- ``DateTime(timezone=True)`` timestamps with default ``func.now()``.
- ``TimestampMixin`` semantics replicated inline.
- FK on ``user_id`` / ``triaged_by_user_id`` → ``users.id`` (no
  cascade; users are soft-deactivated, not removed).

Indexes:
- ``status`` — primary triage filter ("show me everything new").
- ``created_at`` — recency-first listings.
- ``source`` — split authenticated vs public surfaces in the queue.
- ``ip_hash`` — abuse-pattern triage on public submissions.
- ``user_id`` — "everything reported by user X" for support cases.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011_feedback_reports"
down_revision = "0010_contact_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        # Source + visibility.
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default="authenticated",
        ),
        sa.Column(
            "is_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        # Page context.
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("path", sa.String(length=512), nullable=True),
        sa.Column("viewport", sa.String(length=32), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("console_logs", sa.Text(), nullable=True),
        # Authenticated submitter (NULL on public).
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("user_email", sa.String(length=254), nullable=True),
        sa.Column("user_full_name", sa.String(length=200), nullable=True),
        sa.Column("user_roles", sa.String(length=500), nullable=True),
        # Anonymous submitter (NULL on authenticated).
        sa.Column("contact_email", sa.String(length=254), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        # Screenshot.
        sa.Column("screenshot_storage_key", sa.String(length=512), nullable=True),
        sa.Column("screenshot_size_bytes", sa.Integer(), nullable=True),
        # Slack side-effect status.
        sa.Column("slack_message_ts", sa.String(length=64), nullable=True),
        sa.Column(
            "slack_delivery_status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("slack_delivery_error", sa.Text(), nullable=True),
        # Triage workflow.
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="new",
        ),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "triaged_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("triaged_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_feedback_reports_status", "feedback_reports", ["status"]
    )
    op.create_index(
        "ix_feedback_reports_created_at", "feedback_reports", ["created_at"]
    )
    op.create_index(
        "ix_feedback_reports_source", "feedback_reports", ["source"]
    )
    op.create_index(
        "ix_feedback_reports_ip_hash", "feedback_reports", ["ip_hash"]
    )
    op.create_index(
        "ix_feedback_reports_user_id", "feedback_reports", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_reports_user_id", table_name="feedback_reports")
    op.drop_index("ix_feedback_reports_ip_hash", table_name="feedback_reports")
    op.drop_index("ix_feedback_reports_source", table_name="feedback_reports")
    op.drop_index("ix_feedback_reports_created_at", table_name="feedback_reports")
    op.drop_index("ix_feedback_reports_status", table_name="feedback_reports")
    op.drop_table("feedback_reports")
