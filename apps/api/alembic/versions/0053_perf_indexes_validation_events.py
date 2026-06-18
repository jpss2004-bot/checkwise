"""Add B-tree indexes on validation_events for the client portal hot paths.

Revision ID: 0053_perf_indexes_validation_events
Revises: 0052_unaccent_search
Create Date: 2026-06-18

PERF (client-portal pagination/responsiveness pass, 2026-06-18). The client
surfaces read validation_events in three hot paths that only had the implicit
FK index on submission_id:

- (submission_id, event_type): the per-vendor "last review" / reviewer-notes
  lookups and the /submissions latest-reviewer-decision batch filter
  event_type='reviewer_decision' grouped by submission_id.
- (event_type, created_at): the /activity feed filters event_type IN (...) and
  ORDER BY created_at DESC, and counts the same set for its total.

As validation_events grows (every reviewer action + intake event) these
otherwise scan/sort the whole table on /vendors, /vendors/{id} and /activity.

Mirrors the indexes now declared on the ValidationEvent model.

Created with CONCURRENTLY (no ACCESS EXCLUSIVE lock on the live table) inside an
autocommit_block — CONCURRENTLY cannot run inside Alembic's per-migration
transaction. IF NOT EXISTS keeps re-runs idempotent.

NOTE (ops): a failed CONCURRENTLY build can leave an INVALID index; drop it
(DROP INDEX CONCURRENTLY IF EXISTS <name>) before re-running. Snapshot Neon
before deploying — this auto-runs via the Render preDeployCommand. Ensure
idle_in_transaction_session_timeout is set on Neon so a leaked idle-in-tx
session can't stall a CONCURRENTLY build (per the 0049 stall).
"""

from __future__ import annotations

from alembic import op

revision = "0053_perf_indexes_validation_events"
down_revision = "0052_unaccent_search"
branch_labels = None
depends_on = None


_INDEXES = (
    (
        "ix_validation_events_submission_type",
        "validation_events",
        "(submission_id, event_type)",
    ),
    (
        "ix_validation_events_type_created",
        "validation_events",
        "(event_type, created_at)",
    ),
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
