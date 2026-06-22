"""Provider-limit + subscription-plan resolution for client organizations.

Pure counting / limit logic (unit-testable, no FastAPI coupling) plus one
HTTP guard the routers call before creating or restoring a provider. The
guard follows the repo convention of helper-raised ``HTTPException`` (see
``client_users._require_can_manage`` / ``_org_for_client``).

Count semantics: a provider occupies a slot iff its ``Vendor`` row is
non-archived (``status != 'inactive'``) — so archiving a provider frees a
slot and restoring one re-consumes it. The cap lives on the bridging
``Organization`` (the auth + seat boundary); the provider rows are counted
by ``Vendor.client_id`` (Organization↔Client is 1:1 on the provisioning
path).
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants.plans import Plan, coerce_plan, provider_limit_default
from app.constants.statuses import VendorStatus
from app.models import Organization, Vendor

__all__ = [
    "CapacityDecision",
    "active_provider_count",
    "assert_provider_capacity",
    "evaluate_provider_capacity",
    "org_for_client",
    "org_for_client_optional",
    "plan_for_org",
    "provider_limit_for_org",
]


def org_for_client_optional(
    db: Session, client_id: str, *, for_update: bool = False
) -> Organization | None:
    """The ``kind='client'`` org bridging this Client, or ``None``.

    Provisioning creates exactly one; ``order_by(created_at)`` keeps the
    pick deterministic should a legacy tenant ever hold two. Returns
    ``None`` for an orphan legacy Client with no Organization (those
    tenants are treated as uncapped — there is no plan to enforce).
    """
    stmt = (
        select(Organization)
        .where(
            Organization.kind == "client",
            Organization.client_id == client_id,
        )
        .order_by(Organization.created_at.asc())
    )
    if for_update:
        stmt = stmt.with_for_update()
    return db.scalars(stmt).first()


def org_for_client(
    db: Session, client_id: str, *, for_update: bool = False
) -> Organization:
    """Like :func:`org_for_client_optional` but 404s when absent — the
    client self-service paths always run inside a provisioned org, so a
    missing one is an error, not an uncapped fallback."""
    org = org_for_client_optional(db, client_id, for_update=for_update)
    if org is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Este cliente no tiene una organización de usuarios.",
        )
    return org


def plan_for_org(org: Organization) -> Plan:
    return coerce_plan(org.plan)


def provider_limit_for_org(org: Organization) -> int | None:
    """An explicit per-tenant override wins; otherwise the tier default.
    ``None`` = uncapped."""
    if org.provider_limit is not None:
        return org.provider_limit
    return provider_limit_default(plan_for_org(org))


def active_provider_count(db: Session, client_id: str) -> int:
    """Providers occupying a slot = active (non-archived) vendors of this
    client. Uses the same ``status == 'active'`` predicate the rest of the
    portal treats as "active" (``_scoped_workspaces(active_only)``, the
    dashboard vendor totals), so the cap counts exactly what the client
    sees as their active portfolio. Archiving (``status='inactive'``) frees
    a slot; reactivating re-consumes one."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(Vendor)
            .where(
                Vendor.client_id == client_id,
                Vendor.status == VendorStatus.ACTIVE.value,
            )
        )
        or 0
    )


@dataclass(frozen=True)
class CapacityDecision:
    used: int
    limit: int | None  # None = uncapped
    allowed: bool  # may proceed (under cap, uncapped, or internal override)
    over_limit: bool  # at/over cap regardless of override (for audit)


def evaluate_provider_capacity(
    db: Session, org: Organization, *, is_internal: bool
) -> CapacityDecision:
    """Measure usage vs. the org's effective cap. Never raises — used by the
    admin door, which always proceeds but audits an over-limit grant."""
    limit = provider_limit_for_org(org)
    used = active_provider_count(db, org.client_id)
    over = limit is not None and used >= limit
    return CapacityDecision(
        used=used, limit=limit, allowed=(not over) or is_internal, over_limit=over
    )


def assert_provider_capacity(
    db: Session, org: Organization, *, is_internal: bool
) -> CapacityDecision:
    """Raise 409 for a client at/over the cap; ``internal_admin`` passes
    (``over_limit`` flagged so the caller can audit the override).

    The caller MUST already hold a ``SELECT … FOR UPDATE`` lock on ``org``
    so two concurrent adds cannot both observe the last free slot.
    """
    decision = evaluate_provider_capacity(db, org, is_internal=is_internal)
    if not decision.allowed:
        # Structured detail (matches the archived-RFC 409) so the client UI can
        # branch on ``code`` for the upgrade modal and show the numbers.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "provider_limit_reached",
                "limit": decision.limit,
                "used": decision.used,
                "message": (
                    f"Tu plan permite un máximo de {decision.limit} proveedores "
                    "activos. Archiva un proveedor para liberar un lugar, o "
                    "mejora tu plan para añadir más."
                ),
            },
        )
    return decision
