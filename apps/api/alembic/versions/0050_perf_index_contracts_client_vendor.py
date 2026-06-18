"""Add composite index contracts(client_id, vendor_id).

Revision ID: 0050_perf_index_contracts_client_vendor
Revises: 0049_perf_indexes_notifications_reports
Create Date: 2026-06-17

PERF (B-PERF-4, audit 2026-06-17). ``contracts`` is looked up by
``WHERE client_id = ? AND vendor_id = ?`` on the hot paths:

- ``submission_service`` resolves the active contract on every provider
  upload, and
- ``document_analysis/expediente`` resolves it on every expediente analysis.

The table had only its primary key, so each of those was a sequential scan
that grows with the client x vendor relationship count. A composite
(client_id, vendor_id) index serves the predicate directly.

Created with CONCURRENTLY (no ACCESS EXCLUSIVE lock on the live table) inside
an autocommit_block — CONCURRENTLY cannot run inside Alembic's per-migration
transaction. IF NOT EXISTS keeps re-runs idempotent and matches the index now
declared on the Contract model.

NOTE (ops): a failed CONCURRENTLY build can leave an INVALID index; drop it
(DROP INDEX CONCURRENTLY IF EXISTS ix_contracts_client_vendor) before
re-running. Snapshot Neon before deploying — this auto-runs via the Render
preDeployCommand. Watch for an idle-in-transaction session blocking the build
(set idle_in_transaction_session_timeout on Neon), per the 0049 stall.
"""

from __future__ import annotations

from alembic import op

revision = "0050_perf_index_contracts_client_vendor"
down_revision = "0049_perf_indexes_notifications_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_contracts_client_vendor "
            "ON contracts (client_id, vendor_id)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_contracts_client_vendor"
        )
