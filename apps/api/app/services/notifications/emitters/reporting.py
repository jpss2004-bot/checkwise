"""Phase 7 / Slice N6 — periodic reporting emitter (shadow mode).

Walks the recurring REPSE calendar for a workspace and emits one
envelope per crossed threshold for each (workspace, requirement,
period) triple that has no submission yet.

Threshold cadence (Group B of the Phase 7 plan):

    * ``reporting.window.opened``     — fires on day 1 of the due
                                        month (window is open, provider
                                        can start uploading).
    * ``reporting.due.t-7``           — 7 days before the due date.
    * ``reporting.due.t-1``           — 1 day before.
    * ``reporting.due.t-0``           — day of the due date.
    * ``reporting.overdue.t+3``       — 3 days overdue (terminal).

Cumulative-crossing semantics — same shape as the renewal emitter:
the first cron pass after a workspace becomes eligible fires every
crossed threshold in one go, and idempotency ensures subsequent
passes are silent. A submission landing for ``(requirement_code,
period_key)`` suppresses all further events for that triple, because
the existing-submission check sits before the threshold loop.

Window-opened threshold: the "days before due" value depends on
``RecurringRequirement.due_day`` (default 17). For the canonical
day-17 monthly cadence, ``window_opened_days_before_due == 16``
(today is day 1 of the due month). For the annual SAT declaration
(due April 30), the window opens 29 days out.

Shadow mode contract — same as N4 + N5. This module writes
``notification_dispatch`` + ``audit_log`` rows and stamps the
routing decision as ``would_send`` / ``would_skip``. It does not
write in-app rows, send email, or send WhatsApp.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.compliance_catalog import (
    RecurringRequirement,
    normalize_persona_type,
    recurring_for_year,
)
from app.models import ProviderWorkspace, Submission, Vendor
from app.services.notifications.catalog import get_event
from app.services.notifications.dispatcher import DispatchMode, dispatch
from app.services.notifications.emitters._helpers import (
    record_shadow_channels,
    resolve_workspace_recipients,
)
from app.services.notifications.envelope import NotificationEnvelope

ReportingSkipReason = Literal[
    "submission_present",  # provider already submitted for this period
    "no_thresholds",       # eligible but no threshold crossed yet
    "no_recipients",       # workspace has no resolvable recipient
]


@dataclass(frozen=True)
class ReportingEmitOutcome:
    """One result per (workspace, requirement, period) triple."""

    workspace_id: str
    requirement_code: str
    period_key: str
    due_date: date
    thresholds_queued: list[str]
    thresholds_deduped: list[str]
    skip_reason: ReportingSkipReason | None = None


# Canonical map from threshold name to catalog event_type. Order
# is informational ("less urgent first") so emit ordering matches
# the renewal cadence convention.
REPORTING_THRESHOLD_TO_EVENT: dict[str, str] = {
    "window.opened": "reporting.window.opened",
    "due.t-7": "reporting.due.t-7",
    "due.t-1": "reporting.due.t-1",
    "due.t-0": "reporting.due.t-0",
    "overdue.t+3": "reporting.overdue.t+3",
}


def reporting_thresholds_crossed(
    days_remaining: int, *, window_opened_days_before_due: int
) -> list[str]:
    """Return every threshold T such that ``days_remaining <= T``.

    The list is returned in canonical cadence order (window_opened
    first, overdue last) so a fresh workspace catching up fires
    older crossings before more urgent ones.
    """
    crossed: list[str] = []
    if days_remaining <= window_opened_days_before_due:
        crossed.append("window.opened")
    if days_remaining <= 7:
        crossed.append("due.t-7")
    if days_remaining <= 1:
        crossed.append("due.t-1")
    if days_remaining <= 0:
        crossed.append("due.t-0")
    if days_remaining <= -3:
        crossed.append("overdue.t+3")
    return crossed


def emit_reporting_for_workspace(
    db: Session,
    workspace: ProviderWorkspace,
    *,
    today: date,
    mode: DispatchMode = "shadow",
) -> list[ReportingEmitOutcome]:
    """Emit envelopes for every crossed reporting threshold.

    The caller owns the outer transaction — same discipline as the
    renewal emitter. Replays land via the dispatch idempotency
    table; running this on the same day twice produces zero new
    rows on the second pass.
    """
    persona = normalize_persona_type(workspace.persona_type)
    vendor = db.get(Vendor, workspace.vendor_id)
    if vendor is None:
        return []

    catalog: list[RecurringRequirement] = list(
        recurring_for_year(today.year, persona)
    )
    by_slot = _index_submissions(db, workspace=workspace)

    outcomes: list[ReportingEmitOutcome] = []

    for req in catalog:
        due_date = date(today.year, req.due_month, req.due_day)
        days_remaining = (due_date - today).days

        # A submission for this (requirement_code, period_key)
        # short-circuits every threshold — the provider is done.
        if (req.code, req.period_key) in by_slot:
            outcomes.append(
                ReportingEmitOutcome(
                    workspace_id=workspace.id,
                    requirement_code=req.code,
                    period_key=req.period_key,
                    due_date=due_date,
                    thresholds_queued=[],
                    thresholds_deduped=[],
                    skip_reason="submission_present",
                )
            )
            continue

        # ``due_day - 1`` is the day-count remaining when today is
        # the first day of the due month. Pre-N6 we hard-coded this
        # but per-requirement due_day shifts the window opener for
        # the annual SAT obligation (day 30 in April).
        window_offset = max(req.due_day - 1, 7)
        crossed = reporting_thresholds_crossed(
            days_remaining, window_opened_days_before_due=window_offset
        )
        if not crossed:
            outcomes.append(
                ReportingEmitOutcome(
                    workspace_id=workspace.id,
                    requirement_code=req.code,
                    period_key=req.period_key,
                    due_date=due_date,
                    thresholds_queued=[],
                    thresholds_deduped=[],
                    skip_reason="no_thresholds",
                )
            )
            continue

        queued: list[str] = []
        deduped: list[str] = []
        for threshold_name in crossed:
            event_type = REPORTING_THRESHOLD_TO_EVENT[threshold_name]
            event = get_event(event_type)
            recipients = resolve_workspace_recipients(
                db, workspace=workspace, allowed_roles=event.recipients
            )
            if not recipients:
                continue

            envelope = NotificationEnvelope(
                event_type=event_type,
                dedupe_key=_dedupe_key(
                    workspace_id=workspace.id,
                    requirement_code=req.code,
                    period_key=req.period_key,
                    threshold_name=threshold_name,
                ),
                recipients=recipients,
                payload={
                    "vendor_name": vendor.name,
                    "vendor_rfc": vendor.rfc,
                    "requirement_code": req.code,
                    "requirement_name": req.name,
                    "institution": req.institution,
                    "frequency": req.frequency,
                    "period_key": req.period_key,
                    "period_label": req.period_label,
                    "due_on": due_date.isoformat(),
                    "days_remaining": days_remaining,
                },
            )
            result = dispatch(db, envelope, mode=mode)

            if mode == "shadow":
                for outcome in result.outcomes:
                    if outcome.status == "deduped":
                        continue
                    record_shadow_channels(db, outcome=outcome, event=event)

            if result.queued > 0:
                queued.append(threshold_name)
            else:
                deduped.append(threshold_name)

        outcomes.append(
            ReportingEmitOutcome(
                workspace_id=workspace.id,
                requirement_code=req.code,
                period_key=req.period_key,
                due_date=due_date,
                thresholds_queued=queued,
                thresholds_deduped=deduped,
                skip_reason=None,
            )
        )

    return outcomes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _index_submissions(
    db: Session, *, workspace: ProviderWorkspace
) -> dict[tuple[str, str], list[Submission]]:
    """Index workspace submissions by ``(requirement_code, period_key)``.

    Same shape as :func:`app.services.evidence_slots.build_workspace_calendar_slots`
    so the suppression logic at the top of the emitter aligns with
    what the calendar UI shows. Submissions without both keys are
    skipped — they cannot suppress a calendar slot.
    """
    rows = db.scalars(
        select(Submission).where(
            Submission.client_id == workspace.client_id,
            Submission.vendor_id == workspace.vendor_id,
        )
    ).all()
    by_slot: dict[tuple[str, str], list[Submission]] = {}
    for sub in rows:
        if not sub.requirement_code or not sub.period_key:
            continue
        by_slot.setdefault(
            (sub.requirement_code, sub.period_key), []
        ).append(sub)
    return by_slot


def _dedupe_key(
    *,
    workspace_id: str,
    requirement_code: str,
    period_key: str,
    threshold_name: str,
) -> str:
    """Stable key per (workspace, requirement, period, threshold).

    Includes the period_key so consecutive months under the same
    requirement_code emit independently. Period_key itself encodes
    the year, so a workspace that lives across years generates a
    fresh row set automatically when January's catalog rolls over.
    """
    return (
        f"workspace:{workspace_id}"
        f":req:{requirement_code}"
        f":period:{period_key}"
        f":t:{threshold_name}"
    )
