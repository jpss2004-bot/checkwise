"""Phase 7 — shared helpers for notification emitters.

Recipient resolution and shadow channel-decision recording are
identical across the renewal emitter, the verification emitter,
and (soon) the reporting + account emitters. Centralising them
here keeps each emitter focused on its domain walk and prevents
silent drift between the routing decisions different events make
about the same recipient.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Client,
    Membership,
    NotificationDispatch,
    Organization,
    ProviderWorkspace,
    User,
    UserNotificationPreference,
)
from app.services.notifications.catalog import (
    EventDefinition,
    RecipientRole,
)
from app.services.notifications.dispatcher import PerRecipientOutcome
from app.services.notifications.envelope import Recipient
from app.services.notifications.routing import ChannelDecision, decide


def resolve_workspace_recipients(
    db: Session,
    *,
    workspace: ProviderWorkspace,
    allowed_roles: tuple[RecipientRole, ...],
) -> tuple[Recipient, ...]:
    """Resolve provider + client_admin recipients for a workspace.

    Honors the catalog's allowed-roles list — only roles named on the
    event's catalog row are returned. A role with no reachable User
    is dropped silently; the envelope still emits if at least one
    side is reachable.
    """
    items: list[Recipient] = []
    if (
        "provider_owner" in allowed_roles
        and workspace.owner_user_id is not None
    ):
        items.append(
            Recipient(user_id=workspace.owner_user_id, role="provider_owner")
        )
    if "client_admin" in allowed_roles:
        admin = resolve_client_admin(db, client_id=workspace.client_id)
        if admin is not None:
            items.append(Recipient(user_id=admin.id, role="client_admin"))
    return tuple(items)


def resolve_client_admin(db: Session, *, client_id: str) -> User | None:
    """First active client_admin User for a client tenant.

    Mirrors ``transactional_email._resolve_client_admin_user`` so the
    new fabric's recipient set matches the legacy delivery path's
    during the shadow phase.
    """
    if db.get(Client, client_id) is None:
        return None
    return db.scalar(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Organization.kind == "client",
            Organization.client_id == client_id,
            Membership.role == "client_admin",
            Membership.status == "active",
            User.status == "active",
        )
        .limit(1)
    )


def resolve_internal_admins(db: Session) -> list[User]:
    """All active LegalShelf internal_admin Users.

    Admin events fan out to every active internal_admin so an alert
    cannot be silently missed because one operator is on PTO. The
    legacy contact / feedback flow surfaces tickets via Slack —
    this fabric path is the in-app + email companion.
    """
    return list(
        db.scalars(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .join(Organization, Organization.id == Membership.organization_id)
            .where(
                Organization.kind == "internal",
                # CheckWise review team + superadmin (role-model redesign).
                Membership.role.in_(("platform_admin", "operations_admin")),
                Membership.status == "active",
                User.status == "active",
            )
        )
    )


def record_shadow_channels(
    db: Session,
    *,
    outcome: PerRecipientOutcome,
    event: EventDefinition,
) -> ChannelDecision | None:
    """Compute routing.decide() and stamp ``would_send`` /
    ``would_skip`` onto the dispatch row.

    Returns the decision so callers can inspect it in tests or for
    follow-on telemetry. Returns ``None`` only when the outcome's
    ``dispatch_row`` is missing (i.e. the dispatch was deduped) —
    in which case there is nothing to stamp.
    """
    row = outcome.dispatch_row
    if row is None:
        return None

    user = db.get(User, outcome.user_id)
    if user is None:
        row.email_status = "would_skip"
        row.email_reason = "user_not_found"
        row.whatsapp_status = "would_skip"
        row.whatsapp_reason = "user_not_found"
        return None

    mutes = _load_category_mute(db, user_id=user.id, category=event.category)
    decision = decide(
        event=event,
        contact_preference=user.contact_preference,  # type: ignore[arg-type]
        has_verified_phone=user.phone_verified_at is not None,
        category_email_muted=mutes[0],
        category_whatsapp_muted=mutes[1],
    )
    _apply_decision(row, decision)
    return decision


def _load_category_mute(
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


def _apply_decision(
    row: NotificationDispatch, decision: ChannelDecision
) -> None:
    """Shadow vocabulary: ``would_send`` / ``would_skip`` with the
    canonical routing skip reason. When N4b/N5b promote this path
    to authoritative, these strings flip to ``sent`` / ``skipped_*``.
    """
    row.email_status = "would_send" if decision.email else "would_skip"
    row.email_reason = decision.email_skip_reason
    row.whatsapp_status = (
        "would_send" if decision.whatsapp else "would_skip"
    )
    row.whatsapp_reason = decision.whatsapp_skip_reason
