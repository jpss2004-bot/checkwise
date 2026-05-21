"""``attention_list`` block fetcher (P1.3).

Surfaces the documents requiring the provider's attention right now —
blocking submissions (rejected, needs_correction, possible_mismatch),
expired slots, and calendar deadlines within 14 days. Each row carries
a pre-computed ``/portal/upload`` href so the renderer can offer a
one-click fix.

The data is pulled via ``dashboard_compute.build_attention_items_for_vendor``
so the same canonical attention list the provider dashboard hero
already shows is what the report block renders. No new query path,
no LLM-authored hrefs.

The block fetcher applies the planner-supplied filter (states,
institutions, max_rows) on top of the canonical list. Filters narrow,
they cannot widen — anything the dashboard would not surface stays
hidden.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.dashboard_compute import build_attention_items_for_vendor
from app.services.reports.context import ReportScope

_DEFAULT_MAX_ROWS = 10


def fetch_attention_list(
    config: dict, scope: ReportScope, db: Session
) -> dict:
    """Return the attention-list payload, filtered per the block config.

    Shape:

    ```
    {
      "items": [{id, title, institution, state, due_in_days, href,
                 requirement_code, period_key, current_submission_id}],
      "workspace_id": str | None,
      "fetched_at": str,
      "filter_applied": {states?, institutions?, only_due_within_days?},
      "max_rows": int,
      "total_before_filter": int,
    }
    ```

    When ``scope.vendor_id`` is None → empty items shape.
    """
    if scope.vendor_id is None:
        return {
            "items": [],
            "workspace_id": None,
            "fetched_at": None,
            "filter_applied": {},
            "max_rows": _DEFAULT_MAX_ROWS,
            "total_before_filter": 0,
        }

    payload = build_attention_items_for_vendor(db, vendor_id=scope.vendor_id)
    base_items: list[dict] = list(payload["items"])
    total_before = len(base_items)

    cfg = config if isinstance(config, dict) else {}
    flt = cfg.get("filter") if isinstance(cfg.get("filter"), dict) else {}
    states_filter = flt.get("states") if isinstance(flt.get("states"), list) else None
    institutions_filter = (
        flt.get("institutions")
        if isinstance(flt.get("institutions"), list)
        else None
    )
    only_within = flt.get("only_due_within_days")
    max_rows = int(cfg.get("max_rows", _DEFAULT_MAX_ROWS))
    if max_rows < 1:
        max_rows = 1
    if max_rows > 25:
        max_rows = 25

    def _matches(item: dict) -> bool:
        if states_filter and item.get("state") not in states_filter:
            return False
        if institutions_filter and item.get("institution") not in institutions_filter:
            return False
        if only_within is not None:
            due = item.get("due_in_days")
            if due is None:
                return False
            try:
                if int(due) > int(only_within):
                    return False
            except (TypeError, ValueError):
                return False
        return True

    filtered = [it for it in base_items if _matches(it)][:max_rows]

    return {
        "items": filtered,
        "workspace_id": payload["workspace_id"],
        "fetched_at": payload["fetched_at"],
        "filter_applied": {
            k: v
            for k, v in {
                "states": states_filter,
                "institutions": institutions_filter,
                "only_due_within_days": only_within,
            }.items()
            if v is not None
        },
        "max_rows": max_rows,
        "total_before_filter": total_before,
    }
