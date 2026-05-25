"""Transactional email dispatch — preference gate + send + audit.

Junta 2026-05-25 — outbound email for reviewer decisions and
renewal threshold crosses. This module is the thin orchestration
layer between the event sites (submission_workflow,
renewal_dispatch) and the SMTP plumbing in
:mod:`app.services.email_delivery`.

Responsibilities
----------------

1. **Preference gate** — only email when the recipient User has
   ``contact_preference in {"email", "both"}``. Users who picked
   ``"whatsapp"`` get nothing here (WhatsApp transport is a
   separate follow-up).
2. **Resolve recipient User** — given a workspace or a client_id,
   walk the relationship graph to the right ``User.email`` and
   ``User.full_name``.
3. **Audit row** — every send attempt (sent, skipped or failed)
   writes an ``audit_log`` entry with the canonical action name
   ``email.transactional_sent`` so a forensic reader can confirm
   the system tried to email a given user on a given date.
4. **Never raise** — email is best-effort. A SMTP failure must
   not break the workflow or the cron. The caller sees only the
   ``EmailDeliveryResult`` returned by the helper; any exception
   bubbles up as ``status="failed"``.

The functions return ``EmailDeliveryResult`` so callers can record
the outcome in their own audit metadata if desired.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Client,
    Membership,
    Organization,
    ProviderWorkspace,
    Submission,
    User,
    Vendor,
)
from app.services.audit_log import add_audit_event
from app.services.email_delivery import (
    EmailDeliveryResult,
    send_transactional_email,
    smtp_configured,
)
from app.services.email_templates import (
    build_client_renewal_email,
    build_provider_decision_email,
    build_provider_renewal_email,
)

log = logging.getLogger("checkwise.transactional_email")

# Users whose contact_preference falls into this set receive
# outbound email. The values mirror
# ``CheckConstraint("contact_preference IN ('email', 'whatsapp', 'both')")``
# on the users table.
_EMAILABLE_PREFERENCES: frozenset[str] = frozenset({"email", "both"})


__all__ = (
    "email_provider_of_reviewer_decision",
    "email_renewal_threshold_crossed",
)


# ---------------------------------------------------------------------------
# Reviewer decision → provider workspace owner
# ---------------------------------------------------------------------------


def email_provider_of_reviewer_decision(
    db: Session,
    *,
    submission: Submission,
    action: str,
    reason: str | None,
    observations: str | None,
    portal_base_url: str,
) -> EmailDeliveryResult:
    """Email the provider workspace owner about a reviewer decision.

    Resolves the workspace from the submission's (client_id,
    vendor_id) pair. If no workspace exists or the workspace has no
    owner, the call short-circuits to a ``"skipped"`` result — the
    in-app ProviderNotification is the canonical delivery and the
    email is a courtesy redundancy.

    ``portal_base_url`` is the absolute URL of the portal (no trailing
    slash). The CTA inside the email points at
    ``{portal_base_url}/portal/submissions/{submission_id}``.
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
    if not _user_wants_email(user):
        return _skipped("preference_excludes_email", user=user)
    if not smtp_configured():
        return _skipped("smtp_not_configured", user=user)

    vendor = db.get(Vendor, submission.vendor_id)
    requirement_name = (
        submission.requirement.name if submission.requirement else "Documento"
    )
    subject, body = build_provider_decision_email(
        provider_name=_first_name(user.full_name) or user.full_name,
        vendor_name=vendor.name if vendor else "tu empresa",
        requirement_name=requirement_name,
        period_label=submission.period_key,
        action=action,
        reason=reason,
        observations=observations,
        submission_url=f"{portal_base_url.rstrip('/')}/portal/submissions/{submission.id}",
    )

    result = send_transactional_email(
        to_email=user.email, subject=subject, body=body
    )
    _record_audit(
        db,
        recipient=user,
        kind="reviewer_decision",
        entity_type="submission",
        entity_id=submission.id,
        subject=subject,
        result=result,
    )
    return result


# ---------------------------------------------------------------------------
# Renewal threshold cross → provider + client_admin
# ---------------------------------------------------------------------------


def email_renewal_threshold_crossed(
    db: Session,
    *,
    workspace: ProviderWorkspace,
    vendor: Vendor,
    requirement_code: str,
    requirement_name: str,
    due_date: date,
    days_remaining: int,
    severity: str,
    portal_base_url: str,
    client_portal_base_url: str,
) -> tuple[EmailDeliveryResult, EmailDeliveryResult]:
    """Email both the provider workspace owner AND the client_admin
    about a renewal threshold crossing.

    Returns ``(provider_result, client_result)``. Either side may be
    ``"skipped"`` independently — the function never raises.
    """
    provider_result = _email_provider_renewal(
        db,
        workspace=workspace,
        vendor=vendor,
        requirement_code=requirement_code,
        requirement_name=requirement_name,
        due_date=due_date,
        days_remaining=days_remaining,
        severity=severity,
        portal_base_url=portal_base_url,
    )
    client_result = _email_client_renewal(
        db,
        client_id=workspace.client_id,
        vendor=vendor,
        requirement_code=requirement_code,
        requirement_name=requirement_name,
        due_date=due_date,
        days_remaining=days_remaining,
        severity=severity,
        client_portal_base_url=client_portal_base_url,
    )
    return provider_result, client_result


def _email_provider_renewal(
    db: Session,
    *,
    workspace: ProviderWorkspace,
    vendor: Vendor,
    requirement_code: str,
    requirement_name: str,
    due_date: date,
    days_remaining: int,
    severity: str,
    portal_base_url: str,
) -> EmailDeliveryResult:
    if workspace.owner_user_id is None:
        return _skipped("no_workspace_owner")
    user = db.get(User, workspace.owner_user_id)
    if user is None:
        return _skipped("user_not_found")
    if not _user_wants_email(user):
        return _skipped("preference_excludes_email", user=user)
    if not smtp_configured():
        return _skipped("smtp_not_configured", user=user)

    subject, body = build_provider_renewal_email(
        provider_name=_first_name(user.full_name) or user.full_name,
        vendor_name=vendor.name,
        requirement_name=requirement_name,
        due_date=due_date,
        days_remaining=days_remaining,
        severity=severity,
        portal_url=f"{portal_base_url.rstrip('/')}/portal/dashboard",
    )
    result = send_transactional_email(
        to_email=user.email, subject=subject, body=body
    )
    _record_audit(
        db,
        recipient=user,
        kind="renewal_provider",
        entity_type="provider_workspace",
        entity_id=workspace.id,
        subject=subject,
        result=result,
        extra={"requirement_code": requirement_code, "severity": severity},
    )
    return result


def _email_client_renewal(
    db: Session,
    *,
    client_id: str,
    vendor: Vendor,
    requirement_code: str,
    requirement_name: str,
    due_date: date,
    days_remaining: int,
    severity: str,
    client_portal_base_url: str,
) -> EmailDeliveryResult:
    user = _resolve_client_admin_user(db, client_id=client_id)
    if user is None:
        return _skipped("no_client_admin")
    if not _user_wants_email(user):
        return _skipped("preference_excludes_email", user=user)
    if not smtp_configured():
        return _skipped("smtp_not_configured", user=user)

    subject, body = build_client_renewal_email(
        client_contact_name=_first_name(user.full_name) or user.full_name,
        vendor_name=vendor.name,
        requirement_name=requirement_name,
        due_date=due_date,
        days_remaining=days_remaining,
        severity=severity,
        client_portal_url=f"{client_portal_base_url.rstrip('/')}/client/vendors/{vendor.id}",
    )
    result = send_transactional_email(
        to_email=user.email, subject=subject, body=body
    )
    _record_audit(
        db,
        recipient=user,
        kind="renewal_client",
        entity_type="client",
        entity_id=client_id,
        subject=subject,
        result=result,
        extra={"requirement_code": requirement_code, "severity": severity},
    )
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_wants_email(user: User) -> bool:
    """Honor the user's contact_preference."""
    return (user.contact_preference or "email") in _EMAILABLE_PREFERENCES


def _first_name(full_name: str | None) -> str | None:
    if not full_name:
        return None
    parts = full_name.strip().split()
    return parts[0] if parts else None


def _resolve_client_admin_user(db: Session, *, client_id: str) -> User | None:
    """Find the User who has the ``client_admin`` role over ``client_id``.

    Returns the first active matching user. When more than one
    client_admin exists, future work can fan-out to all of them; for
    v1 a single recipient per client keeps inboxes quiet.
    """
    client = db.get(Client, client_id)
    if client is None:
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


def _skipped(reason: str, *, user: User | None = None) -> EmailDeliveryResult:
    """Build a ``"skipped"`` result and log the reason for ops triage."""
    log.info(
        "[transactional_email] skipped reason=%s user=%s",
        reason,
        user.email if user else "<none>",
    )
    return EmailDeliveryResult(delivered=False, status="skipped", error=reason)


def _record_audit(
    db: Session,
    *,
    recipient: User,
    kind: str,
    entity_type: str,
    entity_id: str,
    subject: str,
    result: EmailDeliveryResult,
    extra: dict | None = None,
) -> None:
    """Write the canonical ``email.transactional_sent`` audit row."""
    metadata: dict = {
        "kind": kind,
        "recipient_email": recipient.email,
        "recipient_user_id": recipient.id,
        "subject": subject,
        "status": result.status,
    }
    if result.error:
        metadata["error"] = result.error
    if extra:
        metadata.update(extra)
    try:
        add_audit_event(
            db,
            action="email.transactional_sent",
            entity_type=entity_type,
            entity_id=entity_id,
            actor_type="system",
            actor_id=None,
            metadata=metadata,
        )
    except Exception:  # pragma: no cover — never let audit kill the flow
        log.exception(
            "[transactional_email] failed to write audit row for %s/%s",
            entity_type,
            entity_id,
        )
