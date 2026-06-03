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
from app.services.reports.context import ReportScope, assemble_context
from app.services.reports.deterministic_layouts import (
    LAYOUTS,
    build_deterministic_blocks,
)

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


def _try_ai_version(
    db: Session,
    *,
    actor: ReportActor,
    report: Report,
    recommended_prompt: str,
    period: str | None,
    expected_blocks: int,
) -> ReportVersion | None:
    """Run the real AI pipeline to completion; return the saved version or
    ``None`` if it errored or under-delivered (so the caller falls back)."""
    from app.services.reports.executor import execute_plan
    from app.services.reports.llm import get_llm_client
    from app.services.reports.planner import plan_report

    scope = _scope_for(report, period)
    try:
        context = assemble_context(db, actor=actor, scope=scope)
        llm = get_llm_client()
        plan = plan_report(llm=llm, context=context, user_prompt=recommended_prompt)
        # execute_plan is a streaming generator that persists a version on
        # completion. We don't need the events — just drive it to the end.
        for _event, _data in execute_plan(
            db=db, actor=actor, report=report, plan=plan, context=context, llm=llm
        ):
            pass
        db.refresh(report)
        version = (
            db.get(ReportVersion, report.current_version_id)
            if report.current_version_id
            else None
        )
        n_blocks = len((version.content_json or {}).get("blocks", [])) if version else 0
        # Under-delivery guard: accept only if the planner emitted a
        # meaningful share of the template's blocks.
        threshold = max(2, int(expected_blocks * 0.6))
        if version is not None and n_blocks >= threshold:
            return version
        logger.warning(
            "[reports.generate] AI under-delivered (%d/%d blocks); falling back",
            n_blocks,
            expected_blocks,
        )
        return None
    except Exception:  # noqa: BLE001 — any AI failure must fall back, never 500
        logger.exception(
            "[reports.generate] AI path failed; falling back to deterministic"
        )
        return None


def generate_initial_version(
    db: Session,
    *,
    actor: ReportActor,
    report: Report,
    preset_id: str,
    recommended_prompt: str,
    period: str | None = None,
) -> ReportVersion:
    """Produce a populated v-N for ``report``. Hybrid: AI then deterministic.

    Always returns a ``ReportVersion`` — the deterministic registry is the
    guaranteed floor, so this never leaves the report empty."""
    expected_blocks = len(LAYOUTS.get(preset_id, [])) or 4

    if ai_is_configured():
        version = _try_ai_version(
            db,
            actor=actor,
            report=report,
            recommended_prompt=recommended_prompt,
            period=period,
            expected_blocks=expected_blocks,
        )
        if version is not None:
            return version

    # Deterministic fallback — the always-great floor.
    scope = _scope_for(report, period)
    blocks = build_deterministic_blocks(db, preset_id=preset_id, scope=scope)
    content_json = {
        "schema_version": 1,
        "blocks": blocks,
        "audience": report.audience,
        "global": {"preset_id": preset_id, "generated": "deterministic"},
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
