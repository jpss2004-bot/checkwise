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

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import DocumentInspection
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
    SEVERITY_INFO,
    SEVERITY_MEDIUM,
    RiskReason,
    rollup_authenticity_risk,
    severity_rank,
)
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
    )

    final_result = triage_result
    tiers: dict | None = None

    triggers = _escalation_triggers(
        triage_result,
        requirement_risk_level=requirement_risk_level,
        document_id=document_id,
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

    _persist_shadow_result(
        document_id=document_id,
        submission_id=submission_id,
        result=final_result,
        tiers=tiers,
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
    document_id: str,
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

    if _current_authenticity_risk(document_id) in {RISK_SUSPICIOUS, RISK_HIGH}:
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


def _current_authenticity_risk(document_id: str) -> str | None:
    """Read the inspection row's current deterministic verdict.

    Opens (and closes) its own short-lived session: the runner has no
    ambient session, and the read must never block or fail the run —
    any error reads as "no verdict".
    """
    db = SessionLocal()
    try:
        from sqlalchemy import select

        return db.scalar(
            select(DocumentInspection.authenticity_risk).where(
                DocumentInspection.document_id == document_id
            )
        )
    except Exception:  # noqa: BLE001 — a read failure must not abort the shadow run
        logger.exception(
            "Failed reading authenticity_risk for escalation trigger; document_id=%s",
            document_id,
        )
        return None
    finally:
        db.close()


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
# Persistence helpers
# ---------------------------------------------------------------------------


def _persist_shadow_result(
    *,
    document_id: str,
    submission_id: str,
    result: AnalysisResult,
    tiers: dict | None = None,
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
                "detected_dates": list(result.signals.detected_dates or []),
                "period_mentions": list(result.signals.period_mentions or []),
                "requirement_match_confidence": result.signals.requirement_match_confidence,
                "mismatch_reason": result.signals.mismatch_reason,
                "anomaly_codes": list(result.signals.anomaly_codes or []),
            }
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
    except Exception:  # noqa: BLE001 — never let a background failure crash the worker
        logger.exception("Failed to persist shadow analysis result; document_id=%s", document_id)
        db.rollback()
    finally:
        db.close()


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
