"""Checklist hot-path indexes (performance).

Audit 2026-06-09 (docs/audits/checklist-system-audit-2026-06-09.md) found
that the evidence-slot engine full-scans ``submissions`` on every
dashboard / calendar / onboarding / client-portfolio view, because
Postgres does not auto-index foreign keys and these columns were never
indexed:

    submissions.(client_id, vendor_id)   ← every slot build's WHERE
    submissions.(client_id, status)      ← status-filtered portfolio views
    submissions.period_id                ← calendar / period filters
    submissions.requirement_id           ← requirement detail lookups
    documents.submission_id              ← the app's most common join
    documents.status                     ← status queues
    document_status_history.(document_id, created_at) / submission_id
    audit_log.(entity_type, entity_id) / actor_id

All additive, behavior-preserving, and reversible. Built with
``CREATE INDEX CONCURRENTLY`` so the deploy never takes an
``ACCESS EXCLUSIVE`` lock on a populated prod table — this requires the
statements run OUTSIDE the migration's transaction, hence the
``autocommit_block``. ``IF NOT EXISTS`` keeps re-runs idempotent.

The matching model-level ``__table_args__`` (entities.py) keep the
SQLite test schema (``create_all``) and Alembic autogenerate in parity;
this migration is what actually creates them on Postgres.

Revision ID: 0034_checklist_hot_indexes
Revises: 0033_user_legal_consent
Create Date: 2026-06-09
"""

from __future__ import annotations

from alembic import op

revision = "0034_checklist_hot_indexes"
down_revision = "0033_user_legal_consent"
branch_labels = None
depends_on = None


# (index_name, table, column-list SQL) — kept declarative so up/down
# stay in lockstep.
_INDEXES: list[tuple[str, str, str]] = [
    ("ix_submissions_client_vendor", "submissions", "(client_id, vendor_id)"),
    ("ix_submissions_client_status", "submissions", "(client_id, status)"),
    ("ix_submissions_period_id", "submissions", "(period_id)"),
    ("ix_submissions_requirement_id", "submissions", "(requirement_id)"),
    ("ix_documents_submission_id", "documents", "(submission_id)"),
    ("ix_documents_status", "documents", "(status)"),
    (
        "ix_doc_status_history_document",
        "document_status_history",
        "(document_id, created_at)",
    ),
    (
        "ix_doc_status_history_submission",
        "document_status_history",
        "(submission_id)",
    ),
    ("ix_audit_log_entity", "audit_log", "(entity_type, entity_id)"),
    ("ix_audit_log_actor", "audit_log", "(actor_id)"),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite/other: build plainly (no CONCURRENTLY, no autocommit).
        for name, table, cols in _INDEXES:
            op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} {cols}")
        return
    # Postgres prod path: non-blocking concurrent build, outside the
    # migration transaction.
    with op.get_context().autocommit_block():
        for name, table, cols in _INDEXES:
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} {cols}"
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        for name, _table, _cols in _INDEXES:
            op.execute(f"DROP INDEX IF EXISTS {name}")
        return
    with op.get_context().autocommit_block():
        for name, _table, _cols in _INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
