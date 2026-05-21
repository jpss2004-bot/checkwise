"""Link users to provider workspaces + must-change-password gate.

Revision ID: 0007_user_workspace_link
Revises: 0006_auth_and_rbac
Create Date: 2026-05-14

Two additive columns to support real provider-side authentication:

- ``users.must_change_password`` — boolean, default ``false``. When the
  login response carries ``must_change_password=true`` the frontend
  forces the user through ``/activate`` before any other route. Cleared
  by ``POST /api/v1/auth/set-password``.
- ``provider_workspaces.owner_user_id`` — nullable FK to ``users.id``.
  When set, the workspace can only be entered (cookie minted) by an
  authenticated user matching this id. ``POST /api/v1/portal/enter``
  enforces this; legacy/anonymous workspaces (owner_user_id IS NULL)
  remain readable by their cookie session for backwards compatibility
  but cannot be re-entered without an owner.

Both fields are additive so the migration is reversible without data
loss.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_user_workspace_link"
down_revision = "0006_auth_and_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "provider_workspaces",
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_provider_workspaces_owner_user",
        "provider_workspaces",
        ["owner_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_workspaces_owner_user", table_name="provider_workspaces"
    )
    op.drop_column("provider_workspaces", "owner_user_id")
    op.drop_column("users", "must_change_password")
