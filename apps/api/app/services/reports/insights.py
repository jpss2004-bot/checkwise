"""Deterministic insight engine for reports.

Turns raw portfolio/compliance data into a synthesized VERDICT + the few
FINDINGS that actually matter, so a report can lead with "so what" instead of
just "what". Pure rules over the SAME canonical sources the chart blocks use
(build_client_context + Submission status counts + renewal reminders), so the
insight can never contradict the evidence rendered below it.

This is the always-present, always-correct floor. On prod the AI layer may
rewrite the prose into sharper language, but the structure + the facts come
from here.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.constants.reports import ReportAudience
from app.constants.statuses import DocumentStatus
from app.core.time import today_mx
from app.models import (
    ProviderWorkspace,
    RenewalReminder,
    Submission,
    Vendor,
)
from app.services.reports.context import ReportScope


def _action_links_from_items(
    items: list[dict],
    *,
    types: set[str] | None = None,
    priorities: set[str] | None = None,
    limit: int = 3,
    client_vendor_id: str | None = None,
) -> list[dict]:
    """Project action items into report link dicts.

    When ``client_vendor_id`` is set the report is read by the CLIENT (who
    monitors, not uploads), so each link is rewritten to a client-routable
    deep link into the provider detail (CW-04) instead of the provider's
    ``/portal/upload`` href, and the label becomes a neutral "ver" CTA.
    """
    from app.services.dashboard_compute import client_vendor_focus_href

    links: list[dict] = []
    for item in items:
        if types is not None and item.get("type") not in types:
            continue
        if priorities is not None and item.get("priority") not in priorities:
            continue
        if client_vendor_id is not None:
            href = client_vendor_focus_href(
                client_vendor_id,
                requirement_code=item.get("requirement_code"),
                period_key=item.get("period_key"),
            )
            title = "Ver documento del proveedor"
        else:
            href = item.get("href")
            title = item.get("title")
        links.append(
            {
                "id": item.get("id"),
                "type": item.get("type"),
                "priority": item.get("priority"),
                "title": title,
                "href": href,
                "requirement_code": item.get("requirement_code"),
                "period_key": item.get("period_key"),
            }
        )
        if len(links) >= limit:
            break
    return links

# Renewal cadences (days) keyed by onboarding requirement code — mirrors
# compliance_catalog.renewal_frequency_days for the renewable pieces.
_RENEWAL_FREQ_DAYS = {
    "ONB-CORP-M-002": 90,   # CSF (persona moral)
    "ONB-CORP-F-002": 90,   # CSF (persona física)
    "ONB-REPSE-001": 1095,  # Registro REPSE
    "ONB-PATR-001": 1095,   # Registro patronal
}

_RENEWAL_LABEL = {
    "ONB-CORP-M-002": "Constancia de Situación Fiscal (CSF)",
    "ONB-CORP-F-002": "Constancia de Situación Fiscal (CSF)",
    "ONB-REPSE-001": "Registro REPSE",
    "ONB-PATR-001": "Registro patronal",
}

# Active problems — a vendor carrying these needs attention MORE urgently than
# one that's merely incomplete (still onboarding), so they dominate the
# "most needs attention" ranking.
_RISK_STATUSES = [
    DocumentStatus.RECHAZADO.value,
    DocumentStatus.POSIBLE_MISMATCH.value,
    DocumentStatus.VENCIDO.value,
    DocumentStatus.REQUIERE_ACLARACION.value,
]


def _month_bounds(today: date, offset: int) -> tuple[date, date]:
    """[start, next_start) for the month ``offset`` months before ``today``."""
    y, m = today.year, today.month - offset
    while m <= 0:
        m += 12
        y -= 1
    start = date(y, m, 1)
    next_start = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start, next_start


def _approval_trend(
    db: Session, today: date, *, client_id: str | None = None, vendor_id: str | None = None
) -> int | None:
    """Change in approval rate (points) between the two most recent months
    that had activity — skipping quiet months so a slow current month doesn't
    blank the signal. None when fewer than two active months exist. An honest
    momentum signal, not a snapshot of the cumplimiento %.

    Computed in a SINGLE grouped query over a trailing ~8-month window so the
    client dashboard's overview call stays cheap (this used to be up to eight
    separate per-month scans). A month is "active" only with >=3 submissions
    so a couple of stray uploads can't fake a trend.
    """
    dialect = db.get_bind().dialect.name
    # Portable year-month bucket key ("YYYY-MM"): to_char on Postgres,
    # strftime on SQLite (tests). String sort == chronological sort.
    if dialect == "postgresql":
        month_key = func.to_char(Submission.created_at, "YYYY-MM")
    else:
        month_key = func.strftime("%Y-%m", Submission.created_at)
    window_start, _ = _month_bounds(today, 7)
    stmt = (
        select(
            month_key.label("m"),
            func.count(Submission.id),
            func.sum(
                case(
                    (Submission.status == DocumentStatus.APROBADO.value, 1),
                    else_=0,
                )
            ),
        )
        .where(Submission.created_at >= window_start)
        .group_by(month_key)
        .order_by(month_key.desc())
    )
    if client_id:
        stmt = stmt.where(Submission.client_id == client_id)
    if vendor_id:
        stmt = stmt.where(Submission.vendor_id == vendor_id)

    rates: list[int] = []
    for _m, total, approved in db.execute(stmt).all():
        t = int(total or 0)
        if t < 3:
            continue
        rates.append(round(100 * int(approved or 0) / t))
        if len(rates) == 2:
            break
    if len(rates) < 2:
        return None
    return rates[0] - rates[1]  # most recent − the one before it


def approval_trend_points(
    db: Session,
    today: date,
    *,
    client_id: str | None = None,
    vendor_id: str | None = None,
) -> int | None:
    """Public wrapper over :func:`_approval_trend`.

    Lets non-report surfaces (the client dashboard momentum chip) reuse the
    same honest month-over-month approval-rate delta the report engine uses,
    without importing a private helper. ``None`` when fewer than two active
    months exist.
    """
    return _approval_trend(db, today, client_id=client_id, vendor_id=vendor_id)


def approval_trend_points_by_vendor(
    db: Session, today: date, *, client_id: str
) -> dict[str, int]:
    """Per-vendor approval-rate momentum for a whole client in ONE query.

    Returns ``{vendor_id: delta_points}`` (most recent active month − the one
    before) for every vendor with ≥2 active months. Same definition as
    :func:`_approval_trend`, but grouped by ``(vendor_id, month)`` so the
    client dashboard can annotate its worklist without an N+1 — the portfolio
    query-count contract stays constant in the vendor count.
    """
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        month_key = func.to_char(Submission.created_at, "YYYY-MM")
    else:
        month_key = func.strftime("%Y-%m", Submission.created_at)
    window_start, _ = _month_bounds(today, 7)
    stmt = (
        select(
            Submission.vendor_id,
            month_key.label("m"),
            func.count(Submission.id),
            func.sum(
                case(
                    (Submission.status == DocumentStatus.APROBADO.value, 1),
                    else_=0,
                )
            ),
        )
        .where(
            Submission.created_at >= window_start,
            Submission.client_id == client_id,
        )
        .group_by(Submission.vendor_id, month_key)
        .order_by(Submission.vendor_id, month_key.desc())
    )
    rates: dict[str, list[int]] = defaultdict(list)
    for vendor_id, _m, total, approved in db.execute(stmt).all():
        t = int(total or 0)
        if t < 3:
            continue
        if len(rates[vendor_id]) < 2:
            rates[vendor_id].append(round(100 * int(approved or 0) / t))
    return {
        vid: pts[0] - pts[1] for vid, pts in rates.items() if len(pts) == 2
    }


def _count_status(db: Session, scope: ReportScope, status: DocumentStatus) -> int:
    stmt = select(func.count(Submission.id)).where(Submission.status == status.value)
    if scope.client_id:
        stmt = stmt.where(Submission.client_id == scope.client_id)
    if scope.vendor_id:
        stmt = stmt.where(Submission.vendor_id == scope.vendor_id)
    return int(db.scalar(stmt) or 0)


def _vendor_issue(db: Session, vendor_id: str, missing: int) -> str:
    """The most salient one-line reason a vendor needs attention."""
    def n(status: DocumentStatus) -> int:
        return int(
            db.scalar(
                select(func.count(Submission.id)).where(
                    Submission.vendor_id == vendor_id,
                    Submission.status == status.value,
                )
            )
            or 0
        )

    parts: list[str] = []
    rej = n(DocumentStatus.RECHAZADO)
    mis = n(DocumentStatus.POSIBLE_MISMATCH)
    ven = n(DocumentStatus.VENCIDO)
    acl = n(DocumentStatus.REQUIERE_ACLARACION)
    if rej:
        parts.append(f"{rej} documento{'s' if rej != 1 else ''} rechazado{'s' if rej != 1 else ''}")
    if mis:
        parts.append(f"{mis} con inconsistencia de RFC")
    if ven:
        parts.append(f"{ven} vencido{'s' if ven != 1 else ''}")
    if acl:
        parts.append(f"{acl} requiere aclaración")
    if parts:
        return "Tiene " + ", ".join(parts) + "."
    if missing:
        return f"Expediente incompleto: {missing} obligación(es) sin evidencia."
    return "Requiere seguimiento de su expediente."


def _renewal_finding(db: Session, client_id: str, today: date) -> dict | None:
    """The soonest renewal coming due across the client's providers, if any."""
    rows = db.execute(
        select(
            Vendor.name,
            RenewalReminder.requirement_code,
            RenewalReminder.cycle_anchor_date,
        )
        .join(ProviderWorkspace, ProviderWorkspace.id == RenewalReminder.workspace_id)
        .join(Vendor, Vendor.id == ProviderWorkspace.vendor_id)
        .where(Vendor.client_id == client_id)
    ).all()
    if not rows:
        return None

    soonest: tuple[int, str, str] | None = None  # (days_to_due, vendor, label)
    for vendor_name, code, anchor in rows:
        freq = _RENEWAL_FREQ_DAYS.get(code)
        if not freq or anchor is None:
            continue
        days = (anchor + timedelta(days=freq) - today).days
        if soonest is None or days < soonest[0]:
            soonest = (days, vendor_name, _RENEWAL_LABEL.get(code, code))
    if soonest is None:
        return None
    days, vendor_name, label = soonest
    when = (
        "vence hoy" if days == 0
        else f"venció hace {-days} día(s)" if days < 0
        else f"vence en ~{days} día(s)"
    )
    return {
        "tone": "yellow" if days >= 0 else "red",
        "title": "Renovación próxima a vencer",
        "detail": f"{vendor_name} · {label} {when}.",
    }


def compute_client_insight(
    db: Session, scope: ReportScope, *, today: date | None = None
) -> dict | None:
    """Synthesize the verdict + the 2-3 findings that matter for a client
    portfolio. Returns ``None`` when there's no client scope to reason about."""
    if scope.client_id is None:
        return None
    today = today or today_mx()

    from app.services.wise.client_context import build_client_context_cached

    pf = build_client_context_cached(db, scope.client_id)
    if pf is None:
        return None

    overall = int(pf.overall_compliance_pct)
    red, yellow, green, total = (
        pf.red_count,
        pf.yellow_count,
        pf.green_count,
        pf.vendor_count,
    )
    need_action = red + yellow

    if red > 0 or overall < 50:
        level, word = "red", "En riesgo"
    elif yellow > 0 or overall < 85:
        level, word = "yellow", "En proceso"
    else:
        level, word = "green", "Al día"

    if need_action == 0:
        subhead = "Todos tus proveedores están al día."
    else:
        subhead = (
            f"{need_action} de {total} proveedor{'es' if total != 1 else ''} "
            f"necesita{'n' if need_action != 1 else ''} acción."
        )

    verdict = {
        "level": level,
        "headline": f"{word} · {overall}% de cumplimiento",
        "subhead": subhead,
        "metric": {"value": overall, "label": "Cumplimiento global", "format": "percent"},
        "trend": _approval_trend(db, today, client_id=scope.client_id),
    }

    findings: list[dict] = []
    # 1) The provider that most needs attention. Weight ACTIVE problems
    # (rejections / RFC mismatch / expiry / clarification) above mere
    # incompleteness — an open rejection is more actionable than a provider
    # who simply hasn't started.
    risk_counts: dict[str, int] = dict(
        db.execute(
            select(Submission.vendor_id, func.count(Submission.id))
            .where(
                Submission.client_id == scope.client_id,
                Submission.status.in_(_RISK_STATUSES),
            )
            .group_by(Submission.vendor_id)
        ).all()
    )
    ranked = sorted(
        pf.vendors,
        key=lambda v: (
            -risk_counts.get(v.vendor_id, 0),
            {"red": 0, "yellow": 1, "green": 2}.get(v.semaphore_level, 3),
            v.compliance_pct,
        ),
    )
    worst = ranked[0] if ranked else None
    if worst is not None and (
        risk_counts.get(worst.vendor_id, 0) > 0
        or worst.semaphore_level in ("red", "yellow")
    ):
        from app.services.dashboard_compute import build_suggested_actions_for_vendor

        has_active = risk_counts.get(worst.vendor_id, 0) > 0
        action_items = build_suggested_actions_for_vendor(
            db, vendor_id=worst.vendor_id, today=today
        ).get("items", [])
        findings.append({
            "tone": "red" if (has_active or worst.semaphore_level == "red") else "yellow",
            "title": f"{worst.vendor_name} es quien más atención necesita",
            "detail": _vendor_issue(db, worst.vendor_id, worst.missing_required_count),
            "links": _action_links_from_items(
                action_items, limit=3, client_vendor_id=worst.vendor_id
            ),
        })
    # 2) Soonest renewal coming due.
    rf = _renewal_finding(db, scope.client_id, today)
    if rf is not None:
        findings.append(rf)
    # 3) Review backlog.
    in_review = _count_status(db, scope, DocumentStatus.PENDIENTE_REVISION)
    if in_review >= 5 and len(findings) < 3:
        findings.append({
            "tone": "info",
            "title": f"{in_review} documentos esperan dictamen",
            "detail": "Cerrar la bandeja de revisión libera el avance del periodo.",
        })
    # 4) A positive note, if there's room.
    if green > 0 and len(findings) < 3:
        findings.append({
            "tone": "green",
            "title": f"{green} proveedor{'es' if green != 1 else ''} al 100%",
            "detail": "Expediente y calendario al día, sin faltantes ni rechazos.",
        })

    return {"verdict": verdict, "findings": findings[:3]}


def compute_vendor_insight(
    db: Session, scope: ReportScope, *, today: date | None = None
) -> dict | None:
    """Synthesize the verdict + findings for ONE provider (vendor scope).

    Same shape as the client insight, but the subject is a single provider:
    their semáforo, what needs correction, and what's coming due."""
    if scope.vendor_id is None:
        return None
    today = today or today_mx()

    from app.services.dashboard_compute import (
        build_compliance_state_for_vendor,
        build_suggested_actions_for_vendor,
        build_upcoming_deadlines_for_vendor,
    )

    vendor = db.get(Vendor, scope.vendor_id)
    if vendor is None:
        return None
    # Only the provider's OWN copy (vendor_facing) is addressed in second
    # person ("Tienes… Vuelve a cargar"). A client/auditor/internal reader
    # gets third-person copy about the provider — they can't upload, so
    # "Vuelve a cargar" addressed to them is wrong (the whole report is a
    # findings document they hand to the provider). Mirrors the block-level
    # ``interactive`` gate.
    vendor_reads = scope.audience == ReportAudience.VENDOR_FACING
    # A client/internal reader can't upload — point their report links into
    # the client app (CW-04), not the provider's /portal/upload wizard.
    client_vendor_id = None if vendor_reads else scope.vendor_id
    state = build_compliance_state_for_vendor(db, vendor_id=scope.vendor_id)
    sem = state.get("semaphore", {})
    counts = state.get("document_state_counts", {})
    pct = int(sem.get("compliance_pct", 0))
    level = sem.get("level", "yellow")
    word = {
        "red": "En riesgo",
        "yellow": "En proceso",
        "green": "Al día",
    }.get(level, "En proceso")

    rejected = int(counts.get("rejected", 0))
    needs = int(counts.get("needs_review", 0))
    expired = int(counts.get("expired", 0))
    in_review = int(counts.get("in_review", 0))
    pending = int(counts.get("pending", 0))
    to_correct = rejected + needs + expired
    suggested_actions = build_suggested_actions_for_vendor(
        db, vendor_id=scope.vendor_id, today=today
    ).get("items", [])

    if to_correct:
        plural = "s" if to_correct != 1 else ""
        verb = "requieren" if to_correct != 1 else "requiere"
        subhead = f"{to_correct} documento{plural} {verb} corrección."
    elif pending:
        subhead = f"{pending} obligación(es) pendientes de cargar."
    else:
        subhead = (
            "Tu expediente está al día."
            if vendor_reads
            else "El expediente del proveedor está al día."
        )

    verdict = {
        "level": level,
        "headline": f"{word} · {pct}% de cumplimiento",
        "subhead": subhead,
        "metric": {"value": pct, "label": "Cumplimiento del proveedor", "format": "percent"},
        "trend": _approval_trend(db, today, vendor_id=scope.vendor_id),
    }

    findings: list[dict] = []
    if to_correct:
        parts: list[str] = []
        if rejected:
            parts.append(f"{rejected} rechazado{'s' if rejected != 1 else ''}")
        if needs:
            parts.append(f"{needs} con observación (RFC / aclaración)")
        if expired:
            parts.append(f"{expired} vencido{'s' if expired != 1 else ''}")
        findings.append({
            "tone": "red",
            "title": "Documentos que requieren corrección",
            "detail": (
                "Tienes " + ", ".join(parts) + ". Vuelve a cargar la versión corregida."
                if vendor_reads
                else "El proveedor tiene "
                + ", ".join(parts)
                + ". Debe volver a cargar la versión corregida."
            ),
            "links": _action_links_from_items(
                suggested_actions,
                types={"reupload", "clarify", "verify_mismatch", "regularize"},
                priorities={"high"},
                limit=5,
                client_vendor_id=client_vendor_id,
            ),
        })
    elif pending:
        findings.append({
            "tone": "yellow",
            "title": "Obligaciones por entregar",
            "detail": (
                f"{pending} obligación(es) pendientes de cargar."
                if vendor_reads
                else f"El proveedor tiene {pending} obligación(es) pendientes de cargar."
            ),
            "links": _action_links_from_items(
                suggested_actions,
                types={"complete_onboarding", "upcoming"},
                limit=5,
                client_vendor_id=client_vendor_id,
            ),
        })
    deadlines = build_upcoming_deadlines_for_vendor(db, vendor_id=scope.vendor_id, top=1)
    items = deadlines.get("items", [])
    if items:
        it = items[0]
        d = it.get("due_in_days")
        when = (
            f"vence en ~{d} día(s)" if (d is not None and d >= 0)
            else "está vencido" if d is not None else ""
        )
        findings.append({
            "tone": "yellow",
            "title": "Próximo vencimiento",
            "detail": (
                f"{str(it.get('institution', '')).upper()} · "
                f"{it.get('title', '')} {when}."
            ).strip(),
            "links": _action_links_from_items(
                [it], limit=1, client_vendor_id=client_vendor_id
            ),
        })
    if in_review and len(findings) < 3:
        findings.append({
            "tone": "info",
            "title": f"{in_review} documento{'s' if in_review != 1 else ''} en revisión",
            "detail": "Esperando dictamen del equipo de CheckWise.",
        })
    if level == "green" and len(findings) < 3:
        findings.append({
            "tone": "green",
            "title": "Expediente al día",
            "detail": "Sin rechazos ni faltantes en el periodo.",
        })

    return {"verdict": verdict, "findings": findings[:3]}


def compute_insight(db: Session, scope: ReportScope) -> dict | None:
    """Scope-adaptive: a single provider's insight when vendor-scoped, the
    portfolio insight otherwise."""
    if scope.vendor_id:
        return compute_vendor_insight(db, scope)
    return compute_client_insight(db, scope)


__all__ = [
    "compute_client_insight",
    "compute_vendor_insight",
    "compute_insight",
    "approval_trend_points",
]
