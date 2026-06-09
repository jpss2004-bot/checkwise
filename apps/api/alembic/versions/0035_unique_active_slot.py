"""Enforce one active-genesis submission per evidence slot.

Audit 2026-06-09 (docs/audits/checklist-system-audit-2026-06-09.md). The
upload path now auto-supersedes a slot's current occupant
(``portal._resolve_supersedes_submission``), so a re-upload links to the
prior submission instead of spawning a parallel "genesis" row. This
migration makes that invariant durable:

  one row with ``supersedes_submission_id IS NULL`` per
  ``(client_id, vendor_id, requirement_code, coalesce(period_key, ''))``,
  for canonical (``requirement_code IS NOT NULL``) submissions.

``coalesce(period_key, '')`` folds the onboarding case (no period) so two
NULL-period genesis rows compare equal rather than slipping past the
unique check. Codeless legacy rows are excluded — they can't be slotted.

Two steps:

1. **De-dup backfill.** For any slot that already holds several genesis
   rows (created before auto-supersede existed), chain them by
   ``created_at`` so only the oldest stays a genesis and the rest point at
   their immediate predecessor. This is read-result-preserving: the
   evidence-slot engine picks "current" as the most-recent non-superseded
   leaf, and we only ever add ``supersedes`` pointers toward *older* rows,
   so the newest submission stays the leaf. ``updated_at`` is left
   untouched (raw SQL, no ORM ``onupdate``) so approved-row renewal
   anchors don't shift.
2. **Unique index**, built ``CONCURRENTLY`` (non-blocking) outside the
   migration transaction.

Postgres-only (the constraint protects prod; the SQLite test schema
intentionally omits it — see entities.Submission). Reversible only in the
index direction; the backfill chaining is not un-done on downgrade
(there is nothing unsafe about leaving the rows chained).

Revision ID: 0035_unique_active_slot
Revises: 0034_checklist_hot_indexes
Create Date: 2026-06-09
"""

from __future__ import annotations

from alembic import op

revision = "0035_unique_active_slot"
down_revision = "0034_checklist_hot_indexes"
branch_labels = None
depends_on = None

_INDEX = "ux_submissions_active_slot"

# Collapse pre-existing parallel-genesis rows into a single lineage chain
# per slot. LAG gives each genesis row its immediate predecessor within
# the slot (ordered oldest-first); the partition's first row has no
# predecessor and stays a genesis.
# Correlated-subquery form (rather than UPDATE ... FROM with a target
# alias) so the exact statement is valid on both Postgres and SQLite —
# the migration-logic test runs this verbatim. It only fires once, on a
# bounded set of pre-existing duplicates, so the correlated read is fine.
_DEDUP_SQL = """
WITH genesis AS (
    SELECT
        id,
        LAG(id) OVER (
            PARTITION BY client_id, vendor_id, requirement_code,
                         COALESCE(period_key, '')
            ORDER BY created_at ASC, id ASC
        ) AS prev_id
    FROM submissions
    WHERE supersedes_submission_id IS NULL
      AND requirement_code IS NOT NULL
)
UPDATE submissions
SET supersedes_submission_id = (
    SELECT prev_id FROM genesis g WHERE g.id = submissions.id
)
WHERE submissions.id IN (SELECT id FROM genesis WHERE prev_id IS NOT NULL)
"""

_CREATE_SQL = f"""
CREATE UNIQUE INDEX CONCURRENTLY {_INDEX}
ON submissions (client_id, vendor_id, requirement_code, COALESCE(period_key, ''))
WHERE supersedes_submission_id IS NULL AND requirement_code IS NOT NULL
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # Non-Postgres (shouldn't happen for migrations): no-op. The test
        # schema deliberately omits this constraint.
        return
    # Step 1 — backfill, in the migration's transaction.
    op.execute(_DEDUP_SQL)
    # Step 2 — concurrent unique build, outside any transaction. Drop a
    # possibly-INVALID index left by a prior failed CONCURRENTLY build so
    # the migration is safely re-runnable.
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX}")
        op.execute(_CREATE_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX}")
