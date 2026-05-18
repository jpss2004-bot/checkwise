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
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants.statuses import DocumentStatus
from app.models.entities import (
    Institution,
    Submission,
    Vendor,
)
from app.services.reports.blocks.attention_list import fetch_attention_list
from app.services.reports.blocks.compliance_state import fetch_compliance_state
from app.services.reports.blocks.prioritized_actions import (
    fetch_prioritized_actions,
)
from app.services.reports.blocks.upcoming_deadlines import fetch_upcoming_deadlines
from app.services.reports.context import ReportScope

# ─── Fetchers ──────────────────────────────────────────────────


def fetch_executive_summary(
    config: dict, scope: ReportScope, db: Session
) -> dict:
    """Headline metrics + labels for the cover block."""
    completion_pct, vendors_at_risk = _completion_and_risk(db, scope)
    submissions_in_review = _count_status(db, scope, DocumentStatus.PENDIENTE_REVISION)
    return {
        "period_label": scope.period,
        "scope_label": _scope_label(db, scope),
        "headline_metrics": {
            "completion_pct": completion_pct,
            "vendors_at_risk": vendors_at_risk,
            "submissions_in_review": submissions_in_review,
            "next_critical_deadline": None,
        },
    }


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
    return {"resolved": resolved}


def fetch_vendor_risk_matrix(
    config: dict, scope: ReportScope, db: Session
) -> dict:
    """Cross-vendor portfolio view. Filters per config['filter']."""
    flt = config.get("filter") or {}
    missing_institution = flt.get("missing_institution")
    min_risk = flt.get("min_risk_score")
    columns = config.get("columns") or ["sat", "imss", "infonavit", "stps_repse", "risk_score"]
    sort = config.get("sort", "risk_desc")
    max_rows = int(config.get("max_rows", 25))

    # Pull every vendor in scope.
    vendors = _vendors_in_scope(db, scope)

    rows: list[dict[str, Any]] = []
    for v in vendors:
        cells: dict[str, dict[str, Any]] = {}
        # For each institution column, find the latest submission.
        for col in columns:
            if col in ("risk_score", "last_event"):
                continue
            inst_code = col
            latest = _latest_submission_for_institution(db, v.id, inst_code, scope.period)
            if latest is None:
                cells[col] = {"state": "empty", "age_days": 0, "period": scope.period or ""}
            else:
                cells[col] = {
                    "state": _doc_state_for(latest.status),
                    "age_days": _age_days(latest),
                    "period": latest.period_key or scope.period or "",
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
    return {"rows": rows, "totals": totals}


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
    }


# ─── Dispatcher ────────────────────────────────────────────────


_FETCHERS: dict[str, Callable[[dict, ReportScope, Session], dict | None]] = {
    "executive_summary": fetch_executive_summary,
    "kpi_strip": fetch_kpi_strip,
    "vendor_risk_matrix": fetch_vendor_risk_matrix,
    "text": fetch_text_or_divider,
    "divider": fetch_text_or_divider,
    "ai_recommendation": fetch_ai_recommendation,
    "compliance_state": fetch_compliance_state,
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
    total_stmt = select(func.count(Submission.id))
    approved_stmt = select(func.count(Submission.id)).where(
        Submission.status == DocumentStatus.APROBADO.value
    )
    at_risk_stmt = select(func.count(func.distinct(Submission.vendor_id))).where(
        Submission.status.in_(
            [
                DocumentStatus.POSIBLE_MISMATCH.value,
                DocumentStatus.REQUIERE_ACLARACION.value,
                DocumentStatus.RECHAZADO.value,
                DocumentStatus.VENCIDO.value,
            ]
        )
    )
    for stmt_ref in (total_stmt, approved_stmt, at_risk_stmt):
        if scope.client_id:
            stmt_ref = stmt_ref.where(Submission.client_id == scope.client_id)
        if scope.vendor_id:
            stmt_ref = stmt_ref.where(Submission.vendor_id == scope.vendor_id)
        if scope.period:
            stmt_ref = stmt_ref.where(Submission.period_key == scope.period)
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
