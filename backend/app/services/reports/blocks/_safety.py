"""Defence-in-depth helpers for vendor-scoped block data fetchers.

Every block fetcher that reads vendor-scoped rows (P1.2+ provider
blocks: ``compliance_state``, ``attention_list``,
``upcoming_deadlines``, ``prioritized_actions``) must call
``assert_workspace_scope`` before issuing any DB query. The check is
redundant with the API-layer enforcement in
``services.report_service.list_reports`` / ``get_report`` — that
redundancy is the point.

Two reasons this lives in a separate module rather than inline in each
fetcher:

1. **Reviewability.** A new block author cannot ship a fetcher
   without importing from here. The import is a visible code-review
   signal that the fetcher was thought about against the trust
   boundary.
2. **One place to evolve.** When the actor gains multi-workspace
   visibility (a deferred follow-up), the rule changes in this
   module; every block fetcher picks the fix up for free.

This module deliberately does NOT import from ``services.reports.context``
to avoid an import cycle when block fetchers are wired into the
Context Assembler. It depends only on the long-standing
``report_service`` types.
"""

from __future__ import annotations

from app.constants.reports import ReportAudience
from app.services.report_service import (
    ReportActor,
    ReportPermissionError,
)
from app.services.reports.context import ReportScope


def assert_workspace_scope(*, actor: ReportActor, scope: ReportScope) -> None:
    """Raise ``ReportPermissionError`` when a vendor-only fetcher is
    invoked outside the caller's workspace.

    Rules:

    - ``audience != VENDOR_FACING`` → no-op. The vendor-only check only
      applies to vendor-facing block data; other audiences are gated by
      the normal RBAC in ``report_service``.
    - ``audience == VENDOR_FACING`` and ``actor.is_internal`` → no-op.
      Internal staff may author / fetch for any vendor.
    - ``audience == VENDOR_FACING`` and the caller is a workspace
      owner → ``scope.vendor_id`` must equal ``actor.workspace_vendor_id``.
    - Any other shape (non-internal, non-workspace-owner asking for
      vendor-facing data; missing ``vendor_id`` on scope) → raise.

    The error message is intentionally generic so it doesn't leak
    which check fired — the caller surfaces it as 403 / 404 at the API
    boundary as appropriate.
    """
    if scope.audience != ReportAudience.VENDOR_FACING:
        return

    if scope.vendor_id is None:
        raise ReportPermissionError(
            "Vendor-facing block scope requires a vendor_id."
        )

    if actor.is_internal:
        return

    if not actor.is_workspace_owner:
        raise ReportPermissionError(
            "Caller is not authorised to read vendor-facing block data."
        )

    if scope.vendor_id != actor.workspace_vendor_id:
        raise ReportPermissionError(
            "Caller is not authorised to read vendor-facing block data."
        )
