from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ValidationEvent


def add_validation_event(
    db: Session,
    *,
    submission_id: str,
    document_id: str | None,
    event_type: str,
    result: str,
    severity: str = "info",
    rule_code: str | None = None,
    message: str | None = None,
    confidence: float | None = None,
    payload: dict | None = None,
    actor_type: str = "system",
) -> ValidationEvent:
    event = ValidationEvent(
        submission_id=submission_id,
        document_id=document_id,
        event_type=event_type,
        rule_code=rule_code,
        result=result,
        severity=severity,
        message=message,
        confidence=confidence,
        payload=payload,
        actor_type=actor_type,
    )
    db.add(event)
    return event
