"""Persist the folio / fiscal-UUID anchors extracted at intake into the
indexed ``document_folios`` table (Phase 2 keystone).

A read-only-for-now projection of ``DocumentInspection.verification["folios"]``
— the consumers (cross-tenant recycled-document detection, cross-period reuse,
a live-SAT verification cache) are later phases. Population is idempotent per
(document, kind, value) so re-running the intake reconcile or the backfill
never duplicates rows.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import DocumentFolio
from app.services.document_forensics import (
    RISK_HIGH,
    RISK_SUSPICIOUS,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    RiskReason,
    severity_rank,
)

logger = logging.getLogger(__name__)

_MAX_KIND_LEN = 40
_MAX_VALUE_LEN = 120
_CROSS_TENANT_INSTITUTIONS = ("sat", "imss")


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


def cross_tenant_folio_reason(
    db: Session,
    *,
    client_id: str,
    verification: dict[str, Any] | None,
    detected_institution: str | None,
) -> RiskReason | None:
    """Advisory MEDIUM authenticity reason when this document's CFDI fiscal UUID
    already appears under a DIFFERENT client — a strong recycled-document signal
    (the UUID is unique per invoice and survives a re-export where the file
    sha256 does not). Returns ``None`` when the feature is off, the document is
    not SAT/IMSS (avoids shared-template noise), it carries no CFDI UUID, or no
    other client shares one.

    Count-only: the reason carries HOW MANY other clients collide, never WHICH —
    so it never leaks one tenant's document existence to another. Reads the
    ``document_folios`` index for an OTHER-client match; the current document's
    own (same-client) folios are excluded by the ``client_id !=`` filter, so a
    re-finalize / reconcile of the same upload never self-flags.
    """
    if not settings.CROSS_TENANT_RECYCLED_DETECTION_ENABLED:
        return None
    if (detected_institution or "").strip().lower() not in _CROSS_TENANT_INSTITUTIONS:
        return None
    cfdi_values = [value for kind, value in folio_pairs(verification) if kind == "cfdi_uuid"]
    if not cfdi_values:
        return None
    other_clients = (
        db.scalar(
            select(func.count(func.distinct(DocumentFolio.client_id))).where(
                DocumentFolio.kind == "cfdi_uuid",
                DocumentFolio.value.in_(cfdi_values),
                DocumentFolio.client_id != client_id,
            )
        )
        or 0
    )
    if other_clients <= 0:
        return None
    return RiskReason(
        code="cross_tenant_reuse",
        severity=SEVERITY_MEDIUM,
        detail_es=(
            f"Folio fiscal idéntico detectado en {other_clients} otro(s) "
            "cliente(s) — posible reutilización del mismo documento."
        ),
    )


def apply_cross_tenant_reason(
    db: Session,
    *,
    client_id: str,
    verification: dict[str, Any] | None,
    detected_institution: str | None,
    authenticity_risk: str | None,
    risk_reasons: list | None,
) -> tuple[str | None, list | None]:
    """Merge the cross-tenant recycled-document reason (if any) into the intake
    authenticity verdict, returning the (possibly elevated) ``(authenticity_risk,
    risk_reasons)``.

    FAIL-OPEN: any error leaves the verdict untouched and never blocks intake.
    The read runs inside a SAVEPOINT (``begin_nested``) so a failed SELECT can't
    poison the surrounding intake transaction — a raw failed statement leaves the
    session unusable, which would otherwise make the later intake ``commit`` fail
    despite the swallowed exception.

    "Advisory" means it never changes the user-visible document STATUS (that is
    driven by the deterministic signals, not authenticity_risk). It DOES,
    intentionally, elevate the authenticity verdict — a MEDIUM reason lifts a
    clean/NULL verdict to ``suspicious`` (a high verdict is left as-is) — which in
    turn keeps a recycled document out of auto-approval downstream. Reasons stay
    severity-sorted.
    """
    # Short-circuit before the SAVEPOINT so flag-off intake (the prod default)
    # pays zero overhead — no nested transaction, no query.
    if not settings.CROSS_TENANT_RECYCLED_DETECTION_ENABLED:
        return authenticity_risk, risk_reasons
    try:
        with db.begin_nested():
            reason = cross_tenant_folio_reason(
                db,
                client_id=client_id,
                verification=verification,
                detected_institution=detected_institution,
            )
    except Exception:  # noqa: BLE001 — advisory cross-tenant check never blocks intake
        logger.exception("cross-tenant folio check failed (non-fatal)")
        return authenticity_risk, risk_reasons
    if reason is None:
        return authenticity_risk, risk_reasons
    merged = [*(risk_reasons or []), reason.as_dict()]
    merged.sort(key=lambda r: severity_rank(str(r.get("severity", ""))))
    if reason.severity == SEVERITY_HIGH:
        new_risk: str | None = RISK_HIGH
    else:  # medium
        new_risk = RISK_HIGH if authenticity_risk == RISK_HIGH else RISK_SUSPICIOUS
    return new_risk, merged
