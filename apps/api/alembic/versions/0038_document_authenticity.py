"""Document authenticity forensics — reviewer-facing risk verdict.

Phase A of the document-revalidation feature (2026-06-11). Every
upload already runs the pypdf structural inspection plus heuristic
content signals; this migration adds a *separate* authenticity
verdict produced by ``app.services.document_forensics`` so a reviewer
can see "this PDF was generated with Canva / edited after creation /
created before the period it claims" without that verdict touching
statuses, validations or the prevalidation pipeline.

Three additive nullable columns on ``document_inspections``:

    * ``authenticity_risk`` — ``"clean" | "suspicious" | "high_risk"``.
      NULL means *not analyzed*: legacy rows that predate this
      migration, or rows where the analyzer failed (intake fails
      open — a forensics error NEVER blocks an upload).
    * ``risk_reasons`` — JSON list of named reasons
      ``{"code", "severity" ("info"|"medium"|"high"), "detail_es"}``,
      sorted high→info. Spanish ``detail_es`` is the user-facing
      string for the reviewer UI.
    * ``forensics`` — raw findings dict (producer, creator,
      creation/mod dates, ``%%EOF`` count, JavaScript/OpenAction
      flags, …) so the reviewer detail can show evidence and a
      future re-scoring pass can re-derive verdicts without
      re-reading the files.

No backfill: historical documents keep NULL ("sin analizar") until a
revalidation pass re-runs the analyzer over stored files (later
phase). Purely additive, so the downgrade is three column drops.

Revision ID: 0038_document_authenticity
Revises: 0037_client_multi_user
Create Date: 2026-06-11
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0038_document_authenticity"
down_revision = "0037_client_multi_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_inspections",
        sa.Column("authenticity_risk", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "document_inspections",
        sa.Column("risk_reasons", sa.JSON(), nullable=True),
    )
    op.add_column(
        "document_inspections",
        sa.Column("forensics", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_inspections", "forensics")
    op.drop_column("document_inspections", "risk_reasons")
    op.drop_column("document_inspections", "authenticity_risk")
