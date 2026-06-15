"""User account lockout.

Revision ID: 0045_user_account_lockout
Revises: 0044_backfill_platform_admin
Create Date: 2026-06-15

Adds consecutive-failed-login tracking so an account can be temporarily
locked after too many bad attempts (platform rework follow-up) — distinct
from the per-IP/email request-rate limiter, which doesn't stop a slow
password-guess against one account from rotating IPs.

Columns (additive):
- ``users.failed_login_count`` — INT NOT NULL default 0; consecutive
  failed logins, reset on success / password change / admin reset.
- ``users.locked_until`` — TIMESTAMPTZ NULL; when set and in the future,
  login is refused even with the correct password.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0045_user_account_lockout"
down_revision = "0044_backfill_platform_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "failed_login_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "users",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
