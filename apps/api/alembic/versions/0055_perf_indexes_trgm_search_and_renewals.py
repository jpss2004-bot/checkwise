"""pg_trgm GIN search indexes + admin renewals/radar b-tree indexes.

Revision ID: 0055_perf_indexes_trgm_search_and_renewals
Revises: 0054_admin_calendar_snapshots
Create Date: 2026-06-21

PERF (Batch 7 efficiency pass, 2026-06-21). Two related hot paths were doing
sequential scans that grow with the data:

1. Global search (search_service.search_submissions, name/folio path). The
   predicate is a leading-wildcard ILIKE over a 7-table join:
     f_unaccent(vendors.name) ILIKE f_unaccent('%term%')
     f_unaccent(clients.name) ILIKE f_unaccent('%term%')
     contracts.repse_folio    ILIKE '%term%'
   A ``%term%`` ILIKE cannot use a b-tree index, and the f_unaccent() wrapper
   defeats the plain name indexes — so every keystroke full-scanned the
   submissions join. These pg_trgm GIN indexes are the ones explicitly deferred
   in migration 0051 (line 34-36) and 0052 (line 15). They are built on the
   EXACT expression the search uses so the planner can apply them:
     - GIN (f_unaccent(vendors.name) gin_trgm_ops)
     - GIN (f_unaccent(clients.name) gin_trgm_ops)
     - GIN (contracts.repse_folio gin_trgm_ops)   -- raw column, plain ILIKE
   ``f_unaccent`` is the IMMUTABLE wrapper from migration 0052 (required so the
   expression index is allowed at all). The search service also now raises the
   minimum substring term length to 2 so a 1-char query can't trigger a scan.

2. Admin renewals / radar lanes scan contracts and vendors with no usable index:
     contracts: WHERE status = 'active' AND end_date <= horizon
                ORDER BY end_date ASC   (GET /admin/calendar/renewals)
     vendors:   WHERE status = 'active' (renewals/radar active-vendor scans)
   The only contracts index was ix_contracts_client_vendor (0050), which can't
   serve the status filter or the end_date sort. Add:
     - b-tree contracts(status, end_date)  -- equality + ORDER BY
     - b-tree vendors(status)

provider_workspaces(client_id, vendor_id) is NOT added here — it already exists
as ix_provider_workspaces_vendor from migration 0003 (the entities.py model was
updated in this same pass to declare it so the SQLite test schema matches prod).

All indexes mirror the declarations now on the Vendor / Client (search columns
are not model-declarable as gin_trgm_ops on SQLite) / Contract models.

Created with CONCURRENTLY (no ACCESS EXCLUSIVE lock on the live tables) inside
an autocommit_block — CONCURRENTLY cannot run inside Alembic's per-migration
transaction. IF NOT EXISTS keeps re-runs idempotent. CREATE EXTENSION IF NOT
EXISTS pg_trgm runs first (pg_trgm is on Neon's allowlist).

NOTE (ops): a failed CONCURRENTLY build can leave an INVALID index; drop it
(DROP INDEX CONCURRENTLY IF EXISTS <name>) before re-running. Snapshot Neon
before deploying — this auto-runs via the Render preDeployCommand. Set
idle_in_transaction_session_timeout on Neon first so a leaked idle-in-tx
session can't stall a CONCURRENTLY build (per the 0049 stall). This migration is
Postgres-only DDL; the SQLite test fixtures never run it.
"""

from __future__ import annotations

from alembic import op

revision = "0055_perf_indexes_trgm_search_and_renewals"
down_revision = "0054_admin_calendar_snapshots"
branch_labels = None
depends_on = None


# pg_trgm GIN indexes for the leading-wildcard ILIKE search. The name indexes
# wrap the column in the IMMUTABLE f_unaccent() (migration 0052) to match the
# accent-insensitive search expression exactly; repse_folio uses a plain ILIKE
# so it is indexed on the raw column.
_TRGM_INDEXES = (
    (
        "ix_vendors_name_trgm",
        "vendors",
        "USING gin (f_unaccent(name) gin_trgm_ops)",
    ),
    (
        "ix_clients_name_trgm",
        "clients",
        "USING gin (f_unaccent(name) gin_trgm_ops)",
    ),
    (
        "ix_contracts_repse_folio_trgm",
        "contracts",
        "USING gin (repse_folio gin_trgm_ops)",
    ),
)

# Plain b-tree indexes for the admin renewals / radar scans.
_BTREE_INDEXES = (
    ("ix_contracts_status_end_date", "contracts", "(status, end_date)"),
    ("ix_vendors_status", "vendors", "(status)"),
)


def upgrade() -> None:
    # Extension creation is plain DDL and must NOT be inside the autocommit
    # block alongside the CONCURRENTLY builds — but it is idempotent and cheap,
    # so run it first in its own transaction.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # f_unaccent (migration 0052) had an UNqualified body — `unaccent('unaccent',
    # $1)`. That resolves fine at query time (search_path = "$user", public), but
    # when Postgres INLINES this IMMUTABLE wrapper while building a CONCURRENTLY
    # expression index, the `'unaccent'::regdictionary` cast is evaluated without
    # the runtime search_path and fails:
    #   function unaccent(unknown, text) does not exist
    # (this is the first index built on f_unaccent; 0052 only used it in runtime
    # ILIKE). Redefine the body fully schema-qualified so the inlined expression
    # is search_path-independent. Same function identity — public.f_unaccent(text)
    # — and identical results, so existing callers and the index↔query match are
    # unchanged.
    op.execute(
        "CREATE OR REPLACE FUNCTION public.f_unaccent(text) "
        "RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS "
        "$$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$"
    )

    with op.get_context().autocommit_block():
        for name, table, using in _TRGM_INDEXES:
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} {using}"
            )
        for name, table, cols in _BTREE_INDEXES:
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} {cols}"
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _table, _cols in _BTREE_INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        for name, _table, _using in _TRGM_INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
    # Leave the pg_trgm extension in place — other objects may rely on it and
    # dropping an extension is rarely what a rollback wants (mirrors 0052's
    # treatment of the unaccent extension).
