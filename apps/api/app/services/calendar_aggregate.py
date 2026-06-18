"""Shared calendar aggregation — one obligation-placement pass per client.

Both ``GET /client/calendar`` (one client) and ``GET /admin/calendar/grid``
(every client, rolled up into a clients×months grid) need the *same* answer:
for a given client and year, walk every workspace's recurring catalog, place
each obligation on its authoritative ``due_month``/``due_day`` deadline, and
classify its current severity with :func:`_calendar_item_risk`. Keeping that
walk in one place means the admin grid and the client calendar can never drift
— the provider colors, the month a deadline lands in, and the "due in N days"
math are computed once and consumed by both surfaces.

The heavy lifting is the same batched path the ``/overview`` and ``/vendors``
hot paths use: a single :func:`_portfolio_slot_inputs` prefetch (one
``submissions`` query for the whole client) feeds :func:`_vendor_compliance`
per workspace, so this is ``O(1)`` queries in the vendor count per client. The
admin grid therefore costs *order-of-clients* batched queries, not the
order-of-vendors fan-out the radar uses — it sidesteps the radar's
300-vendor scan cap entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.core.compliance_catalog import (
    normalize_persona_type,
    recurring_anatomy,
    recurring_for_year,
    recurring_required_document,
    recurring_where_to_obtain,
)


@dataclass
class CalendarObligation:
    """One placed-and-classified obligation for a single client's calendar.

    Client-agnostic on purpose (no ``client_id``): the caller aggregates per
    client, so the admin grid tags the client at the call site. Field set
    mirrors ``ClientCalendarItem`` so ``/client/calendar`` maps it 1:1.
    """

    vendor_id: str
    workspace_id: str
    vendor_name: str
    requirement_code: str | None
    requirement_name: str
    institution: str
    frequency: str
    period_key: str | None
    period_label: str
    status: str
    submission_id: str | None
    deadline_iso: str
    due_month: int
    risk_level: str
    anatomy: str
    where_to_obtain: str
    client_href: str


@dataclass
class CalendarProviderRollup:
    """Per-provider risk rollup, sorted worst-first by the caller's helper."""

    vendor_id: str
    vendor_name: str
    semaphore_level: str
    compliance_pct: int
    overdue_count: int
    due_soon_count: int
    action_required_count: int
    next_deadline_iso: str | None


@dataclass
class ClientCalendarAggregate:
    obligations: list[CalendarObligation]
    providers: list[CalendarProviderRollup]


def aggregate_client_calendar(
    db: Session,
    *,
    client_id: str,
    year: int,
    today: date,
    vendor_ids: list[str] | None = None,
) -> ClientCalendarAggregate:
    """Place + classify every obligation for one client's calendar year.

    Behaviour-preserving extraction of the ``/client/calendar`` per-workspace
    loop. ``vendor_ids``, when supplied, narrows to those vendors (others are
    silently dropped — no cross-tenant enumeration), matching the client
    endpoint's filter exactly.

    The api-layer helpers are imported lazily so this service module carries no
    import-time dependency on ``app.api.v1`` (the routers import this function
    at module load; importing them back at the top would be circular). Same
    deferred-import idiom the admin radar endpoint already uses.
    """
    from app.api.v1.client import (
        _SEMAPHORE_SORT_ORDER,
        _calendar_item_risk,
        _portfolio_slot_inputs,
        _scoped_workspaces,
        _vendor_compliance,
        _vendors_by_id,
    )
    from app.api.v1.portal import _calendar_deadline_iso, _calendar_upload_href

    workspaces = _scoped_workspaces(db, client_id)
    if vendor_ids:
        wanted = {v for v in vendor_ids if v}
        workspaces = [w for w in workspaces if w.vendor_id in wanted]
    vendor_lookup = _vendors_by_id(db, [w.vendor_id for w in workspaces])

    # One batched submissions prefetch for the whole client (always the full
    # portfolio, mirroring the client endpoint — the prefetch is keyed by
    # vendor so the ``vendor_ids`` narrowing above just reads fewer buckets).
    subs_by_vendor, institutions_by_id = _portfolio_slot_inputs(db, client_id)

    obligations: list[CalendarObligation] = []
    provider_acc: dict[str, dict] = {}
    for ws in workspaces:
        vendor = vendor_lookup.get(ws.vendor_id)
        if vendor is None:
            continue
        compliance = _vendor_compliance(
            db,
            ws,
            today=today,
            year=year,
            prefetched_submissions=subs_by_vendor.get(ws.vendor_id, []),
            institutions_by_id=institutions_by_id,
        )
        view_by_key = {
            (v.slot_key.requirement_code, v.slot_key.period_key): v
            for v in compliance["calendar_slots"]
        }
        acc = provider_acc.setdefault(
            vendor.id,
            {
                "vendor_name": vendor.name,
                "semaphore_level": compliance["semaphore_level"],
                "compliance_pct": compliance["compliance_pct"],
                "overdue": 0,
                "due_soon": 0,
                "action_required": 0,
                "next_deadline": None,
            },
        )
        catalog = recurring_for_year(year, normalize_persona_type(ws.persona_type))
        for req in catalog:
            view = view_by_key.get((req.code, req.period_key))
            item_status = (
                view.current_status if view and view.current_status else "pendiente"
            )
            deadline_iso = _calendar_deadline_iso(year, req.due_month, req.due_day)
            risk_level = _calendar_item_risk(item_status, deadline_iso, today)
            href = _calendar_upload_href(
                year=year,
                code=req.code,
                period_key=req.period_key,
                name=req.name,
                institution=req.institution,
                load_type=req.frequency,
                v2_mode=bool(req.accepts_documents),
            )
            obligations.append(
                CalendarObligation(
                    vendor_id=vendor.id,
                    workspace_id=ws.id,
                    vendor_name=vendor.name,
                    requirement_code=req.code,
                    requirement_name=recurring_required_document(req),
                    institution=req.institution,
                    frequency=req.frequency,
                    period_key=req.period_key,
                    period_label=req.period_label,
                    status=item_status,
                    submission_id=view.current_submission_id if view else None,
                    deadline_iso=deadline_iso,
                    due_month=req.due_month,
                    risk_level=risk_level,
                    anatomy=recurring_anatomy(req),
                    where_to_obtain=recurring_where_to_obtain(req),
                    client_href=href,
                )
            )
            if risk_level == "overdue":
                acc["overdue"] += 1
            elif risk_level == "action_required":
                acc["action_required"] += 1
            elif risk_level == "due_soon":
                acc["due_soon"] += 1
            if risk_level != "on_track":
                try:
                    due_date: date | None = date.fromisoformat(deadline_iso)
                except ValueError:
                    due_date = None
                if (
                    due_date is not None
                    and due_date >= today
                    and (
                        acc["next_deadline"] is None
                        or due_date < acc["next_deadline"]
                    )
                ):
                    acc["next_deadline"] = due_date

    providers = [
        CalendarProviderRollup(
            vendor_id=vid,
            vendor_name=acc["vendor_name"],
            semaphore_level=acc["semaphore_level"],
            compliance_pct=acc["compliance_pct"],
            overdue_count=acc["overdue"],
            due_soon_count=acc["due_soon"],
            action_required_count=acc["action_required"],
            next_deadline_iso=(
                acc["next_deadline"].isoformat() if acc["next_deadline"] else None
            ),
        )
        for vid, acc in provider_acc.items()
    ]
    providers.sort(
        key=lambda p: (
            _SEMAPHORE_SORT_ORDER.get(p.semaphore_level, 3),
            -p.overdue_count,
            -p.action_required_count,
            -p.due_soon_count,
            p.vendor_name.lower(),
        )
    )
    return ClientCalendarAggregate(obligations=obligations, providers=providers)
