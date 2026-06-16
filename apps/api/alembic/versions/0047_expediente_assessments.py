"""Add the expediente_assessments table (Phase 2 — situational pass).

Revision ID: 0047_expediente_assessments
Revises: 0046_submission_perf_indexes
Create Date: 2026-06-16

Phase 2 of the document-comprehension work. Where the per-document
comprehension lives in ``document_inspections.shadow_signals``, the
expediente-level situational assessment needs its own row keyed by
(client, vendor, period): the unit it reasons about is the whole set of a
provider's documents for a period, not a single document.

Additive and reviewer-facing only — nothing here alters user-visible
status. Re-runs append (history); the scope index serves "latest
assessment for this provider+period" lookups ordered by created_at.

A plain ``create_table`` (no CONCURRENTLY): the table does not exist yet,
so there is no live table to lock.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0047_expediente_assessments"
down_revision = "0046_submission_perf_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expediente_assessments",
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
            nullable=False,
        ),
        sa.Column(
            "period_id",
            sa.String(length=36),
            sa.ForeignKey("periods.id"),
            nullable=True,
        ),
        sa.Column(
            "contract_id",
            sa.String(length=36),
            sa.ForeignKey("contracts.id"),
            nullable=True,
        ),
        sa.Column("provider_id", sa.String(length=120), nullable=True),
        sa.Column("prompt_version", sa.String(length=60), nullable=True),
        sa.Column("coherence", sa.String(length=20), nullable=True),
        sa.Column("findings", sa.JSON(), nullable=True),
        sa.Column("coverage_gaps", sa.JSON(), nullable=True),
        sa.Column("document_ids", sa.JSON(), nullable=True),
        sa.Column("summary_for_reviewer", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_expediente_assessments_scope",
        "expediente_assessments",
        ["client_id", "vendor_id", "period_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_expediente_assessments_scope", table_name="expediente_assessments"
    )
    op.drop_table("expediente_assessments")
