"""Backfill ``document_folios`` from existing ``DocumentInspection.verification``.

Phase 2 keystone backfill. Intake now writes ``document_folios`` for every new
upload; this script populates the table for documents inspected BEFORE the
feature shipped, by re-parsing the folio anchors already stored in
``DocumentInspection.verification["folios"]``. Idempotent (skips folios already
present per document) and resumable via an id keyset — safe to run repeatedly.

Usage::

    cd apps/api
    .venv/bin/python -m scripts.backfill_document_folios --dry-run
    .venv/bin/python -m scripts.backfill_document_folios --apply
    .venv/bin/python -m scripts.backfill_document_folios --apply --batch-size 500

Read-only by default (``--dry-run``). Touches ONLY the new ``document_folios``
table — never modifies inspections, documents, submissions, or any verdict. As
with the other R2/DB backfills, run on prod only with the prod env exported.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models import Document, DocumentInspection, Submission  # noqa: E402
from app.services.document_folios import folio_pairs, persist_document_folios  # noqa: E402


def _batch(db, *, after_id: str, batch_size: int):
    """One id-keyset page of (inspection_id, document_id, verification,
    client_id, vendor_id, period_id) for inspections carrying a verification
    payload, ordered by inspection id so the run is resumable + bounded.

    The id is a random uuid, NOT insertion-ordered — that is fine: keyset
    pagination only needs a STABLE TOTAL ORDER on the cursor column, which any
    unique PK provides. ``ORDER BY id`` + ``WHERE id > after_id`` walks the
    rows in lexicographic id order and visits each exactly once (each page is
    the smallest ``batch_size`` ids above the cursor; nothing in between is
    skipped). See ``test_backfill_multi_batch_visits_every_row``.
    """
    stmt = (
        select(
            DocumentInspection.id,
            DocumentInspection.document_id,
            DocumentInspection.verification,
            Submission.client_id,
            Submission.vendor_id,
            Submission.period_id,
        )
        .join(Document, DocumentInspection.document_id == Document.id)
        .join(Submission, Document.submission_id == Submission.id)
        .where(
            DocumentInspection.verification.is_not(None),
            DocumentInspection.id > after_id,
        )
        .order_by(DocumentInspection.id)
        .limit(batch_size)
    )
    return db.execute(stmt).all()


def run(db, *, apply: bool, batch_size: int) -> tuple[int, int, int]:
    """Returns ``(inspections_scanned, documents_with_new_folios, folios_added)``.
    In dry-run the pending inserts are rolled back per batch (counts still
    reflect what WOULD be written); in apply they are committed per batch."""
    scanned = 0
    docs_with_new = 0
    folios_added = 0
    after_id = ""
    while True:
        rows = _batch(db, after_id=after_id, batch_size=batch_size)
        if not rows:
            break
        for insp_id, document_id, verification, client_id, vendor_id, period_id in rows:
            after_id = insp_id
            scanned += 1
            if not folio_pairs(verification):
                continue
            added = persist_document_folios(
                db,
                document_id=document_id,
                client_id=client_id,
                vendor_id=vendor_id,
                period_id=period_id,
                verification=verification,
            )
            if added:
                docs_with_new += 1
                folios_added += added
        if apply:
            db.commit()
        else:
            # Discard the batch's pending inserts so a large dry-run stays
            # bounded in memory and writes nothing.
            db.rollback()
    return scanned, docs_with_new, folios_added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Commit changes (default: dry-run)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would change without writing (the default).",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    apply = args.apply and not args.dry_run

    db = SessionLocal()
    try:
        scanned, docs_with_new, folios_added = run(
            db, apply=apply, batch_size=args.batch_size
        )
    finally:
        db.close()

    mode = "APPLIED" if apply else "DRY-RUN (no writes)"
    print(
        f"{mode}: scanned {scanned} inspection(s) with verification; "
        f"{folios_added} folio row(s) across {docs_with_new} document(s) "
        f"{'added' if apply else 'would be added'}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
