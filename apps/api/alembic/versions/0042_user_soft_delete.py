"""User soft-delete.

Revision ID: 0042_user_soft_delete
Revises: 0041_wise_events_client_scope
Create Date: 2026-06-13

Adds recoverable soft-delete to user accounts (platform rework, Phase 0).
A soft-deleted account is hidden from the ``/platform/users`` directory
and blocked from login — ``get_current_user`` already rejects any
``status != 'active'`` per request, so no token revocation is needed —
but its row is retained so an accidental delete is recoverable for a
window before a purge cron hard-deletes it.

Columns (all nullable / additive, so this is backward-compatible):
- ``users.deleted_at`` — when the account was soft-deleted; NULL = live.
- ``users.deleted_by_user_id`` — internal operator who deleted it (a
  plain id, not an FK, so the actor may itself be deleted later).
- ``users.deletion_reason`` — optional free-text note.

Plus a partial index over live rows so the default directory query
(``WHERE deleted_at IS NULL ORDER BY created_at DESC``) stays cheap and
ignores the growing soft-deleted tail.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0042_user_soft_delete"
down_revision = "0041_wise_events_client_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("deleted_by_user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("deletion_reason", sa.String(length=200), nullable=True),
    )
    op.create_index(
        "ix_users_active_created",
        "users",
        ["created_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_active_created", table_name="users")
    op.drop_column("users", "deletion_reason")
    op.drop_column("users", "deleted_by_user_id")
    op.drop_column("users", "deleted_at")
