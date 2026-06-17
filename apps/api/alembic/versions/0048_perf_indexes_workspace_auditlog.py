"""Add hot-path indexes: provider_workspaces(vendor_id), audit_log(action, created_at).

Revision ID: 0048_perf_indexes_workspace_auditlog
Revises: 0047_expediente_assessments
Create Date: 2026-06-17

PERF (hardening 2026-06-17). Two read patterns lacked a supporting index:

- ``resolve_workspace_for_vendor`` filters ``provider_workspaces`` by
  ``vendor_id`` (+ status) on nearly every compliance path (dashboard,
  reports, evidence slots). The only index is the ``(client_id, vendor_id)``
  composite, whose leading ``client_id`` cannot serve a vendor-only
  predicate — so those lookups sequentially scan the table.
- The audit-log explorer filters ``audit_log`` by ``action`` and orders by
  ``created_at DESC``, and the ops dashboard scans an ``action``-scoped
  slice on every load. ``audit_log`` is append-only and grows without
  bound, so these scans degrade monotonically. Only
  ``(entity_type, entity_id)`` and ``actor_id`` were indexed. A plain
  ``(action, created_at)`` btree serves the equality-then-range filter and
  the ``ORDER BY created_at DESC`` via a backward index scan.

Both are created with ``CONCURRENTLY`` so the build never takes an ACCESS
EXCLUSIVE lock on the live tables (important on Neon under traffic).
``CONCURRENTLY`` cannot run inside a transaction, and Alembic wraps each
migration in one, so the statements run inside an ``autocommit_block()``.
``IF NOT EXISTS`` keeps re-runs idempotent and matches the indexes now
declared on the ProviderWorkspace and AuditLog models.

NOTE (ops): a failed ``CREATE INDEX CONCURRENTLY`` can leave an INVALID
index behind. If this migration fails partway, drop any invalid index
(``DROP INDEX CONCURRENTLY IF EXISTS ix_provider_workspaces_vendor_id`` /
``ix_audit_log_action_created``) before re-running. Snapshot Neon before
deploying — the team standard for index migrations that auto-run via the
Render preDeployCommand.
"""

from __future__ import annotations

from alembic import op

revision = "0048_perf_indexes_workspace_auditlog"
down_revision = "0047_expediente_assessments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_provider_workspaces_vendor_id "
            "ON provider_workspaces (vendor_id)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_log_action_created "
            "ON audit_log (action, created_at)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_audit_log_action_created")
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_provider_workspaces_vendor_id"
        )
