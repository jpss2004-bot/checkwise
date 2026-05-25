"""Client onboarding profile fields.

Junta 2026-05-23 — the client_admin needs a self-service page to
finish their onboarding after the admin preloads RFC/email/name.
The page collects sector, fiscal address, phone and free-form
notes; ``onboarding_completed_at`` is set on first save so the
client dashboard can render a soft prompt until the page is filled.

All columns are nullable so existing rows stay valid; the
application layer treats ``onboarding_completed_at IS NULL`` as
"not yet completed" and prompts accordingly.

Revision ID: 0023_client_onboarding_fields
Revises: 0022_client_email
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0023_client_onboarding_fields"
down_revision = "0022_client_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("industry", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("fiscal_address", sa.Text(), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("phone", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column(
            "onboarding_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("clients", "onboarding_completed_at")
    op.drop_column("clients", "notes")
    op.drop_column("clients", "phone")
    op.drop_column("clients", "fiscal_address")
    op.drop_column("clients", "industry")
