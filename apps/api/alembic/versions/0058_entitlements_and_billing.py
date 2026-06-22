"""Per-tenant entitlements + provider-agnostic billing seam (Phase D).

Two new tables (no backfill):
  * organization_entitlements — a per-tenant capability override layered over
    the tier default by the capability shim (``capabilities_for_org``), so a
    grant/revoke needs no call-site change. Unique (organization_id, key);
    ON DELETE CASCADE with the org.
  * billing_accounts — one row per client org recording the billing provider
    + mirrored subscription state. 'manual' is the only wired provider;
    'stripe' is reserved for the stubbed adapter (the seam, not a live
    integration).

Plain dual-dialect ``create_table`` (small new tables, no CONCURRENTLY) so the
focused migration test runs verbatim on SQLite. server_default on the
timestamps mirrors 0037's discipline.

Revision ID: 0058_entitlements_and_billing
Revises: 0057_org_status_check_and_demo_index
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0058_entitlements_and_billing"
down_revision = "0057_org_status_check_and_demo_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_entitlements",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("granted_by_user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "organization_id", "key", name="uq_org_entitlements_org_key"
        ),
    )
    op.create_index(
        "ix_org_entitlements_org",
        "organization_entitlements",
        ["organization_id"],
    )
    op.create_table(
        "billing_accounts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "provider", sa.String(length=40), nullable=False, server_default="manual"
        ),
        sa.Column("customer_id", sa.String(length=255), nullable=True),
        sa.Column("subscription_id", sa.String(length=255), nullable=True),
        sa.Column(
            "status", sa.String(length=40), nullable=False, server_default="none"
        ),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("organization_id", name="uq_billing_accounts_org"),
    )


def downgrade() -> None:
    op.drop_table("billing_accounts")
    op.drop_index(
        "ix_org_entitlements_org", table_name="organization_entitlements"
    )
    op.drop_table("organization_entitlements")
