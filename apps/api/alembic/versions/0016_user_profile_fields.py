"""User profile fields + provider-workspace profile_confirmed_at.

Backs the audit follow-up that retires the localStorage-only profile
form on /portal/entra-a-tu-espacio. Adds:

  users.phone (varchar 30, nullable)
  users.job_title (varchar 120, nullable)
  users.contact_preference (varchar 20, not-null, default 'email',
    CHECK constraint matching the frontend enum)
  provider_workspaces.profile_confirmed_at (timestamptz, nullable)

``full_name`` was already on users — the welcome form now collects a
single "Nombre completo" string instead of split first/last, so no
extra columns for names.

Revision ID: 0016_user_profile_fields
Revises: 0015_client_notifications
Create Date: 2026-05-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0016_user_profile_fields"
down_revision = "0015_client_notifications"
branch_labels = None
depends_on = None


_CONTACT_PREFERENCE_CHECK = (
    "contact_preference IN ('email', 'whatsapp', 'both')"
)


def upgrade() -> None:
    # ── users ────────────────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column("phone", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("job_title", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "contact_preference",
            sa.String(length=20),
            nullable=False,
            server_default="email",
        ),
    )
    op.create_check_constraint(
        "ck_users_contact_preference",
        "users",
        _CONTACT_PREFERENCE_CHECK,
    )

    # ── provider_workspaces ─────────────────────────────────────
    op.add_column(
        "provider_workspaces",
        sa.Column(
            "profile_confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("provider_workspaces", "profile_confirmed_at")
    op.drop_constraint("ck_users_contact_preference", "users", type_="check")
    op.drop_column("users", "contact_preference")
    op.drop_column("users", "job_title")
    op.drop_column("users", "phone")
