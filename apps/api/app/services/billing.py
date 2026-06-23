"""Provider-agnostic billing seam (Phase D).

One ``BillingAccount`` per client org records which provider owns the
subscription plus mirrored state (customer/subscription ids, status, period
end). ``manual`` — an internal admin manages the plan by hand — is the only
wired path. ``apply_billing_state`` is the single entry that mirrors provider
state onto the account and (optionally) maps it onto the plan; a future Stripe
webhook calls exactly this. The ``BillingProvider`` protocol + the
``StripeBillingProvider`` STUB mark where a live integration slots in without
coupling the plan/entitlement layer to any provider.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.plans import (
    VALID_BILLING_PROVIDERS,
    VALID_BILLING_STATUSES,
    BillingProviderName,
    Plan,
)
from app.models import BillingAccount, Organization
from app.services.subscription import set_plan

__all__ = [
    "BillingProvider",
    "ManualBillingProvider",
    "StripeBillingProvider",
    "apply_billing_state",
    "get_billing_provider",
    "get_or_create_billing_account",
]


def get_or_create_billing_account(db: Session, org: Organization) -> BillingAccount:
    """The org's billing account, created (provider='manual') on first read."""
    acct = db.scalar(
        select(BillingAccount).where(BillingAccount.organization_id == org.id)
    )
    if acct is None:
        acct = BillingAccount(
            organization_id=org.id,
            provider=BillingProviderName.MANUAL.value,
            status="none",
        )
        db.add(acct)
        db.flush()
    return acct


def apply_billing_state(
    db: Session,
    org: Organization,
    *,
    provider: str | None = None,
    status_value: str | None = None,
    customer_id: str | None = None,
    subscription_id: str | None = None,
    current_period_end: datetime | None = None,
    plan: Plan | None = None,
) -> BillingAccount:
    """Mirror provider/subscription state onto the org's billing account. When
    ``plan`` is given, also move the org to that plan via ``set_plan`` (this is
    how a real webhook would promote a tenant on a successful subscription).
    Validates ``provider`` / ``status_value`` against the canonical sets.
    """
    acct = get_or_create_billing_account(db, org)
    if provider is not None:
        if provider not in VALID_BILLING_PROVIDERS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Proveedor de facturación inválido: {provider!r}.",
            )
        acct.provider = provider
    if status_value is not None:
        if status_value not in VALID_BILLING_STATUSES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Estado de facturación inválido: {status_value!r}.",
            )
        acct.status = status_value
    if customer_id is not None:
        acct.customer_id = customer_id
    if subscription_id is not None:
        acct.subscription_id = subscription_id
    if current_period_end is not None:
        acct.current_period_end = current_period_end
    if plan is not None:
        set_plan(db, org, plan=plan)
    db.flush()
    return acct


# ---------------------------------------------------------------------------
# Provider adapters — the seam. Only ``manual`` is wired.
# ---------------------------------------------------------------------------


class BillingProvider(Protocol):
    name: str

    def start_checkout(self, db: Session, org: Organization, *, plan: Plan) -> str:
        """Return a URL the client is redirected to in order to pay."""
        ...


class ManualBillingProvider:
    """Default — an internal admin sets the plan by hand; there is no checkout."""

    name = BillingProviderName.MANUAL.value

    def start_checkout(self, db: Session, org: Organization, *, plan: Plan) -> str:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Este cliente se factura manualmente; no hay flujo de pago.",
        )


class StripeBillingProvider:
    """STUB — Phase D ships the seam, NOT a live Stripe integration. Wiring
    Stripe means implementing ``start_checkout`` against the Stripe SDK and a
    webhook that calls ``apply_billing_state`` with the synced subscription.
    Until then every method fails loudly so it can never be used by accident.
    """

    name = BillingProviderName.STRIPE.value

    def start_checkout(self, db: Session, org: Organization, *, plan: Plan) -> str:
        raise NotImplementedError(
            "Stripe billing is not wired — Phase D ships the seam only."
        )


_PROVIDERS: dict[str, BillingProvider] = {
    ManualBillingProvider.name: ManualBillingProvider(),
    StripeBillingProvider.name: StripeBillingProvider(),
}


def get_billing_provider(name: str) -> BillingProvider:
    provider = _PROVIDERS.get(name)
    if provider is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Proveedor de facturación desconocido: {name!r}.",
        )
    return provider
