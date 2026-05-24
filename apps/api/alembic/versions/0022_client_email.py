"""Client.email column.

Backs the post-pay onboarding requirement raised in the 2026-05-23
junta: the basic client record needs RFC, email and name at intake
so we can contact the new client. The admin alta form only had
``name``/``rfc``/``responsible_name`` until this revision; this
migration adds the nullable ``email`` column so legacy rows stay
valid and the new admin form can persist the captured address.

Revision ID: 0022_client_email
Revises: 0021_renewal_reminders
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0022_client_email"
down_revision = "0021_renewal_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("email", sa.String(length=254), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clients", "email")
