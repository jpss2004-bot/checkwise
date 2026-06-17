"""Phase 2 — expediente-level situational assessment.

Where the per-document comprehension (Phase 1, persisted under
``DocumentInspection.shadow_signals['comprehension']``) reasons about ONE
document, this pass reasons about the WHOLE situation for a provider in a
period: cross-document coherence (does the IMSS headcount match the
contract's ``estimated_workers``, is the REPSE authorized activity
consistent with the contracted service, do the periods/entities cohere
across documents) plus obligation coverage gaps.

Design (mirrors ``shadow_runner``):

* **Reviewer-facing and additive.** Writes one ``ExpedienteAssessment``
  row; never alters user-visible status.
* **Never raises into the caller.** Every failure path persists an error
  row (or no-ops) instead of propagating.
* **Owns its DB sessions.** Loads the situation, closes the session,
  makes the (slow) LLM call without holding a connection, then reopens to
  persist.
* **Gated.** Off unless ``DOCUMENT_ANALYSIS_EXPEDIENTE_ENABLED`` AND a
  real provider is configured, and bounded by the per-org escalation cap
  (each run is a deep call on the stronger model).
* **Structured output + thinking.** Same mechanism as the deep document
  tier: ``output_config.format`` (composes with adaptive thinking) on the
  ``DOCUMENT_ANALYSIS_MODEL`` deep model.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import (
    Client,
    Contract,
    Document,
    ExpedienteAssessment,
    Period,
    Submission,
    Vendor,
)
from app.services.document_analysis.spend_limiter import (
    check_org_escalation_daily_quota,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "expediente.v1"

_COHERENCE_VALUES = ("coherent", "minor_issues", "incoherent", "indeterminate")
_FINDING_SEVERITIES = ("info", "low", "medium", "high")
_FINDING_CODES = (
    "headcount_inconsistency",
    "activity_inconsistency",
    "period_incoherence",
    "entity_inconsistency",
    "contract_window_mismatch",
    "repse_folio_mismatch",
    "missing_obligation",
    "other",
)


_SYSTEM_PROMPT = (
    "Eres un analista de cumplimiento documental para CheckWise, una "
    "plataforma mexicana de gestión REPSE. Recibes el EXPEDIENTE de un "
    "proveedor para un periodo: los datos del contrato y un conjunto de "
    "documentos ya analizados individualmente (cada uno con su comprensión "
    "y hechos clave).\n\n"
    "Tu trabajo NO es re-evaluar cada documento, sino **razonar sobre la "
    "situación completa**: ¿los documentos cuentan una historia coherente "
    "entre sí y con el contrato? Nunca otorgas aprobación legal final; el "
    "equipo de Legal Shelf decide. Tu salida alerta sobre incoherencias "
    "que sólo se ven al mirar el expediente en conjunto.\n\n"
    "Revisa al menos:\n"
    "- **Trabajadores**: ¿el número de trabajadores en los pagos al IMSS es "
    "congruente con los `trabajadores_estimados` del contrato y con la "
    "nómina? Una diferencia grande es una señal.\n"
    "- **Actividad**: ¿la actividad autorizada en el REPSE es congruente con "
    "el objeto del servicio y la `actividad_registrada` del contrato?\n"
    "- **Folio REPSE**: ¿el folio del registro REPSE coincide con el del "
    "contrato (si está disponible)?\n"
    "- **Periodos**: ¿las fechas y periodos de los documentos son coherentes "
    "entre sí y con la vigencia del contrato?\n"
    "- **Identidad**: ¿todos los documentos pertenecen al mismo proveedor "
    "(RFC/razón social), y no al cliente u otra entidad?\n"
    "- **Cobertura**: dado el contrato y el periodo, ¿faltan obligaciones "
    "que deberían estar presentes o que no se cumplen?\n\n"
    "Reglas:\n"
    "1. Reporta sólo lo que observes en los datos. Sé conservador: un "
    "expediente congruente NO debe llevar hallazgos. En caso de duda usa "
    "`indeterminate` y explica qué falta para concluir.\n"
    "2. `findings` son hallazgos a nivel expediente (cruces entre "
    "documentos / contrato), no problemas de un solo documento. Cada uno: "
    "`{code, severity, detail_es, evidence}`.\n"
    "3. `coverage_gaps` son obligaciones implícitas faltantes o no "
    "cumplidas: `{requirement_code, detail_es}` (usa el código si lo "
    "conoces, o una etiqueta corta).\n"
    "4. `detail_es` y `summary_for_reviewer` en español neutro, sin jerga "
    "técnica y sin mencionar el modelo.\n\n"
    "Devuelve un único objeto JSON conforme al esquema."
)


_EXPEDIENTE_OUTPUT_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "coherence": {"type": "string", "enum": list(_COHERENCE_VALUES)},
            "summary_for_reviewer": {"type": "string"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "code": {"type": "string", "enum": list(_FINDING_CODES)},
                        "severity": {
                            "type": "string",
                            "enum": list(_FINDING_SEVERITIES),
                        },
                        "detail_es": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["code", "severity", "detail_es", "evidence"],
                },
            },
            "coverage_gaps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "requirement_code": {"type": "string"},
                        "detail_es": {"type": "string"},
                    },
                    "required": ["requirement_code", "detail_es"],
                },
            },
        },
        "required": ["coherence", "summary_for_reviewer", "findings", "coverage_gaps"],
    },
}


# ---------------------------------------------------------------------------
# Context assembly (pure where possible, for testability)
# ---------------------------------------------------------------------------


def build_expediente_context(
    *,
    vendor: Any,
    client: Any,
    period: Any | None,
    contract: Any | None,
    document_entries: list[dict],
) -> dict:
    """Shape the situational context sent to the model.

    Pure: takes already-loaded attribute objects (ORM rows or simple
    namespaces) plus the per-document entries and returns a plain dict.
    """
    context: dict[str, Any] = {
        "proveedor": {
            "nombre": getattr(vendor, "name", None),
            "rfc": getattr(vendor, "rfc", None),
            "repse_id": getattr(vendor, "repse_id", None),
        },
        "cliente": {
            "nombre": getattr(client, "name", None),
            "rfc": getattr(client, "rfc", None),
        },
        "periodo": {
            "period_key": getattr(period, "period_key", None),
            "code": getattr(period, "code", None),
        },
        "contrato": None,
        "documentos": document_entries,
    }
    if contract is not None:
        context["contrato"] = {
            "objeto_servicio": getattr(contract, "service_object", None),
            "actividad_registrada": getattr(contract, "registered_activity", None),
            "repse_folio": getattr(contract, "repse_folio", None),
            "trabajadores_estimados": getattr(contract, "estimated_workers", None),
            "ubicacion": getattr(contract, "work_location", None),
            "vigencia": {
                "inicio": _iso(getattr(contract, "start_date", None)),
                "fin": _iso(getattr(contract, "end_date", None)),
            },
        }
    return context


def _iso(value: Any) -> str | None:
    try:
        return value.isoformat() if value is not None else None
    except AttributeError:
        return str(value) if value is not None else None


def _current_submissions(submissions: list[Submission]) -> list[Submission]:
    """Keep the current (non-superseded) leaf of each replacement chain.

    Mirrors ``evidence_slots._pick_current_submission`` semantics across
    the whole expediente: a submission another submission points at via
    ``supersedes_submission_id`` is a prior attempt and is dropped.
    """
    superseded = {
        s.supersedes_submission_id for s in submissions if s.supersedes_submission_id
    }
    return [s for s in submissions if s.id not in superseded]


def _document_entry(submission: Submission, document: Document) -> dict:
    inspection = document.inspection
    requirement = submission.requirement
    comprehension = None
    extraction = None
    if inspection is not None:
        signals = inspection.shadow_signals or {}
        if isinstance(signals, dict):
            comprehension = signals.get("comprehension")
        extraction = {
            "institucion": inspection.detected_institution,
            "tipo": inspection.detected_document_type,
            "rfcs": list(inspection.detected_rfcs or []),
            "confianza": inspection.requirement_match_confidence,
            "discrepancia": inspection.mismatch_reason,
        }
    return {
        "document_id": document.id,
        "requisito": {
            "codigo": submission.requirement_code
            or (requirement.code if requirement is not None else None),
            "nombre": requirement.name if requirement is not None else None,
            "institucion": (
                requirement.institution.code
                if requirement is not None and requirement.institution is not None
                else None
            ),
            "riesgo": requirement.risk_level if requirement is not None else None,
        },
        "estatus": submission.status,
        "comprension": comprehension,
        "extraccion": extraction,
    }


def _recently_assessed(
    db: Any,
    *,
    client_id: str,
    vendor_id: str,
    period_id: str,
    within_hours: int,
) -> bool:
    """True if a non-errored assessment for this scope exists within the window.

    Backs the debounce on the after-deep-run trigger: re-assessing the
    whole expediente on every deep document would be wasteful, so a recent
    assessment short-circuits the next one. Errored rows do not count
    (a failed run should not suppress a retry).
    """
    cutoff = datetime.now(UTC) - timedelta(hours=within_hours)
    row = (
        db.execute(
            select(ExpedienteAssessment.id)
            .where(
                ExpedienteAssessment.client_id == client_id,
                ExpedienteAssessment.vendor_id == vendor_id,
                ExpedienteAssessment.period_id == period_id,
                ExpedienteAssessment.error.is_(None),
                ExpedienteAssessment.created_at >= cutoff,
            )
            .limit(1)
        )
        .first()
    )
    return row is not None


def _load_context(
    db: Any,
    *,
    client_id: str,
    vendor_id: str,
    period_id: str,
) -> tuple[dict | None, list[str], str | None]:
    """Load and shape the expediente context for one (client, vendor, period).

    Returns ``(context, document_ids, contract_id)``. ``context`` is
    ``None`` when there are no current documents to assess.
    """
    submissions = (
        db.execute(
            select(Submission).where(
                Submission.client_id == client_id,
                Submission.vendor_id == vendor_id,
                Submission.period_id == period_id,
            )
        )
        .scalars()
        .all()
    )
    current = _current_submissions(submissions)

    document_entries: list[dict] = []
    document_ids: list[str] = []
    for submission in current:
        for document in submission.documents:
            document_entries.append(_document_entry(submission, document))
            document_ids.append(document.id)

    if not document_entries:
        return None, [], None

    contract = None
    contract_id = next((s.contract_id for s in current if s.contract_id), None)
    if contract_id is not None:
        contract = db.get(Contract, contract_id)
    if contract is None:
        contract = (
            db.execute(
                select(Contract)
                .where(
                    Contract.client_id == client_id,
                    Contract.vendor_id == vendor_id,
                )
                .order_by(Contract.created_at.desc())
            )
            .scalars()
            .first()
        )
        if contract is not None:
            contract_id = contract.id

    vendor = db.get(Vendor, vendor_id)
    client = db.get(Client, client_id)
    period = db.get(Period, period_id)

    context = build_expediente_context(
        vendor=vendor,
        client=client,
        period=period,
        contract=contract,
        document_entries=document_entries,
    )
    return context, document_ids, contract_id


# ---------------------------------------------------------------------------
# LLM pass
# ---------------------------------------------------------------------------


def _build_client() -> Any | None:
    key = (settings.ANTHROPIC_API_KEY or "").strip()
    if not key:
        return None
    try:
        from anthropic import Anthropic
    except ImportError:
        return None
    return Anthropic(api_key=key)


def analyze_expediente(client: Any, context: dict) -> tuple[dict | None, dict, str | None]:
    """Run the situational LLM pass. Returns (assessment, raw_meta, error)."""
    model = (settings.DOCUMENT_ANALYSIS_MODEL or "claude-sonnet-4-6").strip()
    timeout = float(settings.DOCUMENT_ANALYSIS_DEEP_TIMEOUT_SECONDS or 90.0)
    max_tokens = int(settings.DOCUMENT_ANALYSIS_DEEP_MAX_TOKENS or 8192)
    user_text = (
        "Analiza el siguiente expediente y devuelve tu evaluación situacional "
        "conforme al esquema. Datos del expediente (JSON):\n\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
    )
    try:
        response = client.with_options(timeout=timeout).messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": [{"type": "text", "text": user_text}]}],
            thinking={"type": "adaptive"},
            output_config={"format": _EXPEDIENTE_OUTPUT_FORMAT, "effort": "high"},
        )
    except Exception as exc:  # noqa: BLE001 — categorise as a known failure
        name = type(exc).__name__
        if "Timeout" in name or "Connect" in name:
            return None, {}, "timeout"
        return None, {}, f"provider_error:{name}"

    raw_meta: dict[str, Any] = {
        "stop_reason": str(getattr(response, "stop_reason", "")),
        "model": str(getattr(response, "model", "")),
    }
    usage = getattr(response, "usage", None)
    if usage is not None:
        try:
            raw_meta["usage"] = usage.model_dump()
        except Exception:  # noqa: BLE001 — best-effort diagnostic
            raw_meta["usage"] = str(usage)

    text: str | None = None
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", None)
            break
    if not text:
        return None, raw_meta, "malformed_response"
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None, raw_meta, "malformed_response"
    if not isinstance(payload, dict):
        return None, raw_meta, "malformed_response"
    return normalise_assessment(payload), raw_meta, None


def normalise_assessment(payload: dict) -> dict:
    """Tolerantly normalise the model's assessment object."""
    coherence = payload.get("coherence")
    if coherence not in _COHERENCE_VALUES:
        coherence = "indeterminate"

    findings: list[dict[str, str]] = []
    for item in payload.get("findings") or []:
        if not isinstance(item, dict):
            continue
        detail = str(item.get("detail_es") or "").strip()
        if not detail:
            continue
        code = item.get("code")
        if code not in _FINDING_CODES:
            code = "other"
        severity = item.get("severity")
        if severity not in _FINDING_SEVERITIES:
            severity = "medium"
        findings.append(
            {
                "code": code,
                "severity": severity,
                "detail_es": detail,
                "evidence": str(item.get("evidence") or "").strip(),
            }
        )

    coverage_gaps: list[dict[str, str]] = []
    for item in payload.get("coverage_gaps") or []:
        if not isinstance(item, dict):
            continue
        detail = str(item.get("detail_es") or "").strip()
        if not detail:
            continue
        coverage_gaps.append(
            {
                "requirement_code": str(item.get("requirement_code") or "").strip(),
                "detail_es": detail,
            }
        )

    return {
        "coherence": coherence,
        "summary_for_reviewer": (
            str(payload.get("summary_for_reviewer") or "").strip() or None
        ),
        "findings": findings,
        "coverage_gaps": coverage_gaps,
    }


# ---------------------------------------------------------------------------
# Persistence + entry point
# ---------------------------------------------------------------------------


def _persist(
    *,
    client_id: str,
    vendor_id: str,
    period_id: str,
    contract_id: str | None,
    document_ids: list[str],
    provider_id: str | None,
    assessment: dict | None,
    error: str | None,
    latency_ms: int,
) -> None:
    db = SessionLocal()
    try:
        row = ExpedienteAssessment(
            client_id=client_id,
            vendor_id=vendor_id,
            period_id=period_id,
            contract_id=contract_id,
            provider_id=provider_id,
            prompt_version=PROMPT_VERSION,
            coherence=(assessment or {}).get("coherence") if assessment else None,
            findings=(assessment or {}).get("findings") if assessment else None,
            coverage_gaps=(
                (assessment or {}).get("coverage_gaps") if assessment else None
            ),
            document_ids=document_ids,
            summary_for_reviewer=(
                (assessment or {}).get("summary_for_reviewer") if assessment else None
            ),
            latency_ms=latency_ms,
            error=error,
        )
        db.add(row)
        db.commit()
    except Exception:  # noqa: BLE001 — persistence must never crash the worker
        logger.exception(
            "Failed persisting expediente assessment; client_id=%s vendor_id=%s "
            "period_id=%s",
            client_id,
            vendor_id,
            period_id,
        )
        db.rollback()
    finally:
        db.close()


def run_expediente_assessment(
    *,
    client_id: str,
    vendor_id: str,
    period_id: str,
    org_id: str | None = None,
    debounce_hours: int = 0,
) -> None:
    """Run the expediente situational pass for one (client, vendor, period).

    Safe to queue as a FastAPI ``BackgroundTask``. No-op when disabled, no
    provider is configured, the escalation cap is reached, a non-errored
    assessment already ran within ``debounce_hours``, or there are no
    current documents to assess. ``debounce_hours=0`` disables the
    debounce (e.g. a forced on-demand run). Never raises.
    """
    if not settings.DOCUMENT_ANALYSIS_EXPEDIENTE_ENABLED:
        return
    provider_name = (settings.DOCUMENT_ANALYSIS_PROVIDER or "disabled").strip().lower()
    if provider_name in {"disabled", ""}:
        return
    if not check_org_escalation_daily_quota(org_id):
        logger.info(
            "Expediente assessment skipped — escalation cap reached for "
            "org_id=%s (client=%s vendor=%s period=%s)",
            org_id,
            client_id,
            vendor_id,
            period_id,
        )
        return

    db = SessionLocal()
    try:
        if debounce_hours > 0 and _recently_assessed(
            db,
            client_id=client_id,
            vendor_id=vendor_id,
            period_id=period_id,
            within_hours=debounce_hours,
        ):
            return
        context, document_ids, contract_id = _load_context(
            db, client_id=client_id, vendor_id=vendor_id, period_id=period_id
        )
    except Exception:  # noqa: BLE001 — a load failure must not crash the worker
        logger.exception(
            "Failed loading expediente context; client=%s vendor=%s period=%s",
            client_id,
            vendor_id,
            period_id,
        )
        return
    finally:
        db.close()

    if context is None:
        return

    client = _build_client()
    if client is None:
        return

    model = (settings.DOCUMENT_ANALYSIS_MODEL or "claude-sonnet-4-6").strip()
    start = time.monotonic()
    assessment, _raw_meta, error = analyze_expediente(client, context)
    latency_ms = int((time.monotonic() - start) * 1000)

    _persist(
        client_id=client_id,
        vendor_id=vendor_id,
        period_id=period_id,
        contract_id=contract_id,
        document_ids=document_ids,
        provider_id=f"anthropic:{model}",
        assessment=assessment,
        error=error,
        latency_ms=latency_ms,
    )
