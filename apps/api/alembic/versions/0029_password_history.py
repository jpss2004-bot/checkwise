"""Password history for reuse prevention.

Audit-finding #10 (2026-05-26) — a user could reset to the
same password they had before. Compliance reviewers will flag
this. Solution: keep a rolling history of the last N=5 bcrypt
hashes; any new password is rejected if it bcrypt-verifies
against any retained row.

Table shape: ``password_history(id, user_id, password_hash,
created_at)`` with a composite index on ``(user_id, created_at
DESC)`` so the lookup-for-reuse-check is a single index scan.

Trimming is application-level (the service deletes the oldest
when the count exceeds N) so the constraint stays simple and
the cap is tunable without a migration.

Revision ID: 0029_password_history
Revises: 0028_notification_category
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0029_password_history"
down_revision = "0028_notification_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_history",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_password_history_user_created",
        "password_history",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_password_history_user_created", table_name="password_history")
    op.drop_table("password_history")
