"""Per-tenant entitlement overrides (Phase D).

A tenant's effective capabilities = the tier default merged with these rows.
This module owns the entitlement CRUD + the pure ``entitlement_overrides``
reader; the merge itself lives in ``subscription.capabilities_for_org`` (which
holds the tier defaults), keeping this module free of plan logic and import
cycles. The capability call sites change once (to read the merged result) and
never again as new entitlements arrive.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.plans import VALID_ENTITLEMENT_KEYS
from app.core.time import utc_now
from app.models import OrganizationEntitlement

__all__ = [
    "entitlement_overrides",
    "grant_entitlement",
    "list_entitlements",
    "revoke_entitlement",
]


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def entitlement_overrides(
    db: Session, org_id: str, *, now: datetime | None = None
) -> dict[str, bool]:
    """Active (non-expired) capability overrides for an org: ``key -> enabled``."""
    moment = now or utc_now()
    out: dict[str, bool] = {}
    for e in db.scalars(
        select(OrganizationEntitlement).where(
            OrganizationEntitlement.organization_id == org_id
        )
    ):
        if e.expires_at is not None and _as_utc(e.expires_at) <= moment:
            continue
        out[e.key] = e.enabled
    return out


def list_entitlements(db: Session, org_id: str) -> list[OrganizationEntitlement]:
    return list(
        db.scalars(
            select(OrganizationEntitlement)
            .where(OrganizationEntitlement.organization_id == org_id)
            .order_by(OrganizationEntitlement.key.asc())
        )
    )


def grant_entitlement(
    db: Session,
    org_id: str,
    *,
    key: str,
    enabled: bool = True,
    expires_at: datetime | None = None,
    note: str | None = None,
    granted_by: str | None = None,
) -> OrganizationEntitlement:
    """Upsert a per-tenant override of ``key`` (validated against
    ``VALID_ENTITLEMENT_KEYS``)."""
    if key not in VALID_ENTITLEMENT_KEYS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Entitlement inválido: {key!r}.",
        )
    row = db.scalar(
        select(OrganizationEntitlement).where(
            OrganizationEntitlement.organization_id == org_id,
            OrganizationEntitlement.key == key,
        )
    )
    if row is None:
        row = OrganizationEntitlement(organization_id=org_id, key=key)
        db.add(row)
    row.enabled = enabled
    row.expires_at = expires_at
    row.note = note
    row.granted_by_user_id = granted_by
    db.flush()
    return row


def revoke_entitlement(db: Session, org_id: str, *, key: str) -> bool:
    """Drop the override for ``key`` (revert to the tier default). Returns
    True if a row was removed."""
    removed = (
        db.query(OrganizationEntitlement)
        .filter(
            OrganizationEntitlement.organization_id == org_id,
            OrganizationEntitlement.key == key,
        )
        .delete(synchronize_session=False)
    )
    db.flush()
    return removed > 0
