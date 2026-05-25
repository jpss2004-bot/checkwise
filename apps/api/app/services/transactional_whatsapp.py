"""Transactional WhatsApp dispatch — preference gate + send + audit.

Mirrors :mod:`app.services.transactional_email` for the second leg of
the renewal + reviewer-decision delivery story. The event sites call
both helpers (email + whatsapp) and each leg gates on the recipient's
``contact_preference`` independently — a user who picked ``"whatsapp"``
gets WhatsApp and no email, a user on ``"both"`` gets both.

Why mirror the email module's shape:
    Recipient resolution (workspace → owner User, client_id →
    client_admin User) is identical between channels. The only
    differences are (a) which preference values pass the gate, (b)
    which field we read for the destination (``User.phone`` instead of
    ``User.email``), and (c) the audit action name. Keeping the
    function signatures aligned means the event sites can call both
    helpers with the same arguments.

Why this module never raises:
    Same reason as email. Outbound is best-effort. The
    ``WhatsAppDeliveryResult`` returned from the transport is forwarded
    to the caller; any exception inside this module degrades to
    ``status="failed"``.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Membership,
    Organization,
    ProviderWorkspace,
    Submission,
    User,
    Vendor,
)
from app.services.audit_log import add_audit_event
from app.services.whatsapp_delivery import (
    WhatsAppDeliveryResult,
    send_whatsapp_template,
    whatsapp_configured,
)
from app.services.whatsapp_templates import (
    DECISION_TEMPLATE,
    RENEWAL_TEMPLATE,
    build_renewal_threshold_components,
    build_reviewer_decision_components,
)

log = logging.getLogger("checkwise.transactional_whatsapp")

# Users whose contact_preference falls into this set receive outbound
# WhatsApp. Mirrors the email module's ``_EMAILABLE_PREFERENCES`` so
# the gating logic stays symmetric.
_WHATSAPPABLE_PREFERENCES: frozenset[str] = frozenset({"whatsapp", "both"})


__all__ = (
    "whatsapp_provider_of_reviewer_decision",
    "whatsapp_renewal_threshold_crossed",
)


# ---------------------------------------------------------------------------
# Reviewer decision → provider workspace owner
# ---------------------------------------------------------------------------


def whatsapp_provider_of_reviewer_decision(
    db: Session,
    *,
    submission: Submission,
    action: str,
    reviewer_name: str | None = None,
) -> WhatsAppDeliveryResult:
    """Notify the provider workspace owner about a reviewer decision.

    Returns the underlying :class:`WhatsAppDeliveryResult`. Skip reasons
    (no workspace, preference excludes WA, missing phone, etc.) all
    map to a ``status="skipped_*"`` value so the caller doesn't have
    to treat the absence of a send as an error.
    """

    workspace = db.scalar(
        select(ProviderWorkspace).where(
            ProviderWorkspace.client_id == submission.client_id,
            ProviderWorkspace.vendor_id == submission.vendor_id,
        )
    )
    if workspace is None or workspace.owner_user_id is None:
        return _skipped("no_workspace_owner")
    user = db.get(User, workspace.owner_user_id)
    if user is None:
        return _skipped("user_not_found")
    if not _user_wants_whatsapp(user):
        return _skipped("preference_excludes_whatsapp", user=user)
    if not whatsapp_configured():
        return _skipped("whatsapp_not_configured", user=user)
    if not user.phone:
        return _skipped("phone_missing", user=user)

    vendor = db.get(Vendor, submission.vendor_id)
    requirement_name = (
        submission.requirement.name if submission.requirement else "Documento"
    )
    components = build_reviewer_decision_components(
        vendor_name=vendor.name if vendor else "tu empresa",
        requirement_name=requirement_name,
        decision_action=action,
        reviewer_name=reviewer_name,
    )

    result = send_whatsapp_template(
        to_phone=user.phone,
        template_name=DECISION_TEMPLATE,
        components=components,
    )
    _record_audit(
        db,
        recipient=user,
        kind="reviewer_decision",
        entity_type="submission",
        entity_id=submission.id,
        template_name=DECISION_TEMPLATE,
        result=result,
        extra={"decision_action": action},
    )
    return result


# ---------------------------------------------------------------------------
# Renewal threshold cross → provider + client_admin
# ---------------------------------------------------------------------------


def whatsapp_renewal_threshold_crossed(
    db: Session,
    *,
    workspace: ProviderWorkspace,
    vendor: Vendor,
    requirement_name: str,
    due_date: date,
    days_remaining: int,
    severity: Literal["yellow", "red", "info"],
) -> tuple[WhatsAppDeliveryResult, WhatsAppDeliveryResult]:
    """Notify both the provider workspace owner AND the client_admin.

    Returns ``(provider_result, client_result)``. Either side may
    independently skip (no phone, wrong preference, kill switch). The
    function never raises and never partial-fails — both legs run.
    """

    provider_result = _whatsapp_provider_renewal(
        db,
        workspace=workspace,
        vendor=vendor,
        requirement_name=requirement_name,
        due_date=due_date,
        days_remaining=days_remaining,
        severity=severity,
    )
    client_result = _whatsapp_client_renewal(
        db,
        client_id=workspace.client_id,
        vendor=vendor,
        requirement_name=requirement_name,
        due_date=due_date,
        days_remaining=days_remaining,
        severity=severity,
    )
    return provider_result, client_result


def _whatsapp_provider_renewal(
    db: Session,
    *,
    workspace: ProviderWorkspace,
    vendor: Vendor,
    requirement_name: str,
    due_date: date,
    days_remaining: int,
    severity: str,
) -> WhatsAppDeliveryResult:
    if workspace.owner_user_id is None:
        return _skipped("no_workspace_owner")
    user = db.get(User, workspace.owner_user_id)
    if user is None:
        return _skipped("user_not_found")
    if not _user_wants_whatsapp(user):
        return _skipped("preference_excludes_whatsapp", user=user)
    if not whatsapp_configured():
        return _skipped("whatsapp_not_configured", user=user)
    if not user.phone:
        return _skipped("phone_missing", user=user)

    components = build_renewal_threshold_components(
        vendor_name=vendor.name,
        requirement_name=requirement_name,
        due_date=due_date,
        days_remaining=days_remaining,
        severity=severity if severity in {"yellow", "red", "info"} else "info",
    )
    result = send_whatsapp_template(
        to_phone=user.phone,
        template_name=RENEWAL_TEMPLATE,
        components=components,
    )
    _record_audit(
        db,
        recipient=user,
        kind="renewal_provider",
        entity_type="provider_workspace",
        entity_id=workspace.id,
        template_name=RENEWAL_TEMPLATE,
        result=result,
        extra={
            "severity": severity,
            "days_remaining": days_remaining,
            "due_date": due_date.isoformat(),
        },
    )
    return result


def _whatsapp_client_renewal(
    db: Session,
    *,
    client_id: str,
    vendor: Vendor,
    requirement_name: str,
    due_date: date,
    days_remaining: int,
    severity: str,
) -> WhatsAppDeliveryResult:
    user = _resolve_client_admin_user(db, client_id=client_id)
    if user is None:
        return _skipped("no_client_admin")
    if not _user_wants_whatsapp(user):
        return _skipped("preference_excludes_whatsapp", user=user)
    if not whatsapp_configured():
        return _skipped("whatsapp_not_configured", user=user)
    if not user.phone:
        return _skipped("phone_missing", user=user)

    components = build_renewal_threshold_components(
        vendor_name=vendor.name,
        requirement_name=requirement_name,
        due_date=due_date,
        days_remaining=days_remaining,
        severity=severity if severity in {"yellow", "red", "info"} else "info",
    )
    result = send_whatsapp_template(
        to_phone=user.phone,
        template_name=RENEWAL_TEMPLATE,
        components=components,
    )
    _record_audit(
        db,
        recipient=user,
        kind="renewal_client",
        entity_type="client",
        entity_id=client_id,
        template_name=RENEWAL_TEMPLATE,
        result=result,
        extra={
            "severity": severity,
            "days_remaining": days_remaining,
            "due_date": due_date.isoformat(),
            "vendor_id": vendor.id,
        },
    )
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_wants_whatsapp(user: User) -> bool:
    return (user.contact_preference or "") in _WHATSAPPABLE_PREFERENCES


def _resolve_client_admin_user(db: Session, *, client_id: str) -> User | None:
    """Return the first client_admin user reachable from this client.

    Mirrors :func:`transactional_email._resolve_client_admin_user`. We
    walk ``client → organization → membership → user`` and pick the
    earliest-created active client_admin so the choice is stable.
    """

    stmt = (
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .join(Organization, Membership.organization_id == Organization.id)
        .where(
            Organization.client_id == client_id,
            Membership.role == "client_admin",
            Membership.status == "active",
        )
        .order_by(User.created_at.asc())
        .limit(1)
    )
    return db.scalar(stmt)


def _skipped(reason: str, *, user: User | None = None) -> WhatsAppDeliveryResult:
    return WhatsAppDeliveryResult(
        delivered=False,
        status=f"skipped_{reason}" if not reason.startswith("skipped_") else reason,
        error=reason,
        recipient=user.phone if user else None,
    )


def _record_audit(
    db: Session,
    *,
    recipient: User,
    kind: str,
    entity_type: str,
    entity_id: str,
    template_name: str,
    result: WhatsAppDeliveryResult,
    extra: dict | None = None,
) -> None:
    """Write the canonical ``whatsapp.transactional_sent`` audit row."""

    metadata: dict = {
        "kind": kind,
        "recipient_user_id": recipient.id,
        "recipient_phone_present": bool(recipient.phone),
        "template": template_name,
        "status": result.status,
    }
    if result.message_id:
        metadata["message_id"] = result.message_id
    if result.error:
        metadata["error"] = result.error
    if extra:
        metadata.update(extra)
    try:
        add_audit_event(
            db,
            action="whatsapp.transactional_sent",
            entity_type=entity_type,
            entity_id=entity_id,
            actor_type="system",
            actor_id=None,
            metadata=metadata,
        )
    except Exception:  # pragma: no cover — never let audit kill the flow
        log.exception(
            "[transactional_whatsapp] failed to write audit row for %s/%s",
            entity_type,
            entity_id,
        )
