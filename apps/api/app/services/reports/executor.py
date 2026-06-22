"""Block executor — runs a ReportPlan end-to-end and emits SSE-shaped
events to the caller.

The pipeline matches docs/REPORTS_ARCHITECTURE.md §8:

    plan → for each block:
        block_start  →  fetch_data  →  block_data  →
        stream_ai_summary  →  ai_summary_delta*  →  block_complete
    → save ReportVersion
    → done

This module returns an iterator of (event_name, data_dict) tuples
so the API layer can wrap them in `text/event-stream` framing
without owning execution semantics.

Hard rule (matches §7.4 tenant isolation):
    The LLM never sees data outside what the data_fetcher returned.
    Every block's fetch is independently scoped through ReportScope.
    Audience sanitization is applied per block before the LLM call.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import asdict
from typing import Any

from sqlalchemy.orm import Session

from app.constants.reports import ReportAudience, ReportVersionOrigin
from app.models.entities import (
    Report,
    ReportVersion,
    new_id,
    utc_now,
)
from app.services.report_service import ReportActor
from app.services.reports.blocks.ai_summaries import (
    has_ai_summary,
    stream_ai_summary,
    upstream_summary_for_recommendation,
)
from app.services.reports.blocks.data_fetchers import fetch_for_block
from app.services.reports.context import AssembledContext
from app.services.reports.llm.base import LLMClient
from app.services.reports.planner import PlannedBlock, ReportPlan

logger = logging.getLogger(__name__)


# ─── Event shape ────────────────────────────────────────────────


Event = tuple[str, dict[str, Any]]


# ─── PII sanitizer applied per block render ────────────────────


_PII_FIELDS_PER_BLOCK: dict[str, tuple[str, ...]] = {
    # block_type -> tuple of dotted JSON paths carrying vendor identity
    # that must be hidden from audiences not entitled to see *named*
    # providers. See _REDACT_VENDOR_IDENTITY_AUDIENCES.
    "executive_summary": ("scope_label",),
    "vendor_risk_matrix": ("rows.*.vendor_name", "rows.*.vendor_rfc"),
    "compliance_overview": ("by_vendor.*.vendor_name", "by_vendor.*.vendor_rfc"),
}

# Audiences that must NOT receive named-provider identity in structured
# block data:
#   • vendor_facing   — a provider must never receive a portfolio of
#     *other* named vendors (cross-tenant exposure).
#   • external_signed — public share links stay conservative by default.
# Audiences that DO see names:
#   • internal_only   — Legal Shelf staff see everything.
#   • client_facing   — the client owns the providers in its own
#     portfolio; a risk matrix that cannot name them is useless. This
#     was over-redacted before (2026-06): every non-internal audience
#     was masked, so client reports rendered nameless, empty-looking
#     matrices. Clients now see their own providers; only vendor-facing
#     and public/signed surfaces stay masked.
_REDACT_VENDOR_IDENTITY_AUDIENCES: frozenset[ReportAudience] = frozenset(
    {ReportAudience.VENDOR_FACING, ReportAudience.EXTERNAL_SIGNED}
)


def _redact_for_audience(
    block_type: str, data: dict | None, audience: ReportAudience
) -> dict | None:
    """Hide vendor identity in a block's structured data for audiences
    that are not entitled to see named providers.

    internal_only + client_facing pass through (staff see everything; a
    client owns the providers in its own portfolio). vendor_facing +
    external_signed get each tagged path replaced with None (structure
    preserved so the renderer's schema validation doesn't fail).

    Conservative by design — anything the registry hasn't explicitly
    tagged stays untouched. Add new tags to _PII_FIELDS_PER_BLOCK
    alongside any new identity-bearing column.
    """
    if data is None or audience not in _REDACT_VENDOR_IDENTITY_AUDIENCES:
        return data
    paths = _PII_FIELDS_PER_BLOCK.get(block_type, ())
    if not paths:
        return data
    # Deep copy via json round-trip to avoid mutating the original.
    import json as _json

    redacted = _json.loads(_json.dumps(data))
    for path in paths:
        _apply_path_redaction(redacted, path)
    return redacted


def _apply_path_redaction(obj: Any, path: str) -> None:
    """Tiny path resolver: 'rows.*.vendor_name' walks each row and
    sets vendor_name=None. Only supports the two shapes we need
    today: '.' for dict descent and '.*' for list iteration."""
    parts = path.split(".")
    _redact_walk(obj, parts)


def _redact_walk(node: Any, parts: list[str]) -> None:
    if not parts:
        return
    head, *rest = parts
    if head == "*":
        if isinstance(node, list):
            for item in node:
                _redact_walk(item, rest)
        return
    if isinstance(node, dict):
        if not rest:
            if head in node:
                node[head] = None
            return
        _redact_walk(node.get(head), rest)


# ─── Executor ──────────────────────────────────────────────────


def execute_plan(
    *,
    db: Session,
    actor: ReportActor,
    report: Report,
    plan: ReportPlan,
    context: AssembledContext,
    llm: LLMClient,
) -> Iterator[Event]:
    """Drive the plan end-to-end, yielding SSE events.

    The caller (the API endpoint) wraps each event in a
    ``text/event-stream`` frame. This generator owns the order of
    work but not the I/O framing — that lives in the route.

    A new ``report_versions`` row is persisted when the stream
    completes. If the caller's HTTP connection drops mid-stream, the
    persisted version is still consistent because we accumulate the
    AI summary text in memory before committing.
    """
    audience = context.scope.audience

    # Defense-in-depth tenant guard (matches §7.4). Redundant with the
    # API-layer RBAC in report_service.get_report / list_reports — that
    # redundancy is the point. For vendor_facing scopes it asserts the
    # caller owns the workspace whose vendor the report targets; it is a
    # no-op for internal/client/external audiences and for internal staff,
    # so it never affects portfolio renders. Runs once before the per-block
    # loop because every block in a render shares the one scope.
    from app.services.reports.blocks._safety import assert_workspace_scope

    assert_workspace_scope(actor=actor, scope=context.scope)

    # PERF-1: build_client_context is the heaviest call in the pipeline and
    # several blocks need the same client's portfolio. Start a fresh
    # per-render memo so the first block that needs it computes it once and
    # the rest reuse it (and a Session reused across renders never serves a
    # stale portfolio). Imported lazily to keep client_context's heavy
    # import chain off executor module load.
    from app.services.wise.client_context import reset_client_context_memo

    reset_client_context_memo(db)

    # Pre-emit the plan as the first event so the client can render
    # block skeletons immediately.
    yield (
        "plan",
        {
            "plan": {
                "blocks": [
                    {"id": b.id, "type": b.type, "config": b.config} for b in plan.blocks
                ],
                "audience": audience.value,
                "scope_hint": plan.scope_hint,
                "rationale": plan.rationale,
            }
        },
    )

    rendered_blocks: list[dict[str, Any]] = []
    upstream_summaries: list[dict[str, Any]] = []

    for block in plan.blocks:
        yield ("block_start", {"block_id": block.id, "type": block.type})

        config = dict(block.config)

        try:
            data = fetch_for_block(
                block_type=block.type, config=config, scope=context.scope, db=db
            )
        except Exception as exc:
            logger.exception("[reports.executor] data fetch failed for %s", block.type)
            yield (
                "error",
                {
                    "block_id": block.id,
                    "code": "fetch_failed",
                    "message": str(exc),
                },
            )
            data = None

        # ai_recommendation's data dict carries the upstream summaries
        # for the LLM prompt — patch them in here, after fetch.
        if data is not None and block.type == "ai_recommendation":
            data["upstream_block_summaries"] = upstream_summaries

        # Apply audience-based PII redaction to the data the client
        # sees and (since the same dict is what the LLM gets) to
        # what the LLM sees.
        sanitized = _redact_for_audience(block.type, data, audience)

        yield ("block_data", {"block_id": block.id, "data": sanitized})

        ai_text = ""
        if has_ai_summary(block.type):
            try:
                for chunk in stream_ai_summary(
                    block_type=block.type,
                    config=block.config,
                    data=sanitized,
                    audience=audience,
                    llm=llm,
                ):
                    ai_text += chunk
                    yield (
                        "ai_summary_delta",
                        {"block_id": block.id, "delta": chunk},
                    )
            except Exception as exc:
                logger.exception(
                    "[reports.executor] ai summary failed for %s", block.type
                )
                yield (
                    "error",
                    {
                        "block_id": block.id,
                        "code": "ai_summary_failed",
                        "message": str(exc),
                    },
                )

        rendered_block = {
            "id": block.id,
            "type": block.type,
            "config": block.config,
            "data": sanitized,
            "ai_summary": (
                {
                    "text": ai_text,
                    "model": llm.content_model,
                    "prompt_hash": context.snapshot_hash,
                    "generated_at": utc_now().isoformat(),
                    "source_snapshot_id": context.snapshot_id,
                }
                if ai_text
                else None
            ),
            "layout": {"width": "full"},
        }
        rendered_blocks.append(rendered_block)
        upstream_summaries.append(
            upstream_summary_for_recommendation(
                block_id=block.id, block_type=block.type, data=sanitized
            )
        )

        yield ("block_complete", {"block_id": block.id})

    # ── Persist a new ReportVersion ────────────────────────────
    version = _save_version(
        db=db,
        actor=actor,
        report=report,
        plan=plan,
        rendered_blocks=rendered_blocks,
        context=context,
        llm=llm,
    )

    yield (
        "version_saved",
        {
            "version_id": version.id,
            "version_number": version.version_number,
        },
    )

    yield (
        "done",
        {
            "total_blocks": len(rendered_blocks),
            "model": plan.model,
            "snapshot_id": context.snapshot_id,
        },
    )


def _save_version(
    *,
    db: Session,
    actor: ReportActor,
    report: Report,
    plan: ReportPlan,
    rendered_blocks: list[dict[str, Any]],
    context: AssembledContext,
    llm: LLMClient,
) -> ReportVersion:
    """Insert a new report_versions row and bump current_version_id.

    Mirrors report_service.create_version's invariants (atomic next
    version_number, current_version_id advance) without the API-
    layer permission re-checks — those already ran when the report
    was opened.
    """
    from sqlalchemy import func as sa_func
    from sqlalchemy import select as sa_select

    next_n = (
        db.scalar(
            sa_select(sa_func.max(ReportVersion.version_number)).where(
                ReportVersion.report_id == report.id
            )
        )
        or 0
    ) + 1

    content_json: dict[str, Any] = {
        "schema_version": 1,
        "blocks": rendered_blocks,
        "global": {
            "audience": context.scope.audience.value,
            "period": context.scope.period,
        },
    }

    version = ReportVersion(
        id=new_id(),
        report_id=report.id,
        version_number=next_n,
        parent_version_id=report.current_version_id,
        label=None,
        content_json=content_json,
        plan_json={
            "blocks": [asdict(b) for b in plan.blocks],
            "rationale": plan.rationale,
            "scope_hint": plan.scope_hint,
        },
        generated_by=ReportVersionOrigin.AI.value,
        source_snapshot_id=context.snapshot_id,
        llm_metadata={
            "backend": llm.name,
            "planner_model": plan.model,
            "content_model": llm.content_model,
            "usage": plan.usage,
            "stop_reason": plan.stop_reason,
        },
        created_by_user_id=actor.user_id,
        created_at=utc_now(),
    )

    now = utc_now()
    report.current_version_id = version.id
    report.updated_at = now

    db.add(version)
    db.commit()
    db.refresh(version)
    return version


# ─── Public types re-exports ───────────────────────────────────


__all__ = ["execute_plan", "Event", "PlannedBlock"]
