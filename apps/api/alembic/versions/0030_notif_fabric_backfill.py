"""Idempotent backfill of the Phase 7 notification fabric.

Fixes a migration-chain skip introduced by the rebase sequence in
commits 8567e59 → a2e8dd6 → the N0-N3 commit:

    1. The original ``0029_password_history.down_revision`` was
       ``0028_notification_category`` — but no 0028 file existed
       at the time. Migrations were broken.
    2. ``8567e59`` repointed ``0029.down_revision`` to
       ``0023_client_onboarding_fields`` so prod could deploy.
       Prod ran 0029 with parent 0023 and recorded
       ``alembic_version = '0029_password_history'``.
    3. ``a2e8dd6`` rebased ``0029.down_revision`` back to
       ``0028_notification_category`` in anticipation of the real
       Phase 7 migrations.
    4. The Phase 7 commits then added the real 0024-0028.

The file-system chain now reads
``0023 → 0024 → 0025 → 0026 → 0027 → 0028 → 0029``. But every
environment that ran step 2 has ``alembic_version = '0029'``
recorded with the OLD short-circuit chain. Alembic checks
revision identity, not parent traversal — it sees "current = 0029,
head = 0029, nothing to do" and silently skips 0024-0028. The
fabric tables never get created on prod.

This migration runs after 0029 and re-applies every schema change
0024-0028 made, guarded with existence checks via
``sqlalchemy.inspect`` so it is safe to run on:

    * Prod (current = 0029, no fabric tables) → creates everything.
    * Fresh installs that did traverse 0024-0028 → fully no-ops.
    * Any state in between (e.g. a half-applied dev DB) → only
      creates what is missing.

The existence-check pattern is portable across Postgres and SQLite
(the latter still drives the test suite). PG-only constructs like
``ADD COLUMN IF NOT EXISTS`` are deliberately avoided.

Revision ID: 0030_notif_fabric_backfill
Revises: 0029_password_history
Create Date: 2026-05-26
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0030_notif_fabric_backfill"
down_revision = "0029_password_history"
branch_labels = None
depends_on = None


# Kept in lockstep with the prefix table in
# 0028_notification_category._CATEGORY_BY_PREFIX. Duplicated rather
# than imported because alembic should not depend on application
# code that may have moved by the time this migration runs in a
# future replay.
_CATEGORY_BY_PREFIX = (
    ("renewal", "renewal"),
    ("reporting", "reporting"),
    ("document_", "verification"),
    ("submission", "verification"),
    ("provider_uploaded", "verification"),
    ("metadata_ready", "verification"),
    ("account", "account"),
    ("admin", "admin"),
    ("support", "admin"),
)


# Same seed payload as 0026_notification_template_versions._SEED.
# Inserted only if ``notification_template_versions`` is empty so
# we never trample admin-created templates on a running prod.
_TEMPLATE_SEED: list[dict] = [
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


def _has_column(inspector, table: str, column: str) -> bool:
    if not inspector.has_table(table):
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def _has_index(inspector, table: str, name: str) -> bool:
    if not inspector.has_table(table):
        return False
    return any(ix["name"] == name for ix in inspector.get_indexes(table))


def _backfill_categories(bind, table: str) -> None:
    for prefix, category in _CATEGORY_BY_PREFIX:
        bind.execute(
            sa.text(
                f"UPDATE {table} SET category = :cat "
                f"WHERE (category = '' OR category IS NULL) "
                f"AND notification_type LIKE :pat"
            ),
            {"cat": category, "pat": f"{prefix}%"},
        )
    bind.execute(
        sa.text(
            f"UPDATE {table} SET category = 'other' "
            f"WHERE category = '' OR category IS NULL"
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # ─── 0024: notification_dispatch ───
    if not inspector.has_table("notification_dispatch"):
        op.create_table(
            "notification_dispatch",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("recipient_role", sa.String(length=40), nullable=False),
            sa.Column("event_type", sa.String(length=80), nullable=False),
            sa.Column("dedupe_key", sa.String(length=255), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("inapp_id", sa.String(length=36), nullable=True),
            sa.Column("email_status", sa.String(length=20), nullable=True),
            sa.Column("email_reason", sa.String(length=120), nullable=True),
            sa.Column("whatsapp_status", sa.String(length=20), nullable=True),
            sa.Column("whatsapp_reason", sa.String(length=120), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "user_id",
                "event_type",
                "dedupe_key",
                name="uq_notification_dispatch_recipient_event",
            ),
        )
        inspector = inspect(bind)

    if not _has_index(
        inspector, "notification_dispatch", "ix_notification_dispatch_user_created_at"
    ):
        op.create_index(
            "ix_notification_dispatch_user_created_at",
            "notification_dispatch",
            ["user_id", "created_at"],
        )
    if not _has_index(
        inspector,
        "notification_dispatch",
        "ix_notification_dispatch_event_created_at",
    ):
        op.create_index(
            "ix_notification_dispatch_event_created_at",
            "notification_dispatch",
            ["event_type", "created_at"],
        )

    # ─── 0025: users.phone_* + user_notification_preferences ───
    inspector = inspect(bind)
    if not _has_column(inspector, "users", "phone_e164"):
        op.add_column(
            "users",
            sa.Column("phone_e164", sa.String(length=20), nullable=True),
        )
    if not _has_column(inspector, "users", "phone_verified_at"):
        op.add_column(
            "users",
            sa.Column(
                "phone_verified_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
    if not _has_column(inspector, "users", "whatsapp_opt_in_at"):
        op.add_column(
            "users",
            sa.Column(
                "whatsapp_opt_in_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    inspector = inspect(bind)
    if not inspector.has_table("user_notification_preferences"):
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

    # ─── 0026: notification_template_versions + seed ───
    inspector = inspect(bind)
    if not inspector.has_table("notification_template_versions"):
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
        inspector = inspect(bind)

    if not _has_index(
        inspector,
        "notification_template_versions",
        "ix_notif_templates_event_channel_locale",
    ):
        op.create_index(
            "ix_notif_templates_event_channel_locale",
            "notification_template_versions",
            ["event_type", "channel", "locale"],
        )

    # Seed only if the table is empty — never trample admin-created
    # templates or a higher version that already exists.
    existing = bind.execute(
        sa.text("SELECT COUNT(*) FROM notification_template_versions")
    ).scalar()
    if existing == 0:
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
                for row in _TEMPLATE_SEED
            ],
        )

    # ─── 0027: phone_verifications ───
    inspector = inspect(bind)
    if not inspector.has_table("phone_verifications"):
        op.create_table(
            "phone_verifications",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("phone_e164", sa.String(length=20), nullable=False),
            sa.Column("code_hash", sa.String(length=64), nullable=False),
            sa.Column(
                "expires_at", sa.DateTime(timezone=True), nullable=False
            ),
            sa.Column(
                "consumed_at", sa.DateTime(timezone=True), nullable=True
            ),
            sa.Column(
                "attempts",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        inspector = inspect(bind)

    if not _has_index(
        inspector,
        "phone_verifications",
        "ix_phone_verifications_user_created",
    ):
        op.create_index(
            "ix_phone_verifications_user_created",
            "phone_verifications",
            ["user_id", "created_at"],
        )

    # ─── 0028: category on (client|provider)_notifications ───
    for table in ("client_notifications", "provider_notifications"):
        inspector = inspect(bind)
        if not _has_column(inspector, table, "category"):
            op.add_column(
                table,
                sa.Column(
                    "category",
                    sa.String(length=20),
                    nullable=False,
                    server_default="",
                ),
            )
        # Always run backfill — the WHERE clause makes it a no-op on
        # rows already classified, and re-runs are needed for any
        # historical rows the original 0028 missed.
        _backfill_categories(bind, table)

        inspector = inspect(bind)
        ix_name = f"ix_{table}_category_severity"
        if not _has_index(inspector, table, ix_name):
            op.create_index(ix_name, table, ["category", "severity"])


def downgrade() -> None:
    # Reverses everything 0024-0028 would have reversed if they had
    # been allowed to apply. Guarded so a partial downgrade does not
    # raise — useful when this migration was a no-op on a fresh
    # install (0024-0028 ran normally and own their own teardown).
    bind = op.get_bind()
    inspector = inspect(bind)

    for table in ("client_notifications", "provider_notifications"):
        ix_name = f"ix_{table}_category_severity"
        if _has_index(inspector, table, ix_name):
            op.drop_index(ix_name, table_name=table)
        if _has_column(inspector, table, "category"):
            op.drop_column(table, "category")
        inspector = inspect(bind)

    if inspector.has_table("phone_verifications"):
        if _has_index(
            inspector,
            "phone_verifications",
            "ix_phone_verifications_user_created",
        ):
            op.drop_index(
                "ix_phone_verifications_user_created",
                table_name="phone_verifications",
            )
        op.drop_table("phone_verifications")
        inspector = inspect(bind)

    if inspector.has_table("notification_template_versions"):
        if _has_index(
            inspector,
            "notification_template_versions",
            "ix_notif_templates_event_channel_locale",
        ):
            op.drop_index(
                "ix_notif_templates_event_channel_locale",
                table_name="notification_template_versions",
            )
        op.drop_table("notification_template_versions")
        inspector = inspect(bind)

    if inspector.has_table("user_notification_preferences"):
        op.drop_table("user_notification_preferences")
        inspector = inspect(bind)

    for col in ("whatsapp_opt_in_at", "phone_verified_at", "phone_e164"):
        if _has_column(inspector, "users", col):
            op.drop_column("users", col)
        inspector = inspect(bind)

    if inspector.has_table("notification_dispatch"):
        if _has_index(
            inspector,
            "notification_dispatch",
            "ix_notification_dispatch_event_created_at",
        ):
            op.drop_index(
                "ix_notification_dispatch_event_created_at",
                table_name="notification_dispatch",
            )
        if _has_index(
            inspector,
            "notification_dispatch",
            "ix_notification_dispatch_user_created_at",
        ):
            op.drop_index(
                "ix_notification_dispatch_user_created_at",
                table_name="notification_dispatch",
            )
        op.drop_table("notification_dispatch")
