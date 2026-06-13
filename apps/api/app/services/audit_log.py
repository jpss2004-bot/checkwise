from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog


def add_audit_event(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    actor_type: str = "system",
    actor_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    metadata: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    event = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_type=actor_type,
        actor_id=actor_id,
        before=before,
        after=after,
        event_metadata=metadata,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(event)
    return event
