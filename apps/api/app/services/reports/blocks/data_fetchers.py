"""Per-block data fetchers.

Each function reads tenant-scoped data and returns the block's
``data`` payload. The LLM never sees the SQL or the raw rows — it
sees the dict each fetcher returns, AFTER PII sanitization for non-
internal audiences.

Hard rule (matches docs/REPORTS_ARCHITECTURE.md §3 + §7.4):

- Every query joins on scope.organization_id (or one of its
  legitimate descendants: client_id, vendor_id).
- The dispatcher refuses to fetch unknown block types.

Audience sanitization happens in the executor, not in individual
fetchers, so the fetchers stay focused on data shape.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants.statuses import DocumentStatus
from app.models.entities import (
    Institution,
    Submission,
    Vendor,
)
from app.services.dashboard_compute import build_suggested_actions_for_vendor
from app.services.reports.blocks.attention_list import fetch_attention_list
from app.services.reports.blocks.compliance_state import fetch_compliance_state
from app.services.reports.blocks.prioritized_actions import (
    fetch_prioritized_actions,
)
from app.services.reports.blocks.upcoming_deadlines import fetch_upcoming_deadlines
from app.services.reports.context import ReportScope

# ─── Fetchers ──────────────────────────────────────────────────


def _now_iso() -> str:
    """ISO8601 UTC stamp with explicit Z suffix.

    Centralised so every fetcher's freshness stamp has the same shape;
    the per-block ``FreshnessLabel`` renderer reads this verbatim.
    """
    return datetime.utcnow().isoformat() + "Z"


def _action_links_for_vendor(
    db: Session, *, vendor_id: str | None, limit: int
) -> list[dict]:
    if vendor_id is None:
        return []
    payload = build_suggested_actions_for_vendor(db, vendor_id=vendor_id)
    links: list[dict] = []
    for item in payload.get("items", [])[:limit]:
        links.append(
            {
                "id": item.get("id"),
                "type": item.get("type"),
                "priority": item.get("priority"),
                "title": item.get("title"),
                "href": item.get("href"),
                "requirement_code": item.get("requirement_code"),
                "period_key": item.get("period_key"),
            }
        )
    return links


def fetch_executive_summary(
    config: dict, scope: ReportScope, db: Session
) -> dict:
    """Headline metrics + labels + a DETERMINISTIC factual recap for the
    cover block.

    The ``summary`` string is templated from the computed metrics — no
    LLM — so the report's factual headline can never be hallucinated.
    The block still carries an optional AI ``ai_summary`` (generated
    elsewhere), but the frontend renders that as a clearly-labelled,
    subordinate "lectura del equipo" caption *below* this deterministic
    recap, not as the headline.
    """
    completion_pct, vendors_at_risk = _exec_compliance(db, scope)
    submissions_in_review = _count_status(db, scope, DocumentStatus.PENDIENTE_REVISION)
    scope_label = _scope_label(db, scope)
    return {
        "period_label": scope.period,
        "scope_label": scope_label,
        "summary": _exec_summary_sentence(
            scope=scope,
            completion_pct=completion_pct,
            vendors_at_risk=vendors_at_risk,
            submissions_in_review=submissions_in_review,
        ),
        "headline_metrics": {
            "completion_pct": completion_pct,
            "vendors_at_risk": vendors_at_risk,
            "submissions_in_review": submissions_in_review,
            "next_critical_deadline": None,
        },
        "fetched_at": _now_iso(),
    }


def _exec_compliance(db: Session, scope: ReportScope) -> tuple[int, int]:
    """Completion% + vendors-at-risk for the executive cover, drawn from
    the SAME slot-based source as compliance_overview / compliance_radar
    (build_client_context / build_compliance_state_for_vendor) so every
    block in a report agrees. Falls back to the submission-ratio
    _completion_and_risk only when there's no client/vendor scope.

    (kpi_strip still uses the submission-ratio metric; it isn't shown
    alongside the radar in the cliente template, so the two never
    contradict on the same canvas.)
    """
    if scope.vendor_id:
        from app.services.dashboard_compute import build_compliance_state_for_vendor

        payload = build_compliance_state_for_vendor(db, vendor_id=scope.vendor_id)
        return int(payload["semaphore"]["compliance_pct"]), 0
    if scope.client_id:
        from app.models.entities import Client
        from app.services.wise.client_context import build_client_context

        client = db.get(Client, scope.client_id)
        if client is not None:
            ctx = build_client_context(db, client)
            return int(ctx.overall_compliance_pct), int(ctx.red_count)
    return _completion_and_risk(db, scope)


def _exec_summary_sentence(
    *,
    scope: ReportScope,
    completion_pct: int | float,
    vendors_at_risk: int,
    submissions_in_review: int,
) -> str:
    """Build the deterministic factual recap shown as the cover's lead
    paragraph. Pure string templating over already-computed values.

    Deliberately NAME-FREE — uses a scope-kind subject ("el portafolio"
    / "tu expediente") rather than the client/vendor label, so the
    recap is safe for every audience and never needs redaction (the
    label itself is masked separately for vendor_facing / external)."""
    if scope.vendor_id:
        subject = "tu expediente"
    elif scope.client_id:
        subject = "el portafolio"
    else:
        subject = "el alcance del reporte"
    lead = (
        f"En {scope.period}, " if scope.period else "A la fecha, "
    ) + f"{subject} registra {round(completion_pct)}% de cumplimiento"
    clauses: list[str] = []
    # 'proveedores en riesgo' only makes sense at the portfolio level.
    if vendors_at_risk and not scope.vendor_id:
        noun = "proveedor requiere" if vendors_at_risk == 1 else "proveedores requieren"
        clauses.append(f"{vendors_at_risk} {noun} atención")
    if submissions_in_review:
        noun = "documento" if submissions_in_review == 1 else "documentos"
        clauses.append(f"{submissions_in_review} {noun} en revisión")
    if clauses:
        lead += "; " + " y ".join(clauses)
    return lead + "."


def fetch_kpi_strip(config: dict, scope: ReportScope, db: Session) -> dict:
    """Resolve each requested metric_key to a value (no LLM)."""
    metrics = config.get("metrics") or []
    resolved: list[dict[str, Any]] = []
    for m in metrics:
        key = m.get("metric_key")
        value = _resolve_metric(db, scope, key)
        resolved.append(
            {"metric_key": key, "value": value, "trend_pct_vs_prior": None}
        )
    return {"resolved": resolved, "fetched_at": _now_iso()}


# SlotState → the matrix's frontend DocumentStateCode.
_SLOT_TO_MATRIX_STATE: dict[str, str] = {
    "missing": "pending",
    "uploaded": "uploaded",
    "in_review": "in_review",
    "approved": "approved",
    "rejected": "rejected",
    "needs_correction": "needs_review",
    "possible_mismatch": "needs_review",
    "exception": "approved",
    "expired": "expired",
    "not_applicable": "empty",
}

# Worst-first severity so each institution cell reflects its most urgent
# slot (lower rank = more urgent).
_SLOT_SEVERITY: dict[str, int] = {
    "rejected": 0,
    "expired": 1,
    "needs_correction": 2,
    "possible_mismatch": 3,
    "missing": 4,
    "in_review": 5,
    "uploaded": 6,
    "approved": 7,
    "exception": 8,
    "not_applicable": 9,
}


def _institution_states_from_slots(
    db: Session, vendor_id: str, year: int
) -> dict[str, str]:
    """Worst SlotState per institution for one vendor, keyed by lowercase
    institution code. Uses the canonical evidence-slot views (the SAME
    source as compliance_state / compliance_by_institution) so the matrix
    cells populate and stay consistent — the previous
    `_latest_submission_for_institution` join returned nothing on tenants
    whose obligations live in slots, leaving every cell empty ("—")."""
    from app.services.dashboard_compute import resolve_workspace_for_vendor
    from app.services.evidence_slots import (
        build_workspace_calendar_slots,
        build_workspace_onboarding_slots,
    )

    workspace = resolve_workspace_for_vendor(db, vendor_id)
    if workspace is None:
        return {}
    views = build_workspace_onboarding_slots(
        db, workspace
    ) + build_workspace_calendar_slots(db, workspace, year)
    worst: dict[str, str] = {}
    for view in views:
        inst = (view.institution or "").strip().lower()
        if not inst:
            continue
        state = str(view.state)
        if inst not in worst or _SLOT_SEVERITY.get(state, 99) < _SLOT_SEVERITY.get(
            worst[inst], 99
        ):
            worst[inst] = state
    return worst


def fetch_vendor_risk_matrix(
    config: dict, scope: ReportScope, db: Session
) -> dict:
    """Cross-vendor portfolio view. Filters per config['filter']."""
    from datetime import date as _date
    flt = config.get("filter") or {}
    missing_institution = flt.get("missing_institution")
    min_risk = flt.get("min_risk_score")
    columns = config.get("columns") or ["sat", "imss", "infonavit", "stps_repse", "risk_score"]
    sort = config.get("sort", "risk_desc")
    max_rows = int(config.get("max_rows", 25))

    # Pull every vendor in scope.
    vendors = _vendors_in_scope(db, scope)

    year = _date.today().year
    rows: list[dict[str, Any]] = []
    for v in vendors:
        cells: dict[str, dict[str, Any]] = {}
        # Worst slot state per institution for this vendor (slot-based,
        # so cells populate consistently with the rest of the report).
        inst_states = _institution_states_from_slots(db, v.id, year)
        for col in columns:
            if col in ("risk_score", "last_event"):
                continue
            state = inst_states.get(col)
            if state is None:
                cells[col] = {"state": "empty", "age_days": 0, "period": scope.period or ""}
            else:
                cells[col] = {
                    "state": _SLOT_TO_MATRIX_STATE.get(state, "pending"),
                    "age_days": 0,
                    "period": scope.period or "",
                }
        # Filter on missing_institution if requested.
        if missing_institution and cells.get(missing_institution, {}).get("state") not in (
            "empty",
            "rejected",
            "expired",
            "needs_review",
        ):
            continue
        risk = _risk_score_for(cells, missing_institution)
        if min_risk is not None and risk < int(min_risk):
            continue
        rows.append(
            {
                "vendor_id": v.id,
                "vendor_name": v.name,
                "vendor_rfc": v.rfc or "",
                "risk_score": risk,
                "cells": cells,
                "last_event_at": "",
            }
        )

    # Sort + cap.
    if sort == "risk_desc":
        rows.sort(key=lambda r: r["risk_score"], reverse=True)
    elif sort == "risk_asc":
        rows.sort(key=lambda r: r["risk_score"])
    else:
        rows.sort(key=lambda r: r["vendor_name"])
    rows = rows[:max_rows]

    totals: dict[str, dict[str, int]] = {}
    return {"rows": rows, "totals": totals, "fetched_at": _now_iso()}


def _is_portfolio_audience(scope: ReportScope) -> bool:
    """Portfolio blocks (radar, overview) roll up *every* vendor under a
    client. They may only be served to the client's own surface and to
    internal staff — never to a vendor_facing / external_signed report,
    whose scope still carries the workspace's client_id and would
    otherwise leak sibling providers' counts and identities to a single
    provider.
    """
    from app.constants.reports import ReportAudience

    return scope.audience in (
        ReportAudience.CLIENT_FACING,
        ReportAudience.INTERNAL_ONLY,
    )


def fetch_compliance_radar(
    config: dict, scope: ReportScope, db: Session
) -> dict | None:
    """Portfolio-shaped snapshot for the cliente Resumen ejecutivo hero.

    Reuses the cliente Wise portfolio analyzer (``build_client_context``)
    so the donut + per-vendor cards stay numerically identical to what
    the Wise dock surfaces. Returns ``None`` if the scope isn't
    client-shaped — the block is meant for the cliente surface; a
    provider-side preview just doesn't render this block.

    Output shape (consumed by ``compliance-radar.tsx``):

        {
          "client_name": "<str>",
          "vendor_count": <int>,
          "semaphore_counts": {"green": <int>, "yellow": <int>, "red": <int>},
          "overall_compliance_pct": <int>,
          "top_vendors": [
            {
              "vendor_id": "...", "vendor_name": "...",
              "vendor_rfc": "..." | null,
              "semaphore_level": "green" | "yellow" | "red",
              "compliance_pct": <int>,
              "pending_reviews_count": <int>,
              "missing_required_count": <int>,
            },
            ...
          ],
          "history_6mo": [],
          "fetched_at": "<iso>"
        }
    """
    if not _is_portfolio_audience(scope):
        return None
    if scope.client_id is None:
        return None
    from app.models.entities import Client
    from app.services.wise.client_context import build_client_context

    client_row = db.get(Client, scope.client_id)
    if client_row is None:  # pragma: no cover — defensive
        return None

    portfolio = build_client_context(db, client_row)
    top_n = int(config.get("top_n_vendors", 8))

    ordered = sorted(
        portfolio.vendors,
        key=lambda v: (
            {"red": 0, "yellow": 1, "green": 2}.get(v.semaphore_level, 3),
            v.vendor_name.casefold(),
        ),
    )[:top_n]

    history = _compute_compliance_history_6mo(db, scope.client_id)

    return {
        "client_name": portfolio.client_name,
        "vendor_count": portfolio.vendor_count,
        "semaphore_counts": {
            "green": portfolio.green_count,
            "yellow": portfolio.yellow_count,
            "red": portfolio.red_count,
        },
        "overall_compliance_pct": portfolio.overall_compliance_pct,
        "top_vendors": [
            {
                "vendor_id": v.vendor_id,
                "vendor_name": v.vendor_name,
                "vendor_rfc": v.vendor_rfc,
                "semaphore_level": v.semaphore_level,
                "compliance_pct": v.compliance_pct,
                "pending_reviews_count": v.pending_reviews_count,
                "missing_required_count": v.missing_required_count,
            }
            for v in ordered
        ],
        "history_6mo": history,
        "fetched_at": _now_iso(),
    }


def _compute_compliance_history_6mo(
    db: Session, client_id: str
) -> list[dict[str, Any]]:
    """Approximate 6-month compliance trend for the cliente sparkline.

    M5 (2026-06-02) — first pass. A proper "compliance %" historical
    series would need a snapshot table backed by a cron (we don't
    know "total expected obligations" at past timestamps without
    replaying the evidence-slot service against month-end state).
    Instead we ship an approval-rate proxy: for each of the last six
    calendar months, the percentage of submissions created during
    that month that ended (or are still) in the ``aprobado`` status.

    The frontend labels the sparkline "Aprobación mensual" to keep the
    semantic distinction honest — a flat 100% just means every
    submission landed clean, not that the portfolio is 100% complete.

    Returns six points ordered oldest → newest, suitable for the
    radar's existing ``ComplianceSparkline`` component. When the
    portfolio has zero submissions in a month, the point is omitted
    rather than emitted as 0% so the line doesn't dive to the floor
    on quiet months.
    """
    today = date.today()
    points: list[dict[str, Any]] = []

    # Walk back 6 months including the current one.
    for offset in range(5, -1, -1):
        # Naive month arithmetic — works for the 6-month window we
        # care about without dragging in dateutil.relativedelta.
        year = today.year
        month = today.month - offset
        while month <= 0:
            month += 12
            year -= 1
        # Build month bounds [start, next_start).
        start = date(year, month, 1)
        if month == 12:
            next_start = date(year + 1, 1, 1)
        else:
            next_start = date(year, month + 1, 1)

        total = db.scalar(
            select(func.count(Submission.id))
            .join(Vendor, Vendor.id == Submission.vendor_id)
            .where(
                Vendor.client_id == client_id,
                Submission.created_at >= start,
                Submission.created_at < next_start,
            )
        ) or 0
        approved = db.scalar(
            select(func.count(Submission.id))
            .join(Vendor, Vendor.id == Submission.vendor_id)
            .where(
                Vendor.client_id == client_id,
                Submission.status == DocumentStatus.APROBADO,
                Submission.created_at >= start,
                Submission.created_at < next_start,
            )
        ) or 0
        if total == 0:
            # Skip silent months — keeps the line shape honest.
            continue
        pct = int(round((approved / total) * 100))
        points.append(
            {
                "month_key": f"{year:04d}-{month:02d}",
                "compliance_pct": pct,
            }
        )
    return points


def fetch_text_or_divider(config: dict, scope: ReportScope, db: Session) -> dict | None:
    """text + divider blocks carry no server-side data."""
    return None


def fetch_ai_recommendation(
    config: dict, scope: ReportScope, db: Session
) -> dict:
    """Provide the executor's upstream summary list — used as the
    grounding context for the LLM's recommendation text. The actual
    recommendation prose is generated by the AI summary generator;
    this function just collects the data the LLM needs."""
    return {
        "upstream_block_summaries": [],  # filled in by executor pre-pass
        "audience_tone": config.get("audience_tone", "internal"),
        "priority_count": int(config.get("priority_count", 3)),
        "action_links": _action_links_for_vendor(
            db,
            vendor_id=scope.vendor_id,
            limit=int(config.get("priority_count", 3)),
        ),
    }


def fetch_compliance_overview(
    config: dict, scope: ReportScope, db: Session
) -> dict | None:
    """Deterministic at-a-glance band for the cliente report.

    Inspired by real GRC dashboards (a hero KPI row + a per-provider
    bar): every figure here is computed from the live expediente, so the
    block carries NO AI summary and nothing can be hallucinated.

    Reuses ``build_client_context`` (same numbers the Wise dock and the
    radar surface) for the portfolio rollup, and the canonical
    ``Submission.status`` counts for the critical / in-review tallies.

    Returns ``None`` for non-client scopes — this is a portfolio block.

    Output shape (consumed by ``compliance-overview.tsx``):

        {
          "client_name": "<str>",
          "overall_compliance_pct": <int>,
          "vendors_total": <int>,
          "vendors_semaphore": {"green": <int>, "yellow": <int>, "red": <int>},
          "docs_critical": <int>,
          "docs_critical_breakdown": {
            "rechazados": <int>, "vencidos": <int>,
            "inconsistencias": <int>, "aclaracion": <int>
          },
          "docs_in_review": <int>,
          "by_vendor": [
            {"vendor_id","vendor_name","vendor_rfc","semaphore_level",
             "compliance_pct","missing_required_count","pending_reviews_count"},
            ...  # worst-first
          ],
          "fetched_at": "<iso>"
        }
    """
    if not _is_portfolio_audience(scope):
        return None
    if scope.client_id is None:
        return None
    from app.models.entities import Client
    from app.services.wise.client_context import build_client_context

    client_row = db.get(Client, scope.client_id)
    if client_row is None:  # pragma: no cover — defensive
        return None

    portfolio = build_client_context(db, client_row)
    top_n = int(config.get("top_n_vendors", 12))

    # Worst-first: red → yellow → green, then lowest compliance first so
    # the providers that need attention sit at the top of the bar chart.
    ordered = sorted(
        portfolio.vendors,
        key=lambda v: (
            {"red": 0, "yellow": 1, "green": 2}.get(v.semaphore_level, 3),
            v.compliance_pct,
            v.vendor_name.casefold(),
        ),
    )[:top_n]

    critical_breakdown = {
        "rechazados": _count_status(db, scope, DocumentStatus.RECHAZADO),
        "vencidos": _count_status(db, scope, DocumentStatus.VENCIDO),
        "inconsistencias": _count_status(db, scope, DocumentStatus.POSIBLE_MISMATCH),
        "aclaracion": _count_status(db, scope, DocumentStatus.REQUIERE_ACLARACION),
    }
    docs_critical = sum(critical_breakdown.values())
    docs_in_review = _count_status(
        db, scope, DocumentStatus.PENDIENTE_REVISION
    ) + _count_status(db, scope, DocumentStatus.PREVALIDADO)

    return {
        "client_name": portfolio.client_name,
        "overall_compliance_pct": portfolio.overall_compliance_pct,
        "vendors_total": portfolio.vendor_count,
        "vendors_semaphore": {
            "green": portfolio.green_count,
            "yellow": portfolio.yellow_count,
            "red": portfolio.red_count,
        },
        "docs_critical": docs_critical,
        "docs_critical_breakdown": critical_breakdown,
        "docs_in_review": docs_in_review,
        "by_vendor": [
            {
                "vendor_id": v.vendor_id,
                "vendor_name": v.vendor_name,
                "vendor_rfc": v.vendor_rfc,
                "semaphore_level": v.semaphore_level,
                "compliance_pct": v.compliance_pct,
                "missing_required_count": v.missing_required_count,
                "pending_reviews_count": v.pending_reviews_count,
            }
            for v in ordered
        ],
        "fetched_at": _now_iso(),
    }


# Evidence-slot state → semáforo bucket for the by-institution rollup.
# We aggregate the SAME canonical SlotView the compliance_state /
# attention_list blocks use (not a raw Submission join), so the bars are
# populated and numerically consistent with what the rest of the report
# shows. NOT_APPLICABLE slots carry no obligation and are dropped.
#   al_dia    — satisfied (approved / legal exception)
#   en_proceso— pending action: not yet submitted, uploaded, or in review
#   en_riesgo — rejected / expired / needs correction / mismatch (action!)
_SLOT_INSTITUTION_BUCKET: dict[str, str] = {
    "approved": "al_dia",
    "exception": "al_dia",
    "missing": "en_proceso",
    "uploaded": "en_proceso",
    "in_review": "en_proceso",
    "rejected": "en_riesgo",
    "needs_correction": "en_riesgo",
    "possible_mismatch": "en_riesgo",
    "expired": "en_riesgo",
    # not_applicable → intentionally absent (no obligation to count).
}

# Preferred display order; institutions not listed sort alphabetically
# after these. Matched case-insensitively against SlotView.institution.
_INSTITUTION_PREF = ("SAT", "IMSS", "INFONAVIT", "STPS")

# SlotView.institution arrives as a lowercase code; pretty-print the
# known ones, title-case the rest.
_INSTITUTION_LABELS = {
    "sat": "SAT",
    "imss": "IMSS",
    "infonavit": "INFONAVIT",
    "stps_repse": "STPS / REPSE",
    "interno_cliente": "Interno",
    "general": "General",
}


def fetch_compliance_by_institution(
    config: dict, scope: ReportScope, db: Session
) -> dict | None:
    """Deterministic 'cumplimiento por institución' rollup — the
    "by Area of Compliance" view real GRC reports lead with.

    Scope-adaptive, so the same block serves every portal:
      • vendor scope (provider report) → the provider's OWN slots.
      • client scope (cliente / internal report) → every vendor under
        the client, merged.
    Scoped by vendor_id / client_id, so there is no cross-tenant leak
    and no vendor identity to redact. Returns ``None`` when the scope
    resolves to neither.

    Aggregates evidence-slot views (the canonical obligation state, same
    source as compliance_state) by institution into three semáforo
    buckets — fully deterministic, no AI.

    Output shape (consumed by ``compliance-by-institution.tsx``):

        {
          "scope_kind": "vendor" | "client",
          "institutions": [
            {"code","label","al_dia","en_proceso","en_riesgo","total"},
            ...
          ],
          "fetched_at": "<iso>"
        }
    """
    from datetime import date as _date

    from app.services.dashboard_compute import resolve_workspace_for_vendor
    from app.services.evidence_slots import (
        build_workspace_calendar_slots,
        build_workspace_onboarding_slots,
    )

    if scope.vendor_id:
        scope_kind = "vendor"
        vendor_ids = [scope.vendor_id]
    elif scope.client_id:
        scope_kind = "client"
        vendor_ids = [
            v.id
            for v in db.scalars(
                select(Vendor).where(Vendor.client_id == scope.client_id)
            ).all()
        ]
    else:
        return None

    year = _date.today().year
    # label -> {al_dia, en_proceso, en_riesgo}
    tallies: dict[str, dict[str, int]] = {}
    for vid in vendor_ids:
        workspace = resolve_workspace_for_vendor(db, vid)
        if workspace is None:
            continue
        views = build_workspace_onboarding_slots(
            db, workspace
        ) + build_workspace_calendar_slots(db, workspace, year)
        for view in views:
            bucket = _SLOT_INSTITUTION_BUCKET.get(str(view.state))
            if bucket is None:  # not_applicable / unknown — no obligation
                continue
            key = (view.institution or "general").strip().lower() or "general"
            slot = tallies.setdefault(
                key, {"al_dia": 0, "en_proceso": 0, "en_riesgo": 0}
            )
            slot[bucket] += 1

    def _order_key(label: str) -> tuple[int, str]:
        upper = label.upper()
        for i, pref in enumerate(_INSTITUTION_PREF):
            if pref in upper:
                return (i, label)
        return (len(_INSTITUTION_PREF), label)

    institutions = []
    for key in sorted(tallies, key=_order_key):
        slot = tallies[key]
        total = slot["al_dia"] + slot["en_proceso"] + slot["en_riesgo"]
        institutions.append(
            {
                "code": key,
                "label": _INSTITUTION_LABELS.get(key, key.replace("_", " ").title()),
                "al_dia": slot["al_dia"],
                "en_proceso": slot["en_proceso"],
                "en_riesgo": slot["en_riesgo"],
                "total": total,
            }
        )

    return {
        "scope_kind": scope_kind,
        "institutions": institutions,
        "fetched_at": _now_iso(),
    }


# ─── Insight blocks (the "so what" layer) ─────────────────────


def fetch_report_verdict(config: dict, scope: ReportScope, db: Session) -> dict | None:
    """The synthesized verdict that opens an insight-first report. Scope-
    adaptive: a single provider's verdict when vendor-scoped, else portfolio."""
    from app.services.reports.insights import compute_insight

    insight = compute_insight(db, scope)
    if insight is None:
        return None
    return {"verdict": insight["verdict"], "fetched_at": _now_iso()}


def fetch_key_findings(config: dict, scope: ReportScope, db: Session) -> dict | None:
    """The 2-3 findings that matter — the 'lo más importante' callouts."""
    from app.services.reports.insights import compute_insight

    insight = compute_insight(db, scope)
    if insight is None:
        return None
    return {"findings": insight["findings"], "fetched_at": _now_iso()}


# ─── Dispatcher ────────────────────────────────────────────────


_FETCHERS: dict[str, Callable[[dict, ReportScope, Session], dict | None]] = {
    "report_verdict": fetch_report_verdict,
    "key_findings": fetch_key_findings,
    "compliance_overview": fetch_compliance_overview,
    "compliance_by_institution": fetch_compliance_by_institution,
    "executive_summary": fetch_executive_summary,
    "kpi_strip": fetch_kpi_strip,
    "vendor_risk_matrix": fetch_vendor_risk_matrix,
    "text": fetch_text_or_divider,
    "divider": fetch_text_or_divider,
    "ai_recommendation": fetch_ai_recommendation,
    "compliance_state": fetch_compliance_state,
    "compliance_radar": fetch_compliance_radar,
    "attention_list": fetch_attention_list,
    "upcoming_deadlines": fetch_upcoming_deadlines,
    "prioritized_actions": fetch_prioritized_actions,
}


def fetch_for_block(
    *, block_type: str, config: dict, scope: ReportScope, db: Session
) -> dict | None:
    """Public entry point. Returns None for blocks that have no data."""
    fetcher = _FETCHERS.get(block_type)
    if fetcher is None:
        return None
    return fetcher(config, scope, db)


# ─── Internals ─────────────────────────────────────────────────


def _vendors_in_scope(db: Session, scope: ReportScope) -> list[Vendor]:
    stmt = select(Vendor)
    if scope.vendor_id:
        stmt = stmt.where(Vendor.id == scope.vendor_id)
    elif scope.client_id:
        stmt = stmt.where(Vendor.client_id == scope.client_id)
    else:
        # Organization-scoped: pull every vendor whose client belongs
        # to the org's bound client_id. We don't yet have org→client
        # linkage in 3.3a's schema, so for now: when scope is
        # internal_only with no client/vendor, return [] rather than
        # leaking everything. Internal staff who want everything can
        # specify client/vendor explicitly via report metadata.
        return []
    return list(db.scalars(stmt))


def _latest_submission_for_institution(
    db: Session, vendor_id: str, institution_code: str, period: str | None
) -> Submission | None:
    stmt = (
        select(Submission)
        .join(Institution, Submission.institution_id == Institution.id)
        .where(Submission.vendor_id == vendor_id)
        .where(Institution.code == institution_code)
        .order_by(Submission.created_at.desc())
        .limit(1)
    )
    if period:
        stmt = stmt.where(Submission.period_key == period)
    return db.scalar(stmt)


def _doc_state_for(status: str) -> str:
    """Map backend status enum to the document-state code the
    vendor_risk_matrix block expects (frontend types)."""
    return {
        DocumentStatus.PENDIENTE.value: "pending",
        DocumentStatus.RECIBIDO.value: "uploaded",
        DocumentStatus.PENDIENTE_REVISION.value: "in_review",
        DocumentStatus.PREVALIDADO.value: "in_review",
        DocumentStatus.POSIBLE_MISMATCH.value: "needs_review",
        DocumentStatus.APROBADO.value: "approved",
        DocumentStatus.RECHAZADO.value: "rejected",
        DocumentStatus.VENCIDO.value: "expired",
        DocumentStatus.NO_APLICA.value: "approved",
        DocumentStatus.REQUIERE_ACLARACION.value: "needs_review",
        DocumentStatus.EXCEPCION_LEGAL.value: "approved",
    }.get(status, "pending")


def _age_days(s: Submission) -> int:
    from datetime import UTC, datetime

    if not s.created_at:
        return 0
    # SQLite drops timezone info on round-trip; coerce both sides to
    # tz-aware to make the subtraction safe across Postgres + SQLite.
    created = s.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - created
    return max(0, delta.days)


def _risk_score_for(cells: dict[str, dict], missing_institution: str | None) -> int:
    """Coarse risk score: % of institution columns in a bad state.

    Bad states = empty, rejected, expired, needs_review. Scaled 0-100.
    Missing-institution filter doubles the weight on that institution.
    """
    if not cells:
        return 0
    bad = 0
    weight_sum = 0
    for inst, cell in cells.items():
        weight = 2 if inst == missing_institution else 1
        weight_sum += weight
        if cell["state"] in ("empty", "rejected", "expired", "needs_review"):
            bad += weight
    return int(round(100 * bad / max(1, weight_sum)))


def _completion_and_risk(
    db: Session, scope: ReportScope
) -> tuple[int, int]:
    # CRITICAL FIX (2026-06-03): the previous version built the three
    # statements, then looped `for stmt_ref in (...)` reassigning a local
    # with `.where(...)`. SQLAlchemy statements are immutable — `.where`
    # returns a NEW object — so the scope filters were NEVER applied and
    # every executive_summary computed completion% / vendors-at-risk
    # across ALL tenants (a cross-tenant aggregate leak). The filters are
    # now applied to the actual statements via a helper.
    def _scoped(stmt):
        if scope.client_id:
            stmt = stmt.where(Submission.client_id == scope.client_id)
        if scope.vendor_id:
            stmt = stmt.where(Submission.vendor_id == scope.vendor_id)
        if scope.period:
            stmt = stmt.where(Submission.period_key == scope.period)
        return stmt

    total_stmt = _scoped(select(func.count(Submission.id)))
    approved_stmt = _scoped(
        select(func.count(Submission.id)).where(
            Submission.status == DocumentStatus.APROBADO.value
        )
    )
    at_risk_stmt = _scoped(
        select(func.count(func.distinct(Submission.vendor_id))).where(
            Submission.status.in_(
                [
                    DocumentStatus.POSIBLE_MISMATCH.value,
                    DocumentStatus.REQUIERE_ACLARACION.value,
                    DocumentStatus.RECHAZADO.value,
                    DocumentStatus.VENCIDO.value,
                ]
            )
        )
    )
    total = db.scalar(total_stmt) or 0
    approved = db.scalar(approved_stmt) or 0
    at_risk = db.scalar(at_risk_stmt) or 0
    completion_pct = int(round(100 * approved / total)) if total else 0
    return completion_pct, int(at_risk)


def _count_status(db: Session, scope: ReportScope, status: DocumentStatus) -> int:
    stmt = select(func.count(Submission.id)).where(Submission.status == status.value)
    if scope.client_id:
        stmt = stmt.where(Submission.client_id == scope.client_id)
    if scope.vendor_id:
        stmt = stmt.where(Submission.vendor_id == scope.vendor_id)
    if scope.period:
        stmt = stmt.where(Submission.period_key == scope.period)
    return int(db.scalar(stmt) or 0)


def _scope_label(db: Session, scope: ReportScope) -> str:
    """Plain-Spanish description of the scope. Internal callers can
    see vendor / client names; the audience sanitizer in the executor
    strips them for non-internal renders."""
    from app.models.entities import Client

    parts: list[str] = []
    if scope.client_id:
        c = db.get(Client, scope.client_id)
        if c:
            parts.append(c.name)
    if scope.vendor_id:
        v = db.get(Vendor, scope.vendor_id)
        if v:
            parts.append(v.name)
    if not parts:
        parts.append("Cartera completa")
    return " · ".join(parts)


def _resolve_metric(db: Session, scope: ReportScope, metric_key: str) -> int | float | None:
    """Map metric_key to a server-computed value."""
    if metric_key == "completion_pct":
        return _completion_and_risk(db, scope)[0]
    if metric_key == "vendors_at_risk":
        return _completion_and_risk(db, scope)[1]
    if metric_key == "vendors_total":
        stmt = select(func.count(Vendor.id))
        if scope.client_id:
            stmt = stmt.where(Vendor.client_id == scope.client_id)
        if scope.vendor_id:
            stmt = stmt.where(Vendor.id == scope.vendor_id)
        return int(db.scalar(stmt) or 0)
    if metric_key == "submissions_period":
        stmt = select(func.count(Submission.id))
        if scope.client_id:
            stmt = stmt.where(Submission.client_id == scope.client_id)
        if scope.vendor_id:
            stmt = stmt.where(Submission.vendor_id == scope.vendor_id)
        if scope.period:
            stmt = stmt.where(Submission.period_key == scope.period)
        return int(db.scalar(stmt) or 0)
    if metric_key == "in_review_count":
        return _count_status(db, scope, DocumentStatus.PENDIENTE_REVISION)
    if metric_key == "overdue_count":
        return _count_status(db, scope, DocumentStatus.VENCIDO)
    if metric_key == "approved_pct":
        return _completion_and_risk(db, scope)[0]
    if metric_key == "avg_review_hours":
        return None
    if metric_key == "days_to_next_deadline":
        return None
    return None
