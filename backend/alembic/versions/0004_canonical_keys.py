"""Canonical keys: period_key on periods, requirement_code + period_key on submissions.

Revision ID: 0004_canonical_keys
Revises: 0003_provider_workspaces
Create Date: 2026-05-13

Additive-only migration introduced by the Reconciliation Patch. New canonical
keys are nullable: existing rows survive; the new intake path populates them
when the wizard sends ``requirement_code`` / ``period_key`` from the catalog.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_canonical_keys"
down_revision = "0003_provider_workspaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("periods", sa.Column("period_key", sa.String(length=20), nullable=True))
    op.create_index("ix_periods_period_key", "periods", ["period_key"])

    op.add_column(
        "submissions",
        sa.Column("requirement_code", sa.String(length=80), nullable=True),
    )
    op.create_index(
        "ix_submissions_requirement_code", "submissions", ["requirement_code"]
    )

    op.add_column(
        "submissions",
        sa.Column("period_key", sa.String(length=20), nullable=True),
    )
    op.create_index("ix_submissions_period_key", "submissions", ["period_key"])


def downgrade() -> None:
    op.drop_index("ix_submissions_period_key", table_name="submissions")
    op.drop_column("submissions", "period_key")

    op.drop_index("ix_submissions_requirement_code", table_name="submissions")
    op.drop_column("submissions", "requirement_code")

    op.drop_index("ix_periods_period_key", table_name="periods")
    op.drop_column("periods", "period_key")
