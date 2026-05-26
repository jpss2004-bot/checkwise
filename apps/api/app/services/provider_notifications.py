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

from datetime import date
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
    from app.services.notifications.categorize import derive_category

    row = ProviderNotification(
        workspace_id=workspace_id,
        submission_id=submission_id,
        notification_type=notification_type,
        severity=severity,
        # Phase 7 / Slice N9b — derive category at insert time so the
        # row carries it forward without depending on a backfill.
        category=derive_category(notification_type),
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


def notify_provider_of_renewal_due_soon(
    db: Session,
    *,
    workspace_id: str,
    requirement_code: str,
    requirement_name: str,
    due: date,
    threshold_days: int,
    cycle_anchor_date: date,
) -> ProviderNotification:
    """Yellow provider notification for an upcoming renewal threshold.

    Phase 6 / Slice 6B. Direct address — the provider IS the actor
    here, so the copy is imperative ("renueva tu CSF") rather than
    third-person like the client-side equivalent. ``action_url``
    points straight at the upload wizard pre-filled with the
    requirement code so the next click is the upload.
    """
    days_left = threshold_days
    title = f"Renueva {requirement_name} — faltan {days_left} día(s)"
    body = (
        f"Tu {requirement_name} vence el {due.isoformat()} "
        f"(faltan {days_left} día(s)). Sube la versión actualizada para "
        f"mantener tu expediente al corriente."
    )
    return add_provider_notification(
        db,
        workspace_id=workspace_id,
        notification_type="renewal_due_soon",
        severity="yellow",
        title=title,
        body=body,
        action_url=f"/portal/upload?requirement_code={requirement_code}",
        payload={
            "requirement_code": requirement_code,
            "requirement_name": requirement_name,
            "threshold_days": threshold_days,
            "due_date": due.isoformat(),
            "cycle_anchor_date": cycle_anchor_date.isoformat(),
        },
    )


def notify_provider_of_renewal_overdue(
    db: Session,
    *,
    workspace_id: str,
    requirement_code: str,
    requirement_name: str,
    due: date,
    threshold_days: int,
    cycle_anchor_date: date,
) -> ProviderNotification:
    """Red provider notification for the day-of and weekly overdue nags.

    Threshold values are 0 (day of vencimiento), -7, -14, -21, -28.
    Past -28 the dispatcher stops emitting.
    """
    if threshold_days == 0:
        title = f"Vence {requirement_name} hoy — renuévalo"
        body = (
            f"Tu {requirement_name} vence hoy. Sube la versión actualizada "
            f"para que tu cliente no marque el expediente como vencido."
        )
    else:
        days_overdue = -threshold_days
        title = f"{requirement_name} vencido hace {days_overdue} día(s)"
        body = (
            f"Tu {requirement_name} venció el {due.isoformat()} (hace "
            f"{days_overdue} día(s)). Sube la versión actualizada lo antes "
            f"posible para regularizar tu expediente."
        )
    return add_provider_notification(
        db,
        workspace_id=workspace_id,
        notification_type="renewal_overdue",
        severity="red",
        title=title,
        body=body,
        action_url=f"/portal/upload?requirement_code={requirement_code}",
        payload={
            "requirement_code": requirement_code,
            "requirement_name": requirement_name,
            "threshold_days": threshold_days,
            "due_date": due.isoformat(),
            "cycle_anchor_date": cycle_anchor_date.isoformat(),
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
