"""Native intake validation and inspection foundation.

Revision ID: 0002_native_intake_foundation
Revises: 0001_initial_schema
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_native_intake_foundation"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "validation_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "submission_id", sa.String(length=36), sa.ForeignKey("submissions.id"), nullable=False
        ),
        sa.Column(
            "document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=True
        ),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("rule_code", sa.String(length=120), nullable=True),
        sa.Column("result", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False, server_default="info"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("actor_type", sa.String(length=60), nullable=False, server_default="system"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_validation_events_submission_id", "validation_events", ["submission_id"])
    op.create_index("ix_validation_events_event_type", "validation_events", ["event_type"])

    op.create_table(
        "document_inspections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False
        ),
        sa.Column("is_pdf", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_corrupt", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_encrypted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("text_char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_text", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "is_probably_scanned", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("detected_institution", sa.String(length=80), nullable=True),
        sa.Column("detected_document_type", sa.String(length=120), nullable=True),
        sa.Column("detected_rfcs", sa.JSON(), nullable=True),
        sa.Column("detected_dates", sa.JSON(), nullable=True),
        sa.Column("period_mentions", sa.JSON(), nullable=True),
        sa.Column("requirement_match_confidence", sa.Float(), nullable=True),
        sa.Column("mismatch_reason", sa.Text(), nullable=True),
        sa.Column("inspection_error", sa.Text(), nullable=True),
        sa.Column("raw_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("document_id", name="uq_document_inspections_document_id"),
    )


def downgrade() -> None:
    op.drop_table("document_inspections")
    op.drop_index("ix_validation_events_event_type", table_name="validation_events")
    op.drop_index("ix_validation_events_submission_id", table_name="validation_events")
    op.drop_table("validation_events")
