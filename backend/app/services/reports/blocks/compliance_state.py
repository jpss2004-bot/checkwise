"""``compliance_state`` block fetcher (P1.2).

Renders the provider's current compliance pulse — semaphore (green /
yellow / red), reason copy, compliance %, on-track / total tracked,
and the eight-bucket document-state counts. No AI text — the values
are factual and grounded in the canonical evidence-slot service via
``app.services.dashboard_compute``.

Scope contract:

- ``audience == vendor_facing`` and ``scope.vendor_id`` set → the
  block resolves the active ``ProviderWorkspace`` for that vendor and
  computes the payload from its onboarding + calendar slots.
- ``audience == internal_only`` / ``client_facing`` with a vendor_id
  set → the block also renders (internal staff and client admins can
  see a provider's pulse on a vendor-scoped report). The scope check
  is performed by ``assert_workspace_scope`` first.
- Missing vendor_id → empty payload. The dispatcher tolerates ``None``
  vendor_ids today because not every audience requires one; the
  fetcher returns the empty shape rather than raising so the canvas
  can still render the block in a clear "no vendor selected" state.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.dashboard_compute import build_compliance_state_for_vendor
from app.services.reports.context import ReportScope


def fetch_compliance_state(
    config: dict, scope: ReportScope, db: Session
) -> dict:
    """Return the JSON payload the ``compliance_state`` block renders.

    Shape lines up with the frontend ``ComplianceStateData`` interface:

    ```
    {
      "semaphore": {level, label, reason, compliance_pct,
                    total_tracked, on_track},
      "document_state_counts": {approved, in_review, uploaded, pending,
                                needs_review, rejected, expired, exception},
      "workspace_id": str | None,
      "persona_type": str | None,
    }
    ```

    The ``config`` dict is currently empty by design — the block has
    no user-configurable parameters in v1. Reserved for future
    options like ``year`` override on the calendar slot scan.
    """
    if scope.vendor_id is None:
        return {
            "semaphore": {
                "level": "green",
                "label": "Sin proveedor",
                "reason": "Este reporte no está asociado a un proveedor.",
                "compliance_pct": 0,
                "total_tracked": 0,
                "on_track": 0,
            },
            "document_state_counts": {
                "approved": 0,
                "in_review": 0,
                "uploaded": 0,
                "pending": 0,
                "needs_review": 0,
                "rejected": 0,
                "expired": 0,
                "exception": 0,
            },
            "workspace_id": None,
            "persona_type": None,
        }

    year = config.get("year") if isinstance(config, dict) else None
    return build_compliance_state_for_vendor(
        db, vendor_id=scope.vendor_id, year=year
    )
