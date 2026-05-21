"""Auth + RBAC foundation: organizations, users, memberships.

Revision ID: 0006_auth_and_rbac
Revises: 0005_seed_catalog
Create Date: 2026-05-13

Schema-only migration introduced by Patch 6. Adds three tables:

- ``organizations`` — tenant container with a ``kind`` (internal /
  client / vendor) and optional FK back to the legacy ``clients`` /
  ``vendors`` rows.
- ``users`` — real user accounts (email + bcrypt password hash). The
  provider portal continues to authenticate via opaque workspace
  tokens; this table is for LegalShelf staff and (in later patches)
  reviewer / client / vendor accounts.
- ``memberships`` — join table user × organization × role.

The role vocabulary intentionally starts with a single value
(``internal_admin``). ``reviewer`` and ``client_admin`` get added
by Patches 7 and 8 when the surfaces that need them ship.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_auth_and_rbac"
down_revision = "0005_seed_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column(
            "client_id", sa.String(length=36), sa.ForeignKey("clients.id"), nullable=True
        ),
        sa.Column(
            "vendor_id", sa.String(length=36), sa.ForeignKey("vendors.id"), nullable=True
        ),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_organizations_kind", "organizations", ["kind"])

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "memberships",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "user_id", "organization_id", "role", name="uq_memberships_user_org_role"
        ),
    )
    op.create_index("ix_memberships_user", "memberships", ["user_id"])
    op.create_index("ix_memberships_org", "memberships", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_memberships_org", table_name="memberships")
    op.drop_index("ix_memberships_user", table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_index("ix_organizations_kind", table_name="organizations")
    op.drop_table("organizations")
