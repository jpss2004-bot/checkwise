"""Subscription plans: tiers, provider caps, and per-tier capabilities.

The plan is data on ``organizations.plan`` (migration 0056) so lifting a
tenant's tier is an ``UPDATE``, not a deploy — the same discipline as
``seat_limit``. ``organizations.provider_limit`` NULL means "use the tier
default below"; an explicit integer is a per-tenant override (custom /
enterprise deals, or an internal_admin tuning a negotiated cap). ``legacy``
grandfathers every client that predates tiering as uncapped, so introducing
enforcement never strands an existing paying customer.

Phase A consumes ``PLAN_PROVIDER_LIMITS`` (the cap) and *surfaces*
``PLAN_CAPABILITIES`` via ``GET /client/plan``. Phase B *enforces* the
capabilities on the export / audit-package routes; defining them here now
keeps a single source of truth from day one.
"""

from __future__ import annotations

from enum import StrEnum


class Plan(StrEnum):
    """A client organization's subscription tier (``organizations.plan``)."""

    DEMO = "demo"
    STANDARD = "standard"
    GROWTH = "growth"
    ENTERPRISE = "enterprise"  # cap via a per-tenant provider_limit override
    LEGACY = "legacy"  # pre-tiering clients: uncapped, full features


# Value stamped on every existing ``kind='client'`` org by migration 0056.
DEFAULT_PLAN = Plan.LEGACY

# Demo trial length. Phase B sets ``demo_expires_at = now + this`` at
# provisioning; Phase A only models the column.
DEMO_DURATION_DAYS = 14

# Phase B — a frozen demo becomes purge-eligible only after this grace
# window (measured from when it was frozen), so an upgrade can still
# restore everything in place during the window.
DEMO_GRACE_PERIOD_DAYS = 30

# ``organizations.status`` lifecycle (Phase B). ``active`` = normal;
# ``frozen`` = trial ended / suspended (recoverable by upgrade); ``expired``
# is a reserved terminal label set only by an admin. Both non-active states
# block the auth/portal gates, so the single block predicate everywhere is
# ``status != 'active'`` (see ``subscription.is_org_blocked``).
ORG_STATUS_ACTIVE = "active"
ORG_STATUS_FROZEN = "frozen"
ORG_STATUS_EXPIRED = "expired"
VALID_ORG_STATUSES: frozenset[str] = frozenset(
    {ORG_STATUS_ACTIVE, ORG_STATUS_FROZEN, ORG_STATUS_EXPIRED}
)


# Default provider cap per tier. ``None`` = uncapped (no enforcement). An
# explicit ``organizations.provider_limit`` overrides the value here.
PLAN_PROVIDER_LIMITS: dict[Plan, int | None] = {
    Plan.DEMO: 5,
    Plan.STANDARD: 30,
    Plan.GROWTH: 50,
    Plan.ENTERPRISE: None,
    Plan.LEGACY: None,
}

PLAN_LABELS_ES: dict[Plan, str] = {
    Plan.DEMO: "Demo",
    Plan.STANDARD: "Estándar",
    Plan.GROWTH: "Crecimiento",
    Plan.ENTERPRISE: "Empresarial",
    Plan.LEGACY: "Plan actual",
}


class Capability(StrEnum):
    """Feature gates. Phase A SURFACES these (``GET /client/plan``); Phase B
    ENFORCES them on the export / audit-package routes."""

    EXPORT_AUDIT_PACKAGE = "export_audit_package"
    BULK_EXPORT = "bulk_export"
    DOWNLOAD_DOCUMENTS = "download_documents"


# Demo gates heavy / exportable outputs; paid + legacy tiers are full.
_FULL: dict[str, bool] = {c.value: True for c in Capability}
PLAN_CAPABILITIES: dict[Plan, dict[str, bool]] = {
    Plan.DEMO: {
        Capability.EXPORT_AUDIT_PACKAGE.value: False,
        Capability.BULK_EXPORT.value: False,
        Capability.DOWNLOAD_DOCUMENTS.value: True,
    },
    Plan.STANDARD: dict(_FULL),
    Plan.GROWTH: dict(_FULL),
    Plan.ENTERPRISE: dict(_FULL),
    Plan.LEGACY: dict(_FULL),
}


def coerce_plan(value: str | None) -> Plan:
    """NULL / unknown → ``LEGACY`` (uncapped, full) defensively — mirroring
    how the seat layer treats a NULL ``seat_limit`` as the default."""
    if value is None:
        return Plan.LEGACY
    try:
        return Plan(value)
    except ValueError:
        return Plan.LEGACY


def provider_limit_default(plan: Plan) -> int | None:
    """The tier's default provider cap (``None`` = uncapped)."""
    return PLAN_PROVIDER_LIMITS[plan]


def capabilities_for(plan: Plan) -> dict[str, bool]:
    """A fresh copy of the tier's capability flags."""
    return dict(PLAN_CAPABILITIES[plan])


# ---------------------------------------------------------------------------
# Phase D — per-tenant entitlements + the provider-agnostic billing seam
# ---------------------------------------------------------------------------

# Keys an ``OrganizationEntitlement`` row may override. Today these are the
# capability flags (a per-tenant grant/revoke layered over the tier default);
# the set widens as new entitlements arrive — call sites never change because
# they read the merged ``capabilities_for_org``.
VALID_ENTITLEMENT_KEYS: frozenset[str] = frozenset(c.value for c in Capability)


class BillingProviderName(StrEnum):
    """Which billing backend owns a tenant's subscription. ``manual`` = an
    internal admin manages the plan by hand (the only wired path today);
    ``stripe`` is reserved for the stubbed adapter (Phase D ships the seam,
    not a live Stripe integration)."""

    MANUAL = "manual"
    STRIPE = "stripe"


class BillingStatus(StrEnum):
    """Provider-agnostic subscription status mirrored onto ``billing_accounts``."""

    NONE = "none"
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


VALID_BILLING_PROVIDERS: frozenset[str] = frozenset(p.value for p in BillingProviderName)
VALID_BILLING_STATUSES: frozenset[str] = frozenset(s.value for s in BillingStatus)
