"""Phase 7 — Admin Operations Core.

LegalShelf internal control plane. Every endpoint is gated on the
``internal_admin`` role (the ``reviewer`` role alone is **not**
sufficient — reviewers read the queue, admins operate the platform).

Surfaces:

* ``GET /admin/overview`` — single operational summary.
* ``/admin/clients`` — list / get / create / patch (no delete).
* ``/admin/vendors`` — list / get / create / patch (no delete).
  Enforces vendor.client_id refers to an existing client and the
  unique (client_id, rfc) constraint.
* ``/admin/workspaces`` — read + minimal patch (status, owner,
  display_name, filial_name). ``access_token`` is NEVER returned.
* ``/admin/requirements`` — list / get / create / patch. On create,
  an initial ``RequirementVersion`` is spawned when caller supplies
  any version-shaped fields.
* ``GET /admin/periods`` and ``GET /admin/calendar?year=`` —
  read-only operational visibility into period rows + recurring
  catalog summary.
* ``GET /admin/audit-log`` — filtered audit-log explorer.

Every mutation writes an ``AuditLog`` row with
``action="admin.<entity>.<verb>"`` and
``metadata={"source": "admin_operations", ...}`` so the audit-log
explorer itself answers "what did this admin do."
"""

from __future__ import annotations

import re
import unicodedata
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Final, Literal
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.auth import CurrentUser, require_role
from app.constants.roles import MembershipRole
from app.constants.statuses import DocumentStatus
from app.core.compliance_catalog import (
    catalog_metadata,
    recurring_for_year,
    recurring_for_year_v2,
)
from app.core.config import settings
from app.core.period_validation import MAX_YEAR, MIN_YEAR
from app.db.session import get_db
from app.models import (
    AuditLog,
    Client,
    ContactRequest,
    Document,
    FeedbackReport,
    Institution,
    Period,
    ProviderWorkspace,
    Requirement,
    RequirementVersion,
    Submission,
    User,
    ValidationEvent,
    Vendor,
)
from app.services.audit_log import add_audit_event

router = APIRouter(prefix="/admin", tags=["admin"])
DbSession = Annotated[Session, Depends(get_db)]
AdminUser = Annotated[
    CurrentUser, Depends(require_role(MembershipRole.INTERNAL_ADMIN))
]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _audit_admin(
    db: Session,
    *,
    actor: CurrentUser,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict | None,
    after: dict | None,
    extra_metadata: dict | None = None,
) -> None:
    """Write the standard admin-operations audit row.

    Every admin mutation goes through here so the audit-log explorer
    can filter on ``actor_type='internal_admin'`` or
    ``metadata.source='admin_operations'`` and surface every action a
    LegalShelf operator took. Don't bypass this helper.
    """
    metadata = {"source": "admin_operations"}
    if extra_metadata:
        metadata.update(extra_metadata)
    add_audit_event(
        db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_type="internal_admin",
        actor_id=actor.user.id,
        before=before,
        after=after,
        metadata=metadata,
    )


def _client_to_dict(row: Client) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "rfc": row.rfc,
        "email": row.email,
        "responsible_name": row.responsible_name,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _vendor_to_dict(row: Vendor) -> dict:
    return {
        "id": row.id,
        "client_id": row.client_id,
        "name": row.name,
        "rfc": row.rfc,
        "contact_name": row.contact_name,
        "contact_email": row.contact_email,
        "contact_phone": row.contact_phone,
        "repse_id": row.repse_id,
        "persona_type": row.persona_type,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _workspace_to_dict(row: ProviderWorkspace) -> dict:
    """Workspace serializer — NEVER includes the access_token.

    Phase 7 contract: the admin surfaces operate the tenant model but
    must not leak the workspace session token. The token is the
    provider's session credential; exposing it would defeat the
    tenant-safe upload guard.
    """
    return {
        "id": row.id,
        "client_id": row.client_id,
        "vendor_id": row.vendor_id,
        "contract_id": row.contract_id,
        "owner_user_id": row.owner_user_id,
        "persona_type": row.persona_type,
        "display_name": row.display_name,
        "filial_name": row.filial_name,
        "onboarding_completed_at": (
            row.onboarding_completed_at.isoformat()
            if row.onboarding_completed_at
            else None
        ),
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _requirement_to_dict(row: Requirement, *, version: RequirementVersion | None) -> dict:
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "institution_id": row.institution_id,
        "load_type": row.load_type,
        "frequency": row.frequency,
        "risk_level": row.risk_level,
        "is_active": row.is_active,
        "current_version": row.current_version,
        "version": (
            {
                "id": version.id,
                "version": version.version,
                "legal_basis": version.legal_basis,
                "applicability_rule": version.applicability_rule,
                "minimum_validation": version.minimum_validation,
                "automatic_signals": version.automatic_signals,
                "human_review_required": version.human_review_required,
                "missing_state": version.missing_state,
                "temporal_rule": version.temporal_rule,
                "source_url": version.source_url,
                "implementation_notes": version.implementation_notes,
                "required": version.required,
                "effective_from": (
                    version.effective_from.isoformat() if version.effective_from else None
                ),
                "effective_to": (
                    version.effective_to.isoformat() if version.effective_to else None
                ),
            }
            if version is not None
            else None
        ),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _period_to_dict(row: Period) -> dict:
    return {
        "id": row.id,
        "code": row.code,
        "period_key": row.period_key,
        "year": row.year,
        "month": row.month,
        "period_type": row.period_type,
        "starts_on": row.starts_on.isoformat() if row.starts_on else None,
        "ends_on": row.ends_on.isoformat() if row.ends_on else None,
        "due_on": row.due_on.isoformat() if row.due_on else None,
    }


def _load_current_version(db: Session, requirement: Requirement) -> RequirementVersion | None:
    return db.scalar(
        select(RequirementVersion)
        .where(
            RequirementVersion.requirement_id == requirement.id,
            RequirementVersion.version == requirement.current_version,
        )
        .limit(1)
    )


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


_QUEUE_STATUSES = (
    DocumentStatus.RECIBIDO.value,
    DocumentStatus.PENDIENTE_REVISION.value,
    DocumentStatus.PREVALIDADO.value,
    DocumentStatus.POSIBLE_MISMATCH.value,
)
_REJECTED_OR_CORRECTION_STATUSES = (
    DocumentStatus.RECHAZADO.value,
    DocumentStatus.REQUIERE_ACLARACION.value,
    DocumentStatus.POSIBLE_MISMATCH.value,
)


class AdminOverview(BaseModel):
    clients_total: int
    vendors_total: int
    active_workspaces_total: int
    pending_reviews_total: int
    rejected_or_correction_total: int
    recent_submissions_total: int
    recent_audit_events_total: int


@router.get("/overview", response_model=AdminOverview)
def get_overview(db: DbSession, current: AdminUser) -> AdminOverview:
    """Operational counters for the admin home page.

    ``recent_*`` fields count the last 100 rows in the respective
    tables — enough to spot a sudden spike without expensive date math
    on day-one of the surface. Replace with a time-bounded query when
    a real ops dashboard surface lands.
    """
    _ = current
    clients_total = int(db.scalar(select(func.count(Client.id))) or 0)
    vendors_total = int(db.scalar(select(func.count(Vendor.id))) or 0)
    active_workspaces_total = int(
        db.scalar(
            select(func.count(ProviderWorkspace.id)).where(
                ProviderWorkspace.status == "active"
            )
        )
        or 0
    )
    pending_reviews_total = int(
        db.scalar(
            select(func.count(Submission.id)).where(
                Submission.status.in_(_QUEUE_STATUSES)
            )
        )
        or 0
    )
    rejected_or_correction_total = int(
        db.scalar(
            select(func.count(Submission.id)).where(
                Submission.status.in_(_REJECTED_OR_CORRECTION_STATUSES)
            )
        )
        or 0
    )
    submissions_total = int(db.scalar(select(func.count(Submission.id))) or 0)
    audit_total = int(db.scalar(select(func.count(AuditLog.id))) or 0)
    return AdminOverview(
        clients_total=clients_total,
        vendors_total=vendors_total,
        active_workspaces_total=active_workspaces_total,
        pending_reviews_total=pending_reviews_total,
        rejected_or_correction_total=rejected_or_correction_total,
        recent_submissions_total=min(submissions_total, 100),
        recent_audit_events_total=min(audit_total, 100),
    )


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


class ClientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    rfc: str | None = Field(default=None, max_length=13)
    # Junta 2026-05-23 — email es uno de los tres datos mínimos al
    # dar de alta a un cliente nuevo. EmailStr garantiza formato; el
    # admin form lo marca como requerido en UI.
    email: EmailStr = Field(...)
    responsible_name: str | None = Field(default=None, max_length=255)
    status: str = "active"


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    rfc: str | None = Field(default=None, max_length=13)
    email: EmailStr | None = Field(default=None)
    responsible_name: str | None = Field(default=None, max_length=255)
    status: str | None = None


@router.get("/clients")
def list_clients(db: DbSession, current: AdminUser) -> dict:
    _ = current
    rows = list(db.scalars(select(Client).order_by(Client.created_at.desc())))
    return {"items": [_client_to_dict(r) for r in rows], "total": len(rows)}


@router.get("/clients/{client_id}")
def get_client(client_id: str, db: DbSession, current: AdminUser) -> dict:
    _ = current
    row = db.get(Client, client_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")
    return _client_to_dict(row)


@router.post("/clients", status_code=status.HTTP_201_CREATED)
def create_client(payload: ClientCreate, db: DbSession, current: AdminUser) -> dict:
    row = Client(
        name=payload.name.strip(),
        rfc=(payload.rfc or "").strip().upper() or None,
        email=payload.email.strip().lower(),
        responsible_name=(payload.responsible_name or "").strip() or None,
        status=payload.status or "active",
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="RFC ya está en uso."
        ) from exc
    _audit_admin(
        db,
        actor=current,
        action="admin.client.created",
        entity_type="client",
        entity_id=row.id,
        before=None,
        after=_client_to_dict(row),
    )
    db.commit()
    db.refresh(row)
    return _client_to_dict(row)


@router.patch("/clients/{client_id}")
def update_client(
    client_id: str, payload: ClientUpdate, db: DbSession, current: AdminUser
) -> dict:
    row = db.get(Client, client_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")
    before = _client_to_dict(row)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    if "rfc" in data:
        row.rfc = (data["rfc"] or "").strip().upper() or None
    if "email" in data:
        row.email = (data["email"] or "").strip().lower() or None
    if "responsible_name" in data:
        row.responsible_name = (data["responsible_name"] or "").strip() or None
    if "status" in data and data["status"] is not None:
        row.status = data["status"]
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="RFC ya está en uso."
        ) from exc
    after = _client_to_dict(row)
    _audit_admin(
        db,
        actor=current,
        action="admin.client.updated",
        entity_type="client",
        entity_id=row.id,
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(row)
    return _client_to_dict(row)


# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------


class VendorCreate(BaseModel):
    client_id: str
    name: str = Field(min_length=2, max_length=255)
    rfc: str = Field(min_length=12, max_length=13)
    contact_name: str | None = None
    contact_email: str | None = None
    repse_id: str | None = None
    persona_type: Literal["moral", "fisica"] | None = None
    status: str = "active"


class VendorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    contact_name: str | None = None
    contact_email: str | None = None
    repse_id: str | None = None
    persona_type: Literal["moral", "fisica"] | None = None
    status: str | None = None


@router.get("/vendors")
def list_vendors(
    db: DbSession,
    current: AdminUser,
    client_id: str | None = None,
) -> dict:
    _ = current
    stmt = select(Vendor).order_by(Vendor.created_at.desc())
    if client_id:
        stmt = stmt.where(Vendor.client_id == client_id)
    rows = list(db.scalars(stmt))
    return {"items": [_vendor_to_dict(r) for r in rows], "total": len(rows)}


@router.get("/vendors/{vendor_id}")
def get_vendor(vendor_id: str, db: DbSession, current: AdminUser) -> dict:
    _ = current
    row = db.get(Vendor, vendor_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proveedor no encontrado.")
    return _vendor_to_dict(row)


@router.post("/vendors", status_code=status.HTTP_201_CREATED)
def create_vendor(payload: VendorCreate, db: DbSession, current: AdminUser) -> dict:
    client = db.get(Client, payload.client_id)
    if client is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado; crea el cliente antes del proveedor.",
        )
    row = Vendor(
        client_id=payload.client_id,
        name=payload.name.strip(),
        rfc=payload.rfc.strip().upper(),
        contact_name=(payload.contact_name or "").strip() or None,
        contact_email=(payload.contact_email or "").strip() or None,
        repse_id=(payload.repse_id or "").strip() or None,
        persona_type=payload.persona_type,
        status=payload.status or "active",
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Ya existe un proveedor con ese RFC para este cliente.",
        ) from exc
    _audit_admin(
        db,
        actor=current,
        action="admin.vendor.created",
        entity_type="vendor",
        entity_id=row.id,
        before=None,
        after=_vendor_to_dict(row),
    )
    db.commit()
    db.refresh(row)
    return _vendor_to_dict(row)


@router.patch("/vendors/{vendor_id}")
def update_vendor(
    vendor_id: str, payload: VendorUpdate, db: DbSession, current: AdminUser
) -> dict:
    row = db.get(Vendor, vendor_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proveedor no encontrado.")
    before = _vendor_to_dict(row)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    if "contact_name" in data:
        row.contact_name = (data["contact_name"] or "").strip() or None
    if "contact_email" in data:
        row.contact_email = (data["contact_email"] or "").strip() or None
    if "repse_id" in data:
        row.repse_id = (data["repse_id"] or "").strip() or None
    if "persona_type" in data:
        row.persona_type = data["persona_type"]
    if "status" in data and data["status"] is not None:
        row.status = data["status"]
    db.flush()
    after = _vendor_to_dict(row)
    _audit_admin(
        db,
        actor=current,
        action="admin.vendor.updated",
        entity_type="vendor",
        entity_id=row.id,
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(row)
    return _vendor_to_dict(row)


# ---------------------------------------------------------------------------
# Provider workspaces
# ---------------------------------------------------------------------------


class WorkspaceUpdate(BaseModel):
    status: str | None = None
    owner_user_id: str | None = None
    display_name: str | None = None
    filial_name: str | None = None


@router.get("/workspaces")
def list_workspaces(
    db: DbSession,
    current: AdminUser,
    client_id: str | None = None,
    vendor_id: str | None = None,
) -> dict:
    _ = current
    stmt = select(ProviderWorkspace).order_by(ProviderWorkspace.created_at.desc())
    if client_id:
        stmt = stmt.where(ProviderWorkspace.client_id == client_id)
    if vendor_id:
        stmt = stmt.where(ProviderWorkspace.vendor_id == vendor_id)
    rows = list(db.scalars(stmt))
    return {"items": [_workspace_to_dict(r) for r in rows], "total": len(rows)}


@router.get("/workspaces/{workspace_id}")
def get_workspace_admin(
    workspace_id: str, db: DbSession, current: AdminUser
) -> dict:
    _ = current
    row = db.get(ProviderWorkspace, workspace_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Workspace no encontrado.")
    return _workspace_to_dict(row)


@router.patch("/workspaces/{workspace_id}")
def update_workspace_admin(
    workspace_id: str,
    payload: WorkspaceUpdate,
    db: DbSession,
    current: AdminUser,
) -> dict:
    row = db.get(ProviderWorkspace, workspace_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Workspace no encontrado.")
    before = _workspace_to_dict(row)
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] is not None:
        row.status = data["status"]
    if "owner_user_id" in data:
        row.owner_user_id = data["owner_user_id"] or None
    if "display_name" in data:
        row.display_name = (data["display_name"] or "").strip() or None
    if "filial_name" in data:
        row.filial_name = (data["filial_name"] or "").strip() or None
    db.flush()
    after = _workspace_to_dict(row)
    _audit_admin(
        db,
        actor=current,
        action="admin.workspace.updated",
        entity_type="provider_workspace",
        entity_id=row.id,
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(row)
    return _workspace_to_dict(row)


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------


class RequirementCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=255)
    institution_id: str
    load_type: str
    frequency: str
    risk_level: str = "medium"
    is_active: bool = True
    # Optional initial RequirementVersion fields. When any of these are
    # supplied, an initial version=1 row is created alongside the
    # Requirement.
    legal_basis: str | None = None
    applicability_rule: str | None = None
    minimum_validation: str | None = None
    automatic_signals: str | None = None
    human_review_required: bool | None = None
    missing_state: str | None = None
    temporal_rule: str | None = None
    source_url: str | None = None
    implementation_notes: str | None = None
    required: bool | None = None


class RequirementUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    institution_id: str | None = None
    load_type: str | None = None
    frequency: str | None = None
    risk_level: str | None = None
    is_active: bool | None = None


@router.get("/requirements")
def list_requirements(
    db: DbSession,
    current: AdminUser,
    institution_id: str | None = None,
    is_active: bool | None = None,
) -> dict:
    _ = current
    stmt = select(Requirement).order_by(Requirement.code.asc())
    if institution_id:
        stmt = stmt.where(Requirement.institution_id == institution_id)
    if is_active is not None:
        stmt = stmt.where(Requirement.is_active == is_active)
    rows = list(db.scalars(stmt))
    items = []
    for r in rows:
        v = _load_current_version(db, r)
        items.append(_requirement_to_dict(r, version=v))
    return {"items": items, "total": len(items)}


@router.get("/requirements/{requirement_id}")
def get_requirement(
    requirement_id: str, db: DbSession, current: AdminUser
) -> dict:
    _ = current
    row = db.get(Requirement, requirement_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisito no encontrado.")
    return _requirement_to_dict(row, version=_load_current_version(db, row))


@router.post("/requirements", status_code=status.HTTP_201_CREATED)
def create_requirement(
    payload: RequirementCreate, db: DbSession, current: AdminUser
) -> dict:
    institution = db.get(Institution, payload.institution_id)
    if institution is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Institución no encontrada.",
        )
    requirement = Requirement(
        code=payload.code.strip(),
        name=payload.name.strip(),
        institution_id=payload.institution_id,
        load_type=payload.load_type,
        frequency=payload.frequency,
        risk_level=payload.risk_level,
        is_active=payload.is_active,
        current_version=1,
    )
    db.add(requirement)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Ya existe un requisito con ese código.",
        ) from exc

    version: RequirementVersion | None = None
    version_fields = {
        "legal_basis": payload.legal_basis,
        "applicability_rule": payload.applicability_rule,
        "minimum_validation": payload.minimum_validation,
        "automatic_signals": payload.automatic_signals,
        "human_review_required": payload.human_review_required,
        "missing_state": payload.missing_state,
        "temporal_rule": payload.temporal_rule,
        "source_url": payload.source_url,
        "implementation_notes": payload.implementation_notes,
        "required": payload.required,
    }
    if any(v is not None for v in version_fields.values()):
        version = RequirementVersion(
            requirement_id=requirement.id,
            version=1,
            legal_basis=payload.legal_basis,
            applicability_rule=payload.applicability_rule,
            minimum_validation=payload.minimum_validation,
            automatic_signals=payload.automatic_signals,
            human_review_required=(
                payload.human_review_required
                if payload.human_review_required is not None
                else True
            ),
            missing_state=payload.missing_state,
            temporal_rule=payload.temporal_rule,
            source_url=payload.source_url,
            implementation_notes=payload.implementation_notes,
            required=(payload.required if payload.required is not None else True),
        )
        db.add(version)
        db.flush()

    _audit_admin(
        db,
        actor=current,
        action="admin.requirement.created",
        entity_type="requirement",
        entity_id=requirement.id,
        before=None,
        after=_requirement_to_dict(requirement, version=version),
        extra_metadata={"created_version": version.id if version else None},
    )
    db.commit()
    db.refresh(requirement)
    return _requirement_to_dict(requirement, version=_load_current_version(db, requirement))


@router.patch("/requirements/{requirement_id}")
def update_requirement(
    requirement_id: str,
    payload: RequirementUpdate,
    db: DbSession,
    current: AdminUser,
) -> dict:
    row = db.get(Requirement, requirement_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Requisito no encontrado.")
    before = _requirement_to_dict(row, version=_load_current_version(db, row))
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    if "institution_id" in data and data["institution_id"] is not None:
        institution = db.get(Institution, data["institution_id"])
        if institution is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Institución no encontrada."
            )
        row.institution_id = data["institution_id"]
    if "load_type" in data and data["load_type"] is not None:
        row.load_type = data["load_type"]
    if "frequency" in data and data["frequency"] is not None:
        row.frequency = data["frequency"]
    if "risk_level" in data and data["risk_level"] is not None:
        row.risk_level = data["risk_level"]
    if "is_active" in data and data["is_active"] is not None:
        row.is_active = data["is_active"]
    db.flush()
    after = _requirement_to_dict(row, version=_load_current_version(db, row))
    _audit_admin(
        db,
        actor=current,
        action="admin.requirement.updated",
        entity_type="requirement",
        entity_id=row.id,
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(row)
    return _requirement_to_dict(row, version=_load_current_version(db, row))


# ---------------------------------------------------------------------------
# Periods + calendar oversight (read-only)
# ---------------------------------------------------------------------------


@router.get("/periods")
def list_periods(
    db: DbSession,
    current: AdminUser,
    year: Annotated[int | None, Query(ge=MIN_YEAR, le=MAX_YEAR)] = None,
    period_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict:
    """Read-only Period roster. Phase 7 keeps it list-only."""
    _ = current
    stmt = select(Period).order_by(
        Period.year.desc().nulls_last(),
        Period.month.desc().nulls_last(),
    )
    if year is not None:
        stmt = stmt.where(Period.year == year)
    if period_type:
        stmt = stmt.where(Period.period_type == period_type)
    stmt = stmt.limit(limit)
    rows = list(db.scalars(stmt))
    return {"items": [_period_to_dict(r) for r in rows], "total": len(rows)}


@router.get("/calendar")
def get_admin_calendar(
    db: DbSession,
    current: AdminUser,
    year: Annotated[int | None, Query(ge=MIN_YEAR, le=MAX_YEAR)] = None,
    persona_type: Literal["moral", "fisica"] = "moral",
) -> dict:
    """Aggregated recurring catalog snapshot for the requested year.

    Read-only — same canonical catalog that powers the provider
    calendar, summarised by institution × month. The admin surface
    can use this to confirm a year is correctly seeded without
    drilling into per-provider workspaces.

    When ``year`` is omitted, defaults to the current calendar year so
    the snapshot keeps tracking the operator's "now" without a stale
    hardcoded fallback (mirrors the BL-T3 spirit on the frontend).
    """
    _ = current
    target_year = year if year is not None else date.today().year
    # Session 2 (2026-05-21) — flag-aware. The admin-side "expected
    # rows per month" count drops dramatically under v2 (collapsed
    # alternatives). Operators reading this endpoint after the flag
    # flips will see the new totals — consistent with the v2 calendar
    # in the provider portal.
    catalog = (
        recurring_for_year_v2(target_year, persona_type)
        if settings.RECURRING_CATALOG_V2
        else recurring_for_year(target_year, persona_type)
    )
    months: dict[int, dict] = {
        m: {"month": m, "institutions": {}, "expected_total": 0} for m in range(1, 13)
    }
    for req in catalog:
        bucket = months[req.due_month]["institutions"]
        inst = bucket.setdefault(
            req.institution, {"institution": req.institution, "expected": 0}
        )
        inst["expected"] += 1
        months[req.due_month]["expected_total"] += 1
    return {
        "metadata": catalog_metadata(),
        "year": target_year,
        "persona_type": persona_type,
        "months": [
            {
                "month": m["month"],
                "expected_total": m["expected_total"],
                "institutions": list(m["institutions"].values()),
            }
            for m in months.values()
        ],
    }


# ---------------------------------------------------------------------------
# Contact requests (public landing-form leads, P0-3 follow-up)
#
# Valid status values: ``new`` → ``reviewed`` → ``contacted`` → ``closed``.
# Enforced at the Pydantic boundary via ``Literal`` on
# ``ContactRequestStatusUpdate`` and the ``status`` query param of the
# list endpoint; no separate enum needed.
# ---------------------------------------------------------------------------


class ContactRequestAdminItem(BaseModel):
    id: str
    name: str
    email: str
    company: str | None
    role: str | None
    message: str
    source: str
    status: str
    ip_hash: str | None
    user_agent: str | None
    created_at: datetime
    updated_at: datetime


class ContactRequestList(BaseModel):
    items: list[ContactRequestAdminItem]
    total: int
    limit: int
    offset: int


class ContactRequestStatusUpdate(BaseModel):
    status: Literal["new", "reviewed", "contacted", "closed"]


def _contact_to_dict(row: ContactRequest) -> ContactRequestAdminItem:
    return ContactRequestAdminItem(
        id=row.id,
        name=row.name,
        email=row.email,
        company=row.company,
        role=row.role,
        message=row.message,
        source=row.source,
        status=row.status,
        ip_hash=row.ip_hash,
        user_agent=row.user_agent,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/contact-requests", response_model=ContactRequestList)
def list_contact_requests(
    db: DbSession,
    current: AdminUser,
    status_filter: Annotated[
        Literal["new", "reviewed", "contacted", "closed"] | None,
        Query(alias="status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ContactRequestList:
    """List public-landing contact requests, newest first.

    Internal-admin only. Pagination via ``limit`` (max 200) + ``offset``.
    Optional ``status`` query narrows to one of new/reviewed/contacted/closed.
    """
    _ = current
    stmt = select(ContactRequest)
    if status_filter:
        stmt = stmt.where(ContactRequest.status == status_filter)

    total_stmt = select(func.count()).select_from(ContactRequest)
    if status_filter:
        total_stmt = total_stmt.where(ContactRequest.status == status_filter)
    total = int(db.scalar(total_stmt) or 0)

    stmt = stmt.order_by(ContactRequest.created_at.desc()).limit(limit).offset(offset)
    rows = list(db.scalars(stmt))
    return ContactRequestList(
        items=[_contact_to_dict(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/contact-requests/{request_id}",
    response_model=ContactRequestAdminItem,
)
def update_contact_request_status(
    request_id: str,
    payload: ContactRequestStatusUpdate,
    db: DbSession,
    current: AdminUser,
) -> ContactRequestAdminItem:
    """Move a contact request through the triage lifecycle.

    The valid transitions are recorded for audit; we do NOT enforce a
    strict graph (admins can correct a mis-set status). Status values
    are validated by the Pydantic Literal on the payload.
    """
    row = db.get(ContactRequest, request_id)
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada."
        )
    # ``mode="json"`` so datetime fields land as ISO strings — required
    # because the audit_log.before/after columns store as JSON.
    before = _contact_to_dict(row).model_dump(mode="json")
    row.status = payload.status
    db.flush()
    after = _contact_to_dict(row).model_dump(mode="json")
    _audit_admin(
        db,
        actor=current,
        action="admin.contact_request.status_changed",
        entity_type="contact_request",
        entity_id=row.id,
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(row)
    return _contact_to_dict(row)


# ---------------------------------------------------------------------------
# Provider correction-request triage (Stage 2.7-a admin approval flow)
#
# Provider-side submissions land as audit_log rows with
# ``action='correction_request.submitted'``. Admins read them here,
# approve (auto-apply to Vendor.contact_{name|email|phone}) or reject.
# Resolution is tracked by mutating the original row's
# ``event_metadata.status`` AND writing a sibling audit_log row so the
# audit trail captures who decided what and when.
# ---------------------------------------------------------------------------


_CORRECTION_FIELD_TO_VENDOR_COLUMN: Final[dict[str, str]] = {
    "contact_email": "contact_email",
    "contact_phone": "contact_phone",
    "contact_name": "contact_name",
}


class CorrectionRequestAdminItem(BaseModel):
    id: str
    status: Literal["pending", "approved", "rejected"]
    workspace_id: str
    vendor_id: str | None
    vendor_name: str | None
    vendor_rfc: str | None
    client_id: str | None
    client_name: str | None
    user_id: str
    user_email: str | None
    user_name: str | None
    field: str
    current_value: str
    proposed_value: str
    reason: str
    message: str | None
    submitted_at: datetime
    resolved_at: datetime | None = None
    resolved_by_user_id: str | None = None
    resolution_note: str | None = None


class CorrectionRequestList(BaseModel):
    items: list[CorrectionRequestAdminItem]
    total: int
    limit: int
    offset: int


class CorrectionRequestResolution(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


def _correction_row_to_item(
    row: AuditLog,
    *,
    vendor: Vendor | None,
    client: Client | None,
    user: User | None,
) -> CorrectionRequestAdminItem:
    meta = row.event_metadata or {}
    before = row.before or {}
    after = row.after or {}
    raw_status = meta.get("status", "pending")
    status_val: Literal["pending", "approved", "rejected"] = (
        raw_status if raw_status in ("pending", "approved", "rejected") else "pending"
    )
    return CorrectionRequestAdminItem(
        id=row.id,
        status=status_val,
        workspace_id=row.entity_id,
        vendor_id=vendor.id if vendor else None,
        vendor_name=vendor.name if vendor else None,
        vendor_rfc=vendor.rfc if vendor else None,
        client_id=client.id if client else None,
        client_name=client.name if client else None,
        user_id=row.actor_id or "",
        user_email=(meta.get("user_email") if isinstance(meta, dict) else None)
        or (user.email if user else None),
        user_name=user.full_name if user else None,
        field=str(before.get("field") or after.get("field") or ""),
        current_value=str(before.get("value") or ""),
        proposed_value=str(after.get("value") or ""),
        reason=str(meta.get("reason") or ""),
        message=meta.get("message"),
        submitted_at=row.created_at,
        resolved_at=(
            datetime.fromisoformat(meta["resolved_at"])
            if isinstance(meta.get("resolved_at"), str)
            else None
        ),
        resolved_by_user_id=meta.get("resolved_by_user_id"),
        resolution_note=meta.get("resolution_note"),
    )


def _load_correction_context(
    db: Session, row: AuditLog
) -> tuple[Vendor | None, Client | None, User | None]:
    """Look up the workspace -> vendor + client + actor user for an audit row.

    ``row.entity_id`` is the workspace_id. The workspace is the only
    record-level link to the vendor (and through it, the client). Any
    lookup that fails returns None so the list endpoint stays robust
    against an orphaned correction request.
    """
    workspace = db.get(ProviderWorkspace, row.entity_id) if row.entity_id else None
    vendor = workspace.vendor if workspace else None
    client = workspace.client if workspace else None
    user = db.get(User, row.actor_id) if row.actor_id else None
    return vendor, client, user


def _get_correction_row_or_404(db: Session, request_id: str) -> AuditLog:
    row = db.get(AuditLog, request_id)
    if row is None or row.action != "correction_request.submitted":
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Solicitud de corrección no encontrada.",
        )
    return row


@router.get("/correction-requests", response_model=CorrectionRequestList)
def list_correction_requests(
    db: DbSession,
    current: AdminUser,
    status_filter: Annotated[
        Literal["pending", "approved", "rejected"] | None,
        Query(alias="status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CorrectionRequestList:
    """List provider correction requests, newest first.

    Reads ``audit_log`` rows with ``action='correction_request.submitted'``
    and joins the workspace -> vendor + client + actor user for the
    admin UI. Status filtering happens in Python against
    ``event_metadata.status`` because JSON-column WHERE clauses are not
    portable across SQLite (tests) and Postgres (prod). The dataset is
    small enough that the in-memory filter is fine.
    """
    _ = current
    stmt = (
        select(AuditLog)
        .where(AuditLog.action == "correction_request.submitted")
        .order_by(AuditLog.created_at.desc())
    )
    rows = list(db.scalars(stmt))

    def _row_status(r: AuditLog) -> str:
        meta = r.event_metadata or {}
        return meta.get("status", "pending") if isinstance(meta, dict) else "pending"

    if status_filter:
        rows = [r for r in rows if _row_status(r) == status_filter]
    total = len(rows)
    page = rows[offset : offset + limit]

    items: list[CorrectionRequestAdminItem] = []
    for row in page:
        vendor, client, user = _load_correction_context(db, row)
        items.append(
            _correction_row_to_item(row, vendor=vendor, client=client, user=user)
        )

    return CorrectionRequestList(
        items=items, total=total, limit=limit, offset=offset
    )


def _resolve_correction(
    db: Session,
    *,
    current: CurrentUser,
    row: AuditLog,
    decision: Literal["approved", "rejected"],
    note: str | None,
) -> CorrectionRequestAdminItem:
    """Shared resolver for approve / reject. Mutates the original
    audit row's event_metadata to record the decision and writes a
    sibling audit row so the audit explorer can surface the decision
    independently of the submission row."""

    meta = dict(row.event_metadata or {})
    if meta.get("status") in ("approved", "rejected"):
        # Idempotent — return current state without re-applying.
        vendor, client, user = _load_correction_context(db, row)
        return _correction_row_to_item(row, vendor=vendor, client=client, user=user)

    from app.models.entities import utc_now

    resolved_at = utc_now()
    note_clean = (note or "").strip() or None

    vendor, client, user = _load_correction_context(db, row)
    before_field = (row.before or {}).get("field", "")
    proposed_value = (row.after or {}).get("value", "")

    applied_change: dict | None = None
    if decision == "approved":
        column = _CORRECTION_FIELD_TO_VENDOR_COLUMN.get(before_field)
        if column is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Este campo no se aplica automáticamente. Resuelve la "
                    "solicitud manualmente o márcala como rechazada."
                ),
            )
        if vendor is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    "El workspace de esta solicitud ya no apunta a un "
                    "proveedor válido; no podemos aplicar la corrección."
                ),
            )
        previous_value = getattr(vendor, column)
        new_value = proposed_value.strip() or None
        setattr(vendor, column, new_value)
        applied_change = {
            "vendor_id": vendor.id,
            "column": column,
            "previous_value": previous_value,
            "new_value": new_value,
        }

    meta.update(
        {
            "status": decision,
            "resolved_at": resolved_at.isoformat(),
            "resolved_by_user_id": current.user.id,
            "resolution_note": note_clean,
        }
    )
    if applied_change is not None:
        meta["applied_change"] = applied_change
    row.event_metadata = meta

    _audit_admin(
        db,
        actor=current,
        action=(
            "correction_request.approved"
            if decision == "approved"
            else "correction_request.rejected"
        ),
        entity_type="provider_workspace",
        entity_id=row.entity_id,
        before={"field": before_field, "status": "pending"},
        after={
            "field": before_field,
            "status": decision,
            "applied_change": applied_change,
            "note": note_clean,
        },
        extra_metadata={"correction_request_id": row.id},
    )

    db.flush()
    db.commit()
    db.refresh(row)
    if vendor is not None:
        db.refresh(vendor)
    vendor, client, user = _load_correction_context(db, row)
    return _correction_row_to_item(row, vendor=vendor, client=client, user=user)


@router.post(
    "/correction-requests/{request_id}/approve",
    response_model=CorrectionRequestAdminItem,
)
def approve_correction_request(
    request_id: str,
    payload: CorrectionRequestResolution,
    db: DbSession,
    current: AdminUser,
) -> CorrectionRequestAdminItem:
    """Approve a pending correction request and auto-apply the change.

    Writes the proposed value to the vendor's matching contact column
    (``contact_email`` / ``contact_phone`` / ``contact_name``), marks
    the submission row as approved, and records the resolution as a
    sibling audit row. Idempotent on already-resolved rows.
    """
    row = _get_correction_row_or_404(db, request_id)
    return _resolve_correction(
        db,
        current=current,
        row=row,
        decision="approved",
        note=payload.note,
    )


@router.post(
    "/correction-requests/{request_id}/reject",
    response_model=CorrectionRequestAdminItem,
)
def reject_correction_request(
    request_id: str,
    payload: CorrectionRequestResolution,
    db: DbSession,
    current: AdminUser,
) -> CorrectionRequestAdminItem:
    """Reject a pending correction request without applying any change.

    Records the rejection note (when provided) on the submission row's
    ``event_metadata`` and writes a sibling audit_log row capturing
    the decision. Idempotent on already-resolved rows.
    """
    row = _get_correction_row_or_404(db, request_id)
    return _resolve_correction(
        db,
        current=current,
        row=row,
        decision="rejected",
        note=payload.note,
    )


# ---------------------------------------------------------------------------
# Feedback reports (bug + improvement reports from the Reportar launcher)
#
# Two source modes share the same table — ``source='authenticated'`` for
# JWT-backed staff submissions and ``source='public'`` for anonymous
# landing-page reports. Status lifecycle:
#     new → triaged → in_progress → resolved (or wont_fix)
# Same shape as contact-requests triage; admin can correct mis-sets so
# we don't enforce a strict transition graph.
# ---------------------------------------------------------------------------


class FeedbackReportAdminItem(BaseModel):
    id: str
    kind: str
    description: str
    source: str
    is_public: bool
    status: str
    url: str | None
    path: str | None
    viewport: str | None
    user_agent: str | None
    console_logs: str | None
    user_id: str | None
    user_email: str | None
    user_full_name: str | None
    user_roles: str | None
    contact_email: str | None
    ip_hash: str | None
    screenshot_storage_key: str | None
    screenshot_size_bytes: int | None
    screenshot_url: str | None
    """Time-limited download URL when the storage backend supports
    pre-signing (S3/R2). NULL on the local backend — the frontend
    will hit a separate streaming endpoint instead."""
    slack_message_ts: str | None
    slack_delivery_status: str
    slack_delivery_error: str | None
    resolution_note: str | None
    triaged_by_user_id: str | None
    triaged_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FeedbackReportList(BaseModel):
    items: list[FeedbackReportAdminItem]
    total: int
    limit: int
    offset: int


class FeedbackReportStatusUpdate(BaseModel):
    status: Literal["new", "triaged", "in_progress", "resolved", "wont_fix"]
    resolution_note: str | None = Field(default=None, max_length=4000)


def _feedback_to_dict(
    row: FeedbackReport, *, include_screenshot_url: bool = False
) -> FeedbackReportAdminItem:
    """Serialize a FeedbackReport for the admin queue.

    When ``include_screenshot_url`` is True we ask the storage backend
    for a presigned URL; the list endpoint skips this (one-pre-sign
    per row × 50 rows is a needless cost) and only the detail endpoint
    sets it.
    """
    screenshot_url: str | None = None
    if include_screenshot_url and row.screenshot_storage_key:
        try:
            from app.services.storage import get_storage_service

            screenshot_url = get_storage_service().presigned_download_url(
                row.screenshot_storage_key
            )
        except Exception:  # noqa: BLE001 — list rendering must not fail
            screenshot_url = None
    return FeedbackReportAdminItem(
        id=row.id,
        kind=row.kind,
        description=row.description,
        source=row.source,
        is_public=row.is_public,
        status=row.status,
        url=row.url,
        path=row.path,
        viewport=row.viewport,
        user_agent=row.user_agent,
        console_logs=row.console_logs,
        user_id=row.user_id,
        user_email=row.user_email,
        user_full_name=row.user_full_name,
        user_roles=row.user_roles,
        contact_email=row.contact_email,
        ip_hash=row.ip_hash,
        screenshot_storage_key=row.screenshot_storage_key,
        screenshot_size_bytes=row.screenshot_size_bytes,
        screenshot_url=screenshot_url,
        slack_message_ts=row.slack_message_ts,
        slack_delivery_status=row.slack_delivery_status,
        slack_delivery_error=row.slack_delivery_error,
        resolution_note=row.resolution_note,
        triaged_by_user_id=row.triaged_by_user_id,
        triaged_at=row.triaged_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/feedback-reports", response_model=FeedbackReportList)
def list_feedback_reports(
    db: DbSession,
    current: AdminUser,
    status_filter: Annotated[
        Literal["new", "triaged", "in_progress", "resolved", "wont_fix"] | None,
        Query(alias="status"),
    ] = None,
    kind: Annotated[Literal["bug", "improvement"] | None, Query()] = None,
    source: Annotated[Literal["authenticated", "public"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FeedbackReportList:
    """List feedback reports newest first.

    Internal-admin only. Filters compose as AND on
    ``status`` / ``kind`` / ``source``. Pagination via ``limit``
    (hard-capped at 200) + ``offset``.
    """
    _ = current
    stmt = select(FeedbackReport)
    total_stmt = select(func.count()).select_from(FeedbackReport)
    conditions = []
    if status_filter:
        conditions.append(FeedbackReport.status == status_filter)
    if kind:
        conditions.append(FeedbackReport.kind == kind)
    if source:
        conditions.append(FeedbackReport.source == source)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        total_stmt = total_stmt.where(and_(*conditions))
    total = int(db.scalar(total_stmt) or 0)
    stmt = stmt.order_by(FeedbackReport.created_at.desc()).limit(limit).offset(offset)
    rows = list(db.scalars(stmt))
    return FeedbackReportList(
        items=[_feedback_to_dict(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/feedback-reports/{report_id}", response_model=FeedbackReportAdminItem
)
def get_feedback_report(
    report_id: str, db: DbSession, current: AdminUser
) -> FeedbackReportAdminItem:
    """Detail view, including a presigned screenshot URL when available."""
    _ = current
    row = db.get(FeedbackReport, report_id)
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado."
        )
    return _feedback_to_dict(row, include_screenshot_url=True)


@router.patch(
    "/feedback-reports/{report_id}", response_model=FeedbackReportAdminItem
)
def update_feedback_report_status(
    report_id: str,
    payload: FeedbackReportStatusUpdate,
    db: DbSession,
    current: AdminUser,
) -> FeedbackReportAdminItem:
    """Move a feedback report through the triage lifecycle.

    Setting ``status`` to anything other than ``new`` stamps
    ``triaged_by_user_id`` + ``triaged_at`` with the admin's identity
    and the current time on the first such transition. Subsequent
    status changes leave those columns alone so the audit trail
    records who first triaged the report (rerun the audit-log
    explorer for the full history).
    """
    row = db.get(FeedbackReport, report_id)
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado."
        )
    before = _feedback_to_dict(row).model_dump(mode="json")
    row.status = payload.status
    if payload.resolution_note is not None:
        row.resolution_note = payload.resolution_note
    if row.triaged_by_user_id is None and payload.status != "new":
        row.triaged_by_user_id = current.user.id
        from app.models.entities import utc_now

        row.triaged_at = utc_now()
    db.flush()
    after = _feedback_to_dict(row).model_dump(mode="json")
    _audit_admin(
        db,
        actor=current,
        action="admin.feedback_report.status_changed",
        entity_type="feedback_report",
        entity_id=row.id,
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(row)
    return _feedback_to_dict(row, include_screenshot_url=True)


# ---------------------------------------------------------------------------
# Metadata workbook exports
# ---------------------------------------------------------------------------


class MetadataExportListItem(BaseModel):
    id: str
    submission_id: str
    document_id: str | None
    client_id: str | None
    result: str
    severity: str
    document_type_code: str | None
    client_name: str | None
    vendor_name: str | None
    requirement_name: str | None
    period_key: str | None
    original_filename: str | None
    output_path: str | None
    latest_path: str | None
    master_path: str | None
    file_exists: bool
    preview_available: bool
    master_available: bool
    reason: str | None
    created_at: datetime


class MetadataExportListResponse(BaseModel):
    items: list[MetadataExportListItem]
    total: int
    limit: int


class MetadataExportSheetPreview(BaseModel):
    name: str
    rows: list[list[str]]


class MetadataExportPreviewResponse(BaseModel):
    export: MetadataExportListItem
    sheets: list[MetadataExportSheetPreview]


class ClientMasterMetadataPreviewResponse(BaseModel):
    client_id: str
    client_name: str
    master_path: str
    sheets: list[MetadataExportSheetPreview]


class ClientMetadataDocument(BaseModel):
    cliente: str
    proveedor: str
    periodo: str
    nombre_documento: str
    tipo_documento: str
    subtipo: str
    institucion: str
    fecha_principal: str
    participantes: str
    descripcion: str
    anexos: str
    etiquetas: str
    archivo_pdf: str


class ClientMetadataResponse(BaseModel):
    client: dict
    master_available: bool
    master_path: str | None
    documents: list[ClientMetadataDocument]


@router.get("/metadata-exports", response_model=MetadataExportListResponse)
def list_metadata_exports(
    db: DbSession,
    current: AdminUser,
    result: Annotated[
        Literal["completed", "skipped", "failed"] | None,
        Query(description="Filter by metadata export event result."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> MetadataExportListResponse:
    """List XLSX metadata exports generated by provider uploads."""
    _ = current
    stmt = select(ValidationEvent).where(
        ValidationEvent.event_type == "metadata_table_exported"
    )
    if result:
        stmt = stmt.where(ValidationEvent.result == result)
    stmt = stmt.order_by(ValidationEvent.created_at.desc()).limit(limit)
    rows = list(db.scalars(stmt))
    items = [_metadata_export_item(db, row) for row in rows]
    return MetadataExportListResponse(items=items, total=len(items), limit=limit)


@router.get(
    "/metadata-exports/{export_event_id}",
    response_model=MetadataExportPreviewResponse,
)
def preview_metadata_export(
    export_event_id: str, db: DbSession, current: AdminUser
) -> MetadataExportPreviewResponse:
    """Return a compact workbook preview for the admin UI."""
    _ = current
    event = _get_metadata_export_event(db, export_event_id)
    item = _metadata_export_item(db, event)
    path = _metadata_export_file_path(event)
    if path is None or not path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Archivo de metadata no encontrado en el servidor.",
        )
    return MetadataExportPreviewResponse(
        export=item,
        sheets=_read_xlsx_preview(path),
    )


@router.get("/metadata-exports/{export_event_id}/download")
def download_metadata_export(
    export_event_id: str, db: DbSession, current: AdminUser
) -> FileResponse:
    """Download the generated XLSX workbook."""
    _ = current
    event = _get_metadata_export_event(db, export_event_id)
    path = _metadata_export_file_path(event)
    if path is None or not path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Archivo de metadata no encontrado en el servidor.",
        )
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


@router.get(
    "/metadata-exports/clients/{client_id}/master",
    response_model=ClientMasterMetadataPreviewResponse,
)
def preview_client_master_metadata_export(
    client_id: str, db: DbSession, current: AdminUser
) -> ClientMasterMetadataPreviewResponse:
    """Preview the shareable client-level metadata workbook."""
    _ = current
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")
    path = _client_master_file_path(client)
    if not path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Master de metadata no encontrado para este cliente.",
        )
    return ClientMasterMetadataPreviewResponse(
        client_id=client.id,
        client_name=client.name,
        master_path=_display_export_path(str(path)) or path.name,
        sheets=_read_xlsx_preview(path, max_rows_per_sheet=80, max_columns=12),
    )


@router.get("/clients/{client_id}/metadata", response_model=ClientMetadataResponse)
def get_client_metadata(
    client_id: str, db: DbSession, current: AdminUser
) -> ClientMetadataResponse:
    """Client-facing metadata summary for the admin client page."""
    _ = current
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")
    path = _client_master_file_path(client)
    documents: list[ClientMetadataDocument] = []
    if path.exists():
        sheets = _read_xlsx_preview(path, max_rows_per_sheet=500, max_columns=20)
        metadata_sheet = next((sheet for sheet in sheets if sheet.name == "01 Metadata"), None)
        if metadata_sheet and metadata_sheet.rows:
            documents = _client_metadata_documents_from_sheet(metadata_sheet.rows)
    return ClientMetadataResponse(
        client=_client_to_dict(client),
        master_available=path.exists(),
        master_path=_display_export_path(str(path)) if path.exists() else None,
        documents=documents,
    )


@router.get("/metadata-exports/clients/{client_id}/master/download")
def download_client_master_metadata_export(
    client_id: str, db: DbSession, current: AdminUser
) -> FileResponse:
    """Download the shareable client-level metadata workbook."""
    _ = current
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")
    path = _client_master_file_path(client)
    if not path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Master de metadata no encontrado para este cliente.",
        )
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{client.name}_metadata_master.xlsx",
    )


def _get_metadata_export_event(db: Session, export_event_id: str) -> ValidationEvent:
    event = db.get(ValidationEvent, export_event_id)
    if event is None or event.event_type != "metadata_table_exported":
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Export de metadata no encontrado."
        )
    return event


def _metadata_export_item(
    db: Session, event: ValidationEvent
) -> MetadataExportListItem:
    payload = event.payload or {}
    submission = db.get(Submission, event.submission_id)
    document = db.get(Document, event.document_id) if event.document_id else None
    client = db.get(Client, submission.client_id) if submission else None
    vendor = db.get(Vendor, submission.vendor_id) if submission else None
    requirement = db.get(Requirement, submission.requirement_id) if submission else None
    path = _metadata_export_file_path(event)
    file_exists = bool(path and path.exists())
    return MetadataExportListItem(
        id=event.id,
        submission_id=event.submission_id,
        document_id=event.document_id,
        client_id=client.id if client else None,
        result=event.result,
        severity=event.severity,
        document_type_code=payload.get("document_type_code"),
        client_name=client.name if client else None,
        vendor_name=vendor.name if vendor else None,
        requirement_name=requirement.name if requirement else None,
        period_key=submission.period_key if submission else None,
        original_filename=document.original_filename if document else None,
        output_path=_display_export_path(payload.get("output_path")),
        latest_path=_display_export_path(payload.get("latest_path")),
        master_path=_display_export_path(payload.get("master_path"))
        or (_display_export_path(str(_client_master_file_path(client))) if client else None),
        file_exists=file_exists,
        preview_available=event.result == "completed" and file_exists,
        master_available=bool(client and _client_master_file_path(client).exists()),
        reason=payload.get("reason") or event.message,
        created_at=event.created_at,
    )


def _metadata_export_file_path(event: ValidationEvent) -> Path | None:
    payload = event.payload or {}
    raw_path = payload.get("latest_path") or payload.get("output_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    candidate = Path(raw_path).expanduser().resolve()
    export_root = Path(settings.METADATA_EXPORT_PATH).expanduser().resolve()
    try:
        candidate.relative_to(export_root)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Ruta de export fuera del directorio permitido.",
        ) from exc
    return candidate


def _client_master_file_path(client: Client) -> Path:
    return (
        Path(settings.METADATA_EXPORT_PATH).expanduser().resolve()
        / _export_slug(client.name)
        / "client_master_metadata.xlsx"
    )


def _display_export_path(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value).expanduser().resolve()
    export_root = Path(settings.METADATA_EXPORT_PATH).expanduser().resolve()
    try:
        return str(path.relative_to(export_root))
    except ValueError:
        return path.name


def _export_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    clean = re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9]+", " ", ascii_text).lower()).strip()
    return re.sub(r"[^a-z0-9-]+", "-", clean.replace(" ", "-")).strip("-") or "unknown"


def _read_xlsx_preview(
    path: Path, *, max_rows_per_sheet: int = 40, max_columns: int = 12
) -> list[MetadataExportSheetPreview]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            workbook_xml = archive.read("xl/workbook.xml")
            sheet_names = _xlsx_sheet_names(workbook_xml)
            previews = []
            for index, name in enumerate(sheet_names, start=1):
                worksheet_path = f"xl/worksheets/sheet{index}.xml"
                if worksheet_path not in archive.namelist():
                    continue
                previews.append(
                    MetadataExportSheetPreview(
                        name=name,
                        rows=_xlsx_sheet_rows(
                            archive.read(worksheet_path),
                            max_rows=max_rows_per_sheet,
                            max_columns=max_columns,
                        ),
                    )
                )
            return previews
    except (KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No se pudo leer el XLSX de metadata: {exc}",
        ) from exc


def _xlsx_sheet_names(workbook_xml: bytes) -> list[str]:
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(workbook_xml)
    return [
        sheet.attrib.get("name", f"Sheet {index}")
        for index, sheet in enumerate(root.findall(".//x:sheet", namespace), start=1)
    ]


def _xlsx_sheet_rows(
    worksheet_xml: bytes, *, max_rows: int, max_columns: int
) -> list[list[str]]:
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(worksheet_xml)
    parsed_rows: list[list[str]] = []
    for row in root.findall(".//x:sheetData/x:row", namespace)[:max_rows]:
        values = [""] * max_columns
        for cell in row.findall("x:c", namespace):
            column_index = _xlsx_column_index(cell.attrib.get("r", "A1")) - 1
            if not 0 <= column_index < max_columns:
                continue
            values[column_index] = _xlsx_cell_text(cell, namespace)
        while values and values[-1] == "":
            values.pop()
        parsed_rows.append(values)
    return parsed_rows


def _xlsx_column_index(cell_ref: str) -> int:
    index = 0
    for char in cell_ref:
        if not char.isalpha():
            break
        index = index * 26 + (ord(char.upper()) - 64)
    return max(index, 1)


def _xlsx_cell_text(cell: ET.Element, namespace: dict[str, str]) -> str:
    inline = cell.find("x:is", namespace)
    if inline is not None:
        return "".join(node.text or "" for node in inline.findall(".//x:t", namespace))
    value = cell.find("x:v", namespace)
    return value.text if value is not None and value.text is not None else ""


def _client_metadata_documents_from_sheet(
    rows: list[list[str]],
) -> list[ClientMetadataDocument]:
    headers = rows[0]
    items: list[ClientMetadataDocument] = []
    for values in rows[1:]:
        item = {
            header: values[index] if index < len(values) else ""
            for index, header in enumerate(headers)
        }
        items.append(
            ClientMetadataDocument(
                cliente=item.get("Cliente", ""),
                proveedor=item.get("Proveedor", ""),
                periodo=item.get("Periodo", ""),
                nombre_documento=item.get("Nombre del documento", ""),
                tipo_documento=item.get("Tipo de documento", ""),
                subtipo=item.get("Subtipo", ""),
                institucion=item.get("Institucion", ""),
                fecha_principal=item.get("Fecha principal", ""),
                participantes=item.get("Participantes", ""),
                descripcion=item.get("Descripcion", ""),
                anexos=item.get("Anexos", ""),
                etiquetas=item.get("Etiquetas", ""),
                archivo_pdf=item.get("Archivo PDF", ""),
            )
        )
    return items


# ---------------------------------------------------------------------------
# Audit log explorer
# ---------------------------------------------------------------------------


class AuditLogItem(BaseModel):
    id: str
    actor_id: str | None
    actor_type: str
    action: str
    entity_type: str
    entity_id: str
    before: dict | None
    after: dict | None
    metadata: dict | None = Field(default=None, alias="event_metadata")
    created_at: datetime

    model_config = {"populate_by_name": True}


class AuditLogResponse(BaseModel):
    items: list[AuditLogItem]
    total: int
    limit: int


@router.get("/audit-log", response_model=AuditLogResponse)
def list_audit_log(
    db: DbSession,
    current: AdminUser,
    actor_id: str | None = None,
    actor_type: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditLogResponse:
    """Filtered audit-log explorer.

    Newest first. Filters compose as AND. Default limit 50, hard cap
    200. Returns at most ``limit`` rows; the total count is the
    matching row count (or capped at ``limit`` if the DB doesn't make
    the full count cheap — Phase 7 returns the rendered length to keep
    the surface simple).
    """
    _ = current
    filters = []
    if actor_id:
        filters.append(AuditLog.actor_id == actor_id)
    if actor_type:
        filters.append(AuditLog.actor_type == actor_type)
    if action:
        filters.append(AuditLog.action == action)
    if entity_type:
        filters.append(AuditLog.entity_type == entity_type)
    if entity_id:
        filters.append(AuditLog.entity_id == entity_id)
    if date_from:
        filters.append(AuditLog.created_at >= date_from)
    if date_to:
        filters.append(AuditLog.created_at <= date_to)
    stmt = select(AuditLog)
    if filters:
        stmt = stmt.where(and_(*filters))
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    rows = list(db.scalars(stmt))
    items = [
        AuditLogItem(
            id=row.id,
            actor_id=row.actor_id,
            actor_type=row.actor_type,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            before=row.before,
            after=row.after,
            event_metadata=row.event_metadata,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return AuditLogResponse(items=items, total=len(items), limit=limit)


# ---------------------------------------------------------------------------
# Junta 2026-05-23 — bulk ZIP per vendor desde el control plane admin
# ---------------------------------------------------------------------------


@router.get(
    "/vendors/{vendor_id}/expediente.zip",
    summary="Stream a ZIP of a vendor's expediente (internal_admin)",
)
def admin_vendor_expediente_zip(
    vendor_id: str,
    db: DbSession,
    current: AdminUser,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    period_key: str | None = None,
    institution: str | None = None,
) -> Response:
    """Stream a vendor's expediente as a ZIP from the admin surface.

    Mirrors :func:`app.api.v1.client.client_vendor_expediente_zip` but
    with the ``internal_admin`` gate and no per-client scoping —
    LegalShelf staff need cross-client visibility for audits and
    incident response. Composition, caps and filter shape come from
    the shared :mod:`app.services.expediente_zip` service so the three
    surfaces (provider, client_admin, internal_admin) stay in
    lockstep.

    Audit: ``admin.vendor_expediente_downloaded`` with metadata
    ``{scope, vendor_id, client_id, workspace_id, file_count,
    total_bytes, filters}``. Distinguishable from the
    provider/client actions so the forensic reader can answer
    "was this an internal-staff pull?".
    """
    from datetime import datetime

    from fastapi.responses import StreamingResponse

    from app.services.expediente_zip import (
        MAX_FILES,
        MAX_TOTAL_BYTES,
        ExpedienteFilters,
        stream_expediente_zip,
        summarize_expediente,
    )

    vendor = db.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Proveedor no encontrado.",
        )

    workspace = db.scalar(
        select(ProviderWorkspace).where(
            ProviderWorkspace.vendor_id == vendor_id,
        )
    )
    if workspace is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=(
                "Este proveedor no tiene un workspace activo; "
                "no hay documentos para descargar."
            ),
        )

    filters = ExpedienteFilters(
        status=status_filter,
        period_key=period_key,
        institution=institution,
    )

    summary = summarize_expediente(db, workspace, filters)
    if summary.file_count > MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"El expediente tiene {summary.file_count} documentos; "
                f"el límite por descarga es {MAX_FILES}. Filtra por "
                "periodo o institución para reducir el alcance."
            ),
        )
    if summary.total_bytes > MAX_TOTAL_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"El expediente pesa {summary.total_bytes // (1024 * 1024)} MB; "
                f"el límite por descarga es {MAX_TOTAL_BYTES // (1024 * 1024)} MB. "
                "Filtra por periodo o institución para reducir el alcance."
            ),
        )

    add_audit_event(
        db,
        action="admin.vendor_expediente_downloaded",
        entity_type="provider_workspace",
        entity_id=workspace.id,
        actor_type="internal_admin",
        actor_id=current.user.id,
        metadata={
            "scope": "admin_vendor",
            "vendor_id": vendor_id,
            "client_id": workspace.client_id,
            "workspace_id": workspace.id,
            "file_count": summary.file_count,
            "total_bytes": summary.total_bytes,
            "filters": filters.to_audit_dict(),
        },
    )
    db.commit()

    iterator = stream_expediente_zip(db, workspace, filters)

    safe_rfc = (vendor.rfc or "expediente").lower()
    safe_rfc = "".join(ch for ch in safe_rfc if ch.isalnum() or ch in "-_") or "expediente"
    today = datetime.now(UTC).strftime("%Y%m%d")
    filename = f"expediente-{safe_rfc}-{today}.zip"

    return StreamingResponse(
        iterator,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
