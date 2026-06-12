"""Phase E — auto-approval engine for the document-revalidation feature.

Ships DARK: ``AUTO_APPROVE_ENABLED`` defaults to ``False`` and the
per-requirement unlock CSV defaults to empty, so no document is ever
auto-approved until an operator deliberately flips both. The unlock
list is populated MANUALLY, one requirement code at a time, from
calibration-harness reports proving ≥99% precision for that type.

Entry point: :func:`maybe_auto_approve`, invoked at the end of the
shadow runner's ``_persist_shadow_result`` — after the post-LLM
verdict merge has been committed, so eligibility always sees the
FINAL authenticity verdict. The call is fail-open at every layer: an
exception anywhere returns a non-approved outcome (and the call site
in the shadow runner wraps it again) so shadow persistence is never
broken by the engine.

Eligibility gates (ALL must pass, evaluated in order):

1. ``AUTO_APPROVE_ENABLED`` master kill switch.
2. The submission exists and is still in a reviewable queue status.
3. The submission's requirement code is in the unlocked CSV
   (exact match, whitespace-tolerant).
4. The requirement cadence is RECURRING (mensual/bimestral/…/anual —
   never alta_inicial / unica_vez / contrato / evento / renovación).
5. A ``DocumentInspection`` row exists with an analyzed-clean
   authenticity verdict (``authenticity_risk == "clean"``; NULL =
   not analyzed = not eligible).
6. Zero risk reasons of severity medium/high.
7. Best available match confidence (shadow preferred, heuristic
   fallback) ≥ ``AUTO_APPROVE_MIN_CONFIDENCE``.

When eligible, the SAME transition a reviewer approval applies runs
through :func:`app.services.submission_workflow.apply_system_auto_approval`
(shared core — status, history, validation event, audit log,
notifications), with actor ``system`` and audit action
``system.auto_approved`` carrying the full evidence snapshot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.statuses import DocumentStatus
from app.core.config import settings
from app.models import Document, DocumentInspection, Submission
from app.services.document_forensics import (
    RISK_CLEAN,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
)

logger = logging.getLogger(__name__)

# Cadences that repeat on a calendar. Sourced from the catalog
# vocabularies (``app/core/catalogs.py`` LOAD_TYPES +
# ``compliance_catalog.Frequency`` + ``metadata_rules.Frequency``).
# trimestral/semestral are not in today's catalogs but are included
# defensively — they are unambiguously recurring if they ever appear.
# Everything else (alta_inicial, unica_vez, contrato, evento,
# renovacion, cada_3_anios, reporte_interno, …) is NON-recurring by
# allowlist construction: one-shot and event-driven documents must
# never be suggested or auto-approved.
RECURRING_CADENCES: frozenset[str] = frozenset(
    {
        "mensual",
        "bimestral",
        "trimestral",
        "cuatrimestral",
        "semestral",
        "anual",
    }
)

# Statuses still waiting on a decision — mirrors the reviewer queue
# (``app.api.v1.reviewer.QUEUE_STATUSES``). Defined here from the
# canonical enum so the service layer never imports an API module.
_REVIEWABLE_STATUSES: frozenset[str] = frozenset(
    {
        DocumentStatus.RECIBIDO.value,
        DocumentStatus.PENDIENTE_REVISION.value,
        DocumentStatus.PREVALIDADO.value,
        DocumentStatus.POSIBLE_MISMATCH.value,
    }
)


def is_recurring_cadence(value: str | None) -> bool:
    """True iff ``value`` is a recurring catalog cadence (whitespace-tolerant)."""
    return (value or "").strip().lower() in RECURRING_CADENCES


def resolve_submission_cadence(submission: Submission) -> str | None:
    """Best available cadence for a submission.

    Prefers the requirement's declared ``frequency`` (falling back to
    its ``load_type``), then the submission's denormalized
    ``load_type`` for legacy rows whose requirement FK is dangling.
    """
    requirement = submission.requirement
    if requirement is not None:
        return requirement.frequency or requirement.load_type
    return submission.load_type


def best_confidence(
    inspection: DocumentInspection | None,
) -> tuple[float | None, str | None]:
    """Best available match confidence + its source.

    Shadow (LLM) confidence is preferred; the intake heuristic's
    ``requirement_match_confidence`` is the fallback. Returns
    ``(None, None)`` when neither exists (or there is no inspection).
    """
    if inspection is None:
        return None, None
    if inspection.shadow_confidence is not None:
        return float(inspection.shadow_confidence), "shadow"
    if inspection.requirement_match_confidence is not None:
        return float(inspection.requirement_match_confidence), "heuristic"
    return None, None


@dataclass(frozen=True)
class AutoApprovalOutcome:
    """Result of one auto-approval evaluation.

    ``attempted`` is True only when EVERY eligibility gate passed and
    the engine actually tried the transition; ``approved`` then says
    whether the transition committed. ``reason`` is a stable
    machine-readable token for logs/metrics (which gate blocked, or
    ``"approved"``).
    """

    attempted: bool
    approved: bool
    reason: str


def _unlocked_requirement_codes() -> set[str]:
    """Parse the unlock CSV into a set (whitespace/blank tolerant)."""
    raw = (settings.AUTO_APPROVE_UNLOCKED_REQUIREMENT_CODES or "").strip()
    if not raw:
        return set()
    return {chunk.strip() for chunk in raw.split(",") if chunk.strip()}


def _blocked(reason: str) -> AutoApprovalOutcome:
    return AutoApprovalOutcome(attempted=False, approved=False, reason=reason)


def maybe_auto_approve(db: Session, submission_id: str) -> AutoApprovalOutcome:
    """Evaluate + (when fully eligible) apply an automatic approval.

    Never raises: any unexpected error is logged and reported as a
    non-approved outcome so callers (the shadow runner) stay fail-open.
    """
    try:
        return _maybe_auto_approve(db, submission_id)
    except Exception as exc:  # noqa: BLE001 — fail-open is non-negotiable
        logger.exception(
            "Auto-approval engine crashed; submission_id=%s", submission_id
        )
        return AutoApprovalOutcome(
            attempted=True, approved=False, reason=f"error:{type(exc).__name__}"
        )


def _maybe_auto_approve(db: Session, submission_id: str) -> AutoApprovalOutcome:
    if not settings.AUTO_APPROVE_ENABLED:
        return _blocked("disabled")

    submission = db.get(Submission, submission_id)
    if submission is None:
        return _blocked("submission_not_found")

    if submission.status not in _REVIEWABLE_STATUSES:
        return _blocked("status_not_reviewable")

    requirement = submission.requirement
    requirement_code = submission.requirement_code or (
        requirement.code if requirement is not None else None
    )
    unlocked = _unlocked_requirement_codes()
    if not requirement_code or requirement_code not in unlocked:
        return _blocked("requirement_not_unlocked")

    cadence = resolve_submission_cadence(submission)
    if not is_recurring_cadence(cadence):
        return _blocked("cadence_not_recurring")

    document = db.scalar(
        select(Document).where(Document.submission_id == submission.id).limit(1)
    )
    inspection = (
        db.scalar(
            select(DocumentInspection)
            .where(DocumentInspection.document_id == document.id)
            .limit(1)
        )
        if document is not None
        else None
    )
    if inspection is None:
        return _blocked("no_inspection")

    # NULL means "not analyzed" — only an explicit clean verdict passes.
    if inspection.authenticity_risk != RISK_CLEAN:
        return _blocked("authenticity_not_clean")

    risk_reasons = [r for r in (inspection.risk_reasons or []) if isinstance(r, dict)]
    if any(
        r.get("severity") in (SEVERITY_MEDIUM, SEVERITY_HIGH) for r in risk_reasons
    ):
        return _blocked("risk_reasons_present")

    confidence, confidence_source = best_confidence(inspection)
    if confidence is None:
        return _blocked("no_confidence")
    if confidence < settings.AUTO_APPROVE_MIN_CONFIDENCE:
        return _blocked("confidence_below_threshold")

    # Every gate passed — assemble the evidence snapshot the audit row
    # will carry, then apply the shared decision transition.
    shadow_signals = inspection.shadow_signals or {}
    evidence = {
        "source": "auto_approval",
        "requirement_code": requirement_code,
        "cadence": cadence,
        "confidence": confidence,
        "confidence_source": confidence_source,
        "min_confidence": settings.AUTO_APPROVE_MIN_CONFIDENCE,
        "authenticity_risk": inspection.authenticity_risk,
        "risk_reasons": risk_reasons,
        "tiers": shadow_signals.get("_tiers"),
        "unlocked_requirement_codes": sorted(unlocked),
    }

    from app.services.submission_workflow import apply_system_auto_approval

    try:
        result = apply_system_auto_approval(db, submission=submission, evidence=evidence)
    except Exception as exc:  # noqa: BLE001 — a racing reviewer decision (409) is a no-op
        logger.warning(
            "Auto-approval transition did not apply; submission_id=%s error=%s",
            submission_id,
            exc,
        )
        return AutoApprovalOutcome(
            attempted=True, approved=False, reason=f"transition_failed:{type(exc).__name__}"
        )

    # Phase 7 fabric parity — the reviewer router fires the unified
    # notification envelope after every human decision; mirror it here
    # so an auto-approval reaches the same inboxes. Best-effort: the
    # approval above is already committed.
    try:
        from app.services.notifications import emit_reviewer_decision

        emit_reviewer_decision(
            db,
            submission=submission,
            action=result.action,
            reason=result.reason,
            mode="active",
        )
        db.flush()
        db.commit()
    except Exception:  # pragma: no cover — defensive, mirrors the router
        logger.exception(
            "notif_emit_failed event=system.auto_approved submission=%s",
            submission_id,
        )

    logger.info(
        "Auto-approved submission_id=%s requirement_code=%s confidence=%.4f (%s)",
        submission_id,
        requirement_code,
        confidence,
        confidence_source,
    )
    return AutoApprovalOutcome(attempted=True, approved=True, reason="approved")
