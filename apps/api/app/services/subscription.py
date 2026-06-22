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
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants.plans import (
    DEMO_DURATION_DAYS,
    ORG_STATUS_ACTIVE,
    VALID_ORG_STATUSES,
    Plan,
    capabilities_for,
    coerce_plan,
    provider_limit_default,
)
from app.constants.statuses import VendorStatus
from app.core.time import utc_now
from app.models import Organization, Vendor

__all__ = [
    "CapacityDecision",
    "active_provider_count",
    "assert_capability",
    "assert_provider_capacity",
    "evaluate_provider_capacity",
    "is_org_blocked",
    "org_for_client",
    "org_for_client_optional",
    "plan_for_org",
    "provider_limit_for_org",
    "set_org_status",
    "set_plan",
    "start_demo",
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


# ---------------------------------------------------------------------------
# Phase B — org status + demo lifecycle (provisioning, gates, crons)
# ---------------------------------------------------------------------------


def _as_utc(dt: datetime) -> datetime:
    """Coerce a possibly-naive datetime to aware UTC. ``demo_expires_at`` is
    stored timezone-aware on Postgres but can come back naive from SQLite
    (tests); treat naive values as UTC so the comparison never raises."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def is_org_blocked(org: Organization, *, now: datetime | None = None) -> bool:
    """Whether the org should be blocked at the auth / portal gate.

    Blocked iff its status is non-active, OR it is a demo whose deadline has
    passed. This is the single source of truth shared by the login gate (B2)
    and the portal freeze gate (B3) so the freeze rule is never duplicated.
    A demo with ``demo_expires_at IS NULL`` is treated as non-expiring.
    """
    if org.status != ORG_STATUS_ACTIVE:
        return True
    if org.plan == Plan.DEMO.value and org.demo_expires_at is not None:
        return _as_utc(org.demo_expires_at) <= (now or utc_now())
    return False


def start_demo(
    db: Session, org: Organization, *, days: int = DEMO_DURATION_DAYS
) -> Organization:
    """Convert an org to a fresh demo: ``plan='demo'``, a ``days``-day deadline,
    ``status='active'``, and the per-tenant override cleared so the demo tier
    default (5) applies. The caller MUST hold a ``FOR UPDATE`` lock on ``org``.
    """
    org.plan = Plan.DEMO.value
    org.demo_expires_at = utc_now() + timedelta(days=days)
    org.provider_limit = None
    org.status = ORG_STATUS_ACTIVE
    db.flush()
    return org


def set_plan(db: Session, org: Organization, *, plan: Plan) -> Organization:
    """Move the org to a non-demo ``plan``, ALWAYS clearing ``demo_expires_at``
    (a leftover demo deadline on a paid plan would wrongly trip the gate). The
    per-tenant ``provider_limit`` override is left untouched. The caller MUST
    hold a ``FOR UPDATE`` lock on ``org``."""
    org.plan = plan.value
    org.demo_expires_at = None
    db.flush()
    return org


def set_org_status(db: Session, org: Organization, *, status: str) -> Organization:
    """Set ``org.status`` after validating it against ``VALID_ORG_STATUSES``.
    The caller MUST hold a ``FOR UPDATE`` lock on ``org``."""
    if status not in VALID_ORG_STATUSES:
        from fastapi import status as http_status

        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            detail=f"Estado de organización inválido: {status!r}.",
        )
    org.status = status
    db.flush()
    return org


def assert_capability(db: Session, client_id: str, capability: str) -> None:
    """403 unless the client's plan grants ``capability`` (a ``Capability``
    value). Demo lacks ``export_audit_package`` + ``bulk_export``; a missing
    Organization coerces to LEGACY (full), so legacy/orphan clients are never
    gated. Structured ``detail`` so the client UI can branch on ``code``."""
    org = org_for_client_optional(db, client_id)
    plan = plan_for_org(org) if org is not None else Plan.LEGACY
    if not capabilities_for(plan).get(capability, True):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "plan_capability_required",
                "capability": capability,
                "message": "Esta funcionalidad requiere un plan de pago.",
            },
        )
