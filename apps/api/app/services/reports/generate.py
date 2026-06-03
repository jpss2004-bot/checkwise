"""Hybrid one-shot report generation: AI with deterministic fallback.

Powers the "pick a template → it generates → read-only report" flow. Given a
report row that was just created from a preset, produce a fully-populated
``ReportVersion`` in a single synchronous call:

  1. If real AI is configured (``ANTHROPIC_API_KEY`` set, backend not mock),
     run the existing planner + executor against the preset's
     ``recommended_prompt``. The executor persists a version as it streams; we
     consume it to completion and accept the result only if it didn't
     under-deliver (the planner is known to sometimes stop after one or two
     tool calls).
  2. Otherwise — no key, AI error, or under-delivery — fall back to the
     deterministic layout registry (``build_deterministic_blocks``), which is
     instant, key-free, and always fully populated.

Either way the caller gets back the current ``ReportVersion`` to render. No
streaming, no editing — this is the engine behind the non-customizable flow.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.constants.reports import ReportAudience, ReportVersionOrigin
from app.core.config import settings
from app.models import Report, ReportVersion
from app.services.report_service import ReportActor, create_version
from app.services.reports.context import ReportScope
from app.services.reports.deterministic_layouts import build_deterministic_blocks

logger = logging.getLogger(__name__)


def ai_is_configured() -> bool:
    """True when real Anthropic generation is available (not the mock)."""
    backend = (settings.CHECKWISE_LLM_BACKEND or "").strip().lower()
    if backend == "mock":
        return False
    return bool((settings.ANTHROPIC_API_KEY or "").strip())


def _scope_for(report: Report, period: str | None) -> ReportScope:
    return ReportScope(
        organization_id=report.organization_id,
        audience=ReportAudience(report.audience),
        client_id=report.client_id,
        vendor_id=report.vendor_id,
        period=period,
    )


def generate_initial_version(
    db: Session,
    *,
    actor: ReportActor,
    report: Report,
    preset_id: str,
    recommended_prompt: str,
    period: str | None = None,
) -> ReportVersion:
    """Produce a populated v-N for ``report``.

    The curated deterministic insight-first layout is ALWAYS the structure —
    that's the guaranteed-great floor and the thing the templates promise. When
    AI is configured we then ENRICH the prose (verdict + findings wording) in
    place, keeping every number and name. We no longer let an LLM re-pick the
    blocks: that would drop the insight layer it doesn't know about, and the
    product's value is the curated template, not a free-form composition."""
    scope = _scope_for(report, period)
    blocks = build_deterministic_blocks(db, preset_id=preset_id, scope=scope)

    generated = "deterministic"
    if ai_is_configured():
        try:
            from app.services.reports.enrich import enrich_report_prose

            blocks = enrich_report_prose(
                db, scope=scope, blocks=blocks, audience=report.audience
            )
            generated = "deterministic+ai"
        except Exception:  # noqa: BLE001 — enrichment must never break generation
            logger.exception("[reports.generate] prose enrichment failed; using deterministic")

    content_json = {
        "schema_version": 1,
        "blocks": blocks,
        "audience": report.audience,
        "global": {"preset_id": preset_id, "generated": generated},
    }
    return create_version(
        db,
        actor=actor,
        report_id=report.id,
        content_json=content_json,
        label="Generado",
        generated_by=ReportVersionOrigin.AI,
        plan_json={
            "blocks": [
                {"id": b["id"], "type": b["type"], "config": b.get("config", {})}
                for b in blocks
            ],
            "rationale": f"Plantilla determinista ({preset_id}).",
            "scope_hint": preset_id,
        },
    )


__all__ = ["generate_initial_version", "ai_is_configured"]
