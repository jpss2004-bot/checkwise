"""Background shadow-analysis runner.

Invoked by ``submission_service.finalize_intake_submission`` as a
FastAPI ``BackgroundTask`` after the intake transaction has committed
and the response has been returned to the provider. The runner is
deliberately decoupled from the request lifecycle: it opens its own
DB session, looks up the ``DocumentInspection`` row by id, runs the
configured provider, and writes the result to the new ``shadow_*``
columns.

Design properties (load-bearing):

* **Never raises into the worker.** A FastAPI BackgroundTask
  exception is logged and silently dropped by Starlette; we
  explicitly catch + log so an operator dumping the API logs sees
  the failure rather than discovering it weeks later via a coverage
  gap.
* **Single DB session per run.** The intake request's session has
  already been committed and closed by the time the BackgroundTask
  fires. The runner uses ``SessionLocal()`` directly, mirroring the
  pattern in ``app.services.client_notifications``.
* **Spend cap enforced before the provider call.** The per-org daily
  cap (``check_org_daily_quota``) is checked first; when the cap is
  tripped we still persist the shadow row (with
  ``shadow_error="daily_cap_exceeded"``) so a reviewer can tell the
  difference between "no shadow run" and "shadow run was cap-skipped".
* **No-op when the provider is disabled.** If
  ``build_document_analysis_provider`` returns ``None`` the runner
  returns immediately without writing any shadow columns. This
  matches ``DOCUMENT_ANALYSIS_PROVIDER=disabled`` semantics.
* **Idempotent on retry.** If the same document_id is processed
  twice, the second run overwrites the first's shadow_* columns and
  emits a second ``shadow_analysis_completed`` ValidationEvent. The
  audit timeline preserves both, so retries are visible rather than
  silent.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Document, DocumentInspection, Submission, Vendor
from app.models.entities import utc_now
from app.services.document_analysis.base import AnalysisResult
from app.services.document_analysis.factory import build_document_analysis_provider
from app.services.document_analysis.spend_limiter import (
    check_org_daily_quota,
    check_org_escalation_daily_quota,
)
from app.services.document_forensics import (
    RISK_HIGH,
    RISK_SUSPICIOUS,
    SEVERITY_HIGH,
    SEVERITY_INFO,
    SEVERITY_MEDIUM,
    RiskReason,
    rollup_authenticity_risk,
    severity_rank,
)
from app.services.document_image_forensics import (
    IMAGE_TAMPER_REASON_CODES,
    ImageTamperResult,
    analyze_image_tampering,
)
from app.services.document_intelligence import compute_rfc_alignment, normalize_rfc
from app.services.validation_events import add_validation_event

logger = logging.getLogger(__name__)

# RiskReason code for every reason derived from the LLM authenticity
# judgment. Re-runs strip-and-replace on this code so reasons never
# accumulate, and the reviewer UI can style IA findings distinctly.
LLM_AUTHENTICITY_REASON_CODE = "llm_authenticity_concern"

# Requirement risk levels that always warrant the escalation tier.
_HIGH_STAKES_RISK_LEVELS = {"alto", "critico", "crítico"}

# Confidence below which the triage extraction itself is treated as an
# escalation trigger (the cheap model is unsure the document even
# matches the requirement).
_TRIAGE_CONFIDENCE_ESCALATION_THRESHOLD = 0.5


def _pilot_allowlist() -> set[str]:
    """Parse ``DOCUMENT_ANALYSIS_PILOT_ORG_IDS`` into a set of ids.

    Empty string / whitespace-only → empty set, meaning "no cohort
    restriction" (every org is in scope). Whitespace + blank entries
    inside the CSV are tolerated so an operator can paste a value
    like ``"abc, , def "`` without breaking the gate.
    """
    raw = (settings.DOCUMENT_ANALYSIS_PILOT_ORG_IDS or "").strip()
    if not raw:
        return set()
    return {chunk.strip() for chunk in raw.split(",") if chunk.strip()}


def run_shadow_analysis(
    *,
    document_id: str,
    submission_id: str,
    pdf_path: str,
    requirement_code: str | None,
    requirement_name: str,
    institution_code: str,
    period_code: str,
    org_id: str | None,
    requirement_risk_level: str | None = None,
    expected_provider_rfc: str | None = None,
    expected_provider_name: str | None = None,
    expected_client_name: str | None = None,
    expected_client_rfc: str | None = None,
) -> None:
    """Run shadow analysis for one uploaded document (tiered, Phase C).

    Designed to be queued as a FastAPI ``BackgroundTask`` from the
    intake route. All identifiers are passed by primitive value so the
    function does not capture SQLAlchemy objects across the
    request/background boundary (which would error once the original
    session is closed).

    Tiering: every shadow-analyzed upload first runs the cheap
    **triage** tier. The stronger **escalation** tier re-runs the
    document with a deeper authenticity-focused prompt when any
    trigger fires (see ``_escalation_triggers``). A successful
    escalation SUPERSEDES the triage result for the stored ``shadow_*``
    columns; both tiers' bookkeeping is recorded under
    ``shadow_signals['_tiers']``. Escalation failures of any kind
    (cap, provider unavailable, provider error) fall back to the
    triage result — fail-open is non-negotiable.
    """
    try:
        provider = build_document_analysis_provider(tier="triage")
    except Exception:  # noqa: BLE001 — provider construction must never crash the worker
        logger.exception("Failed to build document-analysis provider; skipping shadow run.")
        return
    if provider is None:
        return

    # Phase 3 — pilot-cohort gate. When the allowlist is set, orgs
    # outside it are silently no-ops (no DB write, no event). Treating
    # them like ``provider=disabled`` keeps the audit timeline clean
    # during the limited-cohort rollout; once the env var is unset the
    # gate disappears and every org is in scope.
    allowlist = _pilot_allowlist()
    if allowlist and (org_id is None or org_id not in allowlist):
        return

    if not check_org_daily_quota(org_id):
        _persist_shadow_failure(
            document_id=document_id,
            submission_id=submission_id,
            provider_id=provider.provider_id,
            error="daily_cap_exceeded",
        )
        logger.info(
            "Shadow analysis skipped — daily cap reached for org_id=%s, document_id=%s",
            org_id,
            document_id,
        )
        return

    triage_result = _analyze_safely(
        provider,
        pdf_path=pdf_path,
        requirement_code=requirement_code,
        requirement_name=requirement_name,
        institution_code=institution_code,
        period_code=period_code,
        org_id=org_id,
        expected_provider_rfc=expected_provider_rfc,
        expected_provider_name=expected_provider_name,
        expected_client_name=expected_client_name,
        expected_client_rfc=expected_client_rfc,
    )

    final_result = triage_result
    tiers: dict | None = None
    image_result: ImageTamperResult | None = None

    current_risk, is_probably_scanned = _inspection_trigger_context(document_id)
    triggers = _escalation_triggers(
        triage_result,
        requirement_risk_level=requirement_risk_level,
        current_authenticity_risk=current_risk,
    )
    if triggers:
        tiers = {"triage": _tier_meta(triage_result), "escalation": None}
        escalation_result = _run_escalation(
            triggers=triggers,
            pdf_path=pdf_path,
            requirement_code=requirement_code,
            requirement_name=requirement_name,
            institution_code=institution_code,
            period_code=period_code,
            org_id=org_id,
            document_id=document_id,
            expected_provider_rfc=expected_provider_rfc,
            expected_provider_name=expected_provider_name,
            expected_client_name=expected_client_name,
            expected_client_rfc=expected_client_rfc,
        )
        if isinstance(escalation_result, AnalysisResult):
            tiers["escalation"] = {**_tier_meta(escalation_result), "triggers": triggers}
            if escalation_result.error is None:
                # Escalation supersedes triage for the stored columns.
                final_result = escalation_result
        else:
            # ``escalation_result`` is a skip-marker dict (cap reached /
            # provider unavailable). The triage result stands.
            tiers["escalation"] = {**escalation_result, "triggers": triggers}

        # Phase D — pixel-level tamper forensics. Pure-local (no LLM
        # spend), but CPU-heavy and false-positive-prone, so it rides
        # the same "something already looks off" gate as the deep LLM
        # pass — and only on scanned documents (born-digital PDFs have
        # no scan raster to inspect). Independent of the escalation
        # provider outcome: a cap-skip or provider error never blocks
        # the local checks.
        image_result, image_forensics_meta = _run_image_forensics(
            pdf_path=pdf_path,
            is_probably_scanned=is_probably_scanned,
            document_id=document_id,
        )
        tiers["image_forensics"] = image_forensics_meta

    _persist_shadow_result(
        document_id=document_id,
        submission_id=submission_id,
        result=final_result,
        tiers=tiers,
        image_result=image_result,
    )


def _analyze_safely(
    provider,  # noqa: ANN001 — DocumentAnalysisProvider protocol
    *,
    pdf_path: str,
    requirement_code: str | None,
    requirement_name: str,
    institution_code: str,
    period_code: str,
    org_id: str | None,
    expected_provider_rfc: str | None = None,
    expected_provider_name: str | None = None,
    expected_client_name: str | None = None,
    expected_client_rfc: str | None = None,
) -> AnalysisResult:
    """Call ``provider.analyze`` with defence-in-depth exception capture."""
    try:
        return provider.analyze(
            pdf_path=Path(pdf_path),
            requirement_code=requirement_code,
            requirement_name=requirement_name,
            institution_code=institution_code,
            period_code=period_code,
            org_id=org_id,
            expected_provider_rfc=expected_provider_rfc,
            expected_provider_name=expected_provider_name,
            expected_client_name=expected_client_name,
            expected_client_rfc=expected_client_rfc,
        )
    except Exception as exc:  # noqa: BLE001 — provider should not raise, but defence in depth
        logger.exception("Document-analysis provider raised; persisting as provider_error.")
        return AnalysisResult(
            provider_id=getattr(provider, "provider_id", "unknown"),
            prompt_version=None,
            latency_ms=0,
            signals=None,
            error=f"provider_error:{type(exc).__name__}",
        )


def _escalation_triggers(
    triage_result: AnalysisResult,
    *,
    requirement_risk_level: str | None,
    current_authenticity_risk: str | None,
) -> list[str]:
    """Return the list of fired escalation triggers (empty = no escalation).

    Triggers (any one suffices):

    * ``llm_flags`` — the triage model itself reported authenticity
      concerns or judged the document fabricated.
    * ``low_match_confidence`` — triage ``requirement_match_confidence``
      below 0.5: the cheap model is unsure the document matches at all.
    * ``deterministic_risk`` — the inspection row's current
      ``authenticity_risk`` (Phase A forensics + Phase B verification,
      written at intake) is already suspicious/high_risk.
    * ``requirement_risk_level`` — the requirement is alto/critico, so
      every upload gets the deeper pass (bounded by the escalation cap).
    """
    triggers: list[str] = []

    authenticity = triage_result.authenticity or {}
    if authenticity.get("concerns") or authenticity.get("looks_fabricated"):
        triggers.append("llm_flags")

    confidence = (
        triage_result.signals.requirement_match_confidence
        if triage_result.signals is not None
        else None
    )
    if confidence is not None and confidence < _TRIAGE_CONFIDENCE_ESCALATION_THRESHOLD:
        triggers.append("low_match_confidence")

    if current_authenticity_risk in {RISK_SUSPICIOUS, RISK_HIGH}:
        triggers.append("deterministic_risk")

    if (requirement_risk_level or "").strip().lower() in _HIGH_STAKES_RISK_LEVELS:
        triggers.append("requirement_risk_level")

    return triggers


def _run_escalation(
    *,
    triggers: list[str],
    pdf_path: str,
    requirement_code: str | None,
    requirement_name: str,
    institution_code: str,
    period_code: str,
    org_id: str | None,
    document_id: str,
    expected_provider_rfc: str | None = None,
    expected_provider_name: str | None = None,
    expected_client_name: str | None = None,
    expected_client_rfc: str | None = None,
) -> AnalysisResult | dict:
    """Run the escalation tier, or return a skip-marker dict.

    Returns an ``AnalysisResult`` when the escalation provider was
    actually called (success or failure), or a ``{"skipped": reason}``
    dict when the tier was skipped before any provider call (cap
    exhausted, provider unavailable). Never raises.
    """
    if not check_org_escalation_daily_quota(org_id):
        logger.info(
            "Escalation tier skipped — daily escalation cap reached for "
            "org_id=%s, document_id=%s (triggers=%s)",
            org_id,
            document_id,
            triggers,
        )
        return {"skipped": "daily_cap_exceeded"}

    try:
        escalation_provider = build_document_analysis_provider(tier="escalation")
    except Exception:  # noqa: BLE001 — never crash the worker
        logger.exception("Failed to build escalation provider; keeping triage result.")
        return {"skipped": "provider_unavailable"}
    if escalation_provider is None:
        return {"skipped": "provider_unavailable"}

    return _analyze_safely(
        escalation_provider,
        pdf_path=pdf_path,
        requirement_code=requirement_code,
        requirement_name=requirement_name,
        institution_code=institution_code,
        period_code=period_code,
        org_id=org_id,
        expected_provider_rfc=expected_provider_rfc,
        expected_provider_name=expected_provider_name,
        expected_client_name=expected_client_name,
        expected_client_rfc=expected_client_rfc,
    )


def _tier_meta(result: AnalysisResult) -> dict:
    """Small bookkeeping dict for one tier, stored under ``_tiers``."""
    return {
        "provider_id": result.provider_id,
        "prompt_version": result.prompt_version,
        "latency_ms": result.latency_ms,
        "error": result.error,
        "confidence": (
            result.signals.requirement_match_confidence
            if result.signals is not None
            else None
        ),
        "authenticity": result.authenticity,
    }


def _inspection_trigger_context(document_id: str) -> tuple[str | None, bool]:
    """Read the inspection row's deterministic verdict + scanned flag.

    One short-lived session for both values: ``authenticity_risk``
    feeds the deterministic-risk escalation trigger and
    ``is_probably_scanned`` gates the Phase-D image forensics. The
    runner has no ambient session, and the read must never block or
    fail the run — any error reads as "no verdict, not scanned".
    """
    db = SessionLocal()
    try:
        from sqlalchemy import select

        row = db.execute(
            select(
                DocumentInspection.authenticity_risk,
                DocumentInspection.is_probably_scanned,
            ).where(DocumentInspection.document_id == document_id)
        ).first()
        if row is None:
            return None, False
        return row[0], bool(row[1])
    except Exception:  # noqa: BLE001 — a read failure must not abort the shadow run
        logger.exception(
            "Failed reading inspection context for escalation triggers; document_id=%s",
            document_id,
        )
        return None, False
    finally:
        db.close()


def _run_image_forensics(
    *,
    pdf_path: str,
    is_probably_scanned: bool,
    document_id: str,
) -> tuple[ImageTamperResult | None, dict]:
    """Run Phase-D image tamper forensics, or return a skip marker.

    Returns ``(result, bookkeeping)`` where the bookkeeping dict is
    stored under ``shadow_signals['_tiers']['image_forensics']``. A
    ``None`` result means "nothing to merge" (not scanned / analysis
    failed open) — the persisted verdict is untouched. Never raises.
    """
    if not is_probably_scanned:
        return None, {"ran": False, "skipped": "not_scanned"}
    try:
        result = analyze_image_tampering(Path(pdf_path))
    except Exception as exc:  # noqa: BLE001 — defence in depth; the service already fails open
        logger.exception(
            "Image-tamper forensics raised; document_id=%s", document_id
        )
        return None, {"ran": False, "skipped": f"error:{type(exc).__name__}"}
    duration_ms = result.evidence.get("duration_ms")
    if not result.analyzed:
        return None, {
            "ran": False,
            "skipped": result.error or "analysis_failed",
            "duration_ms": duration_ms,
        }
    return result, {
        "ran": True,
        "findings": len(result.reasons),
        "duration_ms": duration_ms,
    }


# ---------------------------------------------------------------------------
# LLM authenticity merge (Phase C)
# ---------------------------------------------------------------------------

# Single reviewer-facing fallback when the model judged the document
# fabricated but did not itemize any concern. Spanish, neutral tone —
# rendered verbatim in the reviewer authenticity card.
_LLM_FABRICATED_FALLBACK_ES = (
    "El análisis de IA considera que el documento podría ser fabricado."
)


def _llm_risk_reasons(authenticity: dict) -> list[RiskReason]:
    """Translate the provider's authenticity judgment into RiskReasons.

    Policy (agreed, load-bearing):

    * Every reason carries ``code=llm_authenticity_concern`` so re-runs
      can strip-and-replace and the UI can style IA findings apart from
      deterministic forensics.
    * LLM severities are CAPPED at ``medium`` — an LLM judgment alone
      can flag a document (``suspicious``) but can never push it to
      ``high_risk``. Model ``low`` maps to ``info``; ``medium`` (and
      anything unexpected) maps to ``medium`` at most.
    * Each ``detail_es`` is prefixed with ``"IA: "`` so a reviewer can
      tell model findings from deterministic ones at a glance.
    * ``looks_fabricated`` with zero itemized concerns still yields one
      medium reason — a fabricated-verdict must never be silently lost.
    """
    reasons: list[RiskReason] = []
    for item in authenticity.get("concerns") or []:
        if not isinstance(item, dict):
            continue
        detail = str(item.get("concern") or "").strip()
        if not detail:
            continue
        severity = SEVERITY_INFO if item.get("severity") == "low" else SEVERITY_MEDIUM
        reasons.append(
            RiskReason(
                code=LLM_AUTHENTICITY_REASON_CODE,
                severity=severity,
                detail_es=f"IA: {detail}",
            )
        )
    if authenticity.get("looks_fabricated") and not reasons:
        reasons.append(
            RiskReason(
                code=LLM_AUTHENTICITY_REASON_CODE,
                severity=SEVERITY_MEDIUM,
                detail_es=f"IA: {_LLM_FABRICATED_FALLBACK_ES}",
            )
        )
    return reasons


def _merge_llm_authenticity(
    inspection: DocumentInspection, result: AnalysisResult
) -> None:
    """Merge the LLM authenticity judgment into the row's verdict.

    Rules (agreed design — see Phase C notes):

    * ``result.authenticity is None`` (heuristic provider, failed run,
      old-prompt replay) → strict no-op. The deterministic verdict and
      its reasons are untouched.
    * Otherwise: strip every prior ``llm_authenticity_concern`` reason
      (re-runs must replace, never accumulate), append the new LLM
      reasons (capped at medium, ``"IA: "``-prefixed), sort high→info
      like intake does, and re-roll ``authenticity_risk`` through the
      shared ``rollup_authenticity_risk``.
    * Deterministic (forensics / QR-verification) reasons are never
      modified — they pass through the merge verbatim.
    * A clean LLM judgment with nothing stale to strip leaves the row
      completely untouched — including ``authenticity_risk=None``
      ("sin analizar") rows, which must not be flipped to ``clean`` by
      a pass that only looked at fabrication signals.
    """
    authenticity = result.authenticity
    if authenticity is None:
        return

    prior = [r for r in (inspection.risk_reasons or []) if isinstance(r, dict)]
    deterministic = [
        r for r in prior if r.get("code") != LLM_AUTHENTICITY_REASON_CODE
    ]
    had_llm_reasons = len(deterministic) != len(prior)

    llm_reasons = _llm_risk_reasons(authenticity)
    if not llm_reasons and not had_llm_reasons:
        # Clean judgment, nothing stale to replace — leave the
        # deterministic verdict exactly as intake wrote it.
        return

    merged = sorted(
        [*deterministic, *(reason.as_dict() for reason in llm_reasons)],
        key=lambda reason: severity_rank(str(reason.get("severity") or "")),
    )
    inspection.risk_reasons = merged

    if llm_reasons or inspection.authenticity_risk is not None:
        inspection.authenticity_risk = rollup_authenticity_risk(
            [
                RiskReason(
                    code=str(reason.get("code") or ""),
                    severity=str(reason.get("severity") or ""),
                    detail_es=str(reason.get("detail_es") or ""),
                )
                for reason in merged
            ]
        )


# ---------------------------------------------------------------------------
# Image-forensics merge (Phase D)
# ---------------------------------------------------------------------------


def _merge_image_forensics(
    inspection: DocumentInspection, result: ImageTamperResult | None
) -> None:
    """Merge Phase-D tamper findings into the row's verdict.

    Mirrors ``_merge_llm_authenticity`` exactly:

    * ``result is None`` / ``analyzed=False`` (not scanned, analysis
      failed open) → strict no-op; the stored verdict is untouched.
    * Otherwise strip every prior ``ela_anomaly`` / ``copy_move_detected``
      reason (re-runs replace, never accumulate), append the new ones
      (defensively capped at medium — image forensics alone can never
      push a document to ``high_risk``), sort high→info, and re-roll
      through the shared ``rollup_authenticity_risk``.
    * Deterministic / LLM reasons pass through verbatim.
    * A clean run with nothing stale to strip leaves the row completely
      untouched — including ``authenticity_risk=None`` ("sin analizar")
      rows, which must not be flipped to ``clean`` by a pass that only
      looked at the scan pixels.

    The raw per-page evidence lands under
    ``inspection.forensics['image_forensics']`` whenever the merge
    writes anything, so the reviewer evidence panel can show it.
    """
    if result is None or not result.analyzed:
        return

    prior = [r for r in (inspection.risk_reasons or []) if isinstance(r, dict)]
    kept = [r for r in prior if r.get("code") not in IMAGE_TAMPER_REASON_CODES]
    had_image_reasons = len(kept) != len(prior)

    new_reasons = [
        RiskReason(
            code=reason.code,
            severity=(
                SEVERITY_MEDIUM
                if reason.severity == SEVERITY_HIGH
                else reason.severity
            ),
            detail_es=reason.detail_es,
        )
        for reason in result.reasons
    ]
    if not new_reasons and not had_image_reasons:
        return

    merged = sorted(
        [*kept, *(reason.as_dict() for reason in new_reasons)],
        key=lambda reason: severity_rank(str(reason.get("severity") or "")),
    )
    inspection.risk_reasons = merged

    forensics = dict(inspection.forensics or {})
    forensics["image_forensics"] = result.evidence
    inspection.forensics = forensics

    if new_reasons or inspection.authenticity_risk is not None:
        inspection.authenticity_risk = rollup_authenticity_risk(
            [
                RiskReason(
                    code=str(reason.get("code") or ""),
                    severity=str(reason.get("severity") or ""),
                    detail_es=str(reason.get("detail_es") or ""),
                )
                for reason in merged
            ]
        )


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _persist_shadow_result(
    *,
    document_id: str,
    submission_id: str,
    result: AnalysisResult,
    tiers: dict | None = None,
    image_result: ImageTamperResult | None = None,
) -> None:
    """Write the AnalysisResult to ``document_inspections.shadow_*``.

    Opens a fresh session so the call is safe from a BackgroundTask.
    Commits on success; on any DB error we log and abandon — the
    intake row is unaffected because we are AFTER the original
    transaction's commit.

    Phase C additions:

    * ``tiers`` (when an escalation decision happened) is stored under
      ``shadow_signals['_tiers']`` so the reviewer comparison card can
      show both passes and why the escalation fired/was skipped.
    * The LLM authenticity judgment on ``result`` is translated into
      ``llm_authenticity_concern`` RiskReasons and merged into the
      row's ``risk_reasons`` / ``authenticity_risk`` (see
      ``_merge_llm_authenticity``).

    Phase D addition: ``image_result`` (tamper findings from the local
    image forensics, escalation path only) merges through
    ``_merge_image_forensics`` with the same strip-and-replace rules
    under its own reason codes, so LLM and image reasons coexist.
    """
    db = SessionLocal()
    try:
        inspection = db.get(DocumentInspection, _inspection_pk(db, document_id))
        if inspection is None:
            logger.warning(
                "Shadow analysis result has no inspection row to attach to; "
                "document_id=%s",
                document_id,
            )
            return

        shadow_signals_blob = None
        shadow_confidence = None
        if result.signals is not None:
            shadow_signals_blob = {
                "detected_institution": result.signals.detected_institution,
                "detected_document_type": result.signals.detected_document_type,
                "detected_rfcs": list(result.signals.detected_rfcs or []),
                "expected_rfc": normalize_rfc(inspection.expected_rfc)
                or _expected_rfc_for_document(db, document_id),
                "detected_dates": list(result.signals.detected_dates or []),
                "period_mentions": list(result.signals.period_mentions or []),
                "requirement_match_confidence": result.signals.requirement_match_confidence,
                "mismatch_reason": result.signals.mismatch_reason,
                "anomaly_codes": list(result.signals.anomaly_codes or []),
            }
            detected_union = sorted(
                {
                    rfc
                    for rfc in (
                        normalize_rfc(value)
                        for value in [
                            *(inspection.detected_rfcs or []),
                            *(result.signals.detected_rfcs or []),
                        ]
                    )
                    if rfc
                }
            )
            expected_rfc = shadow_signals_blob["expected_rfc"]
            inspection.expected_rfc = expected_rfc
            inspection.rfc_alignment = compute_rfc_alignment(
                detected_union,
                expected_rfc,
            )
            shadow_signals_blob["rfc_alignment"] = inspection.rfc_alignment
            shadow_confidence = result.signals.requirement_match_confidence
            if result.raw_meta:
                shadow_signals_blob["_meta"] = result.raw_meta
            if result.authenticity is not None:
                shadow_signals_blob["authenticity"] = result.authenticity
        if tiers is not None:
            # Keep the tier bookkeeping even when the final result has
            # no signals (e.g., both tiers errored) — the skip/error
            # trail is exactly what an operator needs in that case.
            shadow_signals_blob = shadow_signals_blob or {}
            shadow_signals_blob["_tiers"] = tiers

        _merge_llm_authenticity(inspection, result)
        _merge_image_forensics(inspection, image_result)

        inspection.shadow_provider_id = result.provider_id
        inspection.shadow_prompt_version = result.prompt_version
        inspection.shadow_signals = shadow_signals_blob
        inspection.shadow_confidence = shadow_confidence
        inspection.shadow_latency_ms = result.latency_ms
        inspection.shadow_error = result.error
        inspection.shadow_completed_at = utc_now()

        event_result = "pass" if result.error is None else "warning"
        message = (
            "Análisis IA en sombra completado."
            if result.error is None
            else f"Análisis IA en sombra no disponible: {result.error}."
        )
        add_validation_event(
            db,
            submission_id=submission_id,
            document_id=document_id,
            event_type="shadow_analysis_completed",
            rule_code="shadow_document_analysis",
            result=event_result,
            severity="info",
            message=message,
            confidence=shadow_confidence,
            payload={
                "provider_id": result.provider_id,
                "prompt_version": result.prompt_version,
                "latency_ms": result.latency_ms,
                "error": result.error,
            },
            actor_type="system",
        )

        db.commit()

        # Phase E — auto-approval hook. Runs AFTER the commit above so
        # eligibility sees the final post-LLM merged verdict, and is
        # wrapped in its own fail-open guard: an engine failure logs
        # and never disturbs the already-persisted shadow result. The
        # engine ships dark (``AUTO_APPROVE_ENABLED=False``) so this
        # is a cheap no-op until an operator unlocks it.
        try:
            from app.services.auto_approval import maybe_auto_approve

            outcome = maybe_auto_approve(db, submission_id)
            if outcome.attempted:
                logger.info(
                    "Auto-approval outcome submission_id=%s approved=%s reason=%s",
                    submission_id,
                    outcome.approved,
                    outcome.reason,
                )
        except Exception:  # noqa: BLE001 — fail-open; shadow persistence already landed
            logger.exception(
                "Auto-approval hook crashed; shadow result already persisted. "
                "submission_id=%s",
                submission_id,
            )
    except Exception:  # noqa: BLE001 — never let a background failure crash the worker
        logger.exception("Failed to persist shadow analysis result; document_id=%s", document_id)
        db.rollback()
    finally:
        db.close()


def _expected_rfc_for_document(db, document_id: str) -> str | None:  # noqa: ANN001
    return normalize_rfc(
        db.scalar(
            select(Vendor.rfc)
            .join(Submission, Submission.vendor_id == Vendor.id)
            .join(Document, Document.submission_id == Submission.id)
            .where(Document.id == document_id)
            .limit(1)
        )
    )


def _persist_shadow_failure(
    *,
    document_id: str,
    submission_id: str,
    provider_id: str,
    error: str,
) -> None:
    """Persist a non-provider failure (e.g., daily cap) without a provider call.

    Same shape as ``_persist_shadow_result`` for a failure outcome, but
    short-circuits the signal payload because no provider call ran.
    """
    failure = AnalysisResult(
        provider_id=provider_id,
        prompt_version=None,
        latency_ms=0,
        signals=None,
        error=error,
    )
    _persist_shadow_result(
        document_id=document_id,
        submission_id=submission_id,
        result=failure,
    )


def _inspection_pk(db, document_id: str) -> str | None:
    """Resolve the DocumentInspection.id for a given Document.id.

    DocumentInspection has ``document_id UNIQUE NOT NULL``, so this is
    a single row lookup. We resolve the PK first so ``db.get`` is the
    canonical single-row primary-key fetch (the alternative would be a
    ``select().where().scalar()`` which still works but is less
    explicit about the 1:1 expectation).
    """
    from sqlalchemy import select

    return db.scalar(
        select(DocumentInspection.id).where(DocumentInspection.document_id == document_id)
    )
