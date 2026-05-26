"""Notification dispatch idempotency anchor.

Phase 7 / Slice N1 — generalizes the proven ``renewal_reminders``
pattern (Slice 6B) into a single table that every notification
event in the new fabric uses to gate its sends.

One row per ``(user_id, event_type, dedupe_key)`` triple. The
dispatcher inserts first; an ``IntegrityError`` on the unique
constraint is the entire dedupe mechanism — no SELECT-then-INSERT
race window, no read-side replica drift to worry about.

Why a new table rather than reusing ``renewal_reminders``:
    * The dedupe key for renewals is the
      ``(workspace, requirement, cycle, threshold)`` tuple, which
      does not map to recipients. Reporting / verification / account
      / admin events need a recipient-keyed anchor.
    * ``notification_dispatch`` also doubles as the cross-channel
      attempt record: subsequent slices populate ``email_status``
      and ``whatsapp_status`` here so a single SELECT answers
      "what did we send this user, on what channels, and what
      happened" — the trazabilidad contract from the renewal PDF.

``renewal_reminders`` is kept as a parallel anchor for one release
during the renewal-emitter cutover (Slice N4) so we can replay
either path. The two converge in Slice N10 with a one-time backfill
and ``renewal_reminders`` becomes the historical record.

Why ``user_id`` is **not** a foreign key to ``users``:
    The recipient model is heterogeneous. Provider workspaces
    authenticate via opaque tokens — they do not yet have ``User``
    rows. The N1 column stores a generic principal identifier
    (``users.id`` for staff / client_admin / invitee, a workspace
    or vendor identifier for the provider_owner role) and the
    accompanying ``recipient_role`` column discriminates. Adding a
    hard FK now would block the dispatcher on a refactor that
    belongs in the invitation-flow slice.

Revision ID: 0024_notification_dispatch
Revises: 0023_client_onboarding_fields
Create Date: 2026-05-25
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0024_notification_dispatch"
down_revision = "0023_client_onboarding_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_dispatch",
        sa.Column("id", sa.String(length=36), primary_key=True),
        # Generic principal identifier — see module docstring on why
        # this is not a FK. Stored as 36-char string to match every
        # other id column in the schema.
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "recipient_role", sa.String(length=40), nullable=False
        ),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        # Free-form, ≤255 chars. The dispatcher only cares about
        # equality; the catalog comment documents the conventions
        # callers should follow. Keeping a string column (rather than
        # encoding the parts) means future event groups can choose
        # their own dedupe shape without a migration.
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        # Snapshot of catalog severity at emit time. Stored here so a
        # future cadence / catalog change does not silently rewrite
        # the historical record of what we sent (same discipline as
        # ``renewal_reminders.severity``).
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        # The in-app notification row this dispatch produced. NULL
        # at N1 because in-app row writes land in Slice N4. Nullable
        # for admin-tier events whose in-app surface is the audit log
        # rather than a notification row.
        sa.Column("inapp_id", sa.String(length=36), nullable=True),
        # Channel attempt records — NULL at N1; populated by Slice
        # N4 once routing + delivery wire in. Status canonicals:
        # ``sent`` | ``skipped_pref`` | ``skipped_muted`` |
        # ``skipped_no_address`` | ``failed``.
        sa.Column("email_status", sa.String(length=20), nullable=True),
        sa.Column("email_reason", sa.String(length=120), nullable=True),
        sa.Column(
            "whatsapp_status", sa.String(length=20), nullable=True
        ),
        sa.Column(
            "whatsapp_reason", sa.String(length=120), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # The entire idempotency mechanism. Insert-first; the
        # IntegrityError on collision is how the dispatcher learns
        # "already emitted, skip". Role is intentionally NOT part of
        # the key — a recipient identified by ``user_id`` should
        # only ever receive one copy per ``(event, dedupe_key)``
        # regardless of which role the emitter resolved them under.
        sa.UniqueConstraint(
            "user_id",
            "event_type",
            "dedupe_key",
            name="uq_notification_dispatch_recipient_event",
        ),
    )
    # Hot-path index for the per-user inbox query the notification
    # center will run in Slice N9 ("show me everything dispatched to
    # me, newest first").
    op.create_index(
        "ix_notification_dispatch_user_created_at",
        "notification_dispatch",
        ["user_id", "created_at"],
    )
    # Operational index for "what fired in the last cron pass".
    op.create_index(
        "ix_notification_dispatch_event_created_at",
        "notification_dispatch",
        ["event_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_dispatch_event_created_at",
        table_name="notification_dispatch",
    )
    op.drop_index(
        "ix_notification_dispatch_user_created_at",
        table_name="notification_dispatch",
    )
    op.drop_table("notification_dispatch")
