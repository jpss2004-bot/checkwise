"""Phase 3 — replacement lineage on submissions.

Adds ``submissions.supersedes_submission_id``: a nullable self-FK that a
new submission uses to record "I replace this prior submission" when a
provider re-uploads after a rejection / clarification / mismatch /
expiry. The new column is indexed because the evidence-slots service
queries it directly to decide which submission is "current" for an
obligation slot.

The migration is additive — every existing row stays valid with
``supersedes_submission_id IS NULL`` (no submission supersedes anyone
yet). Reversible.

Revision ID: 0008_submission_supersedes
Revises: 0007_user_workspace_link
Create Date: 2026-05-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_submission_supersedes"
down_revision = "0007_user_workspace_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column(
            "supersedes_submission_id",
            sa.String(length=36),
            sa.ForeignKey("submissions.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_submissions_supersedes_submission_id",
        "submissions",
        ["supersedes_submission_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_submissions_supersedes_submission_id", table_name="submissions"
    )
    op.drop_column("submissions", "supersedes_submission_id")
