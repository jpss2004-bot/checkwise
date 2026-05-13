"""Provider workspaces for V1.2 portal demo.

Revision ID: 0003_provider_workspaces
Revises: 0002_native_intake_foundation
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_provider_workspaces"
down_revision = "0002_native_intake_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vendors", sa.Column("persona_type", sa.String(length=20), nullable=True))

    op.create_table(
        "provider_workspaces",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("client_id", sa.String(length=36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("vendor_id", sa.String(length=36), sa.ForeignKey("vendors.id"), nullable=False),
        sa.Column(
            "contract_id", sa.String(length=36), sa.ForeignKey("contracts.id"), nullable=True
        ),
        sa.Column("filial_name", sa.String(length=255), nullable=True),
        sa.Column("persona_type", sa.String(length=20), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("access_token", sa.String(length=64), nullable=False),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("access_token", name="uq_provider_workspaces_token"),
    )
    op.create_index(
        "ix_provider_workspaces_vendor",
        "provider_workspaces",
        ["client_id", "vendor_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_workspaces_vendor", table_name="provider_workspaces")
    op.drop_table("provider_workspaces")
    op.drop_column("vendors", "persona_type")
