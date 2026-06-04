"""User legal-consent columns (client-side gate).

Legal review v2 (2026-06-03) — every client_admin must now accept the
legal package, not only providers. Acceptance is persisted per-user on
``users`` (a client_admin accepts once per version regardless of how
many client orgs they manage) plus an ``AuditLog`` event with
``action="client.legal_consent_accepted"`` carrying IP + user-agent.

Two additive nullable columns. No backfill: existing client_admins are
treated as un-consented and re-prompted on next entry — which is the
intended effect of the v1 -> v2 bump.

Revision ID: 0033_user_legal_consent
Revises: 0032_doc_inspection_shadow
Create Date: 2026-06-03
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0033_user_legal_consent"
down_revision = "0032_doc_inspection_shadow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "legal_consent_accepted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "legal_consent_version",
            sa.String(length=120),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "legal_consent_version")
    op.drop_column("users", "legal_consent_accepted_at")
