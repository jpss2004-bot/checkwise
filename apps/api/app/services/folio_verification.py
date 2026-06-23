"""Reviewer-triggered live SAT CFDI folio verification (B1).

The deterministic intake checks (QR decode + host allowlist, forensics) can be
fooled by a stolen-real or convincingly-fabricated CFDI. This worker closes that
gap by asking SAT directly whether the document's CFDI fiscal UUID is
``vigente`` / ``cancelado`` / ``no_existe``, caching the verdict in
``folio_verifications`` and elevating the document's authenticity verdict with a
HIGH ``folio_not_found_at_sat`` reason when SAT says the comprobante is cancelled
or does not exist.

Load-bearing properties:

* **Reviewer-triggered, NEVER intake-blocking.** Intake never calls this. A
  reviewer (UI button / endpoint) triggers it on demand, so the live call's
  latency / availability / ToS never sits on the provider's upload path.
* **FAIL-OPEN-TO-REVIEW, never to-clean.** Only ``cancelado`` / ``no_existe``
  elevate the verdict. ``vigente`` and ``not_verifiable`` (stub mode, transport
  error, missing inputs) NEVER downgrade a verdict to clean — a doc SAT can't
  confirm stays exactly as the deterministic + AI signals left it, for a human.
* **Advisory.** It changes ``authenticity_risk`` (which gates auto-approval),
  never the user-visible document STATUS.
* **Idempotent + reversible.** Re-verifying strips the prior
  ``folio_not_found_at_sat`` reason first, so a CFDI later found ``vigente``
  un-flags the document; a NULL ("not analyzed") verdict is never fabricated to
  ``clean``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Client,
    Document,
    DocumentFolio,
    DocumentInspection,
    FolioVerification,
    Submission,
    Vendor,
)
from app.models.entities import utc_now
from app.services.document_forensics import (
    SEVERITY_HIGH,
    RiskReason,
    rollup_authenticity_risk,
    severity_rank,
)
from app.services.document_intelligence import normalize_rfc
from app.services.sat_cfdi_client import (
    INVALIDATING_STATUSES,
    STATUS_CANCELADO,
    STATUS_NOT_VERIFIABLE,
    VALID_STATUSES,
    SATConsultaResult,
    build_sat_cfdi_client,
)

logger = logging.getLogger(__name__)

# Re-runs strip-and-replace on this code so the SAT reason never accumulates and
# a later ``vigente`` re-check removes a stale cancelled/no-existe flag.
FOLIO_SAT_REASON_CODE = "folio_not_found_at_sat"

_REASON_DETAIL = {
    STATUS_CANCELADO: (
        "SAT reporta el CFDI como CANCELADO — el comprobante no es válido."
    ),
    # default (no_existe / anything else invalidating)
    "_default": (
        "SAT no encuentra el CFDI (no existe) — folio fiscal no verificable como válido."
    ),
}


@dataclass(frozen=True)
class _FolioInputs:
    document_id: str
    cfdi_uuid: str
    emisor_rfc: str
    receptor_rfc: str


def verify_document_folio(
    db: Session,
    document_id: str,
    *,
    force_refresh: bool = False,
) -> dict:
    """Verify one document's CFDI against SAT (cached). Returns a summary dict.

    Never raises: any failure falls open to ``not_verifiable`` and leaves the
    verdict untouched. Commits its own changes (the reviewer endpoint owns the
    request session but this is a discrete, idempotent operation).
    """
    if not settings.SAT_CFDI_VERIFICATION_ENABLED:
        return {"verified": False, "status": "disabled"}

    try:
        inputs = _gather_inputs(db, document_id)
    except Exception:  # noqa: BLE001 — input resolution must never crash the worker
        logger.exception("Folio verification input resolution failed; document_id=%s", document_id)
        return {"verified": False, "status": STATUS_NOT_VERIFIABLE, "reason": "input_error"}

    if inputs is None:
        return {"verified": False, "status": STATUS_NOT_VERIFIABLE, "reason": "no_document"}
    if not inputs.cfdi_uuid:
        return {"verified": False, "status": STATUS_NOT_VERIFIABLE, "reason": "no_cfdi_uuid"}

    try:
        cached = _lookup_cache(db, inputs)
        cache_fresh = (
            cached is not None and not force_refresh and not _is_stale(cached)
        )
    except Exception:  # noqa: BLE001 — a cache-read failure must not crash the worker
        logger.exception("Folio cache lookup failed; treating as miss. document_id=%s", document_id)
        db.rollback()
        cached, cache_fresh = None, False

    if cache_fresh:
        status, source = cached.status, cached.source
        from_cache = True
    else:
        result = _consultar(inputs)
        status, source = result.status, result.source
        from_cache = False
        try:
            _persist_cache(db, inputs, result)
        except Exception:  # noqa: BLE001 — caching is best-effort; the verdict still applies
            logger.exception("Failed caching folio verification; document_id=%s", document_id)
            db.rollback()

    elevated = False
    try:
        elevated = _apply_folio_verdict(db, inputs.document_id, status)
        db.commit()
    except Exception:  # noqa: BLE001 — fail-open: a verdict-merge failure never blocks
        logger.exception("Failed applying folio verdict; document_id=%s", document_id)
        db.rollback()

    return {
        "verified": True,
        "status": status,
        "source": source,
        "from_cache": from_cache,
        "authenticity_elevated": elevated,
        "cfdi_uuid": inputs.cfdi_uuid,
    }


def _gather_inputs(db: Session, document_id: str) -> _FolioInputs | None:
    """Resolve (cfdi_uuid, emisor_rfc, receptor_rfc) for a document.

    cfdi_uuid comes from the indexed ``document_folios`` projection. The emisor
    is the provider (vendor) and the receptor is the client — the common case
    for a provider's CFDI issued to its client. RFCs are normalized; a missing
    one becomes ``""`` (the SAT consulta would then return not_verifiable).
    """
    row = db.execute(
        select(Vendor.rfc, Client.rfc)
        .join(Submission, Submission.vendor_id == Vendor.id)
        .join(Client, Client.id == Submission.client_id)
        .join(Document, Document.submission_id == Submission.id)
        .where(Document.id == document_id)
        .limit(1)
    ).first()
    if row is None:
        return None
    emisor_rfc = normalize_rfc(row[0]) or ""
    receptor_rfc = normalize_rfc(row[1]) or ""

    cfdi_uuid = db.scalar(
        select(DocumentFolio.value)
        .where(
            DocumentFolio.document_id == document_id,
            DocumentFolio.kind == "cfdi_uuid",
        )
        .limit(1)
    )
    return _FolioInputs(
        document_id=document_id,
        cfdi_uuid=(cfdi_uuid or "").strip().upper(),
        emisor_rfc=emisor_rfc,
        receptor_rfc=receptor_rfc,
    )


def _lookup_cache(db: Session, inputs: _FolioInputs) -> FolioVerification | None:
    return db.scalar(
        select(FolioVerification).where(
            FolioVerification.cfdi_uuid == inputs.cfdi_uuid,
            FolioVerification.emisor_rfc == inputs.emisor_rfc,
            FolioVerification.receptor_rfc == inputs.receptor_rfc,
        )
    )


def _is_stale(row: FolioVerification) -> bool:
    ttl_hours = int(settings.SAT_CFDI_CACHE_TTL_HOURS or 0)
    if ttl_hours <= 0 or row.checked_at is None:
        return False
    checked_at = row.checked_at
    if checked_at.tzinfo is None:  # SQLite stores naive; treat as UTC
        checked_at = checked_at.replace(tzinfo=UTC)
    age = utc_now() - checked_at
    return age.total_seconds() > ttl_hours * 3600


def _consultar(inputs: _FolioInputs) -> SATConsultaResult:
    client = build_sat_cfdi_client()
    try:
        result = client.consultar(
            cfdi_uuid=inputs.cfdi_uuid,
            emisor_rfc=inputs.emisor_rfc,
            receptor_rfc=inputs.receptor_rfc,
        )
    except Exception as exc:  # noqa: BLE001 — fail-open-to-review on any client error
        logger.exception("SAT CFDI consulta failed; falling open to not_verifiable.")
        return SATConsultaResult(
            status=STATUS_NOT_VERIFIABLE,
            source="error",
            raw={"error": type(exc).__name__},
        )
    if result.status not in VALID_STATUSES:
        logger.warning("SAT client returned unknown status %r; not_verifiable.", result.status)
        return SATConsultaResult(
            status=STATUS_NOT_VERIFIABLE, source=result.source, raw=result.raw
        )
    return result


def _persist_cache(db: Session, inputs: _FolioInputs, result: SATConsultaResult) -> None:
    row = _lookup_cache(db, inputs)
    if row is None:
        row = FolioVerification(
            cfdi_uuid=inputs.cfdi_uuid,
            emisor_rfc=inputs.emisor_rfc,
            receptor_rfc=inputs.receptor_rfc,
        )
        db.add(row)
    row.status = result.status
    row.source = result.source
    row.raw = result.raw
    row.last_document_id = inputs.document_id
    row.checked_at = utc_now()
    db.flush()


def _apply_folio_verdict(db: Session, document_id: str, status: str) -> bool:
    """Merge / strip the ``folio_not_found_at_sat`` reason, re-roll the verdict.

    Returns True when an invalidating reason was applied (the verdict elevated).
    Strip-and-replace so re-verification is idempotent and reversible; a NULL
    ("not analyzed") verdict is never fabricated to ``clean``.
    """
    inspection = db.scalar(
        select(DocumentInspection).where(DocumentInspection.document_id == document_id)
    )
    if inspection is None:
        return False

    prior = [r for r in (inspection.risk_reasons or []) if isinstance(r, dict)]
    kept = [r for r in prior if r.get("code") != FOLIO_SAT_REASON_CODE]
    had_folio_reason = len(kept) != len(prior)

    new_reason: RiskReason | None = None
    if status in INVALIDATING_STATUSES:
        detail = _REASON_DETAIL.get(status, _REASON_DETAIL["_default"])
        new_reason = RiskReason(
            code=FOLIO_SAT_REASON_CODE, severity=SEVERITY_HIGH, detail_es=detail
        )

    if new_reason is None and not had_folio_reason:
        # vigente / not_verifiable with nothing stale to strip → leave the
        # deterministic + AI verdict exactly as it was (never fabricate clean).
        return False

    merged = sorted(
        [*kept, *([new_reason.as_dict()] if new_reason else [])],
        key=lambda r: severity_rank(str(r.get("severity") or "")),
    )
    inspection.risk_reasons = merged

    if new_reason is not None or inspection.authenticity_risk is not None:
        inspection.authenticity_risk = rollup_authenticity_risk(
            [
                RiskReason(
                    code=str(r.get("code") or ""),
                    severity=str(r.get("severity") or ""),
                    detail_es=str(r.get("detail_es") or ""),
                )
                for r in merged
            ]
        )
    return new_reason is not None
