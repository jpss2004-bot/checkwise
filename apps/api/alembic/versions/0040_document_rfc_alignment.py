"""Reviewer advisory RFC alignment.

Adds two nullable columns to ``document_inspections`` so the reviewer
queue can show whether extracted RFCs match the uploading provider's
registered RFC. The verdict is advisory only and does not participate
in provider-facing status derivation.

Revision ID: 0040_document_rfc_alignment
Revises: 0039_document_verification
Create Date: 2026-06-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0040_document_rfc_alignment"
down_revision = "0039_document_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_inspections",
        sa.Column("expected_rfc", sa.String(length=13), nullable=True),
    )
    op.add_column(
        "document_inspections",
        sa.Column("rfc_alignment", sa.String(length=40), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_inspections", "rfc_alignment")
    op.drop_column("document_inspections", "expected_rfc")
