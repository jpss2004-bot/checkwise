"""Provider legal-consent columns.

Phase 1 / Slice 1A — block a provider from entering their workspace
until they accept the three legal notices (aviso de privacidad,
términos de uso, aviso de consentimiento). Acceptance is persisted
on the workspace row plus an ``AuditLog`` event with
``action="provider.legal_consent_accepted"``.

Two additive nullable columns. No backfill: existing providers are
treated as un-consented and re-prompted on next entry (locked
decision — see Phase 1 Slice 1A approval).

Revision ID: 0018_provider_legal_consent
Revises: 0017_vendor_contact_phone
Create Date: 2026-05-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0018_provider_legal_consent"
down_revision = "0017_vendor_contact_phone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_workspaces",
        sa.Column(
            "legal_consent_accepted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "provider_workspaces",
        sa.Column(
            "legal_consent_version",
            sa.String(length=120),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("provider_workspaces", "legal_consent_version")
    op.drop_column("provider_workspaces", "legal_consent_accepted_at")
