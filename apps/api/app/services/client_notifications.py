"""Client notification helpers.

Notifications are the durable client-facing layer on top of uploads,
metadata generation, and reviewer decisions. They intentionally carry
plain-language titles/bodies so the UI can show them without exposing
internal validation-event names.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.constants.statuses import ReviewerAction
from app.models import ClientNotification, Submission, Vendor


def add_client_notification(
    db: Session,
    *,
    client_id: str,
    notification_type: str,
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
) -> ClientNotification:
    vendor = submission.vendor
    vendor_name = vendor.name if vendor else "Proveedor"
    label = _decision_label(action)
    body = f"{label} para {_requirement_label(submission)}{_period_label(submission)}."
    if reason:
        body = f"{body} Nota: {reason}"
    return add_client_notification(
        db,
        client_id=submission.client_id,
        vendor_id=submission.vendor_id,
        submission_id=submission.id,
        notification_type=f"document_{action.value}",
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
