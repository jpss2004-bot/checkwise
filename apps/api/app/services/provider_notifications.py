"""Provider notification helpers.

Phase 4 / Slice 4B — portal-side analogue of
``client_notifications``. Today the only emit-site is the
reviewer-decision branch of ``submission_workflow.apply_reviewer_decision``;
the slice deliberately scopes to that single event so the surface
ships small. Future emit-sites (scheduled expiry, "due soon")
will land alongside their runners.

Severity vocabulary matches the client-side semáforo and the Slice
4A locked decision:
  * ``approve`` / ``mark_exception`` → ``green`` (slot resolved).
  * ``reject`` → ``red`` (provider must act).
  * ``request_clarification`` → ``yellow`` (still pending answer).

Locked behavior (Phase 4B):
  * The body INCLUDES the reviewer's reason when present so the
    provider sees the explanation without click-through.
  * If no ``ProviderWorkspace`` exists for the submission's
    (client_id, vendor_id), the emit is silently skipped — the
    reviewer flow must not break for legacy / partial seed data.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.statuses import ReviewerAction
from app.models import ProviderNotification, ProviderWorkspace, Submission

NotificationSeverity = Literal["green", "yellow", "red", "info"]


def add_provider_notification(
    db: Session,
    *,
    workspace_id: str,
    notification_type: str,
    severity: NotificationSeverity,
    title: str,
    body: str,
    submission_id: str | None = None,
    action_url: str | None = None,
    payload: dict | None = None,
) -> ProviderNotification:
    row = ProviderNotification(
        workspace_id=workspace_id,
        submission_id=submission_id,
        notification_type=notification_type,
        severity=severity,
        title=title,
        body=body,
        action_url=action_url,
        payload=payload,
    )
    db.add(row)
    return row


def notify_provider_of_reviewer_decision(
    db: Session,
    *,
    submission: Submission,
    action: ReviewerAction,
    reason: str | None,
    observations: str | None = None,
) -> ProviderNotification | None:
    """Emit a provider notification for a reviewer decision.

    Resolves the workspace via (client_id, vendor_id). Returns the
    inserted row on success, or ``None`` when no workspace matches
    (silent skip per the locked Phase 4B behavior).

    Slice 9A — body renders ``Razón`` and ``Observación`` on
    distinct lines when present, so the provider sees the formal
    reason and any operational context as two separate sentences
    without click-through.
    """
    workspace = db.scalar(
        select(ProviderWorkspace).where(
            ProviderWorkspace.client_id == submission.client_id,
            ProviderWorkspace.vendor_id == submission.vendor_id,
        )
    )
    if workspace is None:
        return None

    requirement_label = _requirement_label(submission)
    period_label = _period_label(submission)
    decision_label = _decision_label(action)
    body = f"{decision_label} para {requirement_label}{period_label}."
    if reason:
        body = f"{body} Razón: {reason}"
    if observations:
        body = f"{body} Observación: {observations}"

    return add_provider_notification(
        db,
        workspace_id=workspace.id,
        submission_id=submission.id,
        notification_type=f"document_{action.value}",
        severity=_severity_for_decision(action),
        title=decision_label,
        body=body,
        action_url=f"/portal/submissions/{submission.id}",
        payload={
            "reviewer_action": action.value,
            "status": submission.status,
            "requirement_code": submission.requirement_code,
            "period_key": submission.period_key,
        },
    )


def _severity_for_decision(action: ReviewerAction) -> NotificationSeverity:
    if action in (ReviewerAction.APPROVE, ReviewerAction.MARK_EXCEPTION):
        return "green"
    if action == ReviewerAction.REJECT:
        return "red"
    return "yellow"


def _decision_label(action: ReviewerAction) -> str:
    if action == ReviewerAction.APPROVE:
        return "Documento aprobado"
    if action == ReviewerAction.REJECT:
        return "Documento rechazado"
    if action == ReviewerAction.REQUEST_CLARIFICATION:
        return "Aclaración solicitada"
    if action == ReviewerAction.MARK_EXCEPTION:
        return "Excepción registrada"
    return "Documento revisado"


def _requirement_label(submission: Submission) -> str:
    if submission.requirement and submission.requirement.name:
        return submission.requirement.name
    return submission.requirement_code or "el documento"


def _period_label(submission: Submission) -> str:
    return f" ({submission.period_key})" if submission.period_key else ""
