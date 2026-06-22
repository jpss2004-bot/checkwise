"""Organization status CHECK + demo-expiry sweep index (Phase B).

Formalizes ``organizations.status`` to {active, frozen, expired} — the value
every Phase B gate (login, portal) and cron reads — with a Postgres CHECK so a
typo'd status cannot silently bypass a gate. Adds a partial index powering the
daily demo-expiry sweep (WHERE plan='demo' AND demo_expires_at <= now()).

Both are Postgres-only (the SQLite test schema, built via create_all, omits
them — the gates fail-closed on ``status != 'active'`` regardless), dialect-
guarded exactly like 0056's plan CHECK. The orgs table is tiny and every row
is ``status='active'`` from 0056, so a validated CHECK + a plain partial index
are safe (no CONCURRENTLY needed). No backfill.

Revision ID: 0057_org_status_check_and_demo_index
Revises: 0056_org_subscription_plan
Create Date: 2026-06-22
"""

from __future__ import annotations

from alembic import op

revision = "0057_org_status_check_and_demo_index"
down_revision = "0056_org_subscription_plan"
branch_labels = None
depends_on = None

# Keep literal (re-running a historical migration must not depend on the live
# constant drifting). A test asserts this matches plans.VALID_ORG_STATUSES.
_STATUS_VALUES: tuple[str, ...] = ("active", "frozen", "expired")
_STATUS_CK = "ck_organizations_status"
_SWEEP_INDEX = "ix_organizations_demo_expiry_sweep"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    in_list = ", ".join(f"'{v}'" for v in _STATUS_VALUES)
    op.execute(
        f"ALTER TABLE organizations ADD CONSTRAINT {_STATUS_CK} "
        f"CHECK (status IN ({in_list}))"
    )
    op.execute(
        f"CREATE INDEX {_SWEEP_INDEX} ON organizations (demo_expires_at) "
        "WHERE plan = 'demo' AND demo_expires_at IS NOT NULL"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"DROP INDEX IF EXISTS {_SWEEP_INDEX}")
    op.execute(f"ALTER TABLE organizations DROP CONSTRAINT IF EXISTS {_STATUS_CK}")
