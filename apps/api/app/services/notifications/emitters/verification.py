"""Phase 7 / Slice N5 — verification lifecycle emitter (shadow mode).

Three event sites in the document lifecycle:

  * ``submission.received`` — fires on intake completion (provider
    has finished uploading; the document is queued for review).
  * ``submission.in_review`` — fires when a reviewer claims the
    submission and begins evaluation.
  * ``submission.{approved,rejected,clarification_requested}`` —
    fires on reviewer decision.

All five are info/critical events whose catalog rows declare a
``recipients`` tuple. This emitter resolves the workspace from the
submission's ``(client_id, vendor_id)`` pair (same lookup as
:func:`app.services.transactional_email.email_provider_of_reviewer_decision`)
and produces envelopes through the unified dispatcher.

Shadow mode contract — same as the renewal emitter at N4. This
module writes ``notification_dispatch`` + ``audit_log`` rows and
records the routing decision in shadow vocabulary
(``would_send`` / ``would_skip``). It does NOT write
``ProviderNotification`` or ``ClientNotification`` rows, send
email, or send WhatsApp. The existing reviewer-decision endpoints
remain authoritative for user-visible delivery; a follow-up slice
flips the call sites.

Action mapping — :class:`app.constants.statuses.ReviewerAction` →
event_type:

    * ``APPROVE``                → ``submission.approved``
    * ``REJECT``                 → ``submission.rejected``
    * ``REQUEST_CLARIFICATION``  → ``submission.clarification_requested``
    * ``MARK_EXCEPTION``         → (no catalog event; caller skips)
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.statuses import ReviewerAction
from app.models import ProviderWorkspace, Submission, Vendor
from app.services.notifications.catalog import get_event
from app.services.notifications.dispatcher import (
    DispatchMode,
    DispatchResult,
    dispatch,
)
from app.services.notifications.emitters._helpers import (
    record_shadow_channels,
    resolve_workspace_recipients,
)
from app.services.notifications.envelope import NotificationEnvelope

REVIEWER_ACTION_EVENT_TYPE: dict[str, str] = {
    ReviewerAction.APPROVE.value: "submission.approved",
    ReviewerAction.REJECT.value: "submission.rejected",
    ReviewerAction.REQUEST_CLARIFICATION.value: "submission.clarification_requested",
    # MARK_EXCEPTION intentionally absent — no catalog event at N5.
}


def emit_submission_received(
    db: Session,
    *,
    submission: Submission,
    mode: DispatchMode = "shadow",
) -> DispatchResult | None:
    """Fire ``submission.received`` for the provider workspace owner.

    Returns ``None`` when there is no resolvable workspace owner or
    when the dispatch was fully deduped — callers should treat None
    as "nothing to chain off of" and continue.
    """
    return _emit_for_submission(
        db,
        submission=submission,
        event_type="submission.received",
        dedupe_suffix="received",
        extra_payload={},
        mode=mode,
    )


def emit_submission_in_review(
    db: Session,
    *,
    submission: Submission,
    mode: DispatchMode = "shadow",
) -> DispatchResult | None:
    """Fire ``submission.in_review`` when a reviewer claims the doc."""
    return _emit_for_submission(
        db,
        submission=submission,
        event_type="submission.in_review",
        dedupe_suffix="in_review",
        extra_payload={},
        mode=mode,
    )


def emit_reviewer_decision(
    db: Session,
    *,
    submission: Submission,
    action: str,
    reason: str | None = None,
    mode: DispatchMode = "shadow",
) -> DispatchResult | None:
    """Fire the event matching the reviewer's terminal decision.

    Unknown / unsupported actions (e.g. ``mark_exception`` at N5)
    return ``None`` without writing anything. The caller can fall
    back to the legacy decision path with the same idempotency
    guarantees as today.
    """
    event_type = REVIEWER_ACTION_EVENT_TYPE.get(action)
    if event_type is None:
        return None
    return _emit_for_submission(
        db,
        submission=submission,
        event_type=event_type,
        # ``action`` is part of the dedupe key so a reviewer who
        # later changes their decision (reject → approve) gets a
        # fresh envelope under the new action.
        dedupe_suffix=action,
        extra_payload={"reason": reason or ""},
        mode=mode,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _emit_for_submission(
    db: Session,
    *,
    submission: Submission,
    event_type: str,
    dedupe_suffix: str,
    extra_payload: dict,
    mode: DispatchMode = "shadow",
) -> DispatchResult | None:
    event = get_event(event_type)

    workspace = db.scalar(
        select(ProviderWorkspace).where(
            ProviderWorkspace.client_id == submission.client_id,
            ProviderWorkspace.vendor_id == submission.vendor_id,
        )
    )
    if workspace is None:
        return None

    recipients = resolve_workspace_recipients(
        db, workspace=workspace, allowed_roles=event.recipients
    )
    if not recipients:
        return None

    vendor = db.get(Vendor, submission.vendor_id)
    requirement_name = (
        submission.requirement.name
        if submission.requirement is not None
        else (submission.requirement_code or "Documento")
    )

    payload = {
        "submission_id": submission.id,
        "requirement_code": submission.requirement_code or "",
        "requirement_name": requirement_name,
        "vendor_name": vendor.name if vendor else "",
        "vendor_rfc": vendor.rfc if vendor else "",
        "period_key": submission.period_key or "",
        "status": submission.status,
    }
    payload.update(extra_payload)

    envelope = NotificationEnvelope(
        event_type=event_type,
        dedupe_key=f"submission:{submission.id}:{dedupe_suffix}",
        recipients=recipients,
        payload=payload,
    )
    result = dispatch(db, envelope, mode=mode)

    if mode == "shadow":
        for outcome in result.outcomes:
            if outcome.status == "deduped":
                continue
            record_shadow_channels(db, outcome=outcome, event=event)

    return result
