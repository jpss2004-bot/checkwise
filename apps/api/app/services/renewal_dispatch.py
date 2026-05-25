"""Phase 6 / Slice 6B — renewal notification dispatcher.

Walks the renewal-bearing onboarding requirements for a workspace,
computes which threshold crossings have happened since the last run,
and emits one client + one provider notification per *new* crossing.

The dedupe mechanism is the ``renewal_reminders`` table's unique
constraint on ``(workspace_id, requirement_code, cycle_anchor_date,
threshold_days)``. The dispatcher inserts that row first; a
``IntegrityError`` on collision means "already emitted, skip" without
writing any notifications. SAVEPOINT (``begin_nested``) isolates each
threshold so a single dupe does not poison the outer transaction.

Cycle reset semantics: ``cycle_anchor_date`` is part of the unique
key. When a provider uploads a new approved CSF / REPSE / patronal,
``renewal_anchor_date`` returns a different value → new cycle → all
threshold slots are fresh under the new anchor and fire again as the
new cycle progresses. The historical reminders for the prior cycle
stay on the table as the audit record.

Commit boundary: this service NEVER commits. The caller (the manual
CLI in Slice 6B, a scheduler in Slice 6C, a future HTTP admin
endpoint) owns the commit so reminders and notifications either both
land or both roll back together.

Out of scope here:
    * Scheduler / runner (Slice 6C).
    * Email / WhatsApp delivery (deferred per the locked roadmap).
    * Recurring-calendar renewals — the calendar service already drives
      its own "due soon" via the dashboard suggested-actions list and
      does not need this dispatcher.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.compliance_catalog import (
    expediente_for_persona,
    normalize_persona_type,
)
from app.models import ProviderWorkspace, RenewalReminder, Vendor
from app.services.client_notifications import (
    notify_client_of_renewal_due_soon,
    notify_client_of_renewal_overdue,
)
from app.services.evidence_slots import (
    current_onboarding_submission_for_workspace,
    next_renewal_due_date,
    renewal_anchor_date,
)
from app.services.provider_notifications import (
    notify_provider_of_renewal_due_soon,
    notify_provider_of_renewal_overdue,
)
from app.services.transactional_email import (
    email_renewal_threshold_crossed,
)

# Locked Phase 6 cadence (gate question answered 2026-05-23).
# Order matters: descending so the dispatcher fires more-urgent
# crossings after less-urgent ones — useful only for human-reading
# ordering, the unique constraint handles correctness regardless.
YELLOW_THRESHOLDS: tuple[int, ...] = (30, 14, 7)
RED_THRESHOLDS: tuple[int, ...] = (0, -7, -14, -21, -28)
ALL_THRESHOLDS: tuple[int, ...] = YELLOW_THRESHOLDS + RED_THRESHOLDS

DispatchSkipReason = Literal[
    "no_frequency",   # requirement is one-time onboarding, no cadence
    "no_anchor",      # cadence exists but no approved submission yet
    "no_thresholds",  # cadence + anchor exist but nothing has crossed
]


@dataclass(frozen=True)
class DispatchOutcome:
    """Per-(workspace, requirement) result of one dispatch pass.

    Distinguishes three causes for an "empty" outcome (no thresholds
    fired this run) so the CLI / future runner can log meaningfully
    instead of just "0 notifications".
    """

    workspace_id: str
    requirement_code: str
    requirement_name: str
    cycle_anchor_date: date | None
    due_date: date | None
    thresholds_fired: list[int] = field(default_factory=list)
    thresholds_skipped_existing: list[int] = field(default_factory=list)
    skip_reason: DispatchSkipReason | None = None


def thresholds_crossed(days_remaining: int) -> list[int]:
    """Return every threshold T such that ``days_remaining <= T``.

    A 30-day-out anchor crosses only T=30. A 5-day-out anchor crosses
    {30, 14, 7}. A 10-day-overdue anchor crosses {30, 14, 7, 0, -7}.
    Past T=-28 the set saturates — no further thresholds are emitted,
    so the dispatcher naturally goes silent ~4 weeks past due.

    The list is returned in the canonical cadence order (most urgent
    last) so callers iterating it emit older crossings first.
    """
    return [t for t in ALL_THRESHOLDS if days_remaining <= t]


def _severity_for_threshold(threshold: int) -> str:
    return "yellow" if threshold > 0 else "red"


def dispatch_renewals_for_workspace(
    db: Session,
    workspace: ProviderWorkspace,
    *,
    today: date,
) -> list[DispatchOutcome]:
    """Emit renewal reminders for all renewal-bearing requirements.

    Returns one :class:`DispatchOutcome` per renewal-bearing
    requirement that applies to the workspace's persona type. The
    caller is responsible for committing the session — neither this
    function nor the helpers it calls commit.

    Notifications and the ``RenewalReminder`` row land in the same
    outer transaction. If the caller rolls back, all of them roll
    back together.
    """
    persona = normalize_persona_type(workspace.persona_type)
    vendor = db.get(Vendor, workspace.vendor_id)
    if vendor is None:
        # Defensive — a workspace without its vendor row is data
        # corruption that should be surfaced upstream, but we should
        # not crash the dispatcher for it.
        return []

    outcomes: list[DispatchOutcome] = []

    for req in expediente_for_persona(persona):
        if req.renewal_frequency_days is None:
            outcomes.append(
                DispatchOutcome(
                    workspace_id=workspace.id,
                    requirement_code=req.code,
                    requirement_name=req.name,
                    cycle_anchor_date=None,
                    due_date=None,
                    skip_reason="no_frequency",
                )
            )
            continue

        current = current_onboarding_submission_for_workspace(
            db,
            workspace=workspace,
            requirement_code=req.code,
        )
        anchor = renewal_anchor_date(current)
        if anchor is None:
            outcomes.append(
                DispatchOutcome(
                    workspace_id=workspace.id,
                    requirement_code=req.code,
                    requirement_name=req.name,
                    cycle_anchor_date=None,
                    due_date=None,
                    skip_reason="no_anchor",
                )
            )
            continue

        due = next_renewal_due_date(
            anchor=anchor,
            frequency_days=req.renewal_frequency_days,
        )
        if due is None:
            # Should not happen — both inputs are present — but
            # treat as no_anchor for the caller's sake.
            outcomes.append(
                DispatchOutcome(
                    workspace_id=workspace.id,
                    requirement_code=req.code,
                    requirement_name=req.name,
                    cycle_anchor_date=anchor,
                    due_date=None,
                    skip_reason="no_anchor",
                )
            )
            continue

        days_remaining = (due - today).days
        crossed = thresholds_crossed(days_remaining)
        if not crossed:
            outcomes.append(
                DispatchOutcome(
                    workspace_id=workspace.id,
                    requirement_code=req.code,
                    requirement_name=req.name,
                    cycle_anchor_date=anchor,
                    due_date=due,
                    skip_reason="no_thresholds",
                )
            )
            continue

        fired: list[int] = []
        skipped: list[int] = []

        for threshold in crossed:
            severity = _severity_for_threshold(threshold)
            try:
                # SAVEPOINT so the IntegrityError on collision does
                # not abort the outer transaction. Postgres + SQLite
                # both support nested via SAVEPOINT.
                with db.begin_nested():
                    db.add(
                        RenewalReminder(
                            workspace_id=workspace.id,
                            requirement_code=req.code,
                            cycle_anchor_date=anchor,
                            threshold_days=threshold,
                            severity=severity,
                        )
                    )
            except IntegrityError:
                skipped.append(threshold)
                continue

            # Reminder insert succeeded — emit both notifications.
            # They land in the outer transaction alongside the
            # reminder row; rollback at commit-time undoes the whole
            # set together.
            if threshold > 0:
                notify_client_of_renewal_due_soon(
                    db,
                    client_id=workspace.client_id,
                    vendor=vendor,
                    requirement_code=req.code,
                    requirement_name=req.name,
                    due=due,
                    threshold_days=threshold,
                    cycle_anchor_date=anchor,
                )
                notify_provider_of_renewal_due_soon(
                    db,
                    workspace_id=workspace.id,
                    requirement_code=req.code,
                    requirement_name=req.name,
                    due=due,
                    threshold_days=threshold,
                    cycle_anchor_date=anchor,
                )
            else:
                notify_client_of_renewal_overdue(
                    db,
                    client_id=workspace.client_id,
                    vendor=vendor,
                    requirement_code=req.code,
                    requirement_name=req.name,
                    due=due,
                    threshold_days=threshold,
                    cycle_anchor_date=anchor,
                )
                notify_provider_of_renewal_overdue(
                    db,
                    workspace_id=workspace.id,
                    requirement_code=req.code,
                    requirement_name=req.name,
                    due=due,
                    threshold_days=threshold,
                    cycle_anchor_date=anchor,
                )

            # Junta 2026-05-25 — also email the provider AND the
            # client_admin. Best-effort: skipped/failed returns don't
            # raise, the in-app notifications above are the canonical
            # delivery. Imported lazily inside the dispatcher so an
            # import-time failure (no SMTP config, missing module)
            # never breaks the cron.
            try:
                from app.core.config import settings as _settings

                email_renewal_threshold_crossed(
                    db,
                    workspace=workspace,
                    vendor=vendor,
                    requirement_code=req.code,
                    requirement_name=req.name,
                    due_date=due,
                    days_remaining=threshold,
                    severity=severity,
                    portal_base_url=_settings.FRONTEND_BASE_URL,
                    client_portal_base_url=_settings.FRONTEND_BASE_URL,
                )
            except Exception:  # pragma: no cover — defensive
                import logging as _logging

                _logging.getLogger(
                    "checkwise.renewal_dispatch"
                ).exception(
                    "[renewal_dispatch] outbound email crashed; reminder still fired"
                )

            # M-WA (2026-05-25) — WhatsApp delivery for users on
            # contact_preference={"whatsapp","both"}. Independent of
            # email above: a failure on one channel never blocks the
            # other. Lazy import so a missing module / broken Meta
            # token can never break the cron at import time.
            try:
                from app.services.transactional_whatsapp import (
                    whatsapp_renewal_threshold_crossed,
                )

                whatsapp_renewal_threshold_crossed(
                    db,
                    workspace=workspace,
                    vendor=vendor,
                    requirement_name=req.name,
                    due_date=due,
                    days_remaining=threshold,
                    severity=severity,
                )
            except Exception:  # pragma: no cover — defensive
                import logging as _logging

                _logging.getLogger(
                    "checkwise.renewal_dispatch"
                ).exception(
                    "[renewal_dispatch] outbound whatsapp crashed; reminder still fired"
                )

            fired.append(threshold)

        outcomes.append(
            DispatchOutcome(
                workspace_id=workspace.id,
                requirement_code=req.code,
                requirement_name=req.name,
                cycle_anchor_date=anchor,
                due_date=due,
                thresholds_fired=fired,
                thresholds_skipped_existing=skipped,
            )
        )

    return outcomes


__all__ = [
    "ALL_THRESHOLDS",
    "DispatchOutcome",
    "DispatchSkipReason",
    "RED_THRESHOLDS",
    "YELLOW_THRESHOLDS",
    "dispatch_renewals_for_workspace",
    "thresholds_crossed",
]
