"""Renewal reminder dedupe table.

Phase 6 / Slice 6B — the per-cycle, per-threshold idempotency anchor
for the renewal notification emit-site. One row per
``(workspace, requirement, cycle_anchor, threshold_days)``. The
unique constraint is the entire mechanism — the dispatcher inserts
into this table first, and a unique-constraint violation tells it
"already emitted, skip" without writing any notifications.

Why a dedicated table instead of querying the existing notification
tables (client + provider) or encoding the dedupe key into
``notification_type``:

* Keeps ``notification_type`` clean (``"renewal_due_soon"`` /
  ``"renewal_overdue"``) so the existing frontend filter contract
  works with equality, no LIKE / startswith.
* Single source of truth for "did we already nag for this threshold
  on this cycle". The alternative — scanning two notification tables
  with JSON containment — is correctness-fragile (client + provider
  rows could drift) and re-runs the dedupe index on every dispatch.
* Doubles as the ops audit trail: ``SELECT * FROM renewal_reminders
  WHERE workspace_id = ?`` answers "what reminders has this provider
  received this year".

Cycle reset: ``cycle_anchor_date`` is in the unique key. When a
provider uploads a new approved CSF (or REPSE / patronal), the
renewal anchor changes; all 9 threshold slots
(30/14/7/0/-7/-14/-21/-28 plus the silent past-28 region) are fresh
under the new anchor and can fire again as the new cycle progresses.

Revision ID: 0021_renewal_reminders
Revises: 0020_provider_notifications
Create Date: 2026-05-23
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0021_renewal_reminders"
down_revision = "0020_provider_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "renewal_reminders",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("provider_workspaces.id"),
            nullable=False,
        ),
        # The requirement is referenced by its canonical catalog code
        # (e.g. "ONB-CORP-M-002") rather than the ``requirements.id``
        # FK because renewal cadence lives on the catalog, not on the
        # DB requirement rows. This keeps the table decoupled from
        # the requirement-versioning subsystem.
        sa.Column(
            "requirement_code", sa.String(length=80), nullable=False
        ),
        # The day the standing approved submission became evidence —
        # i.e. the value returned by ``renewal_anchor_date``. New
        # approved submission → new anchor → new cycle → unique key
        # reset so the 9 threshold slots fire again.
        sa.Column("cycle_anchor_date", sa.Date(), nullable=False),
        # One of 30, 14, 7, 0, -7, -14, -21, -28 per the Slice 6B
        # locked cadence. Stored as a signed int because negative
        # values encode the overdue weekly nags.
        sa.Column("threshold_days", sa.Integer(), nullable=False),
        # Mirror of the notification severity at the time of emit.
        # Kept on this row (rather than re-derived from threshold_days
        # at read time) so a future cadence tweak does not silently
        # rewrite the historical record of what was sent.
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # The entire idempotency mechanism. Insert-first; the
        # IntegrityError on collision is how the dispatcher learns
        # "already emitted, skip".
        sa.UniqueConstraint(
            "workspace_id",
            "requirement_code",
            "cycle_anchor_date",
            "threshold_days",
            name="uq_renewal_reminders_cycle_threshold",
        ),
    )
    # Hot-path index for the per-workspace audit query the ops CLI
    # uses to answer "what reminders did this provider receive".
    op.create_index(
        "ix_renewal_reminders_workspace_created_at",
        "renewal_reminders",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_renewal_reminders_workspace_created_at",
        table_name="renewal_reminders",
    )
    op.drop_table("renewal_reminders")
