"""Subscription plan + provider cap on client organizations.

Three nullable columns on ``organizations``, mirroring the seat_limit
discipline (the cap is data, not code, so lifting a tenant's tier is an
UPDATE, not a deploy):

  * ``plan``           — tier enum. Backfilled 'legacy' for every existing
                         ``kind='client'`` org so they stay UNCAPPED — a
                         surprise cap on a paying customer at deploy time is
                         exactly the regression we must avoid. NULL on
                         internal/vendor orgs.
  * ``provider_limit`` — per-tenant override of the tier default. Left NULL
                         everywhere (incl. new demos): NULL means "use the
                         plans.py default for the tier"; an admin sets an
                         integer only for a custom/enterprise cap.
  * ``demo_expires_at``— populated by Phase B demo provisioning; the column
                         lands now so Phase B is purely additive.

Plain dual-dialect statements (no CONCURRENTLY — ``organizations`` is tiny)
so the focused migration test runs them verbatim on SQLite. The plan CHECK
is Postgres-only + ``NOT VALID`` (legacy rows that pre-date the enum can't
fail the deploy), the same discipline as 0036.

Revision ID: 0056_org_subscription_plan
Revises: 0055_perf_indexes_trgm_search_and_renewals
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0056_org_subscription_plan"
down_revision = "0055_perf_indexes_trgm_search_and_renewals"
branch_labels = None
depends_on = None

_PLAN_VALUES: tuple[str, ...] = ("demo", "standard", "growth", "enterprise", "legacy")
_PLAN_CK = "ck_organizations_plan"

# Grandfather every existing client org as uncapped: tag the plan 'legacy'
# and leave provider_limit NULL (the service treats both as "no cap").
_BACKFILL_PLAN_SQL = "UPDATE organizations SET plan = 'legacy' WHERE kind = 'client'"


def upgrade() -> None:
    op.add_column(
        "organizations", sa.Column("plan", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "organizations", sa.Column("provider_limit", sa.Integer(), nullable=True)
    )
    op.add_column(
        "organizations",
        sa.Column("demo_expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(_BACKFILL_PLAN_SQL)

    # Postgres-only guard rail (SQLite test schema omits CHECKs, like 0036).
    # NOT VALID so the deploy never scans or fails on a legacy row.
    if op.get_bind().dialect.name == "postgresql":
        in_list = ", ".join(f"'{v}'" for v in _PLAN_VALUES)
        op.execute(
            f"ALTER TABLE organizations ADD CONSTRAINT {_PLAN_CK} "
            f"CHECK (plan IS NULL OR plan IN ({in_list})) NOT VALID"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"ALTER TABLE organizations DROP CONSTRAINT IF EXISTS {_PLAN_CK}")
    op.drop_column("organizations", "demo_expires_at")
    op.drop_column("organizations", "provider_limit")
    op.drop_column("organizations", "plan")
