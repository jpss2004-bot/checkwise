"""Add B-tree indexes for the admin-list pagination + reviewer-queue COUNTs.

Revision ID: 0051_perf_indexes_admin_lists_and_queue
Revises: 0050_perf_index_contracts_client_vendor
Create Date: 2026-06-18

PERF (systemic pagination/virtualization pass, 2026-06-18). The server-side
pagination added to the admin rosters and the reviewer queue/COUNT paths need
indexes to be fast at thousands of rows, otherwise each page is a sort/scan of
the whole table:

- clients (created_at): /admin/clients lists ORDER BY created_at DESC + offset.
- vendors (client_id, created_at): /admin/vendors filtered by client_id then
  ORDER BY created_at DESC + offset (e.g. the per-client vendor view).
- submissions (status, created_at): the reviewer queue filters
  WHERE status IN (...) ORDER BY created_at and runs a COUNT over the same set
  on every load.
- submissions (status, updated_at): the rolling-7-day throughput counters
  (reviewer stat strip + admin /rollup) filter WHERE status IN (...)
  AND updated_at >= cutoff.

Mirrors the indexes now declared on the Client / Vendor / Submission models.

Created with CONCURRENTLY (no ACCESS EXCLUSIVE lock on the live tables) inside
an autocommit_block — CONCURRENTLY cannot run inside Alembic's per-migration
transaction. IF NOT EXISTS keeps re-runs idempotent.

NOTE (ops): a failed CONCURRENTLY build can leave an INVALID index; drop it
(DROP INDEX CONCURRENTLY IF EXISTS <name>) before re-running. Snapshot Neon
before deploying — this auto-runs via the Render preDeployCommand. Set
idle_in_transaction_session_timeout on Neon first so a leaked idle-in-tx
session can't stall a CONCURRENTLY build (per the 0049 stall).

Trigram (pg_trgm) indexes for the new ILIKE search were deliberately deferred:
they need the pg_trgm extension + GIN indexes, and at the current catalog sizes
a search-time scan is acceptable. Revisit if search latency shows up.
"""

from __future__ import annotations

from alembic import op

revision = "0051_perf_indexes_admin_lists_and_queue"
down_revision = "0050_perf_index_contracts_client_vendor"
branch_labels = None
depends_on = None


_INDEXES = (
    ("ix_clients_created", "clients", "(created_at)"),
    ("ix_vendors_client_created", "vendors", "(client_id, created_at)"),
    ("ix_submissions_status_created", "submissions", "(status, created_at)"),
    ("ix_submissions_status_updated", "submissions", "(status, updated_at)"),
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, cols in _INDEXES:
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} {cols}"
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _table, _cols in _INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
