"""Add composite list+sort indexes: notifications + reports.

Revision ID: 0049_perf_indexes_notifications_reports
Revises: 0048_perf_indexes_workspace_auditlog
Create Date: 2026-06-17

PERF (hardening 2026-06-17). Three tenant-scoped list endpoints filter by an
owner column and order by a time column, but only had separate single-column
indexes (the planner picks one, then must filter-or-sort the remainder):

- client inbox: client_notifications WHERE client_id = ? [AND read_at IS NULL]
  ORDER BY created_at DESC
- provider inbox: provider_notifications WHERE workspace_id = ? [...]
  ORDER BY created_at DESC
- report list (list_reports): reports WHERE organization_id [= | IN] ?
  ORDER BY updated_at DESC

A composite (owner, time) serves the filter and the ordering from one index.
All three tables grow with usage, so the win compounds over time.

Created with CONCURRENTLY (no ACCESS EXCLUSIVE lock on the live tables) inside
an autocommit_block — CONCURRENTLY cannot run inside Alembic's per-migration
transaction. IF NOT EXISTS keeps re-runs idempotent and matches the indexes
now declared on the ClientNotification, ProviderNotification and Report models.

NOTE (ops): a failed CONCURRENTLY build can leave an INVALID index; drop it
(DROP INDEX CONCURRENTLY IF EXISTS <name>) before re-running. Snapshot Neon
before deploying — these auto-run via the Render preDeployCommand.
"""

from __future__ import annotations

from alembic import op

revision = "0049_perf_indexes_notifications_reports"
down_revision = "0048_perf_indexes_workspace_auditlog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_client_notifications_client_created "
            "ON client_notifications (client_id, created_at)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_provider_notifications_workspace_created "
            "ON provider_notifications (workspace_id, created_at)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_reports_org_updated "
            "ON reports (organization_id, updated_at)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_reports_org_updated")
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_provider_notifications_workspace_created"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_client_notifications_client_created"
        )
