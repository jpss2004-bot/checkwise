"""Phase 7 / Slice N7 — account lifecycle emitter (shadow mode).

Five account events, all keyed on a single User row:

  * ``account.invitation_sent``         — critical, role=invitee.
                                          Fires once per single-use
                                          invitation token.
  * ``account.welcome``                 — important, role=user.
                                          Fires once per User lifetime,
                                          on first successful login
                                          post-invitation.
  * ``account.password_reset_requested`` — critical, role=user.
                                          Fires once per reset token.
  * ``account.channel_preference_changed`` — info, role=user.
                                          Fires every time the user
                                          updates their preferences;
                                          dedupe_key carries the
                                          ``updated_at`` timestamp so
                                          each change is distinct.
  * ``account.whatsapp_verified``       — info, role=user.
                                          Fires once when OTP confirms
                                          (Slice N8 will be the
                                          authoritative caller).

Account events do not have a workspace context. The recipient is
the User row itself, in the role declared by the catalog. The
emitter accepts a ``User`` object directly and does not need to
join through Memberships or workspaces.

Shadow mode (same as N4–N6): writes ``notification_dispatch`` +
``audit_log`` and stamps the routing decision; does not write
``ClientNotification`` / ``ProviderNotification``, send email, or
send WhatsApp. The existing transactional paths remain
authoritative until the cutover slice.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import User
from app.services.notifications.catalog import RecipientRole, get_event
from app.services.notifications.dispatcher import (
    DispatchMode,
    DispatchResult,
    dispatch,
)
from app.services.notifications.emitters._helpers import (
    record_shadow_channels,
)
from app.services.notifications.envelope import (
    NotificationEnvelope,
    Recipient,
)


def emit_invitation_sent(
    db: Session,
    *,
    user: User,
    invitation_token_id: str,
    invitation_url: str,
    mode: DispatchMode = "shadow",
) -> DispatchResult:
    """Fire ``account.invitation_sent`` for a freshly invited User.

    ``invitation_token_id`` becomes part of the dedupe key so a
    re-send (issuing a new token) emits a fresh envelope, while a
    duplicate POST against the same token silently short-circuits.
    """
    return _emit_for_user(
        db,
        user=user,
        event_type="account.invitation_sent",
        role="invitee",
        dedupe_suffix=f"invitation:{invitation_token_id}",
        payload={
            "full_name": user.full_name,
            "email": user.email,
            "invitation_url": invitation_url,
        },
        mode=mode,
    )


def emit_welcome(
    db: Session, *, user: User, mode: DispatchMode = "shadow"
) -> DispatchResult:
    """Fire ``account.welcome`` after the user's first login.

    Dedupe key is keyed on the user alone — only one welcome ever
    lands per User, even if the caller invokes the emitter on every
    login event by mistake.
    """
    return _emit_for_user(
        db,
        user=user,
        event_type="account.welcome",
        role="user",
        dedupe_suffix="welcome",
        payload={
            "full_name": user.full_name,
            "email": user.email,
        },
        mode=mode,
    )


def emit_password_reset_requested(
    db: Session,
    *,
    user: User,
    reset_token_id: str,
    reset_url: str,
    mode: DispatchMode = "shadow",
) -> DispatchResult:
    """Fire ``account.password_reset_requested``.

    Includes the ``reset_token_id`` in the dedupe key so each reset
    request is its own envelope. Critical-tier; email always fires.
    WhatsApp is intentionally not eligible at the catalog level for
    this event — Meta's policy treats credential-recovery as a
    surface they want to govern separately.
    """
    return _emit_for_user(
        db,
        user=user,
        event_type="account.password_reset_requested",
        role="user",
        dedupe_suffix=f"password_reset:{reset_token_id}",
        payload={
            "full_name": user.full_name,
            "email": user.email,
            "reset_url": reset_url,
        },
        mode=mode,
    )


def emit_channel_preference_changed(
    db: Session,
    *,
    user: User,
    change_id: str,
    mode: DispatchMode = "shadow",
) -> DispatchResult:
    """Fire ``account.channel_preference_changed`` after a profile edit.

    ``change_id`` is any unique-per-edit string (e.g. the audit_log
    row id or an ISO timestamp). The user can change preferences
    repeatedly and each change deserves its own confirmation row.
    """
    return _emit_for_user(
        db,
        user=user,
        event_type="account.channel_preference_changed",
        role="user",
        dedupe_suffix=f"pref:{change_id}",
        payload={
            "full_name": user.full_name,
            "contact_preference": user.contact_preference,
        },
        mode=mode,
    )


def emit_whatsapp_verified(
    db: Session, *, user: User, mode: DispatchMode = "shadow"
) -> DispatchResult:
    """Fire ``account.whatsapp_verified`` after OTP confirmation.

    Dedupe is per-user — a user who re-verifies after a phone
    change still gets one envelope (the dedupe key is stable), and
    a duplicate OTP confirmation never spams.
    """
    return _emit_for_user(
        db,
        user=user,
        event_type="account.whatsapp_verified",
        role="user",
        dedupe_suffix="whatsapp_verified",
        payload={
            "full_name": user.full_name,
            "phone_e164": user.phone_e164 or "",
        },
        mode=mode,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _emit_for_user(
    db: Session,
    *,
    user: User,
    event_type: str,
    role: RecipientRole,
    dedupe_suffix: str,
    payload: dict,
    mode: DispatchMode = "shadow",
) -> DispatchResult:
    event = get_event(event_type)
    envelope = NotificationEnvelope(
        event_type=event_type,
        dedupe_key=f"user:{user.id}:{dedupe_suffix}",
        recipients=(Recipient(user_id=user.id, role=role),),
        payload=payload,
    )
    result = dispatch(db, envelope, mode=mode)
    if mode == "shadow":
        for outcome in result.outcomes:
            if outcome.status == "deduped":
                continue
            record_shadow_channels(db, outcome=outcome, event=event)
    return result
