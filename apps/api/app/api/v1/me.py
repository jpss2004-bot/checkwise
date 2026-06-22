"""Phase 7 / Slice N2 — per-user notification preferences endpoint.

Surfaces the mute matrix and channel preference the routing
function in :mod:`app.services.notifications.routing` consumes.

Routes:

  * ``GET /api/v1/me/notification-preferences`` — returns the
    current user's contact preference, WhatsApp verification state,
    and the full per-category mute matrix. The response always
    contains a row for every catalog category, even when the user
    has no override on the table — absence in the DB is materialized
    as ``email_muted=False, whatsapp_muted=False`` in the response
    so the frontend can render a complete toggle grid.

  * ``PUT /api/v1/me/notification-preferences`` — updates the
    ``contact_preference`` field on ``users`` and upserts category
    mute rows. The payload accepts a partial ``categories`` list:
    omitted categories keep their current state (or the default).

Phone identity is intentionally read-only here. ``phone_e164`` and
``phone_verified_at`` change only via the OTP verification flow
that lands in Slice N8; surfacing them on this endpoint as
mutable would let a user bypass verification.

Provider-workspace recipients do not have ``User`` rows yet, so
this endpoint is staff-only at N2. Provider preference capture
arrives with the alta-form work in Slice N8.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth import CurrentUser, get_current_user
from app.core.rate_limit import (
    _RATE_LIMITED_DETAIL,
    hash_identifier,
    phone_verify_limiter,
)
from app.db.session import get_db
from app.models import User, UserNotificationPreference
from app.models.entities import utc_now
from app.services.audit_log import add_audit_event
from app.services.notifications import emit_whatsapp_verified
from app.services.notifications.catalog import EventCategory
from app.services.phone_verification import (
    confirm_verification,
    request_verification,
)
from app.services.whatsapp_delivery import (
    normalize_phone_e164,
    send_whatsapp_template,
)
from app.services.whatsapp_templates import (
    PHONE_OTP_TEMPLATE,
    build_phone_otp_components,
)

router = APIRouter(prefix="/me", tags=["me"])
DbSession = Annotated[Session, Depends(get_db)]

# Single source of truth for which categories the matrix surfaces.
# Mirrors :data:`app.services.notifications.catalog.EventCategory`
# but pinned here so the API response order is deterministic.
_CATEGORIES: tuple[EventCategory, ...] = (
    "renewal",
    "reporting",
    "verification",
    "account",
    "admin",
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CategoryMute(BaseModel):
    category: EventCategory
    email_muted: bool = False
    whatsapp_muted: bool = False


class CategoryMuteIn(BaseModel):
    category: EventCategory
    email_muted: bool = False
    whatsapp_muted: bool = False


class NotificationPreferencesResponse(BaseModel):
    contact_preference: Literal["email", "whatsapp", "both"]
    phone_e164: str | None
    phone_verified: bool
    whatsapp_opt_in_at: datetime | None
    categories: list[CategoryMute]


class NotificationPreferencesUpdate(BaseModel):
    contact_preference: (
        Literal["email", "whatsapp", "both"] | None
    ) = None
    categories: list[CategoryMuteIn] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_mute_map(
    db: Session, user_id: str
) -> dict[str, UserNotificationPreference]:
    rows = (
        db.execute(
            select(UserNotificationPreference).where(
                UserNotificationPreference.user_id == user_id
            )
        )
        .scalars()
        .all()
    )
    return {row.category: row for row in rows}


def _build_response(
    user: User, mute_map: dict[str, UserNotificationPreference]
) -> NotificationPreferencesResponse:
    return NotificationPreferencesResponse(
        contact_preference=user.contact_preference,  # type: ignore[arg-type]
        phone_e164=user.phone_e164,
        phone_verified=user.phone_verified_at is not None,
        whatsapp_opt_in_at=user.whatsapp_opt_in_at,
        categories=[
            CategoryMute(
                category=cat,
                email_muted=(
                    mute_map[cat].email_muted if cat in mute_map else False
                ),
                whatsapp_muted=(
                    mute_map[cat].whatsapp_muted
                    if cat in mute_map
                    else False
                ),
            )
            for cat in _CATEGORIES
        ],
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/notification-preferences",
    response_model=NotificationPreferencesResponse,
)
def get_notification_preferences(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    db: DbSession,
) -> NotificationPreferencesResponse:
    user = db.get(User, current.user.id)
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado."
        )
    return _build_response(user, _load_mute_map(db, user.id))


@router.put(
    "/notification-preferences",
    response_model=NotificationPreferencesResponse,
)
def update_notification_preferences(
    payload: NotificationPreferencesUpdate,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    db: DbSession,
) -> NotificationPreferencesResponse:
    user = db.get(User, current.user.id)
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado."
        )

    # Capture before-state for audit. We do not include the mute
    # matrix snapshot in audit_log because it is read on every
    # dispatch — the canonical source is the table itself.
    before = {
        "contact_preference": user.contact_preference,
    }

    if payload.contact_preference is not None:
        user.contact_preference = payload.contact_preference

    mute_map = _load_mute_map(db, user.id)
    now = utc_now()
    for incoming in payload.categories:
        existing = mute_map.get(incoming.category)
        if existing is None:
            # Skip the insert when both flags are the default — keep
            # the table sparse so the routing read stays cheap.
            if not incoming.email_muted and not incoming.whatsapp_muted:
                continue
            row = UserNotificationPreference(
                user_id=user.id,
                category=incoming.category,
                email_muted=incoming.email_muted,
                whatsapp_muted=incoming.whatsapp_muted,
                updated_at=now,
            )
            db.add(row)
            mute_map[incoming.category] = row
        else:
            existing.email_muted = incoming.email_muted
            existing.whatsapp_muted = incoming.whatsapp_muted
            existing.updated_at = now

    audit_row = add_audit_event(
        db,
        action="user.notification_preferences_updated",
        entity_type="user",
        entity_id=user.id,
        actor_type="user",
        actor_id=user.id,
        before=before,
        after={
            "contact_preference": user.contact_preference,
            "category_overrides": sorted(mute_map.keys()),
        },
    )
    db.flush()

    # Phase 7 cutover (Slice C) — confirmation echo through the
    # unified fabric. Info-tier event → in-app only (no email or
    # SMS spam). The audit row id is the unique-per-edit dedupe
    # key, matching the emitter's contract.
    try:
        import logging

        from app.services.notifications import (
            emit_channel_preference_changed,
        )

        emit_channel_preference_changed(
            db,
            user=user,
            change_id=audit_row.id,
            mode="active",
        )
        db.flush()
    except Exception:  # pragma: no cover — defensive during cutover
        logging.getLogger("checkwise.me").exception(
            "notif_emit_failed event=account.channel_preference_changed user=%s",
            user.id,
        )

    db.commit()

    return _build_response(user, _load_mute_map(db, user.id))


# ---------------------------------------------------------------------------
# Phone-verification OTP (Phase 7 / Slice N8)
# ---------------------------------------------------------------------------


class PhoneVerifyRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=30)


class PhoneVerifyConfirmRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=30)
    code: str = Field(min_length=6, max_length=6)


class PhoneVerifyResponse(BaseModel):
    status: Literal["sent", "skipped", "failed"]
    expires_in_seconds: int
    delivery_detail: str | None = None


class PhoneConfirmResponse(BaseModel):
    phone_e164: str
    phone_verified_at: datetime
    whatsapp_opt_in_at: datetime


# Caps tuned conservatively: 3 OTP requests per minute and 10 per
# hour per user. Meta charges per template send and the OTP isn't
# something users should be triggering rapidly.
_PHONE_VERIFY_PER_MINUTE = 3
_PHONE_VERIFY_PER_HOUR = 10


def _enforce_phone_verify_rate(user_id: str) -> None:
    user_h = hash_identifier(user_id)
    ok_min = phone_verify_limiter.check(
        f"phone:user-min:{user_h}",
        limit=_PHONE_VERIFY_PER_MINUTE,
        window_seconds=60,
    )
    ok_hour = phone_verify_limiter.check(
        f"phone:user-hour:{user_h}",
        limit=_PHONE_VERIFY_PER_HOUR,
        window_seconds=3600,
    )
    if not ok_min or not ok_hour:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, detail=_RATE_LIMITED_DETAIL
        )


def _enforce_phone_confirm_rate(user_id: str) -> None:
    """Per-request cap on OTP *confirm* attempts.

    The confirm handler otherwise relies solely on the per-code OTP
    attempt counter; a per-user request limiter bounds rapid code-guessing
    across rows (a fresh /phone/verify mints a new code+counter). Uses a
    confirm-scoped bucket so it doesn't share budget with the send path.
    """
    user_h = hash_identifier(user_id)
    ok_min = phone_verify_limiter.check(
        f"phone:confirm-min:{user_h}",
        limit=_PHONE_VERIFY_PER_MINUTE,
        window_seconds=60,
    )
    ok_hour = phone_verify_limiter.check(
        f"phone:confirm-hour:{user_h}",
        limit=_PHONE_VERIFY_PER_HOUR,
        window_seconds=3600,
    )
    if not ok_min or not ok_hour:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, detail=_RATE_LIMITED_DETAIL
        )


@router.post("/phone/verify", response_model=PhoneVerifyResponse)
def request_phone_verification(
    payload: PhoneVerifyRequest,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    db: DbSession,
) -> PhoneVerifyResponse:
    """Start the OTP flow: generate a code + send it via WhatsApp.

    Body: ``{"phone": "+52 55 1234 5678"}`` (any common format —
    :func:`normalize_phone_e164` strips dashes/spaces/parens). The
    request rate-limits per-user. The response never includes the
    plaintext code; the user reads it off their phone screen.
    """
    user = db.get(User, current.user.id)
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado."
        )

    _enforce_phone_verify_rate(user.id)

    normalized = normalize_phone_e164(payload.phone)
    if normalized is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Número de teléfono inválido.",
        )

    row, plaintext = request_verification(db, user=user, phone_e164=normalized)

    # Send the WhatsApp template. Failures here are non-fatal: the
    # row already exists, so a retry (within rate-limit) reissues a
    # fresh code. In dev / when the template isn't approved yet,
    # the operator reads the OTP from the server log.
    delivery = send_whatsapp_template(
        to_phone=normalized,
        template_name=PHONE_OTP_TEMPLATE,
        components=build_phone_otp_components(code=plaintext),
    )

    add_audit_event(
        db,
        action="user.phone_verification_requested",
        entity_type="user",
        entity_id=user.id,
        actor_type="user",
        actor_id=user.id,
        metadata={
            "phone_last4": normalized[-4:],
            "delivery_status": delivery.status,
        },
    )
    db.commit()

    # Map the WhatsApp delivery status into the API surface. ``sent``
    # is the happy path; everything else is "we tried but the
    # outbound channel didn't accept it" — the row is still valid,
    # so the user can confirm using the code from the log in dev.
    api_status = "sent" if delivery.status == "sent" else (
        "skipped" if delivery.status.startswith("skipped") else "failed"
    )
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        # SQLite roundtrip strips the tz; normalize for the subtract.
        expires_at = expires_at.replace(tzinfo=UTC)
    return PhoneVerifyResponse(
        status=api_status,
        expires_in_seconds=int((expires_at - utc_now()).total_seconds()),
        delivery_detail=delivery.status,
    )


@router.post(
    "/phone/verify/confirm", response_model=PhoneConfirmResponse
)
def confirm_phone_verification(
    payload: PhoneVerifyConfirmRequest,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    db: DbSession,
) -> PhoneConfirmResponse:
    """Confirm the OTP and mark the user's phone verified.

    On success, sets ``user.phone_e164``, ``phone_verified_at``, and
    ``whatsapp_opt_in_at``; fires ``account.whatsapp_verified``
    through the unified notification fabric (shadow at N8 — the
    in-app confirmation row lands at cutover).

    Failure responses converge on ``400 Bad Request`` with a
    Spanish detail so an attacker probing for OTP state cannot
    distinguish expired / wrong-code / wrong-phone / no-active-row.
    """
    user = db.get(User, current.user.id)
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado."
        )

    _enforce_phone_confirm_rate(user.id)

    normalized = normalize_phone_e164(payload.phone)
    if normalized is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Número de teléfono inválido.",
        )

    row = confirm_verification(
        db, user=user, phone_e164=normalized, code=payload.code
    )
    if row is None:
        db.commit()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Código de verificación inválido o expirado.",
        )

    now = utc_now()
    user.phone_e164 = normalized
    user.phone_verified_at = now
    user.whatsapp_opt_in_at = now

    add_audit_event(
        db,
        action="user.phone_verification_confirmed",
        entity_type="user",
        entity_id=user.id,
        actor_type="user",
        actor_id=user.id,
        metadata={"phone_last4": normalized[-4:]},
    )

    # Phase 7 cutover (Slice C) — fire the catalog event through the
    # unified fabric. Info-tier event → in-app only (the user just
    # came back from confirming WhatsApp, no need to email about it).
    try:
        emit_whatsapp_verified(db, user=user, mode="active")
    except Exception:  # pragma: no cover — defensive
        pass

    db.commit()

    return PhoneConfirmResponse(
        phone_e164=normalized,
        phone_verified_at=now,
        whatsapp_opt_in_at=now,
    )
