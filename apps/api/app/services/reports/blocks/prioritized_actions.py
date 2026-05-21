"""``prioritized_actions`` block fetcher (P1.5).

Provider-facing remediation list — the structured closer that
replaces the generic ``ai_recommendation`` for vendor-facing
reports. Each row carries a stable id, action type, priority
chip, canonical title + body, and a one-click upload href.

The data comes verbatim from
``dashboard_compute.build_suggested_actions_for_vendor`` — the same
canonical computation the provider dashboard hero already uses.
Title + body are deterministic (no LLM in the loop), which means
the block can never invent a remediation that contradicts the
reviewer note or the slot state.

The block's filter narrows; it cannot widen. ``priorities`` /
``types`` filters drop rows that don't match. ``max_actions`` caps
the rendered count (1..5).

A future AI-tone slice may layer an optional ``body_override`` per
row that softens the canonical copy for tone, while keeping the
canonical body as fall-through ground truth.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.dashboard_compute import build_suggested_actions_for_vendor
from app.services.reports.context import ReportScope

_DEFAULT_MAX = 3
_MAX_CAP = 5


def fetch_prioritized_actions(
    config: dict, scope: ReportScope, db: Session
) -> dict:
    """Return the prioritized-actions payload, filtered per the block config.

    Shape:

    ```
    {
      "items": [{id, type, title, body, priority, href,
                 requirement_code, period_key}],
      "workspace_id": str | None,
      "fetched_at": str,
      "as_of": str,
      "filter_applied": {priorities?: [...], types?: [...]},
      "max_actions": int,
      "total_before_filter": int,
    }
    ```
    """
    cfg = config if isinstance(config, dict) else {}
    flt = cfg.get("filter") if isinstance(cfg.get("filter"), dict) else {}
    priorities_filter = (
        flt.get("priorities")
        if isinstance(flt.get("priorities"), list)
        else None
    )
    types_filter = (
        flt.get("types") if isinstance(flt.get("types"), list) else None
    )
    max_actions = int(cfg.get("max_actions", _DEFAULT_MAX))
    if max_actions < 1:
        max_actions = 1
    if max_actions > _MAX_CAP:
        max_actions = _MAX_CAP

    if scope.vendor_id is None:
        return {
            "items": [],
            "workspace_id": None,
            "fetched_at": None,
            "as_of": None,
            "filter_applied": {},
            "max_actions": max_actions,
            "total_before_filter": 0,
        }

    payload = build_suggested_actions_for_vendor(db, vendor_id=scope.vendor_id)
    base_items: list[dict] = list(payload["items"])
    total_before = len(base_items)

    def _matches(item: dict) -> bool:
        if priorities_filter and item.get("priority") not in priorities_filter:
            return False
        if types_filter and item.get("type") not in types_filter:
            return False
        return True

    filtered = [it for it in base_items if _matches(it)][:max_actions]

    return {
        "items": filtered,
        "workspace_id": payload["workspace_id"],
        "fetched_at": payload["fetched_at"],
        "as_of": payload["as_of"],
        "filter_applied": {
            k: v
            for k, v in {
                "priorities": priorities_filter,
                "types": types_filter,
            }.items()
            if v is not None
        },
        "max_actions": max_actions,
        "total_before_filter": total_before,
    }
