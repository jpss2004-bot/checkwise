"""Precomputed admin-calendar overview cache (stale-while-revalidate).

The overview (``GET /admin/calendar/grid`` with no ``client_id``) is an
``O(clients)`` compliance scan at ~90 ms/client — seconds per load once the
portfolio is large. This caches each client's contribution (12-month cells +
the rollup the overview needs) into ``admin_calendar_snapshots`` so the endpoint
reads + sums JSON rows instead of re-scanning.

Read path (in the endpoint): if a snapshot exists for the year it is served
immediately; if it is older than ``STALE_AFTER_SECONDS`` a background refresh is
kicked (serve-stale-while-revalidate); on a cold table the endpoint computes
live once and schedules a populate. The per-client DRILL stays live, so
obligation detail is never stale — only the portfolio map can lag by minutes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AdminCalendarSnapshot, Client
from app.services.calendar_aggregate import aggregate_client_calendar
from app.services.calendar_risk import worst_calendar_risk as _worst

STALE_AFTER_SECONDS = 1200  # 20 min — the map can lag this much; detail is live.

# Dedup concurrent background refreshes of the same year (a read burst past the
# staleness edge would otherwise kick N identical full scans).
_refreshing: set[int] = set()


def _due_in(deadline_iso: str, today: date) -> int:
    try:
        return (date.fromisoformat(deadline_iso) - today).days
    except ValueError:
        return 0


def build_client_snapshot_payload(
    db: Session, client: Client, *, year: int, today: date
) -> dict:
    """One client's cached contribution: its row rollup + 12-month cells.

    Same numbers the live overview loop produces, just precomputed. Cells carry
    a per-institution {count, worst_risk, delivered} so the FE institution
    filter and the month gap both work off the cache.
    """
    agg = aggregate_client_calendar(db, client_id=client.id, year=year, today=today)

    if agg.providers:
        level = "green"
        for p in agg.providers:
            if p.semaphore_level == "red":
                level = "red"
                break
            if p.semaphore_level == "yellow":
                level = "yellow"
        compliance_pct = round(
            sum(p.compliance_pct for p in agg.providers) / len(agg.providers)
        )
    else:
        level = "green"
        compliance_pct = 100

    cell_acc: dict[int, dict] = {}
    overdue_total = due_7d_total = 0
    for ob in agg.obligations:
        c = cell_acc.setdefault(ob.due_month, {"risks": [], "delivered": 0, "by_inst": {}})
        delivered = 1 if ob.risk_level == "on_track" else 0
        c["risks"].append(ob.risk_level)
        c["delivered"] += delivered
        bi = c["by_inst"].setdefault(ob.institution, {"risks": [], "delivered": 0})
        bi["risks"].append(ob.risk_level)
        bi["delivered"] += delivered
        if ob.risk_level == "overdue":
            overdue_total += 1
        elif 0 <= _due_in(ob.deadline_iso, today) <= 7 and ob.risk_level != "on_track":
            due_7d_total += 1

    cells = [
        {
            "month": month,
            "count": len(c["risks"]),
            "worst_risk": _worst(c["risks"]),
            "delivered": c["delivered"],
            "by_institution": {
                inst: {
                    "count": len(v["risks"]),
                    "worst_risk": _worst(v["risks"]),
                    "delivered": v["delivered"],
                }
                for inst, v in c["by_inst"].items()
            },
        }
        for month, c in cell_acc.items()
    ]

    return {
        "client_name": client.name,
        "semaphore_level": level,
        "compliance_pct": compliance_pct,
        "overdue_count": sum(p.overdue_count for p in agg.providers),
        "due_soon_count": sum(p.due_soon_count for p in agg.providers),
        "overdue_total": overdue_total,
        "due_7d_total": due_7d_total,
        "cells": cells,
    }


def refresh_admin_calendar_snapshot(db: Session, *, year: int, today: date) -> int:
    """Recompute + fully replace the snapshot for ``year``. Returns client count."""
    clients = list(db.scalars(select(Client)))
    now = datetime.now(UTC)
    db.query(AdminCalendarSnapshot).filter(
        AdminCalendarSnapshot.year == year
    ).delete(synchronize_session=False)
    for cl in clients:
        db.add(
            AdminCalendarSnapshot(
                year=year,
                client_id=cl.id,
                client_name=cl.name,
                payload=build_client_snapshot_payload(db, cl, year=year, today=today),
                computed_at=now,
            )
        )
    db.commit()
    return len(clients)


def load_admin_calendar_snapshot(
    db: Session, year: int
) -> list[AdminCalendarSnapshot] | None:
    """Snapshot rows for the year, or None when the cache is cold."""
    rows = list(
        db.scalars(
            select(AdminCalendarSnapshot).where(AdminCalendarSnapshot.year == year)
        )
    )
    return rows or None


def is_stale(computed_at: datetime, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=UTC)
    return (now - computed_at).total_seconds() > STALE_AFTER_SECONDS


def refresh_admin_calendar_snapshot_background(year: int) -> None:
    """Background-task entry: own session, deduped so a read burst past the
    staleness edge doesn't pile up identical full scans."""
    if year in _refreshing:
        return
    _refreshing.add(year)
    try:
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            refresh_admin_calendar_snapshot(db, year=year, today=date.today())
        finally:
            db.close()
    except Exception:
        # Never let a background refresh failure surface; the next read retries.
        pass
    finally:
        _refreshing.discard(year)
