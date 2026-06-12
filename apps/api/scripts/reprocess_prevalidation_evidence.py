"""Recompute stored prevalidation evidence for existing uploads.

Usage:
  cd apps/api
  .venv/bin/python -m scripts.reprocess_prevalidation_evidence --limit 100
  .venv/bin/python -m scripts.reprocess_prevalidation_evidence --apply

Default mode is dry-run. ``--apply`` updates DocumentInspection extraction
columns and the raw_metadata["_prevalidation_evidence"] block, but does not
change Submission.status or provider-facing validations.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models import Document, DocumentInspection, Submission  # noqa: E402
from app.services.document_intelligence import analyze_document_text  # noqa: E402
from app.services.pdf_validation import inspect_pdf_with_ocr_fallback  # noqa: E402
from app.services.storage import get_storage_service  # noqa: E402
from app.services.submission_service import (  # noqa: E402
    PREVALIDATION_EVIDENCE_METADATA_KEY,
)  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--submission-id", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    storage = get_storage_service()
    inspected = 0
    updated = 0
    missing = 0
    try:
        stmt = (
            select(DocumentInspection)
            .join(Document, DocumentInspection.document_id == Document.id)
            .join(Submission, Document.submission_id == Submission.id)
            .options(
                selectinload(DocumentInspection.document)
                .selectinload(Document.submission)
                .selectinload(Submission.vendor),
                selectinload(DocumentInspection.document)
                .selectinload(Document.submission)
                .selectinload(Submission.client),
                selectinload(DocumentInspection.document)
                .selectinload(Document.submission)
                .selectinload(Submission.requirement),
                selectinload(DocumentInspection.document)
                .selectinload(Document.submission)
                .selectinload(Submission.institution),
            )
            .order_by(DocumentInspection.created_at.asc())
        )
        if args.submission_id:
            stmt = stmt.where(Submission.id == args.submission_id)
        if args.limit:
            stmt = stmt.limit(args.limit)

        for inspection in db.scalars(stmt):
            inspected += 1
            document = inspection.document
            submission = document.submission
            vendor = submission.vendor
            client = submission.client
            requirement = submission.requirement
            institution = submission.institution
            try:
                path = storage.open_for_read(document.storage_key)
            except Exception:  # noqa: BLE001
                missing += 1
                print(f"missing\t{submission.id}\t{document.storage_key}")
                continue
            if not path.exists():
                missing += 1
                print(f"missing\t{submission.id}\t{document.storage_key}")
                continue

            pdf = inspect_pdf_with_ocr_fallback(path)
            signals = analyze_document_text(
                pdf.text_sample,
                expected_requirement=(
                    requirement.name
                    if requirement is not None
                    else submission.requirement_code or ""
                ),
                expected_institution=(
                    institution.code if institution is not None else ""
                ),
                expected_period=submission.period_key or "",
                expected_rfc=vendor.rfc if vendor is not None else None,
                expected_vendor_name=vendor.name if vendor is not None else None,
                expected_client_name=client.name if client is not None else None,
                expected_client_rfc=client.rfc if client is not None else None,
            )
            evidence = signals.evidence or {}
            if args.apply:
                inspection.is_pdf = pdf.is_pdf
                inspection.is_corrupt = pdf.is_corrupt
                inspection.is_encrypted = pdf.is_encrypted
                inspection.page_count = pdf.page_count
                inspection.text_char_count = pdf.text_char_count
                inspection.has_text = pdf.has_text
                inspection.is_probably_scanned = pdf.is_probably_scanned
                inspection.detected_institution = signals.detected_institution
                inspection.detected_document_type = signals.detected_document_type
                inspection.detected_rfcs = signals.detected_rfcs
                inspection.expected_rfc = signals.expected_rfc
                inspection.rfc_alignment = signals.rfc_alignment
                inspection.detected_dates = signals.detected_dates
                inspection.period_mentions = signals.period_mentions
                inspection.requirement_match_confidence = (
                    signals.requirement_match_confidence
                )
                inspection.mismatch_reason = signals.mismatch_reason
                raw = dict(pdf.metadata or {})
                raw[PREVALIDATION_EVIDENCE_METADATA_KEY] = evidence
                inspection.raw_metadata = raw
                updated += 1
            print(
                "\t".join(
                    [
                        "updated" if args.apply else "would_update",
                        submission.id,
                        str(signals.rfc_alignment),
                        str(signals.period_alignment),
                        str(signals.identity_alignment),
                        str(signals.requirement_match_confidence),
                    ]
                )
            )

        if args.apply:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    print(
        f"summary\tinspected={inspected}\tupdated={updated}\tmissing={missing}\tapply={args.apply}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
