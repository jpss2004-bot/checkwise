"""Add hot-path indexes for vendor-keyed and created_at-ranged submission queries.

Revision ID: 0046_submission_perf_indexes
Revises: 0045_user_account_lockout
Create Date: 2026-06-15

PERF-7 (audit 2026-06-15). Two submission read patterns lacked a
supporting index:

- ``WHERE vendor_id IN (...)`` and the ``JOIN ... ON vendor_id`` used by
  the 6-month approval-history block and the bulk last-activity lookup.
  The existing ``(client_id, vendor_id)`` composite cannot serve a
  vendor-only predicate (``client_id`` is the leading column), so those
  queries sequentially scan ``submissions``.
- ``WHERE client_id = ? ORDER BY created_at DESC`` on the submission
  lists and the per-month history ranges, which had no ``created_at``
  index at all.

Both are created with ``CONCURRENTLY`` so the build never takes an
ACCESS EXCLUSIVE lock on the live ``submissions`` table (important on
Neon under traffic). ``CONCURRENTLY`` cannot run inside a transaction,
and Alembic wraps each migration in one, so the statements run inside an
``autocommit_block()``. ``IF NOT EXISTS`` keeps re-runs idempotent and
matches the indexes now declared on the ``Submission`` model.

NOTE (ops): a failed ``CREATE INDEX CONCURRENTLY`` can leave an INVALID
index behind. If this migration fails partway, drop any invalid index
(``DROP INDEX CONCURRENTLY IF EXISTS ix_submissions_vendor_id`` /
``ix_submissions_client_created``) before re-running.
"""

from __future__ import annotations

from alembic import op

revision = "0046_submission_perf_indexes"
down_revision = "0045_user_account_lockout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_submissions_vendor_id "
            "ON submissions (vendor_id)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_submissions_client_created "
            "ON submissions (client_id, created_at)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_submissions_client_created")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_submissions_vendor_id")
