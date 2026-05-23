"""Client notification helpers.

Notifications are the durable client-facing layer on top of uploads,
metadata generation, and reviewer decisions. They intentionally carry
plain-language titles/bodies so the UI can show them without exposing
internal validation-event names.

Phase 4 / Slice 4A — every emitter passes an explicit ``severity``
keyword. The canonical semáforo values are ``green`` (approved /
complete), ``yellow`` (pending / in review / due soon), ``red``
(rejected / missing / expired), and ``info`` (background automation,
non-actionable). Storing the choice per row instead of deriving it
from ``notification_type`` keeps future types free to pick their own
severity without retrofitting a global mapping.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from sqlalchemy.orm import Session

from app.constants.statuses import ReviewerAction
from app.models import ClientNotification, Submission, Vendor

NotificationSeverity = Literal["green", "yellow", "red", "info"]


def add_client_notification(
    db: Session,
    *,
    client_id: str,
    notification_type: str,
    severity: NotificationSeverity,
    title: str,
    body: str,
    vendor_id: str | None = None,
    submission_id: str | None = None,
    action_url: str | None = None,
    payload: dict | None = None,
) -> ClientNotification:
    row = ClientNotification(
        client_id=client_id,
        vendor_id=vendor_id,
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


def notify_provider_uploaded(
    db: Session,
    *,
    submission: Submission,
    vendor: Vendor,
    document_count: int = 1,
) -> ClientNotification:
    requirement = _requirement_label(submission)
    period = _period_label(submission)
    count_text = (
        "un documento"
        if document_count == 1
        else f"{document_count} documentos"
    )
    return add_client_notification(
        db,
        client_id=submission.client_id,
        vendor_id=submission.vendor_id,
        submission_id=submission.id,
        notification_type="provider_uploaded",
        # An upload sits in the review queue waiting for a human
        # decision — that's the canonical "pending" state.
        severity="yellow",
        title=f"{vendor.name} subio {count_text}",
        body=f"Recibimos {count_text} para {requirement}{period}.",
        action_url=f"/client/submissions?vendor_id={submission.vendor_id}",
        payload={
            "requirement_code": submission.requirement_code,
            "period_key": submission.period_key,
            "status": submission.status,
            "document_count": document_count,
        },
    )


def notify_metadata_ready(
    db: Session,
    *,
    submission: Submission,
    vendor: Vendor,
    master_path: str | None,
) -> ClientNotification:
    return add_client_notification(
        db,
        client_id=submission.client_id,
        vendor_id=submission.vendor_id,
        submission_id=submission.id,
        notification_type="metadata_ready",
        # Background automation completed; nothing for the client to
        # act on. Neutral severity keeps these from competing visually
        # with actionable approval / rejection rows.
        severity="info",
        title="Metadata actualizada",
        body=(
            f"El Excel maestro del cliente ya incluye la metadata de "
            f"{vendor.name}."
        ),
        action_url="/client/metadata",
        payload={
            "requirement_code": submission.requirement_code,
            "period_key": submission.period_key,
            "master_path": master_path,
        },
    )


def notify_reviewer_decision(
    db: Session,
    *,
    submission: Submission,
    action: ReviewerAction,
    reason: str | None,
    observations: str | None = None,
) -> ClientNotification:
    vendor = submission.vendor
    vendor_name = vendor.name if vendor else "Proveedor"
    label = _decision_label(action)
    body = f"{label} para {_requirement_label(submission)}{_period_label(submission)}."
    if reason:
        body = f"{body} Razón: {reason}"
    # Slice 9A — observations render as a distinct line so the client
    # admin can scan reason vs. context separately. Empty string
    # collapses to None upstream in the workflow service, so a blank
    # field never renders a stray "Observación:" heading.
    if observations:
        body = f"{body} Observación: {observations}"
    return add_client_notification(
        db,
        client_id=submission.client_id,
        vendor_id=submission.vendor_id,
        submission_id=submission.id,
        notification_type=f"document_{action.value}",
        severity=_severity_for_decision(action),
        title=f"{vendor_name}: {label.lower()}",
        body=body,
        action_url=f"/client/submissions?vendor_id={submission.vendor_id}",
        payload={
            "reviewer_action": action.value,
            "status": submission.status,
            "requirement_code": submission.requirement_code,
            "period_key": submission.period_key,
        },
    )


def notify_client_of_renewal_due_soon(
    db: Session,
    *,
    client_id: str,
    vendor: Vendor,
    requirement_code: str,
    requirement_name: str,
    due: date,
    threshold_days: int,
    cycle_anchor_date: date,
) -> ClientNotification:
    """Yellow client notification for an upcoming renewal threshold.

    Phase 6 / Slice 6B. Emitted by ``renewal_dispatch`` when a
    ``due_soon`` threshold (30, 14, or 7 days) is crossed for the
    first time on the current renewal cycle. The dispatcher inserts a
    ``RenewalReminder`` row before calling this so a retry on the same
    day does not re-emit. ``threshold_days`` is the cadence step that
    fired (positive int); ``due`` is the absolute renewal date so the
    client UI can render either ``"faltan 7 días"`` (from threshold)
    or the exact date.
    """
    days_left = threshold_days
    body = (
        f"Faltan {days_left} día(s) para renovar {requirement_name} de "
        f"{vendor.name}. Fecha de vencimiento: {due.isoformat()}."
    )
    return add_client_notification(
        db,
        client_id=client_id,
        vendor_id=vendor.id,
        notification_type="renewal_due_soon",
        severity="yellow",
        title=f"{vendor.name}: renueva {requirement_name} en {days_left} día(s)",
        body=body,
        action_url=f"/client/submissions?vendor_id={vendor.id}",
        payload={
            "requirement_code": requirement_code,
            "requirement_name": requirement_name,
            "threshold_days": threshold_days,
            "due_date": due.isoformat(),
            "cycle_anchor_date": cycle_anchor_date.isoformat(),
        },
    )


def notify_client_of_renewal_overdue(
    db: Session,
    *,
    client_id: str,
    vendor: Vendor,
    requirement_code: str,
    requirement_name: str,
    due: date,
    threshold_days: int,
    cycle_anchor_date: date,
) -> ClientNotification:
    """Red client notification for the day-of and weekly overdue nags.

    Phase 6 / Slice 6B. Threshold values are 0 (day of vencimiento),
    -7, -14, -21, -28 (weekly nags). Past -28 the dispatcher stops
    emitting — the slot stays "overdue" on the dashboard forever, but
    further nags would only be noise.
    """
    if threshold_days == 0:
        title = f"{vendor.name}: vence {requirement_name} hoy"
        body = (
            f"Hoy vence la renovación de {requirement_name} de {vendor.name}. "
            f"Pídele al proveedor que suba el documento actualizado."
        )
    else:
        days_overdue = -threshold_days
        title = (
            f"{vendor.name}: {requirement_name} vencido hace "
            f"{days_overdue} día(s)"
        )
        body = (
            f"La renovación de {requirement_name} de {vendor.name} venció el "
            f"{due.isoformat()} (hace {days_overdue} día(s))."
        )
    return add_client_notification(
        db,
        client_id=client_id,
        vendor_id=vendor.id,
        notification_type="renewal_overdue",
        severity="red",
        title=title,
        body=body,
        action_url=f"/client/submissions?vendor_id={vendor.id}",
        payload={
            "requirement_code": requirement_code,
            "requirement_name": requirement_name,
            "threshold_days": threshold_days,
            "due_date": due.isoformat(),
            "cycle_anchor_date": cycle_anchor_date.isoformat(),
        },
    )


def _severity_for_decision(action: ReviewerAction) -> NotificationSeverity:
    """Map a reviewer action onto a semáforo severity.

    Aligns with the locked Phase 4 vocabulary:
      * ``approve`` and ``mark_exception`` resolve the slot → green.
      * ``reject`` puts the ball back in the provider's court and
        carries explicit blame → red.
      * ``request_clarification`` is still pending an answer → yellow.
    """
    if action in (ReviewerAction.APPROVE, ReviewerAction.MARK_EXCEPTION):
        return "green"
    if action == ReviewerAction.REJECT:
        return "red"
    return "yellow"


def _requirement_label(submission: Submission) -> str:
    if submission.requirement and submission.requirement.name:
        return submission.requirement.name
    return submission.requirement_code or "el documento"


def _period_label(submission: Submission) -> str:
    return f" ({submission.period_key})" if submission.period_key else ""


def _decision_label(action: ReviewerAction) -> str:
    if action == ReviewerAction.APPROVE:
        return "Documento aprobado"
    if action == ReviewerAction.REJECT:
        return "Documento rechazado"
    if action == ReviewerAction.REQUEST_CLARIFICATION:
        return "Aclaracion solicitada"
    if action == ReviewerAction.MARK_EXCEPTION:
        return "Excepcion registrada"
    return "Documento revisado"
