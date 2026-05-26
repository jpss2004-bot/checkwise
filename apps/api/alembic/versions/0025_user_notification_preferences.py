"""User notification preferences + WhatsApp identity fields.

Phase 7 / Slice N2 — adds the per-user mute matrix the routing
layer consults at dispatch time, plus the verified-phone columns
that the WhatsApp routing path requires.

Why two surfaces in one migration:

    * Adding ``phone_e164`` / ``phone_verified_at`` /
      ``whatsapp_opt_in_at`` to ``users`` is the data the routing
      function reads to decide whether WhatsApp fires.
    * The new ``user_notification_preferences`` table is the
      per-category mute matrix. Both land together because the
      routing function at N2 reads both in a single decide() call.

Schema discipline:

    * No FK on ``user_notification_preferences.user_id`` is
      strictly required for the dispatcher to work, but we keep
      one with ``ON DELETE CASCADE`` so a user removal does not
      leave orphan preference rows.
    * Rows in ``user_notification_preferences`` exist only when
      the user has overridden the catalog default. Absence of a
      row means "no override" → the routing function treats both
      mute flags as ``false``. This keeps the table small (most
      users never mute anything) and avoids a backfill.
    * ``category`` is constrained at the application layer to the
      five values in :data:`app.services.notifications.catalog.EventCategory`.
      We deliberately do NOT add a DB CHECK constraint — adding
      a category to the catalog should not require a migration.

Revision ID: 0025_user_notification_preferences
Revises: 0024_notification_dispatch
Create Date: 2026-05-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0025_user_notification_preferences"
down_revision = "0024_notification_dispatch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Phone identity columns on ``users``. All nullable — existing
    # rows stay valid; N8 fills them in via the alta OTP flow.
    op.add_column(
        "users",
        sa.Column("phone_e164", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "phone_verified_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "whatsapp_opt_in_at", sa.DateTime(timezone=True), nullable=True
        ),
    )

    op.create_table(
        "user_notification_preferences",
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "category", sa.String(length=40), primary_key=True
        ),
        sa.Column(
            "email_muted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "whatsapp_muted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("user_notification_preferences")
    op.drop_column("users", "whatsapp_opt_in_at")
    op.drop_column("users", "phone_verified_at")
    op.drop_column("users", "phone_e164")
