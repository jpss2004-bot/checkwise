"""``upcoming_deadlines`` block fetcher (P1.4).

Shows the next ``top`` (default 5) deadlines from the provider's
calendar — required slots, not-yet-resolved, not-yet-overdue —
plus an urgency-bucket count strip (this week / 2 weeks / month /
later) so the renderer can lay out a visual timeline.

The data comes verbatim from
``dashboard_compute.build_upcoming_deadlines_for_vendor``. The block
adds optional filtering for institutions + a configurable ``top``
cap (1..12). Filters narrow, they cannot widen.

The block has no AI text — every value is grounded in the canonical
calendar slot service.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.dashboard_compute import (
    URGENCY_BANDS,
    bucket_upcoming_by_urgency,
    build_upcoming_deadlines_for_vendor,
)
from app.services.reports.context import ReportScope

_DEFAULT_TOP = 5
_MAX_TOP = 12


def fetch_upcoming_deadlines(
    config: dict, scope: ReportScope, db: Session
) -> dict:
    """Return the upcoming-deadlines payload, filtered per the block config.

    Shape:

    ```
    {
      "items": [{id, title, institution, period_key, due_month,
                 due_in_days, state, href, requirement_code}],
      "urgency_buckets": {week, fortnight, month, later},
      "workspace_id": str | None,
      "fetched_at": str,
      "as_of": str,
      "filter_applied": {institutions?: [...]},
      "top": int,
      "total_before_filter": int,
    }
    ```
    """
    cfg = config if isinstance(config, dict) else {}
    flt = cfg.get("filter") if isinstance(cfg.get("filter"), dict) else {}
    institutions_filter = (
        flt.get("institutions")
        if isinstance(flt.get("institutions"), list)
        else None
    )
    top = int(cfg.get("top", _DEFAULT_TOP))
    if top < 1:
        top = 1
    if top > _MAX_TOP:
        top = _MAX_TOP

    if scope.vendor_id is None:
        return {
            "items": [],
            "urgency_buckets": {b["key"]: 0 for b in URGENCY_BANDS},
            "workspace_id": None,
            "fetched_at": None,
            "as_of": None,
            "filter_applied": {},
            "top": top,
            "total_before_filter": 0,
        }

    # Pull a generous slate so institution filtering doesn't starve the
    # final list. The canonical builder pre-sorts; we re-apply ``top``
    # post-filter to honour the user's cap intent.
    payload = build_upcoming_deadlines_for_vendor(
        db, vendor_id=scope.vendor_id, top=_MAX_TOP
    )
    base_items: list[dict] = list(payload["items"])
    total_before = len(base_items)

    if institutions_filter:
        filtered = [
            it for it in base_items if it.get("institution") in institutions_filter
        ]
    else:
        filtered = base_items
    filtered = filtered[:top]

    return {
        "items": filtered,
        "urgency_buckets": bucket_upcoming_by_urgency(filtered),
        "workspace_id": payload["workspace_id"],
        "fetched_at": payload["fetched_at"],
        "as_of": payload["as_of"],
        "filter_applied": (
            {"institutions": institutions_filter}
            if institutions_filter
            else {}
        ),
        "top": top,
        "total_before_filter": total_before,
    }
