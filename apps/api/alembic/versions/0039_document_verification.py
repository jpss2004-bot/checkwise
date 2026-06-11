"""Document verification anchors — QR codes and folios.

Phase B of the document-revalidation feature (2026-06-11). Phase A
(0038) gave the reviewer a container-level authenticity verdict; this
phase extracts the document's *verifiable anchors* — QR codes decoded
from the embedded page images (with an official-domain classification
against the SAT/IMSS/INFONAVIT/STPS allowlist) and printed folios
(CFDI UUID, opinion folios) — so a reviewer can jump to the issuing
institution's verification portal instead of eyeballing the PDF.

One additive nullable column on ``document_inspections``:

    * ``verification`` — JSON dict shaped
      ``{"qr_codes": [{"page", "content", "is_url", "host",
      "official", "institution_guess"}, ...],
      "folios": [{"kind", "value"}, ...],
      "pages_scanned": int, "images_scanned": int,
      "error": str|None}``.
      NULL means *not analyzed*: legacy rows that predate this
      migration (intake fails open — a verification error NEVER
      blocks an upload; an in-band failure stores ``error`` instead).

The verification *risk reasons* (``qr_non_official_domain``,
``missing_expected_qr``) do not get their own column: they are merged
into the Phase-A ``risk_reasons`` list and rolled into
``authenticity_risk`` at intake, keeping one verdict surface.

No backfill: historical documents keep NULL ("sin analizar") until a
revalidation pass re-runs the extractor over stored files (later
phase). Purely additive, so the downgrade is one column drop.

Revision ID: 0039_document_verification
Revises: 0038_document_authenticity
Create Date: 2026-06-11
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0039_document_verification"
down_revision = "0038_document_authenticity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_inspections",
        sa.Column("verification", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_inspections", "verification")
