"""Versioned notification templates.

Phase 7 / Slice N3 — DB-backed copy table so operations can A/B
notification text and roll back without a code deploy.

One row per ``(event_type, channel, locale, version)``. The unique
constraint enforces version monotonicity per key; the
"exactly-one-active-row-per-key" invariant is enforced at the
application layer inside a transaction
(:func:`app.api.v1.admin_notification_templates.activate_version`)
rather than via a partial unique index, because SQLite does not
support partial indexes and the rest of the codebase runs SQLite
in tests.

What lives where:

    * ``subject`` — email subject line. NULL for non-email channels.
    * ``body`` — the renderable template text. ``{{var}}`` placeholders
      are substituted by :func:`app.services.notifications.rendering.render`
      from the envelope ``payload``. For WhatsApp, the body is a
      developer-readable shadow of the Meta-approved template — the
      actual on-wire text comes from Meta when the template name is
      invoked.
    * ``meta_template_name`` — the registered WhatsApp template name
      on Meta's side (e.g. ``cw_renewal_threshold``). NULL for non-
      WhatsApp channels. Templates are pre-approved by Meta; this
      column lets us swap which approved template a given event uses
      without a deploy.

N3 ships a small seed set (renewal + reviewer-decision events for
email + WhatsApp, plus in-app rows). Slice N4 wires the dispatcher
to render through this table. Until then the existing in-code
builders in :mod:`app.services.email_templates` and
:mod:`app.services.whatsapp_templates` remain authoritative —
:func:`render` is the fallback site, not yet the canonical path.

Revision ID: 0026_notification_template_versions
Revises: 0025_user_notification_preferences
Create Date: 2026-05-26
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "0026_notification_template_versions"
down_revision = "0025_user_notification_preferences"
branch_labels = None
depends_on = None


# Seed rows for the first version. Kept minimal: only the
# event_types whose copy already lives in production code today
# (renewal thresholds + reviewer decisions). Other events get
# their first DB-backed template the day their UI/feature ships.
#
# Substitution uses ``{{var}}`` — see
# :mod:`app.services.notifications.rendering`. Available variables
# per event are documented in the seed below.
_SEED: list[dict] = [
    # ─────── Renewal — t-7 (important, WhatsApp eligible) ───────
    {
        "event_type": "renewal.threshold.t-7",
        "channel": "inapp",
        "subject": None,
        "body": "{{requirement_name}} de {{vendor_name}} vence en 7 días.",
        "meta_template_name": None,
    },
    {
        "event_type": "renewal.threshold.t-7",
        "channel": "email",
        "subject": "Tu {{requirement_name}} vence en 7 días",
        "body": (
            "Hola,\n\n"
            "El documento {{requirement_name}} de {{vendor_name}} "
            "vence el {{due_on}}. Sube la versión actualizada en "
            "CheckWise para mantener el expediente en regla.\n\n"
            "{{cta_url}}\n\n"
            "CheckWise"
        ),
        "meta_template_name": None,
    },
    {
        "event_type": "renewal.threshold.t-7",
        "channel": "whatsapp",
        "subject": None,
        "body": (
            "{{requirement_name}} de {{vendor_name}} vence el "
            "{{due_on}} (Próximo a vencer)."
        ),
        "meta_template_name": "cw_renewal_threshold",
    },
    # ─────── Renewal — t-0 (critical) ───────
    {
        "event_type": "renewal.threshold.t-0",
        "channel": "inapp",
        "subject": None,
        "body": "{{requirement_name}} de {{vendor_name}} vence HOY.",
        "meta_template_name": None,
    },
    {
        "event_type": "renewal.threshold.t-0",
        "channel": "email",
        "subject": "Tu {{requirement_name}} vence hoy",
        "body": (
            "Hola,\n\n"
            "El documento {{requirement_name}} de {{vendor_name}} "
            "vence hoy. Sube la versión actualizada antes del cierre "
            "del día.\n\n"
            "{{cta_url}}\n\n"
            "CheckWise"
        ),
        "meta_template_name": None,
    },
    {
        "event_type": "renewal.threshold.t-0",
        "channel": "whatsapp",
        "subject": None,
        "body": (
            "{{requirement_name}} de {{vendor_name}} vence HOY "
            "({{due_on}})."
        ),
        "meta_template_name": "cw_renewal_threshold",
    },
    # ─────── Submission decisions (critical) ───────
    {
        "event_type": "submission.rejected",
        "channel": "inapp",
        "subject": None,
        "body": "Tu {{requirement_name}} necesita correcciones.",
        "meta_template_name": None,
    },
    {
        "event_type": "submission.rejected",
        "channel": "email",
        "subject": "Tu documento necesita correcciones",
        "body": (
            "Hola,\n\n"
            "El documento {{requirement_name}} requiere correcciones. "
            "Motivo: {{reason}}.\n\n"
            "Sube una versión corregida en CheckWise:\n\n"
            "{{cta_url}}\n\n"
            "CheckWise"
        ),
        "meta_template_name": None,
    },
    {
        "event_type": "submission.rejected",
        "channel": "whatsapp",
        "subject": None,
        "body": (
            "Tu documento {{requirement_name}} fue rechazado. "
            "Motivo: {{reason}}."
        ),
        "meta_template_name": "cw_reviewer_decision",
    },
    {
        "event_type": "submission.approved",
        "channel": "inapp",
        "subject": None,
        "body": "Tu {{requirement_name}} fue aprobado.",
        "meta_template_name": None,
    },
    {
        "event_type": "submission.approved",
        "channel": "email",
        "subject": "Tu documento fue aprobado",
        "body": (
            "Hola,\n\n"
            "El documento {{requirement_name}} de {{vendor_name}} "
            "fue aprobado por Legal Shelf. No se requiere acción "
            "adicional.\n\n"
            "{{cta_url}}\n\n"
            "CheckWise"
        ),
        "meta_template_name": None,
    },
    {
        "event_type": "submission.approved",
        "channel": "whatsapp",
        "subject": None,
        "body": "Tu documento {{requirement_name}} fue aprobado.",
        "meta_template_name": "cw_reviewer_decision",
    },
]


def upgrade() -> None:
    op.create_table(
        "notification_template_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column(
            "locale",
            sa.String(length=10),
            nullable=False,
            server_default="es-MX",
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "meta_template_name", sa.String(length=80), nullable=True
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "event_type",
            "channel",
            "locale",
            "version",
            name="uq_notif_templates_event_channel_locale_version",
        ),
    )
    op.create_index(
        "ix_notif_templates_event_channel_locale",
        "notification_template_versions",
        ["event_type", "channel", "locale"],
    )

    # Seed v1 rows, all marked active. We bake the IDs + timestamps
    # in Python because ``op.bulk_insert`` does not honor
    # ``default=`` callable defaults declared on the SQLAlchemy
    # model.
    now = datetime.now(UTC)
    table = sa.table(
        "notification_template_versions",
        sa.column("id", sa.String),
        sa.column("event_type", sa.String),
        sa.column("channel", sa.String),
        sa.column("locale", sa.String),
        sa.column("version", sa.Integer),
        sa.column("subject", sa.String),
        sa.column("body", sa.Text),
        sa.column("meta_template_name", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        table,
        [
            {
                "id": str(uuid.uuid4()),
                "event_type": row["event_type"],
                "channel": row["channel"],
                "locale": "es-MX",
                "version": 1,
                "subject": row["subject"],
                "body": row["body"],
                "meta_template_name": row["meta_template_name"],
                "is_active": True,
                "created_at": now,
            }
            for row in _SEED
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notif_templates_event_channel_locale",
        table_name="notification_template_versions",
    )
    op.drop_table("notification_template_versions")
