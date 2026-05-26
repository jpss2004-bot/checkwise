"""Phase 7 — channel fan-out for the active dispatcher mode.

When the dispatcher runs with ``mode="active"``, it delegates the
per-recipient delivery work to :func:`fanout_channels` here. The
function is structured so every step short-circuits cleanly:

  1. Resolve the recipient User → if missing, stamp ``user_not_found``
     on both channels and return.
  2. Load category mutes + compute the routing decision (the same
     ``routing.decide()`` pure function the shadow path used).
  3. Write the in-app notification row (ClientNotification for
     ``client_admin``, ProviderNotification for ``provider_owner``).
     Other roles (``internal_admin``, ``invitee``, ``user``) currently
     have no dedicated table — for them the email is the primary
     delivery and the dispatch row is the audit anchor.
  4. Send email via :mod:`app.services.email_delivery` when routing
     says yes and a template renders.
  5. Send the SMS / WhatsApp message via
     :mod:`app.services.messaging_delivery` when routing says yes.

Every step stamps a canonical status on the ``NotificationDispatch``
row (``sent`` / ``skipped`` / ``failed`` with a reason). Failures
never propagate — same discipline as the legacy email + WhatsApp
delivery modules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ClientNotification,
    Membership,
    NotificationDispatch,
    Organization,
    ProviderNotification,
    ProviderWorkspace,
    User,
    UserNotificationPreference,
)
from app.services.email_delivery import (
    send_transactional_email,
    smtp_configured,
)
from app.services.messaging_delivery import send_message
from app.services.notifications.categorize import derive_category
from app.services.notifications.envelope import NotificationEnvelope, Recipient
from app.services.notifications.rendering import (
    MissingTemplateVariable,
    render,
)
from app.services.notifications.routing import ChannelDecision, decide

log = logging.getLogger("checkwise.notifications.fanout")


@dataclass(frozen=True)
class _Rendered:
    subject: str | None
    body: str
    meta_template_name: str | None


def fanout_channels(
    db: Session,
    *,
    envelope: NotificationEnvelope,
    recipient: Recipient,
    dispatch_row: NotificationDispatch,
) -> None:
    """Drive the per-channel send for one (envelope, recipient) pair.

    Never raises. Always updates the dispatch row to a canonical
    status so the audit trail is complete even on errors.
    """
    event = envelope.definition

    user = db.get(User, recipient.user_id)
    if user is None:
        # ``provider_owner`` recipients sometimes carry a workspace
        # id when the workspace has no owner_user_id yet. Treat as a
        # missing-User skip — outbound channels need a real address.
        _stamp_skip(dispatch_row, "user_not_found")
        return

    mutes = _load_mutes(db, user_id=user.id, category=event.category)
    routing_decision = decide(
        event=event,
        contact_preference=user.contact_preference,  # type: ignore[arg-type]
        has_verified_phone=user.phone_verified_at is not None,
        category_email_muted=mutes[0],
        category_whatsapp_muted=mutes[1],
    )

    rendered_email = _render(db, envelope, channel="email")
    rendered_wa = _render(db, envelope, channel="whatsapp")
    rendered_inapp = _render(db, envelope, channel="inapp")

    # ---- In-app ----------------------------------------------------------
    inapp_id = _write_inapp_row(
        db,
        envelope=envelope,
        recipient=recipient,
        rendered=rendered_inapp,
    )
    if inapp_id is not None:
        dispatch_row.inapp_id = inapp_id

    # ---- Email -----------------------------------------------------------
    _send_email_if_eligible(
        envelope=envelope,
        user=user,
        decision=routing_decision,
        rendered=rendered_email,
        dispatch_row=dispatch_row,
    )

    # ---- Messaging (SMS / WhatsApp) --------------------------------------
    _send_messaging_if_eligible(
        envelope=envelope,
        user=user,
        decision=routing_decision,
        rendered=rendered_wa,
        dispatch_row=dispatch_row,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stamp_skip(row: NotificationDispatch, reason: str) -> None:
    row.email_status = "skipped"
    row.email_reason = reason
    row.whatsapp_status = "skipped"
    row.whatsapp_reason = reason


def _load_mutes(
    db: Session, *, user_id: str, category: str
) -> tuple[bool, bool]:
    row = db.scalar(
        select(UserNotificationPreference).where(
            UserNotificationPreference.user_id == user_id,
            UserNotificationPreference.category == category,
        )
    )
    if row is None:
        return (False, False)
    return (row.email_muted, row.whatsapp_muted)


def _render(
    db: Session, envelope: NotificationEnvelope, *, channel: str
) -> _Rendered | None:
    """Render the active template; return None on any failure mode."""
    try:
        out = render(
            db,
            event_type=envelope.event_type,
            channel=channel,  # type: ignore[arg-type]
            payload=envelope.payload,
        )
    except MissingTemplateVariable as exc:
        log.warning(
            "[fanout] missing template var event=%s channel=%s err=%s",
            envelope.event_type,
            channel,
            exc,
        )
        return None
    if out is None:
        return None
    return _Rendered(
        subject=out.subject,
        body=out.body,
        meta_template_name=out.meta_template_name,
    )


def _write_inapp_row(
    db: Session,
    *,
    envelope: NotificationEnvelope,
    recipient: Recipient,
    rendered: _Rendered | None,
) -> str | None:
    """Write the in-app notification for roles that have a feed.

    ``provider_owner`` → ProviderNotification (keyed by workspace).
    ``client_admin``   → ClientNotification (keyed by client).
    Other roles (``internal_admin``, ``invitee``, ``user``) currently
    have no dedicated table — for them email is the primary surface.
    """
    event = envelope.definition
    title_default = (
        envelope.payload.get("title")
        or rendered.body[:120] if rendered else event.description
    )
    body_default = rendered.body if rendered else event.description

    if recipient.role == "provider_owner":
        workspace_id = _resolve_workspace_id_from_user(
            db, user_id=recipient.user_id
        )
        if workspace_id is None:
            return None
        notif = ProviderNotification(
            workspace_id=workspace_id,
            submission_id=envelope.payload.get("submission_id") or None,
            notification_type=envelope.event_type,
            severity=_inapp_severity(event.severity),
            category=derive_category(envelope.event_type),
            title=str(title_default)[:180],
            body=str(body_default),
            action_url=envelope.payload.get("cta_url"),
            payload=dict(envelope.payload),
        )
        db.add(notif)
        db.flush()
        return notif.id

    if recipient.role == "client_admin":
        client_id = _resolve_client_id_from_user(
            db, user_id=recipient.user_id
        )
        if client_id is None:
            return None
        notif = ClientNotification(
            client_id=client_id,
            vendor_id=envelope.payload.get("vendor_id") or None,
            submission_id=envelope.payload.get("submission_id") or None,
            notification_type=envelope.event_type,
            severity=_inapp_severity(event.severity),
            category=derive_category(envelope.event_type),
            title=str(title_default)[:180],
            body=str(body_default),
            action_url=envelope.payload.get("cta_url"),
            payload=dict(envelope.payload),
        )
        db.add(notif)
        db.flush()
        return notif.id

    return None


def _send_email_if_eligible(
    *,
    envelope: NotificationEnvelope,
    user: User,
    decision: ChannelDecision,
    rendered: _Rendered | None,
    dispatch_row: NotificationDispatch,
) -> None:
    _ = envelope  # reserved for future audit hooks
    if not decision.email:
        dispatch_row.email_status = "skipped"
        dispatch_row.email_reason = decision.email_skip_reason
        return
    if rendered is None:
        dispatch_row.email_status = "skipped"
        dispatch_row.email_reason = "no_template"
        return
    if not smtp_configured():
        dispatch_row.email_status = "skipped"
        dispatch_row.email_reason = "smtp_not_configured"
        return

    subject = rendered.subject or "CheckWise"
    result = send_transactional_email(
        to_email=user.email, subject=subject, body=rendered.body
    )
    if result.delivered:
        dispatch_row.email_status = "sent"
        dispatch_row.email_reason = None
        return
    if result.status == "skipped":
        dispatch_row.email_status = "skipped"
        dispatch_row.email_reason = result.error or "skipped"
    else:
        dispatch_row.email_status = "failed"
        dispatch_row.email_reason = result.error or result.status


def _send_messaging_if_eligible(
    *,
    envelope: NotificationEnvelope,
    user: User,
    decision: ChannelDecision,
    rendered: _Rendered | None,
    dispatch_row: NotificationDispatch,
) -> None:
    _ = envelope  # reserved
    if not decision.whatsapp:
        dispatch_row.whatsapp_status = "skipped"
        dispatch_row.whatsapp_reason = decision.whatsapp_skip_reason
        return
    if not user.phone_e164:
        dispatch_row.whatsapp_status = "skipped"
        dispatch_row.whatsapp_reason = "phone_not_verified"
        return
    if rendered is None:
        dispatch_row.whatsapp_status = "skipped"
        dispatch_row.whatsapp_reason = "no_template"
        return

    # Building the structured ``components`` array for the WhatsApp
    # template requires per-event domain knowledge (the existing
    # builders in :mod:`app.services.whatsapp_templates`). Until
    # those are registered against the new event_types AND Meta
    # approves the templates, ``components=None`` short-circuits
    # the WhatsApp path inside :func:`send_message`, falling through
    # to Twilio SMS with the rendered plaintext body — exactly the
    # cutover plan locked with the operator.
    result = send_message(
        to_phone=user.phone_e164,
        body=rendered.body,
        whatsapp_template_name=rendered.meta_template_name,
        whatsapp_components=None,
    )
    if result.delivered:
        dispatch_row.whatsapp_status = "sent"
        dispatch_row.whatsapp_reason = None
        return
    if result.status.startswith("skipped"):
        dispatch_row.whatsapp_status = "skipped"
        dispatch_row.whatsapp_reason = result.status
    else:
        dispatch_row.whatsapp_status = "failed"
        dispatch_row.whatsapp_reason = result.error or result.status


def _resolve_workspace_id_from_user(
    db: Session, *, user_id: str
) -> str | None:
    ws = db.scalar(
        select(ProviderWorkspace).where(
            ProviderWorkspace.owner_user_id == user_id
        )
    )
    return ws.id if ws else None


def _resolve_client_id_from_user(
    db: Session, *, user_id: str
) -> str | None:
    org = db.scalar(
        select(Organization)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(
            Membership.user_id == user_id,
            Membership.role == "client_admin",
            Membership.status == "active",
            Organization.kind == "client",
        )
        .limit(1)
    )
    return org.client_id if org else None


def _inapp_severity(catalog_severity: str) -> str:
    """Map catalog severity tier → in-app row semáforo color.

    The in-app row column accepts ``red | yellow | green | info``.
    Catalog ``critical`` lands as ``red``; ``important`` as
    ``yellow``; ``info`` as ``info``. ``green`` is reserved for
    the legacy "approved / complete" rows and not produced here.
    """
    return {
        "critical": "red",
        "important": "yellow",
        "info": "info",
    }.get(catalog_severity, "info")
