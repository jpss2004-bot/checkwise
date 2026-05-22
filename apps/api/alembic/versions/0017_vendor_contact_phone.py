"""Vendor contact_phone column.

Backs the admin correction-request approval flow. The provider Tier B
form already accepts ``contact_phone`` as a correction target, but the
Vendor table only had ``contact_name`` + ``contact_email`` — there was
nowhere for the admin's auto-apply path to write a phone value to.
Adding the column closes the gap so an approved correction can update
the canonical record without a manual SQL fix.

Revision ID: 0017_vendor_contact_phone
Revises: 0016_user_profile_fields
Create Date: 2026-05-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0017_vendor_contact_phone"
down_revision = "0016_user_profile_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vendors",
        sa.Column("contact_phone", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vendors", "contact_phone")
