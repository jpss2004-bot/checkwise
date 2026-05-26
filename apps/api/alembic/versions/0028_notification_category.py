"""Notification category column + backfill.

Phase 7 / Slice N9b — moves the category derivation off the
frontend and onto the row itself. Both ``client_notifications``
and ``provider_notifications`` gain a ``category`` column with
the canonical Phase 7 vocabulary
(``renewal``, ``reporting``, ``verification``, ``account``,
``admin``, plus the catch-all ``other``).

Why server-side: the frontend was deriving category by prefix-
matching ``notification_type`` (renewal_*, document_*, etc.).
That worked but couples the UI to legacy emit strings; any new
emitter has to remember to use a prefix the UI's switch knows
about. With the column on the row, every emit site sets the
category once and the UI just renders.

Backfill: this migration walks existing rows and assigns
categories via the same prefix logic the frontend used at N9a.
Future emits set the column explicitly.

Revision ID: 0028_notification_category
Revises: 0027_phone_verifications
Create Date: 2026-05-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0028_notification_category"
down_revision = "0027_phone_verifications"
branch_labels = None
depends_on = None


# Same prefix logic the frontend used at N9a. Keep in lockstep
# with :func:`app.services.notifications.categorize.derive_category`.
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


def _backfill_categories(table: str) -> None:
    """One UPDATE per (prefix, category) row. Cheap on Postgres,
    portable to SQLite (the test runner). The fall-through default
    is ``other`` so rows whose ``notification_type`` doesn't match
    any prefix get a stable value rather than NULL."""
    bind = op.get_bind()
    for prefix, category in _CATEGORY_BY_PREFIX:
        bind.execute(
            sa.text(
                f"UPDATE {table} SET category = :cat "
                f"WHERE category = '' AND notification_type LIKE :pat"
            ),
            {"cat": category, "pat": f"{prefix}%"},
        )
    # Anything still unmatched buckets to ``other``.
    bind.execute(
        sa.text(
            f"UPDATE {table} SET category = 'other' WHERE category = ''"
        )
    )


def upgrade() -> None:
    for table in ("client_notifications", "provider_notifications"):
        # Nullable + empty-string default so the column lands without
        # rewriting every historical row in a single transaction;
        # backfill below fills it in.
        op.add_column(
            table,
            sa.Column(
                "category",
                sa.String(length=20),
                nullable=False,
                server_default="",
            ),
        )
        _backfill_categories(table)

    # Indexes for the dashboard filter chip query — "count my
    # actionable notifications by category". Composite with
    # severity because the filter always pairs them.
    op.create_index(
        "ix_client_notifications_category_severity",
        "client_notifications",
        ["category", "severity"],
    )
    op.create_index(
        "ix_provider_notifications_category_severity",
        "provider_notifications",
        ["category", "severity"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_notifications_category_severity",
        table_name="provider_notifications",
    )
    op.drop_index(
        "ix_client_notifications_category_severity",
        table_name="client_notifications",
    )
    op.drop_column("provider_notifications", "category")
    op.drop_column("client_notifications", "category")
