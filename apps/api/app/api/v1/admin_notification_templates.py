"""Phase 7 / Slice N3 — admin CRUD for versioned notification templates.

Endpoints (all internal-admin only):

  * ``GET    /api/v1/admin/notification-templates``
    Lists every template version, newest first. Optional query
    filters: ``event_type``, ``channel``, ``locale``, ``is_active``.

  * ``GET    /api/v1/admin/notification-templates/{template_id}``
    Single row by id.

  * ``POST   /api/v1/admin/notification-templates``
    Create a new version. The version number is auto-assigned as
    ``max(version for same event_type+channel+locale) + 1``. If
    ``set_active=true``, the prior active row (if any) is demoted
    in the same transaction so the swap is atomic.

  * ``POST   /api/v1/admin/notification-templates/{template_id}/activate``
    Atomically demote the current active row for the same key and
    promote ``template_id``. Idempotent — calling it twice on the
    already-active row is a no-op.

Every mutation writes an ``audit_log`` entry with
``action="admin.notification_template.<verb>"``.

Render-time invariants the dispatcher relies on (enforced here):

  * At most one row with ``is_active=true`` per
    ``(event_type, channel, locale)``. Enforced at the application
    layer inside a transaction; partial unique indexes are not
    portable to SQLite, which we use in tests.
  * ``meta_template_name`` only on WhatsApp rows; ``subject`` only
    on email rows. Validation rejects mismatches up front.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.v1.auth import CurrentUser, require_any_role
from app.constants.roles import MembershipRole
from app.db.session import get_db
from app.models import NotificationTemplateVersion
from app.services.audit_log import add_audit_event
from app.services.notifications.catalog import EVENT_TYPES

router = APIRouter(
    prefix="/admin/notification-templates",
    tags=["admin", "notifications"],
)
DbSession = Annotated[Session, Depends(get_db)]
AdminUser = Annotated[
    CurrentUser,
    Depends(
        require_any_role(
            MembershipRole.PLATFORM_ADMIN, MembershipRole.OPERATIONS_ADMIN
        )
    ),
]


def _actor_role(current: CurrentUser) -> str:
    """The acting staff role for an audit row — superadmin if held,
    otherwise the review team."""
    if MembershipRole.OPERATIONS_ADMIN.value in current.roles:
        return MembershipRole.OPERATIONS_ADMIN.value
    return MembershipRole.PLATFORM_ADMIN.value

TemplateChannel = Literal["email", "whatsapp", "inapp"]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TemplateOut(BaseModel):
    id: str
    event_type: str
    channel: TemplateChannel
    locale: str
    version: int
    subject: str | None
    body: str
    meta_template_name: str | None
    is_active: bool


class TemplateCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=80)
    channel: TemplateChannel
    locale: str = Field(default="es-MX", min_length=2, max_length=10)
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=1)
    meta_template_name: str | None = Field(default=None, max_length=80)
    set_active: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize(row: NotificationTemplateVersion) -> TemplateOut:
    return TemplateOut(
        id=row.id,
        event_type=row.event_type,
        channel=row.channel,  # type: ignore[arg-type]
        locale=row.locale,
        version=row.version,
        subject=row.subject,
        body=row.body,
        meta_template_name=row.meta_template_name,
        is_active=row.is_active,
    )


def _validate_channel_specific_fields(payload: TemplateCreate) -> None:
    """Subject is email-only; meta_template_name is whatsapp-only.

    Reject mismatches at the API boundary so an operator cannot
    create a row that will silently misbehave at render time.
    """
    if payload.channel == "email" and not payload.subject:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El canal email requiere un subject.",
        )
    if payload.channel != "email" and payload.subject:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El campo subject solo aplica al canal email.",
        )
    if payload.channel == "whatsapp" and not payload.meta_template_name:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El canal whatsapp requiere meta_template_name.",
        )
    if payload.channel != "whatsapp" and payload.meta_template_name:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El campo meta_template_name solo aplica al canal whatsapp.",
        )


def _activate(
    db: Session,
    *,
    target: NotificationTemplateVersion,
) -> None:
    """Atomically demote sibling active rows and promote ``target``.

    Both updates land inside the caller's outer transaction; if it
    rolls back, the swap is undone. The demote uses a single UPDATE
    statement rather than an ORM iteration so a key with many
    historical versions stays cheap.
    """
    db.execute(
        update(NotificationTemplateVersion)
        .where(
            NotificationTemplateVersion.event_type == target.event_type,
            NotificationTemplateVersion.channel == target.channel,
            NotificationTemplateVersion.locale == target.locale,
            NotificationTemplateVersion.is_active.is_(True),
            NotificationTemplateVersion.id != target.id,
        )
        .values(is_active=False)
    )
    target.is_active = True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[TemplateOut])
def list_templates(
    _: AdminUser,
    db: DbSession,
    event_type: Annotated[str | None, Query()] = None,
    channel: Annotated[TemplateChannel | None, Query()] = None,
    locale: Annotated[str | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> list[TemplateOut]:
    stmt = select(NotificationTemplateVersion).order_by(
        NotificationTemplateVersion.event_type,
        NotificationTemplateVersion.channel,
        NotificationTemplateVersion.locale,
        NotificationTemplateVersion.version.desc(),
    )
    if event_type is not None:
        stmt = stmt.where(NotificationTemplateVersion.event_type == event_type)
    if channel is not None:
        stmt = stmt.where(NotificationTemplateVersion.channel == channel)
    if locale is not None:
        stmt = stmt.where(NotificationTemplateVersion.locale == locale)
    if is_active is not None:
        stmt = stmt.where(NotificationTemplateVersion.is_active.is_(is_active))
    rows = db.execute(stmt).scalars().all()
    return [_serialize(r) for r in rows]


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(
    template_id: str,
    _: AdminUser,
    db: DbSession,
) -> TemplateOut:
    row = db.get(NotificationTemplateVersion, template_id)
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Plantilla no encontrada."
        )
    return _serialize(row)


@router.post(
    "",
    response_model=TemplateOut,
    status_code=status.HTTP_201_CREATED,
)
def create_template(
    payload: TemplateCreate,
    current: AdminUser,
    db: DbSession,
) -> TemplateOut:
    if payload.event_type not in EVENT_TYPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"event_type {payload.event_type!r} no está en el catálogo. "
                "Agrégalo a app.services.notifications.catalog antes de "
                "crear su plantilla."
            ),
        )
    _validate_channel_specific_fields(payload)

    # Next version number for this key.
    max_version = (
        db.execute(
            select(func.max(NotificationTemplateVersion.version)).where(
                NotificationTemplateVersion.event_type == payload.event_type,
                NotificationTemplateVersion.channel == payload.channel,
                NotificationTemplateVersion.locale == payload.locale,
            )
        ).scalar()
        or 0
    )

    row = NotificationTemplateVersion(
        event_type=payload.event_type,
        channel=payload.channel,
        locale=payload.locale,
        version=max_version + 1,
        subject=payload.subject,
        body=payload.body,
        meta_template_name=payload.meta_template_name,
        is_active=False,
    )
    db.add(row)
    db.flush()

    if payload.set_active:
        _activate(db, target=row)

    add_audit_event(
        db,
        action="admin.notification_template.created",
        entity_type="notification_template",
        entity_id=row.id,
        actor_type=_actor_role(current),
        actor_id=current.user.id,
        after={
            "event_type": row.event_type,
            "channel": row.channel,
            "locale": row.locale,
            "version": row.version,
            "is_active": row.is_active,
        },
    )
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.post(
    "/{template_id}/activate", response_model=TemplateOut
)
def activate_template(
    template_id: str,
    current: AdminUser,
    db: DbSession,
) -> TemplateOut:
    row = db.get(NotificationTemplateVersion, template_id)
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Plantilla no encontrada."
        )

    if row.is_active:
        # Idempotent — no audit row, no state change.
        return _serialize(row)

    # Capture the previously-active row id (if any) for the audit
    # log, before the demote UPDATE clears the flag.
    prior_active_id = db.execute(
        select(NotificationTemplateVersion.id).where(
            NotificationTemplateVersion.event_type == row.event_type,
            NotificationTemplateVersion.channel == row.channel,
            NotificationTemplateVersion.locale == row.locale,
            NotificationTemplateVersion.is_active.is_(True),
        )
    ).scalar_one_or_none()

    _activate(db, target=row)

    add_audit_event(
        db,
        action="admin.notification_template.activated",
        entity_type="notification_template",
        entity_id=row.id,
        actor_type=_actor_role(current),
        actor_id=current.user.id,
        before={"prior_active_id": prior_active_id},
        after={
            "event_type": row.event_type,
            "channel": row.channel,
            "locale": row.locale,
            "version": row.version,
        },
    )
    db.commit()
    db.refresh(row)
    return _serialize(row)
