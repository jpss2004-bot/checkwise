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
