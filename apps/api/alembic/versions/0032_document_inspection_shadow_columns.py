"""Phase 2 — shadow-analysis columns on document_inspections.

Adds the columns used by the background ``shadow_runner`` to persist
the secondary AI extraction (Claude) alongside the existing inline
heuristic extraction. The user-visible flow is unchanged: heuristic
still drives status, badges, and reviewer messaging. These columns
are populated by a FastAPI ``BackgroundTask`` fired after the intake
transaction commits.

Columns:

* ``shadow_provider_id``     — e.g. ``anthropic:claude-sonnet-4-6``.
* ``shadow_prompt_version``  — prompt-file stem, e.g. ``csf_sat.v1``.
* ``shadow_signals``         — JSON blob mirroring DocumentSignals.
* ``shadow_confidence``      — float copied from
  ``signals.requirement_match_confidence`` for cheap range queries.
* ``shadow_latency_ms``      — wall-clock duration of the provider
  call, used to monitor performance regressions over time.
* ``shadow_error``           — opaque error code when the run failed
  (``timeout`` / ``provider_error`` / ``daily_cap_exceeded`` / etc.).
* ``shadow_completed_at``    — set when a run finishes, success or
  failure. ``NULL`` means "no shadow run yet" — the reviewer UI uses
  this to distinguish pending from failed.

All columns are nullable. The migration is additive and safely
reversible.

Revision ID: 0032_document_inspection_shadow_columns
Revises: 0031_audit_log_append_only
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0032_document_inspection_shadow_columns"
down_revision = "0031_audit_log_append_only"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ``JSON`` (not ``JSONB``) for parity with the existing
    # ``raw_metadata`` column on the same table. Postgres in
    # production uses JSON storage either way; SQLite (test) tolerates
    # both via the SQLAlchemy ``JSON`` type.
    op.add_column(
        "document_inspections",
        sa.Column("shadow_provider_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "document_inspections",
        sa.Column("shadow_prompt_version", sa.String(length=60), nullable=True),
    )
    op.add_column(
        "document_inspections",
        sa.Column(
            "shadow_signals",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )
    op.add_column(
        "document_inspections",
        sa.Column("shadow_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "document_inspections",
        sa.Column("shadow_latency_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_inspections",
        sa.Column("shadow_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_inspections",
        sa.Column(
            "shadow_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("document_inspections", "shadow_completed_at")
    op.drop_column("document_inspections", "shadow_error")
    op.drop_column("document_inspections", "shadow_latency_ms")
    op.drop_column("document_inspections", "shadow_confidence")
    op.drop_column("document_inspections", "shadow_signals")
    op.drop_column("document_inspections", "shadow_prompt_version")
    op.drop_column("document_inspections", "shadow_provider_id")
