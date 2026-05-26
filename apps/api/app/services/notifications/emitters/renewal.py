"""Phase 7 / Slice N4 — renewal threshold emitter (shadow mode).

Walks the renewal-bearing expediente requirements for a workspace,
identifies threshold crossings (same logic as the legacy
:mod:`app.services.renewal_dispatch`), and emits one envelope per
crossing through the unified dispatcher.

Shadow vs cutover
-----------------

This module runs in **shadow** at N4. It writes the audit trail and
the ``notification_dispatch`` idempotency row, and records what
channels routing *would have* fired for each recipient — but it does
not write ``ClientNotification`` / ``ProviderNotification`` rows,
does not send email, does not send WhatsApp. The legacy renewal
dispatcher remains user-visible authoritative until a follow-up
slice flips the cron's source of truth.

The shadow run is safe to enable in production today: it is purely
additive against the new tables and never produces a user-visible
notification or message.

Channel-decision recording
--------------------------

For each ``queued`` outcome we compute :func:`routing.decide` and
write the result onto the dispatch row using a shadow vocabulary:

    * ``would_send`` — routing returned ``True``; the real cutover
      would have sent on this channel.
    * ``would_skip`` — routing returned ``False``; the
      ``email_reason`` / ``whatsapp_reason`` column captures which
      rule excluded the channel.

When N4b promotes this path to authoritative, these strings flip
to the canonical ``sent`` / ``skipped_*`` set.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy.orm import Session

from app.core.compliance_catalog import (
    expediente_for_persona,
    normalize_persona_type,
)
from app.models import ProviderWorkspace, Vendor
from app.services.evidence_slots import (
    current_onboarding_submission_for_workspace,
    next_renewal_due_date,
    renewal_anchor_date,
)
from app.services.notifications.catalog import get_event
from app.services.notifications.dispatcher import DispatchMode, dispatch
from app.services.notifications.emitters._helpers import (
    record_shadow_channels,
    resolve_workspace_recipients,
)
from app.services.notifications.envelope import NotificationEnvelope
from app.services.renewal_dispatch import ALL_THRESHOLDS, thresholds_crossed

EmitSkipReason = Literal[
    "no_frequency",
    "no_anchor",
    "no_thresholds",
    "no_vendor",
    "no_recipients",
]


@dataclass(frozen=True)
class EmitOutcome:
    """Per-(workspace, requirement) emission outcome.

    Mirrors :class:`app.services.renewal_dispatch.DispatchOutcome`
    so the cron entry can render either result with the same
    formatter at cutover time.
    """

    workspace_id: str
    requirement_code: str
    requirement_name: str
    cycle_anchor_date: date | None
    due_date: date | None
    thresholds_queued: list[int]
    thresholds_deduped: list[int]
    skip_reason: EmitSkipReason | None = None


# Canonical map from threshold-days to catalog event_type. Positive
# threshold values are pre-due ("t-N"); zero and negatives map to
# the day-of and overdue strings ("t-0", "t+N"). Keys mirror
# ``ALL_THRESHOLDS`` exactly so an audit notices if the legacy
# cadence and the new fabric ever drift.
THRESHOLD_TO_EVENT_TYPE: dict[int, str] = {
    30: "renewal.threshold.t-30",
    14: "renewal.threshold.t-14",
    7: "renewal.threshold.t-7",
    0: "renewal.threshold.t-0",
    -7: "renewal.threshold.t+7",
    -14: "renewal.threshold.t+14",
    -21: "renewal.threshold.t+21",
    -28: "renewal.threshold.t+28",
}


def emit_renewals_for_workspace(
    db: Session,
    workspace: ProviderWorkspace,
    *,
    today: date,
    mode: DispatchMode = "shadow",
) -> list[EmitOutcome]:
    """Emit envelopes for every renewal threshold crossing.

    Mirrors :func:`app.services.renewal_dispatch.dispatch_renewals_for_workspace`
    one-for-one on inputs and the (workspace, requirement, threshold)
    loop, but produces envelopes rather than writing notifications.
    """
    # Catalog vocabulary cross-check — fail loud at import time would
    # be ideal, but the catalog import is structural. This assert
    # makes the threshold/event map a hard contract that any future
    # edit to ALL_THRESHOLDS must keep in lockstep with the catalog.
    assert set(ALL_THRESHOLDS) == set(THRESHOLD_TO_EVENT_TYPE.keys()), (
        "renewal_dispatch.ALL_THRESHOLDS and THRESHOLD_TO_EVENT_TYPE "
        "have drifted; reconcile both sides."
    )

    persona = normalize_persona_type(workspace.persona_type)
    vendor = db.get(Vendor, workspace.vendor_id)
    if vendor is None:
        return []

    outcomes: list[EmitOutcome] = []

    for req in expediente_for_persona(persona):
        if req.renewal_frequency_days is None:
            outcomes.append(
                EmitOutcome(
                    workspace_id=workspace.id,
                    requirement_code=req.code,
                    requirement_name=req.name,
                    cycle_anchor_date=None,
                    due_date=None,
                    thresholds_queued=[],
                    thresholds_deduped=[],
                    skip_reason="no_frequency",
                )
            )
            continue

        current = current_onboarding_submission_for_workspace(
            db, workspace=workspace, requirement_code=req.code
        )
        anchor = renewal_anchor_date(current)
        if anchor is None:
            outcomes.append(
                EmitOutcome(
                    workspace_id=workspace.id,
                    requirement_code=req.code,
                    requirement_name=req.name,
                    cycle_anchor_date=None,
                    due_date=None,
                    thresholds_queued=[],
                    thresholds_deduped=[],
                    skip_reason="no_anchor",
                )
            )
            continue

        due = next_renewal_due_date(
            anchor=anchor, frequency_days=req.renewal_frequency_days
        )
        if due is None:
            outcomes.append(
                EmitOutcome(
                    workspace_id=workspace.id,
                    requirement_code=req.code,
                    requirement_name=req.name,
                    cycle_anchor_date=anchor,
                    due_date=None,
                    thresholds_queued=[],
                    thresholds_deduped=[],
                    skip_reason="no_anchor",
                )
            )
            continue

        days_remaining = (due - today).days
        crossed = thresholds_crossed(days_remaining)
        if not crossed:
            outcomes.append(
                EmitOutcome(
                    workspace_id=workspace.id,
                    requirement_code=req.code,
                    requirement_name=req.name,
                    cycle_anchor_date=anchor,
                    due_date=due,
                    thresholds_queued=[],
                    thresholds_deduped=[],
                    skip_reason="no_thresholds",
                )
            )
            continue

        queued: list[int] = []
        deduped: list[int] = []
        for threshold in crossed:
            event_type = THRESHOLD_TO_EVENT_TYPE[threshold]
            event = get_event(event_type)
            recipients = resolve_workspace_recipients(
                db, workspace=workspace, allowed_roles=event.recipients
            )
            if not recipients:
                # No reachable users — record on the workspace-level
                # outcome via skip_reason; we cannot dispatch without
                # at least one recipient per envelope contract.
                continue

            envelope = NotificationEnvelope(
                event_type=event_type,
                dedupe_key=_dedupe_key(
                    workspace_id=workspace.id,
                    requirement_code=req.code,
                    cycle_anchor=anchor,
                    threshold=threshold,
                ),
                recipients=recipients,
                payload={
                    "vendor_name": vendor.name,
                    "vendor_rfc": vendor.rfc,
                    "requirement_code": req.code,
                    "requirement_name": req.name,
                    "due_on": due.isoformat(),
                    "days_remaining": days_remaining,
                    "cycle_anchor": anchor.isoformat(),
                    "threshold_days": threshold,
                },
            )
            result = dispatch(db, envelope, mode=mode)

            if mode == "shadow":
                for outcome in result.outcomes:
                    if outcome.status == "deduped":
                        continue
                    record_shadow_channels(db, outcome=outcome, event=event)

            if result.queued > 0:
                queued.append(threshold)
            else:
                deduped.append(threshold)

        outcomes.append(
            EmitOutcome(
                workspace_id=workspace.id,
                requirement_code=req.code,
                requirement_name=req.name,
                cycle_anchor_date=anchor,
                due_date=due,
                thresholds_queued=queued,
                thresholds_deduped=deduped,
                skip_reason=None,
            )
        )

    return outcomes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dedupe_key(
    *,
    workspace_id: str,
    requirement_code: str,
    cycle_anchor: date,
    threshold: int,
) -> str:
    """Stable string keyed on the same four dimensions as the legacy
    ``RenewalReminder`` unique constraint. Critical for parity during
    the shadow phase — two paths writing two anchors must converge."""
    return (
        f"workspace:{workspace_id}"
        f":req:{requirement_code}"
        f":cycle:{cycle_anchor.isoformat()}"
        f":t:{threshold}"
    )
