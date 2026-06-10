"""Multi-user client organizations — seats, primary owner, per-user reads.

Multi-user access groundwork (2026-06-10). A client organization may
hold up to 3 user accounts: one Primary Account Owner plus two
secondary users the owner provisions. All three share the same
``client_admin`` role so every existing endpoint, route gate and
login redirect keeps working unmodified; the *owner* is distinguished
by a membership flag, not a new role. Role granularity arrives later
as new ``memberships.role`` values — nothing here needs undoing.

Three surfaces in one migration because they are one feature:

    * ``memberships.is_primary`` — marks the Primary Account Owner.
      Exactly one *active* primary per organization, enforced by the
      partial unique index ``ux_memberships_primary_per_org``. The
      predicate includes ``status = 'active'`` so a removed/disabled
      primary row keeps its historical flag while the org designates
      a successor.
    * ``organizations.seat_limit`` — the cap as data, not code.
      Backfilled to 3 for ``kind='client'``; NULL elsewhere means
      "no cap" (internal staff org). Lifting the limit for a future
      enterprise client is an UPDATE, not a deploy. The service-layer
      cap check (next patch) treats NULL on a client org as the
      default 3 defensively.
    * ``client_notification_reads`` — per-user read marks for
      ``client_notifications``. The parent row's ``read_at`` is
      client-scoped: with two users in one org, user A marking a
      notification read would silently mark it read for user B. The
      junction table gives each user an independent read state; the
      notification endpoints switch over in a follow-up patch, and
      the legacy column stays as a transition fallback.

Backfill discipline: today every client org has exactly one active
``client_admin`` membership (the provisioning flow creates them 1:1),
but the backfill still ranks by ``created_at`` per org and promotes
only the oldest, so it is correct even on a tenant where extra
memberships were hand-seeded. Internal and vendor orgs are untouched.

Both statements are plain dual-dialect SQL (no CONCURRENTLY — the
``memberships`` table is tens of rows) so the focused migration test
runs them verbatim on SQLite.

Revision ID: 0037_client_multi_user
Revises: 0036_status_check_constraints
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0037_client_multi_user"
down_revision = "0036_status_check_constraints"
branch_labels = None
depends_on = None

_PRIMARY_INDEX = "ux_memberships_primary_per_org"

# Promote the oldest active client_admin membership of every client
# org to primary. Window-function form mirrors 0035's backfill: valid
# verbatim on both Postgres and SQLite, fires once on a bounded set.
_BACKFILL_PRIMARY_SQL = """
WITH ranked AS (
    SELECT m.id,
           ROW_NUMBER() OVER (
               PARTITION BY m.organization_id
               ORDER BY m.created_at ASC, m.id ASC
           ) AS rn
    FROM memberships m
    JOIN organizations o ON o.id = m.organization_id
    WHERE o.kind = 'client'
      AND m.role = 'client_admin'
      AND m.status = 'active'
)
UPDATE memberships
SET is_primary = TRUE
WHERE id IN (SELECT id FROM ranked WHERE rn = 1)
"""

# One active primary per organization. Plain (non-concurrent) build is
# fine at this table size and keeps the statement SQLite-compatible
# for the migration-logic test.
_PRIMARY_INDEX_SQL = f"""
CREATE UNIQUE INDEX {_PRIMARY_INDEX}
ON memberships (organization_id)
WHERE is_primary AND status = 'active'
"""

_SEAT_BACKFILL_SQL = """
UPDATE organizations SET seat_limit = 3 WHERE kind = 'client'
"""


def upgrade() -> None:
    # ``server_default`` so existing rows land as non-primary without
    # a table rewrite lock; the backfill then promotes one per org.
    op.add_column(
        "memberships",
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("seat_limit", sa.Integer(), nullable=True),
    )

    op.execute(_BACKFILL_PRIMARY_SQL)
    op.execute(_SEAT_BACKFILL_SQL)
    op.execute(_PRIMARY_INDEX_SQL)

    op.create_table(
        "client_notification_reads",
        sa.Column(
            "notification_id",
            sa.String(length=36),
            sa.ForeignKey("client_notifications.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # The composite PK covers notification-first lookups; this covers
    # "everything user X has read" (unread-count query + CASCADE path).
    op.create_index(
        "ix_client_notification_reads_user",
        "client_notification_reads",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_client_notification_reads_user",
        table_name="client_notification_reads",
    )
    op.drop_table("client_notification_reads")
    op.execute(f"DROP INDEX IF EXISTS {_PRIMARY_INDEX}")
    op.drop_column("organizations", "seat_limit")
    op.drop_column("memberships", "is_primary")
