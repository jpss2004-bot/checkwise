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
from app.services.document_analysis.spend_limiter import check_org_daily_quota
from app.services.validation_events import add_validation_event

logger = logging.getLogger(__name__)


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
) -> None:
    """Run shadow analysis for one uploaded document.

    Designed to be queued as a FastAPI ``BackgroundTask`` from the
    intake route. All identifiers are passed by primitive value so the
    function does not capture SQLAlchemy objects across the
    request/background boundary (which would error once the original
    session is closed).
    """
    try:
        provider = build_document_analysis_provider()
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

    try:
        result = provider.analyze(
            pdf_path=Path(pdf_path),
            requirement_code=requirement_code,
            requirement_name=requirement_name,
            institution_code=institution_code,
            period_code=period_code,
            org_id=org_id,
        )
    except Exception as exc:  # noqa: BLE001 — provider should not raise, but defence in depth
        logger.exception("Document-analysis provider raised; persisting as provider_error.")
        result = AnalysisResult(
            provider_id=getattr(provider, "provider_id", "unknown"),
            prompt_version=None,
            latency_ms=0,
            signals=None,
            error=f"provider_error:{type(exc).__name__}",
        )

    _persist_shadow_result(
        document_id=document_id,
        submission_id=submission_id,
        result=result,
    )


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _persist_shadow_result(
    *,
    document_id: str,
    submission_id: str,
    result: AnalysisResult,
) -> None:
    """Write the AnalysisResult to ``document_inspections.shadow_*``.

    Opens a fresh session so the call is safe from a BackgroundTask.
    Commits on success; on any DB error we log and abandon — the
    intake row is unaffected because we are AFTER the original
    transaction's commit.
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
