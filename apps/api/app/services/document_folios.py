"""Persist the folio / fiscal-UUID anchors extracted at intake into the
indexed ``document_folios`` table (Phase 2 keystone).

A read-only-for-now projection of ``DocumentInspection.verification["folios"]``
— the consumers (cross-tenant recycled-document detection, cross-period reuse,
a live-SAT verification cache) are later phases. Population is idempotent per
(document, kind, value) so re-running the intake reconcile or the backfill
never duplicates rows.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DocumentFolio

_MAX_KIND_LEN = 40
_MAX_VALUE_LEN = 120


def folio_pairs(verification: dict[str, Any] | None) -> list[tuple[str, str]]:
    """The cleaned, deduped ``(kind, value)`` pairs in a verification payload's
    ``folios`` list (order-preserving). Tolerates a missing / malformed payload
    by returning an empty list — folio indexing never assumes a shape."""
    if not isinstance(verification, dict):
        return []
    raw = verification.get("folios")
    if not isinstance(raw, list):
        return []
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        value = entry.get("value")
        # Skip only truly-absent fields (None / empty string) — a folio needs
        # both. Explicit rather than a bare falsiness test so a legitimate
        # 0/False-ish value wouldn't be dropped. (The real producer,
        # ``extract_folios``, only ever emits non-empty strings; any ``kind``
        # is stored verbatim — none is special-cased here.)
        if kind in (None, "") or value in (None, ""):
            continue
        pair = (str(kind)[:_MAX_KIND_LEN], str(value)[:_MAX_VALUE_LEN])
        if pair in seen:
            continue
        seen.add(pair)
        pairs.append(pair)
    return pairs


def persist_document_folios(
    db: Session,
    *,
    document_id: str,
    client_id: str,
    vendor_id: str,
    period_id: str | None,
    verification: dict[str, Any] | None,
) -> int:
    """Insert one ``DocumentFolio`` per extracted folio not already present for
    this document. Adds to the session WITHOUT committing — the caller's
    transaction owns the commit. Idempotent: existing (document, kind, value)
    rows are skipped, so the intake reconcile + the backfill are safe to
    re-run. Returns the number of new rows added."""
    pairs = folio_pairs(verification)
    if not pairs:
        return 0
    existing = {
        (kind, value)
        for kind, value in db.execute(
            select(DocumentFolio.kind, DocumentFolio.value).where(
                DocumentFolio.document_id == document_id
            )
        ).all()
    }
    added = 0
    for kind, value in pairs:
        if (kind, value) in existing:
            continue
        existing.add((kind, value))
        db.add(
            DocumentFolio(
                document_id=document_id,
                client_id=client_id,
                vendor_id=vendor_id,
                period_id=period_id,
                kind=kind,
                value=value,
            )
        )
        added += 1
    return added
