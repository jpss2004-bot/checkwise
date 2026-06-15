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
* ``GET /admin/institutions`` — read-only institution catalog for
  the requirements form dropdowns.
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
import secrets
import unicodedata
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Final, Literal
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.auth import CurrentUser, require_any_role, require_role
from app.api.v1.client import (
    _last_activity_timestamps_bulk,
    _portfolio_slot_inputs,
    _vendor_compliance,
)
from app.api.v1.reviewer import QUEUE_STATUSES
from app.constants.roles import MembershipRole
from app.constants.statuses import DocumentStatus
from app.core.compliance_catalog import (
    catalog_metadata,
    recurring_for_year,
    recurring_for_year_v2,
)
from app.core.config import settings
from app.core.rate_limit import client_ip_from_request
from app.core.period_validation import MAX_YEAR, MIN_YEAR
from app.db.session import get_db
from app.models import (
    AuditLog,
    Client,
    ContactRequest,
    Document,
    FeedbackReport,
    Institution,
    Membership,
    Organization,
    PasswordHistory,
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
from app.services.auth import (
    generate_temp_password,
    hash_password,
)
from app.services.email_delivery import (
    send_owner_reset_temp_password_email,
    send_transactional_email,
    send_welcome_with_temp_password_email,
)
from app.services.metadata_store import ensure_local_export, mirror_enabled
from app.services.search_service import SearchHit, search_submissions

router = APIRouter(prefix="/admin", tags=["admin"])
DbSession = Annotated[Session, Depends(get_db)]
AdminUser = Annotated[
    CurrentUser, Depends(require_role(MembershipRole.INTERNAL_ADMIN))
]

# Platform/IT surfaces (user provisioning, audit log, feedback triage)
# accept either the compliance ``internal_admin`` or the dedicated
# ``platform_admin`` role (platform rework, Phase 1). Migration 0044
# backfilled ``platform_admin`` onto every existing internal_admin, so
# accepting both keeps today's operators working while letting a future
# IT-only account reach just these endpoints — not the compliance ones,
# which stay gated on ``AdminUser``.
PlatformUser = Annotated[
    CurrentUser,
    Depends(
        require_any_role(
            MembershipRole.INTERNAL_ADMIN, MembershipRole.PLATFORM_ADMIN
        )
    ),
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
    request: Request | None = None,
) -> None:
    """Write the standard admin-operations audit row.

    Every admin mutation goes through here so the audit-log explorer
    can filter on ``actor_type='internal_admin'`` or
    ``metadata.source='admin_operations'`` and surface every action a
    LegalShelf operator took. Don't bypass this helper.

    Pass ``request`` to stamp the originating IP + user-agent onto the
    row (migration 0043). It is optional so existing callers keep
    working and simply record NULL provenance until they thread it
    through; new/edited mutations should always pass it.
    """
    metadata = {"source": "admin_operations"}
    if extra_metadata:
        metadata.update(extra_metadata)
    ip_address: str | None = None
    user_agent: str | None = None
    if request is not None:
        ip_address = client_ip_from_request(request)
        # AuditLog.user_agent is VARCHAR(512); truncate defensively so a
        # pathological header never overflows the column on Postgres.
        ua = request.headers.get("user-agent")
        user_agent = ua[:512] if ua else None
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
        ip_address=ip_address,
        user_agent=user_agent,
    )


def _client_to_dict(row: Client) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "rfc": row.rfc,
        "email": row.email,
        "responsible_name": row.responsible_name,
        "industry": row.industry,
        "fiscal_address": row.fiscal_address,
        "phone": row.phone,
        "notes": row.notes,
        "onboarding_completed_at": (
            row.onboarding_completed_at.isoformat()
            if row.onboarding_completed_at
            else None
        ),
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

    ``recent_*`` fields are real 7-day windows: rows whose
    ``created_at`` falls within the last 7 days (UTC) in the
    submissions and audit-log tables respectively.
    """
    _ = current
    recent_cutoff = datetime.now(UTC) - timedelta(days=7)
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
    recent_submissions_total = int(
        db.scalar(
            select(func.count(Submission.id)).where(
                Submission.created_at >= recent_cutoff
            )
        )
        or 0
    )
    recent_audit_events_total = int(
        db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.created_at >= recent_cutoff
            )
        )
        or 0
    )
    return AdminOverview(
        clients_total=clients_total,
        vendors_total=vendors_total,
        active_workspaces_total=active_workspaces_total,
        pending_reviews_total=pending_reviews_total,
        rejected_or_correction_total=rejected_or_correction_total,
        recent_submissions_total=recent_submissions_total,
        recent_audit_events_total=recent_audit_events_total,
    )


# ---------------------------------------------------------------------------
# Ops-console rollup (P2 of the 2026-06-10 audit)
#
# Reuses the per-vendor compliance machinery from ``client.py``
# (``_portfolio_slot_inputs`` + ``_vendor_compliance`` +
# ``_last_activity_timestamps_bulk``) so the admin dashboard's
# red/yellow/green semantics match the client portal exactly.
# Cross-router imports are the established pattern here (client.py
# imports from portal.py; client_users.py imports from client.py).
# ---------------------------------------------------------------------------


_SEMAPHORE_LEVEL_ORDER: Final[dict[str, int]] = {"red": 0, "yellow": 1, "green": 2}


class RollupClientRow(BaseModel):
    client_id: str
    client_name: str
    vendors_total: int
    green_count: int
    yellow_count: int
    red_count: int
    compliance_pct: int
    missing_required_total: int
    pending_reviews_total: int
    due_soon_total: int


class RollupQueueAgeBuckets(BaseModel):
    """Exclusive buckets: ``over_72h`` is 72h < age <= 7d; older
    submissions fall only into ``over_7d``."""

    under_24h: int
    h24_to_72h: int
    over_72h: int
    over_7d: int


class RollupQueue(BaseModel):
    pending_total: int
    oldest_age_hours: int | None
    age_buckets: RollupQueueAgeBuckets


class RollupThroughput(BaseModel):
    approved_last_7d: int
    rejected_last_7d: int


class RollupVendorAtRisk(BaseModel):
    vendor_id: str
    vendor_name: str
    client_id: str
    client_name: str
    semaphore_level: Literal["green", "yellow", "red"]
    compliance_pct: int
    missing_required_count: int
    rejected_or_correction_count: int
    last_activity_at: str | None


class RollupInbox(BaseModel):
    contact_requests_pending: int
    correction_requests_pending: int
    feedback_reports_new: int


class AdminRollup(BaseModel):
    clients: list[RollupClientRow]
    queue: RollupQueue
    throughput: RollupThroughput
    vendors_at_risk: list[RollupVendorAtRisk]
    inbox: RollupInbox


class AdminClientComplianceVendorRow(BaseModel):
    vendor_id: str
    vendor_name: str
    vendor_rfc: str | None
    workspace_id: str
    workspace_status: str
    semaphore_level: Literal["green", "yellow", "red"]
    compliance_pct: int
    missing_required_count: int
    rejected_or_correction_count: int
    pending_reviews_count: int
    due_soon_count: int
    last_activity_at: str | None


class AdminClientComplianceResponse(BaseModel):
    client_id: str
    client_name: str
    vendors: list[AdminClientComplianceVendorRow]


def _as_utc(ts: datetime) -> datetime:
    """Normalize a DB timestamp (naive on SQLite) to aware UTC."""
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts


def _client_vendor_compliance_rows(
    db: Session, client: Client, *, today: date, year: int
) -> list[dict]:
    """Per-workspace compliance summaries for one client.

    Mirrors ``client.client_overview`` / ``client.client_vendors``:
    one ``_portfolio_slot_inputs`` prefetch (a single submissions
    query for the whole client) feeds ``_vendor_compliance`` per
    workspace, so query count stays constant in the vendor count.
    Each row is ``{vendor, workspace, summary, last_activity_at}``
    where ``last_activity_at`` is the most recent of the vendor's
    last submission / last reviewer decision (ISO string or None).
    """
    workspaces = list(
        db.scalars(
            select(ProviderWorkspace)
            .where(ProviderWorkspace.client_id == client.id)
            .order_by(ProviderWorkspace.created_at.desc())
        )
    )
    if not workspaces:
        return []
    vendor_ids = [w.vendor_id for w in workspaces]
    vendors = {
        v.id: v for v in db.scalars(select(Vendor).where(Vendor.id.in_(vendor_ids)))
    }
    subs_by_vendor, institutions_by_id = _portfolio_slot_inputs(db, client.id)
    last_sub_map, last_review_map = _last_activity_timestamps_bulk(db, vendor_ids)

    rows: list[dict] = []
    for ws in workspaces:
        vendor = vendors.get(ws.vendor_id)
        if vendor is None:
            continue
        summary = _vendor_compliance(
            db,
            ws,
            today=today,
            year=year,
            prefetched_submissions=subs_by_vendor.get(ws.vendor_id, []),
            institutions_by_id=institutions_by_id,
        )
        activity_candidates = [
            _as_utc(ts)
            for ts in (last_sub_map.get(vendor.id), last_review_map.get(vendor.id))
            if ts is not None
        ]
        last_activity = max(activity_candidates) if activity_candidates else None
        rows.append(
            {
                "vendor": vendor,
                "workspace": ws,
                "summary": summary,
                "last_activity_at": (
                    last_activity.isoformat() if last_activity else None
                ),
            }
        )
    return rows


@router.get("/rollup", response_model=AdminRollup)
def get_rollup(db: DbSession, current: AdminUser) -> AdminRollup:
    """Everything the ops-console dashboard renders, in one call.

    Per-client semáforo rollup (worst first), reviewer-queue ageing,
    7-day throughput (mirrors the reviewer queue's stat-strip
    counters), the 8 worst at-risk vendors (red, then yellow —
    green vendors are not "at risk" and are excluded), and the
    triage inbox counters.
    """
    _ = current
    today = date.today()
    year = today.year
    now = datetime.now(UTC)

    # --- Per-client compliance rollup + at-risk vendor collection ----
    clients = list(db.scalars(select(Client).order_by(Client.created_at.desc())))
    client_rows: list[RollupClientRow] = []
    risk_rows: list[RollupVendorAtRisk] = []
    for cl in clients:
        vendor_rows = _client_vendor_compliance_rows(db, cl, today=today, year=year)
        vendors_total = int(
            db.scalar(select(func.count(Vendor.id)).where(Vendor.client_id == cl.id))
            or 0
        )
        green = yellow = red = 0
        missing_required_total = 0
        pending_reviews_total = 0
        due_soon_total = 0
        pct_sum = 0
        for row in vendor_rows:
            summary = row["summary"]
            level = summary["semaphore_level"]
            if level == "green":
                green += 1
            elif level == "yellow":
                yellow += 1
            else:
                red += 1
            missing_required_total += summary["missing_required_count"]
            pending_reviews_total += summary["pending_reviews_count"]
            due_soon_total += summary["due_soon_count"]
            pct_sum += summary["compliance_pct"]
            if level in ("red", "yellow"):
                vendor = row["vendor"]
                risk_rows.append(
                    RollupVendorAtRisk(
                        vendor_id=vendor.id,
                        vendor_name=vendor.name,
                        client_id=cl.id,
                        client_name=cl.name,
                        semaphore_level=level,
                        compliance_pct=summary["compliance_pct"],
                        missing_required_count=summary["missing_required_count"],
                        rejected_or_correction_count=summary[
                            "rejected_or_correction_count"
                        ],
                        last_activity_at=row["last_activity_at"],
                    )
                )
        # Same average ``client_overview`` uses: mean of per-vendor pct,
        # 100 when the client has no workspaces yet.
        compliance_pct = round(pct_sum / len(vendor_rows)) if vendor_rows else 100
        client_rows.append(
            RollupClientRow(
                client_id=cl.id,
                client_name=cl.name,
                vendors_total=vendors_total,
                green_count=green,
                yellow_count=yellow,
                red_count=red,
                compliance_pct=compliance_pct,
                missing_required_total=missing_required_total,
                pending_reviews_total=pending_reviews_total,
                due_soon_total=due_soon_total,
            )
        )

    client_rows.sort(key=lambda r: (-r.red_count, r.compliance_pct))
    risk_rows.sort(
        key=lambda r: (_SEMAPHORE_LEVEL_ORDER[r.semaphore_level], r.compliance_pct)
    )
    vendors_at_risk = risk_rows[:8]

    # --- Reviewer queue ageing ----------------------------------------
    pending_created = list(
        db.scalars(
            select(Submission.created_at).where(Submission.status.in_(QUEUE_STATUSES))
        )
    )
    under_24h = h24_to_72h = over_72h = over_7d = 0
    oldest_age_hours: int | None = None
    for ts in pending_created:
        age_hours = max(0.0, (now - _as_utc(ts)).total_seconds() / 3600)
        if age_hours < 24:
            under_24h += 1
        elif age_hours <= 72:
            h24_to_72h += 1
        elif age_hours <= 24 * 7:
            over_72h += 1
        else:
            over_7d += 1
        whole_hours = int(age_hours)  # same floor as reviewer.py age_hours
        if oldest_age_hours is None or whole_hours > oldest_age_hours:
            oldest_age_hours = whole_hours

    # --- 7-day throughput (mirrors reviewer.list_queue's counters) ----
    cutoff = now - timedelta(days=7)
    approved_last_7d = int(
        db.scalar(
            select(func.count(Submission.id)).where(
                Submission.status.in_(
                    (
                        DocumentStatus.APROBADO.value,
                        DocumentStatus.EXCEPCION_LEGAL.value,
                    )
                ),
                Submission.updated_at >= cutoff,
            )
        )
        or 0
    )
    rejected_last_7d = int(
        db.scalar(
            select(func.count(Submission.id)).where(
                Submission.status == DocumentStatus.RECHAZADO.value,
                Submission.updated_at >= cutoff,
            )
        )
        or 0
    )

    # --- Triage inbox --------------------------------------------------
    contact_requests_pending = int(
        db.scalar(
            select(func.count())
            .select_from(ContactRequest)
            .where(ContactRequest.status == "new")
        )
        or 0
    )
    # Correction requests live as audit rows; ``pending`` is in
    # ``event_metadata.status`` and JSON-column WHEREs are not portable
    # across SQLite (tests) / Postgres (prod) — same constraint as
    # ``list_correction_requests``. Fetch only the metadata column and
    # count in Python (cheaper than the list endpoint's full ORM scan,
    # but still O(rows); fine at current volume).
    correction_requests_pending = 0
    for (meta,) in db.execute(
        select(AuditLog.event_metadata).where(
            AuditLog.action == "correction_request.submitted"
        )
    ):
        meta_status = (
            meta.get("status", "pending") if isinstance(meta, dict) else "pending"
        )
        if meta_status == "pending":
            correction_requests_pending += 1
    feedback_reports_new = int(
        db.scalar(
            select(func.count())
            .select_from(FeedbackReport)
            .where(FeedbackReport.status == "new")
        )
        or 0
    )

    return AdminRollup(
        clients=client_rows,
        queue=RollupQueue(
            pending_total=len(pending_created),
            oldest_age_hours=oldest_age_hours,
            age_buckets=RollupQueueAgeBuckets(
                under_24h=under_24h,
                h24_to_72h=h24_to_72h,
                over_72h=over_72h,
                over_7d=over_7d,
            ),
        ),
        throughput=RollupThroughput(
            approved_last_7d=approved_last_7d,
            rejected_last_7d=rejected_last_7d,
        ),
        vendors_at_risk=vendors_at_risk,
        inbox=RollupInbox(
            contact_requests_pending=contact_requests_pending,
            correction_requests_pending=correction_requests_pending,
            feedback_reports_new=feedback_reports_new,
        ),
    )


@router.get(
    "/clients/{client_id}/compliance",
    response_model=AdminClientComplianceResponse,
)
def get_client_compliance(
    client_id: str, db: DbSession, current: AdminUser
) -> AdminClientComplianceResponse:
    """Per-vendor compliance rows for the admin client-detail page.

    Same machinery as ``/admin/rollup`` scoped to one client. Rows are
    ordered worst-first: red, then yellow, then green, with
    ``compliance_pct`` ascending within each level.
    """
    _ = current
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")
    today = date.today()
    rows = _client_vendor_compliance_rows(db, client, today=today, year=today.year)
    vendor_rows = [
        AdminClientComplianceVendorRow(
            vendor_id=row["vendor"].id,
            vendor_name=row["vendor"].name,
            vendor_rfc=row["vendor"].rfc,
            workspace_id=row["workspace"].id,
            workspace_status=row["workspace"].status,
            semaphore_level=row["summary"]["semaphore_level"],
            compliance_pct=row["summary"]["compliance_pct"],
            missing_required_count=row["summary"]["missing_required_count"],
            rejected_or_correction_count=row["summary"][
                "rejected_or_correction_count"
            ],
            pending_reviews_count=row["summary"]["pending_reviews_count"],
            due_soon_count=row["summary"]["due_soon_count"],
            last_activity_at=row["last_activity_at"],
        )
        for row in rows
    ]
    vendor_rows.sort(
        key=lambda r: (_SEMAPHORE_LEVEL_ORDER[r.semaphore_level], r.compliance_pct)
    )
    return AdminClientComplianceResponse(
        client_id=client.id, client_name=client.name, vendors=vendor_rows
    )


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Item 8 v2 — unified add-user flow
# ---------------------------------------------------------------------------
#
# Single endpoint that handles both clients and providers. Replaces:
#   * POST /admin/clients          (silent client create, no email)
#   * POST /admin/clients/provision (client provision with reset link)
# Per Junta 2026-05-26 lock — see project-sprint-2026-05-26 memory.
#
# Generates a real plaintext temp password, bcrypts it onto the User
# row, returns the plaintext in the response (one-time view, shown to
# the admin so they can hand it to the recipient over WhatsApp if SMTP
# skipped) AND emails it. The recipient logs in with the temp password
# once and is forced through ``/activate`` by ``must_change_password``.


# Shared internal organisation for portal-provisioned admins. Mirrors
# ``DEFAULT_ORG_NAME`` in scripts/add_internal_admin.py so a web-created
# admin lands in the same org as a CLI-bootstrapped one.
INTERNAL_ORG_NAME: Final = "LegalShelf — Internal"


class ProvisionUserPayload(BaseModel):
    """Body for ``POST /admin/users``.

    ``role`` switches the downstream stack:
      * ``client`` → Client + Organization(kind=client) + Membership(client_admin)
      * ``provider`` → Vendor + ProviderWorkspace(owner_user_id=user.id)
        attached to the requested ``client_id``.
      * ``admin`` → Membership(internal_admin) on the internal
        LegalShelf organisation. No client/vendor fields needed.

    Email + name are common to all roles. Role-specific fields are
    optional at the Pydantic layer; the handler validates the right
    subset based on ``role`` and returns a clear 422 otherwise.
    """

    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr = Field(...)
    role: Literal["client", "provider", "admin"] = Field(...)

    # --- client-only fields ---
    client_name: str | None = Field(default=None, max_length=255)
    client_rfc: str | None = Field(default=None, max_length=13)

    # --- provider-only fields ---
    vendor_name: str | None = Field(default=None, max_length=255)
    vendor_rfc: str | None = Field(default=None, max_length=13)
    persona_type: Literal["moral", "fisica"] | None = Field(default=None)
    contact_phone: str | None = Field(default=None, max_length=30)
    parent_client_id: str | None = Field(
        default=None,
        description=(
            "Required when role=='provider'. The Vendor row is anchored "
            "under this client; the provider's portal session will see "
            "the documents belonging to this client's workspace."
        ),
    )


class ProvisionUserResponse(BaseModel):
    """Result of ``POST /admin/users``.

    ``temp_password`` is the freshly-generated plaintext, returned ONCE
    for the admin's confirmation screen. Never persisted in this shape
    — the User row only carries the bcrypt hash.
    """

    user_id: str
    role: Literal["client", "provider", "admin"]
    email: str
    temp_password: str
    login_url: str
    email_status: str
    email_error: str | None = None
    # Role-specific id of the entity the user was attached to.
    client_id: str | None = None
    organization_id: str | None = None
    vendor_id: str | None = None
    workspace_id: str | None = None


@router.post(
    "/users",
    response_model=ProvisionUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Provision a new user (client or provider) with temp credentials",
)
def provision_user(
    payload: ProvisionUserPayload,
    db: DbSession,
    current: PlatformUser,
    request: Request,
) -> ProvisionUserResponse:
    """Create a new User (client_admin or provider) end-to-end.

    Shared steps:
      1. Validate role-specific required fields.
      2. Reject duplicate email (409).
      3. Mint a 14-char plaintext temp password; bcrypt onto the User.
      4. Send the welcome email with the plaintext + login URL.
      5. Audit ``admin.user.provisioned`` with the role + outcome.

    Role=client extra:
      * Insert Client + Organization(kind=client) + Membership(client_admin).

    Role=provider extra:
      * Resolve ``parent_client_id`` against an existing Client row.
      * Insert Vendor under that client + ProviderWorkspace with
        ``owner_user_id=user.id`` so ``/portal/enter`` recognises the
        provider. No Membership/Organization — the existing portal
        cookie path is the auth carrier for /portal endpoints.

    Returns the plaintext temp password ONCE for the admin's
    confirmation surface; the User row stores only the bcrypt hash.
    """
    full_name = payload.full_name.strip()
    email = payload.email.strip().lower()

    # ---- Reject duplicate email before any inserts. ----------------
    # The 409 carries a structured summary of the existing account so the
    # New User form can offer guided actions (open / reactivate / reset)
    # instead of a dead-end error — the safe alternative to the
    # delete-and-recreate reflex (Phase 3 resolver).
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "message": "Ya existe una cuenta con ese correo.",
                "existing_user": {
                    "user_id": existing_user.id,
                    "full_name": existing_user.full_name,
                    "email": existing_user.email,
                    "status": existing_user.status,
                    "roles": _active_roles(db, existing_user.id),
                },
            },
        )

    # ---- Mint the temp password + User row. ------------------------
    temp_password = generate_temp_password()
    user = User(
        email=email,
        password_hash=hash_password(temp_password),
        full_name=full_name,
        status="active",
        must_change_password=True,
    )
    db.add(user)
    db.flush()

    client_id: str | None = None
    organization_id: str | None = None
    vendor_id: str | None = None
    workspace_id: str | None = None
    welcome_org_name: str | None = None

    if payload.role == "client":
        if not payload.client_name or not payload.client_name.strip():
            db.rollback()
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Para un cliente, ``client_name`` es obligatorio.",
            )
        name = payload.client_name.strip()
        rfc_value = (payload.client_rfc or "").strip().upper() or None
        client_row = Client(
            name=name,
            rfc=rfc_value,
            email=email,
            responsible_name=full_name,
            status="active",
        )
        db.add(client_row)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail="RFC ya está en uso."
            ) from exc
        # Multi-user (migration 0037) — new client orgs start with the
        # default 3-seat cap, and the provisioned admin is the Primary
        # Account Owner who manages the other two seats.
        org = Organization(
            name=name,
            kind="client",
            client_id=client_row.id,
            seat_limit=3,
            status="active",
        )
        db.add(org)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org.id,
                role=MembershipRole.CLIENT_ADMIN.value,
                is_primary=True,
                status="active",
            )
        )
        db.flush()
        client_id = client_row.id
        organization_id = org.id
        welcome_org_name = name
    elif payload.role == "admin":
        # Internal LegalShelf admin. Get-or-create the shared internal
        # organisation (mirrors scripts/add_internal_admin.py), then
        # bind an internal_admin membership. No Client/Vendor stack.
        org = db.scalar(
            select(Organization).where(
                Organization.name == INTERNAL_ORG_NAME,
                Organization.kind == "internal",
            )
        )
        if org is None:
            org = Organization(
                name=INTERNAL_ORG_NAME, kind="internal", status="active"
            )
            db.add(org)
            db.flush()
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org.id,
                role=MembershipRole.INTERNAL_ADMIN.value,
                status="active",
            )
        )
        db.flush()
        organization_id = org.id
        welcome_org_name = None
    else:  # role == "provider"
        if not payload.vendor_name or not payload.parent_client_id:
            db.rollback()
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Para un proveedor, ``vendor_name`` y "
                    "``parent_client_id`` son obligatorios."
                ),
            )
        parent_client = db.get(Client, payload.parent_client_id)
        if parent_client is None:
            db.rollback()
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="Cliente padre no encontrado.",
            )
        v_name = payload.vendor_name.strip()
        v_rfc = (payload.vendor_rfc or "").strip().upper() or None
        if not v_rfc:
            db.rollback()
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Para un proveedor, ``vendor_rfc`` es obligatorio.",
            )
        vendor = Vendor(
            client_id=parent_client.id,
            name=v_name,
            rfc=v_rfc,
            contact_name=full_name,
            contact_email=email,
            contact_phone=(payload.contact_phone or "").strip() or None,
            persona_type=payload.persona_type or "moral",
            status="active",
        )
        db.add(vendor)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    "Ya existe un proveedor con ese RFC para el cliente."
                ),
            ) from exc
        workspace = ProviderWorkspace(
            client_id=parent_client.id,
            vendor_id=vendor.id,
            persona_type=payload.persona_type or "moral",
            display_name=v_name,
            access_token=secrets.token_urlsafe(32),
            owner_user_id=user.id,
        )
        db.add(workspace)
        db.flush()
        vendor_id = vendor.id
        workspace_id = workspace.id
        welcome_org_name = v_name

    login_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/login"
    delivery = send_welcome_with_temp_password_email(
        to_email=email,
        full_name=full_name,
        login_url=login_url,
        temp_password=temp_password,
        role=payload.role,
        organization_name=welcome_org_name,
    )

    _audit_admin(
        db,
        actor=current,
        action="admin.user.provisioned",
        entity_type="user",
        entity_id=user.id,
        before=None,
        after={
            "role": payload.role,
            "user_id": user.id,
            "user_email": user.email,
            "client_id": client_id,
            "organization_id": organization_id,
            "vendor_id": vendor_id,
            "workspace_id": workspace_id,
            "email_delivery_status": delivery.status,
        },
        request=request,
    )

    # Phase 7 cutover (Slice C) — emit through the unified fabric so
    # the in-app bell + SMS path light up alongside the legacy
    # welcome email. The legacy email above is the user-visible
    # primary delivery; this emit is the audit + SMS companion.
    # ``user.id`` is the dedupe key suffix so retries / duplicate
    # provisions never double-fire.
    try:
        import logging

        from app.services.notifications import emit_invitation_sent

        emit_invitation_sent(
            db,
            user=user,
            invitation_token_id=user.id,
            invitation_url=login_url,
            mode="active",
        )
        db.flush()
    except Exception:  # pragma: no cover — defensive during cutover
        logging.getLogger("checkwise.admin").exception(
            "notif_emit_failed event=account.invitation_sent user=%s", user.id
        )

    db.commit()

    return ProvisionUserResponse(
        user_id=user.id,
        role=payload.role,
        email=email,
        temp_password=temp_password,
        login_url=login_url,
        email_status=delivery.status,
        email_error=delivery.error,
        client_id=client_id,
        organization_id=organization_id,
        vendor_id=vendor_id,
        workspace_id=workspace_id,
    )


# ---------------------------------------------------------------------------
# P3 (2026-06-10 audit) — user management: list / disable / reset password
# ---------------------------------------------------------------------------
#
# Until now POST /admin/users (create) was the ONLY user surface — no
# way to list accounts, lock one out, or reissue credentials. These
# three endpoints close the lifecycle, mirroring the client-side
# 3-seat flow in ``app.api.v1.client_users`` (temp password +
# ``must_change_password`` + password-history push + reset email).


class AdminUserOrgItem(BaseModel):
    id: str
    name: str
    kind: str


class AdminUserItem(BaseModel):
    user_id: str
    email: str
    full_name: str
    status: str
    must_change_password: bool
    last_login_at: str | None
    created_at: str
    roles: list[str]
    """Distinct ACTIVE membership roles, sorted."""
    organizations: list[AdminUserOrgItem]
    """Organizations of the user's active memberships."""


class AdminUsersListResponse(BaseModel):
    items: list[AdminUserItem]
    total: int
    """Real count for the q/status/role filters (not len(items))."""


class AdminUserStatusPayload(BaseModel):
    status: Literal["active", "disabled"]


class AdminUserStatusResponse(BaseModel):
    user_id: str
    status: str


class AdminUserResetPasswordResponse(BaseModel):
    """``temp_password`` is plaintext, returned ONCE for the admin's
    confirmation screen — the User row only stores the bcrypt hash."""

    user_id: str
    email: str
    temp_password: str
    email_status: str
    email_error: str | None = None


def _admin_user_filters(
    q: str | None, status_value: str | None, role: str | None
) -> list:
    filters: list = []
    if q and q.strip():
        needle = f"%{q.strip()}%"
        filters.append(
            or_(User.email.ilike(needle), User.full_name.ilike(needle))
        )
    if status_value:
        filters.append(User.status == status_value)
    if role:
        filters.append(
            User.id.in_(
                select(Membership.user_id).where(
                    Membership.role == role,
                    Membership.status == "active",
                )
            )
        )
    return filters


@router.get("/users", response_model=AdminUsersListResponse)
def list_users(
    db: DbSession,
    current: PlatformUser,
    q: str | None = None,
    status_filter: Annotated[
        Literal["active", "disabled"] | None, Query(alias="status")
    ] = None,
    role: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminUsersListResponse:
    """Paged user directory for the admin console.

    * ``q`` — case-insensitive substring match on email OR full_name.
    * ``status`` — ``active`` | ``disabled``.
    * ``role`` — users holding that role on an ACTIVE membership.
    * ``total`` is the real count for the filters, independent of
      the page window. Newest accounts first.

    Memberships + organizations for the page are bulk-loaded with a
    single IN query (no per-row lookups).
    """
    _ = current
    filters = _admin_user_filters(q, status_filter, role)

    count_stmt = select(func.count()).select_from(User)
    page_stmt = select(User)
    if filters:
        count_stmt = count_stmt.where(and_(*filters))
        page_stmt = page_stmt.where(and_(*filters))
    total = int(db.scalar(count_stmt) or 0)
    rows = list(
        db.scalars(
            page_stmt.order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )

    user_ids = [u.id for u in rows]
    roles_by_user: dict[str, set[str]] = {uid: set() for uid in user_ids}
    orgs_by_user: dict[str, dict[str, Organization]] = {
        uid: {} for uid in user_ids
    }
    if user_ids:
        membership_rows = db.execute(
            select(Membership, Organization)
            .join(Organization, Organization.id == Membership.organization_id)
            .where(
                Membership.user_id.in_(user_ids),
                Membership.status == "active",
            )
        ).all()
        for membership, org in membership_rows:
            roles_by_user[membership.user_id].add(membership.role)
            orgs_by_user[membership.user_id].setdefault(org.id, org)

    items = [
        AdminUserItem(
            user_id=u.id,
            email=u.email,
            full_name=u.full_name,
            status=u.status,
            must_change_password=u.must_change_password,
            last_login_at=(
                u.last_login_at.isoformat() if u.last_login_at else None
            ),
            created_at=u.created_at.isoformat() if u.created_at else "",
            roles=sorted(roles_by_user.get(u.id, set())),
            organizations=[
                AdminUserOrgItem(id=org.id, name=org.name, kind=org.kind)
                for org in orgs_by_user.get(u.id, {}).values()
            ],
        )
        for u in rows
    ]
    return AdminUsersListResponse(items=items, total=total)


@router.patch("/users/{user_id}", response_model=AdminUserStatusResponse)
def update_user_status(
    user_id: str,
    payload: AdminUserStatusPayload,
    db: DbSession,
    current: PlatformUser,
    request: Request,
) -> AdminUserStatusResponse:
    """Disable (reversible lockout) or reactivate a user account.

    The auth dependency re-reads the User row per request, so a
    disable locks the account out immediately. Self-disable is
    rejected — an admin cannot saw off the branch they sit on.
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado."
        )
    if payload.status == "disabled" and target.id == current.user.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="No puedes desactivar tu propia cuenta.",
        )

    before_status = target.status
    target.status = payload.status
    db.flush()

    _audit_admin(
        db,
        actor=current,
        action=(
            "admin.user_disabled"
            if payload.status == "disabled"
            else "admin.user_reactivated"
        ),
        entity_type="user",
        entity_id=target.id,
        before={"status": before_status},
        after={"status": payload.status, "user_email": target.email},
        request=request,
    )
    db.commit()
    return AdminUserStatusResponse(user_id=target.id, status=payload.status)


@router.post(
    "/users/{user_id}/reset-password",
    response_model=AdminUserResetPasswordResponse,
    summary="Issue fresh temp credentials to a user (internal_admin)",
)
def reset_user_password(
    user_id: str,
    db: DbSession,
    current: PlatformUser,
    request: Request,
) -> AdminUserResetPasswordResponse:
    """Admin-issued temp credentials for a locked-out user.

    Mirrors the owner-driven flow in ``client_users``: push the old
    hash to the password history, bcrypt a fresh temp password onto
    the row, force ``must_change_password``, and email the temp
    credentials. Email delivery NEVER fails the request — the
    plaintext is returned once so the admin can hand it over out of
    band when SMTP skipped/failed.
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado."
        )
    if target.status != "active":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Reactiva al usuario antes de restablecer su contraseña.",
        )

    temp_password = generate_temp_password()
    # Record the hash being replaced (lazily, like client_users /
    # auth._apply_password_change — the next regular change trims).
    if target.password_hash:
        db.add(
            PasswordHistory(
                user_id=target.id, password_hash=target.password_hash
            )
        )
    target.password_hash = hash_password(temp_password)
    target.must_change_password = True
    db.flush()

    login_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/login"
    delivery = send_owner_reset_temp_password_email(
        to_email=target.email,
        full_name=target.full_name,
        login_url=login_url,
        temp_password=temp_password,
        organization_name=None,
    )

    _audit_admin(
        db,
        actor=current,
        action="admin.user_password_reset",
        entity_type="user",
        entity_id=target.id,
        before=None,
        after={
            "user_email": target.email,
            "email_delivery_status": delivery.status,
        },
        request=request,
    )
    db.commit()

    return AdminUserResetPasswordResponse(
        user_id=target.id,
        email=target.email,
        temp_password=temp_password,
        email_status=delivery.status,
        email_error=delivery.error,
    )


def _active_roles(db: Session, user_id: str) -> list[str]:
    """Distinct ACTIVE membership roles for a user, sorted. Shared by the
    duplicate-email resolver and anywhere a role summary is needed."""
    return sorted(
        {
            role
            for (role,) in db.execute(
                select(Membership.role).where(
                    Membership.user_id == user_id,
                    Membership.status == "active",
                )
            )
        }
    )


def _primary_client_for_user(db: Session, user_id: str) -> Client | None:
    """The Client a user is the Primary Account Owner of, if any.

    Resolves the user's active *primary* ``client_admin`` membership →
    its client-kind org → the linked Client. Returns None for
    secondaries, providers, and internal staff. Used to keep the
    canonical ``Client.email`` contact in sync when the owner's login
    email changes.
    """
    org = db.scalar(
        select(Organization)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(
            Membership.user_id == user_id,
            Membership.status == "active",
            Membership.is_primary.is_(True),
            Organization.kind == "client",
        )
    )
    if org is None or org.client_id is None:
        return None
    return db.get(Client, org.client_id)


class AdminUserIdentityPayload(BaseModel):
    """Partial identity edit. Every field is optional; at least one must
    be present. ``email`` is normalised (trimmed + lowercased) and must
    be unique across users. ``phone`` accepts an empty string to clear."""

    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None


class AdminUserIdentityResponse(BaseModel):
    user_id: str
    full_name: str
    email: str
    phone: str | None
    email_changed: bool
    # Combined delivery status of the old+new change notifications, or
    # None when the email did not change. "sent" | "skipped" | "partial".
    notification_status: str | None = None


@router.patch(
    "/users/{user_id}/identity", response_model=AdminUserIdentityResponse
)
def update_user_identity(
    user_id: str,
    payload: AdminUserIdentityPayload,
    db: DbSession,
    current: PlatformUser,
    request: Request,
) -> AdminUserIdentityResponse:
    """Edit a user's name, email, and/or phone.

    The fix for the delete-and-recreate anti-pattern: a typo'd email is
    correctable in place. On an email change the new address must be free
    (409 otherwise); the canonical ``Client.email`` is kept in sync when
    the user is a client's Primary Account Owner; and BOTH the old and
    new addresses are notified (no verification loop — this is an
    operator-driven internal tool). Audited as ``admin.user.identity_updated``.
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado."
        )
    if target.deleted_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="No puedes editar una cuenta eliminada. Restáurala primero.",
        )

    before = {
        "full_name": target.full_name,
        "email": target.email,
        "phone": target.phone,
    }

    # Resolve the requested changes (only fields actually present in the
    # body — model_fields_set distinguishes "omitted" from "sent as null").
    sent = payload.model_fields_set
    if not sent:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Envía al menos un campo para actualizar.",
        )

    if "full_name" in sent:
        new_name = (payload.full_name or "").strip()
        if not new_name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El nombre no puede quedar vacío.",
            )
        target.full_name = new_name

    if "phone" in sent:
        target.phone = (payload.phone or "").strip() or None

    email_changed = False
    notification_status: str | None = None
    if "email" in sent and payload.email is not None:
        new_email = payload.email.strip().lower()
        if new_email != target.email:
            clash = db.scalar(
                select(User).where(
                    User.email == new_email, User.id != target.id
                )
            )
            if clash is not None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail="Ya existe otra cuenta con ese correo.",
                )
            old_email = target.email
            target.email = new_email
            email_changed = True

            # Keep the canonical client contact in sync for owners.
            client = _primary_client_for_user(db, target.id)
            if client is not None and (client.email or "").lower() == (
                old_email or ""
            ).lower():
                client.email = new_email

            # Notify BOTH addresses. send_transactional_email never raises
            # (skips cleanly when SMTP is unconfigured), so delivery
            # trouble can't fail the edit.
            old_res = send_transactional_email(
                to_email=old_email,
                subject="Tu correo de acceso a CheckWise cambió",
                body=(
                    f"Hola {target.full_name},\n\n"
                    f"El correo de acceso de tu cuenta de CheckWise cambió de "
                    f"{old_email} a {new_email}.\n\n"
                    "Si no reconoces este cambio, contacta a soporte de "
                    "inmediato.\n\n— Equipo CheckWise"
                ),
            )
            new_res = send_transactional_email(
                to_email=new_email,
                subject="Confirmación: nuevo correo de acceso a CheckWise",
                body=(
                    f"Hola {target.full_name},\n\n"
                    f"A partir de ahora inicia sesión en CheckWise con este "
                    f"correo: {new_email}.\n\n— Equipo CheckWise"
                ),
            )
            statuses = {old_res.status, new_res.status}
            if statuses == {"sent"}:
                notification_status = "sent"
            elif statuses == {"skipped"}:
                notification_status = "skipped"
            else:
                notification_status = "partial"

    after = {
        "full_name": target.full_name,
        "email": target.email,
        "phone": target.phone,
    }
    if before == after:
        # Nothing actually changed (e.g. same values re-sent) — skip the
        # audit row and return the current state.
        return AdminUserIdentityResponse(
            user_id=target.id,
            full_name=target.full_name,
            email=target.email,
            phone=target.phone,
            email_changed=False,
            notification_status=None,
        )

    db.flush()
    _audit_admin(
        db,
        actor=current,
        action="admin.user.identity_updated",
        entity_type="user",
        entity_id=target.id,
        before=before,
        after=after,
        extra_metadata=(
            {"email_notification_status": notification_status}
            if email_changed
            else None
        ),
        request=request,
    )
    db.commit()

    return AdminUserIdentityResponse(
        user_id=target.id,
        full_name=target.full_name,
        email=target.email,
        phone=target.phone,
        email_changed=email_changed,
        notification_status=notification_status,
    )


# ---------------------------------------------------------------------------
# Membership management (platform rework, Phase 4)
#
# Grant / revoke roles and transfer the Primary Account Owner from the
# user-detail page. Mirrors the seat-cap + primary-owner guards proven in
# ``client_users.py`` but operates platform-wide (any org), gated on
# PlatformUser rather than the org owner.
# ---------------------------------------------------------------------------

_DEFAULT_CLIENT_SEAT_LIMIT: Final = 3

# Which org ``kind`` each role may be granted in. Keeps an operator from
# attaching ``internal_admin`` to a client tenant (or vice-versa).
_ROLE_ORG_KIND: Final = {
    MembershipRole.CLIENT_ADMIN.value: "client",
    MembershipRole.INTERNAL_ADMIN.value: "internal",
    MembershipRole.REVIEWER.value: "internal",
    MembershipRole.PLATFORM_ADMIN.value: "internal",
}

MembershipRoleLiteral = Literal[
    "client_admin", "internal_admin", "reviewer", "platform_admin"
]


class AdminMembershipGrantPayload(BaseModel):
    organization_id: str
    role: MembershipRoleLiteral


class AdminMembershipResponse(BaseModel):
    user_id: str
    membership_id: str
    organization_id: str
    role: str
    status: str
    is_primary: bool


def _membership_audit_dict(m: Membership) -> dict:
    return {
        "membership_id": m.id,
        "user_id": m.user_id,
        "organization_id": m.organization_id,
        "role": m.role,
        "status": m.status,
        "is_primary": m.is_primary,
    }


def _seat_count(db: Session, org_id: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.organization_id == org_id,
                Membership.status == "active",
            )
        )
        or 0
    )


@router.post(
    "/users/{user_id}/memberships", response_model=AdminMembershipResponse
)
def grant_user_membership(
    user_id: str,
    payload: AdminMembershipGrantPayload,
    db: DbSession,
    current: PlatformUser,
    request: Request,
) -> AdminMembershipResponse:
    """Grant a role to a user within an organization.

    Guards: the org must exist and its ``kind`` must match the role
    (``client_admin``→client, internal roles→internal); client orgs
    enforce the seat cap (locked ``SELECT … FOR UPDATE`` so concurrent
    grants can't overshoot). A previously-removed membership for the same
    (user, org, role) is reactivated rather than re-inserted — the unique
    constraint spans all statuses. New grants are never primary; transfer
    ownership via PATCH. Audited ``admin.user.membership_granted``.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado."
        )
    if user.deleted_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="No puedes asignar roles a una cuenta eliminada.",
        )

    # Lock the org row so the seat-cap check below is race-free.
    org = db.scalars(
        select(Organization)
        .where(Organization.id == payload.organization_id)
        .with_for_update()
    ).first()
    if org is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Organización no encontrada."
        )
    expected_kind = _ROLE_ORG_KIND[payload.role]
    if org.kind != expected_kind:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"El rol '{payload.role}' solo puede asignarse en una "
                f"organización de tipo '{expected_kind}'."
            ),
        )

    existing = db.scalars(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == org.id,
            Membership.role == payload.role,
        )
    ).first()
    if existing is not None and existing.status == "active":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="El usuario ya tiene ese rol en esta organización.",
        )

    # Seat cap applies to client orgs. A reactivation of an existing
    # member still consumes a seat, so it's checked the same way.
    if org.kind == "client":
        limit = org.seat_limit or _DEFAULT_CLIENT_SEAT_LIMIT
        if _seat_count(db, org.id) >= limit:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"La organización alcanzó su límite de {limit} "
                    "asientos. Libera uno antes de asignar otro."
                ),
            )

    if existing is not None:
        before = _membership_audit_dict(existing)
        existing.status = "active"
        membership = existing
    else:
        before = None
        membership = Membership(
            user_id=user_id,
            organization_id=org.id,
            role=payload.role,
            is_primary=False,
            status="active",
        )
        db.add(membership)
    db.flush()

    _audit_admin(
        db,
        actor=current,
        action="admin.user.membership_granted",
        entity_type="membership",
        entity_id=membership.id,
        before=before,
        after=_membership_audit_dict(membership),
        extra_metadata={"user_id": user_id, "user_email": user.email},
        request=request,
    )
    db.commit()
    return AdminMembershipResponse(
        user_id=user_id,
        membership_id=membership.id,
        organization_id=membership.organization_id,
        role=membership.role,
        status=membership.status,
        is_primary=membership.is_primary,
    )


def _membership_for_user_or_404(
    db: Session, user_id: str, membership_id: str
) -> Membership:
    membership = db.get(Membership, membership_id)
    if membership is None or membership.user_id != user_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Membresía no encontrada."
        )
    return membership


@router.delete(
    "/users/{user_id}/memberships/{membership_id}",
    response_model=AdminMembershipResponse,
)
def revoke_user_membership(
    user_id: str,
    membership_id: str,
    db: DbSession,
    current: PlatformUser,
    request: Request,
) -> AdminMembershipResponse:
    """Revoke a role (soft — ``status='removed'``).

    The active Primary Account Owner can't be revoked here; transfer
    ownership to another member first (PATCH). Already-removed
    memberships return as-is (idempotent). Audited
    ``admin.user.membership_revoked``.
    """
    membership = _membership_for_user_or_404(db, user_id, membership_id)
    if membership.is_primary and membership.status == "active":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "Es el titular de la organización. Transfiere la "
                "titularidad a otro miembro antes de quitar este rol."
            ),
        )
    if membership.status != "removed":
        before = _membership_audit_dict(membership)
        membership.status = "removed"
        db.flush()
        _audit_admin(
            db,
            actor=current,
            action="admin.user.membership_revoked",
            entity_type="membership",
            entity_id=membership.id,
            before=before,
            after=_membership_audit_dict(membership),
            extra_metadata={"user_id": user_id},
            request=request,
        )
        db.commit()
    return AdminMembershipResponse(
        user_id=user_id,
        membership_id=membership.id,
        organization_id=membership.organization_id,
        role=membership.role,
        status=membership.status,
        is_primary=membership.is_primary,
    )


class AdminMembershipPromotePayload(BaseModel):
    is_primary: Literal[True]


@router.patch(
    "/users/{user_id}/memberships/{membership_id}",
    response_model=AdminMembershipResponse,
)
def promote_user_membership(
    user_id: str,
    membership_id: str,
    payload: AdminMembershipPromotePayload,
    db: DbSession,
    current: PlatformUser,
    request: Request,
) -> AdminMembershipResponse:
    """Make this membership the organization's Primary Account Owner.

    Client orgs only (primary ownership is the 3-seat model's concept).
    The org is locked and the current primary demoted BEFORE this one is
    promoted, so the one-active-primary-per-org partial unique index is
    never transiently violated. Audited ``admin.user.membership_promoted``.
    """
    _ = payload  # is_primary is constrained to True by the schema.
    membership = _membership_for_user_or_404(db, user_id, membership_id)
    if membership.status != "active":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Solo una membresía activa puede ser titular.",
        )
    # Lock the org to serialize ownership transfers.
    org = db.scalars(
        select(Organization)
        .where(Organization.id == membership.organization_id)
        .with_for_update()
    ).first()
    if org is None or org.kind != "client":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="La titularidad solo aplica a organizaciones cliente.",
        )
    if membership.is_primary:
        # Already the owner — no-op.
        return AdminMembershipResponse(
            user_id=user_id,
            membership_id=membership.id,
            organization_id=membership.organization_id,
            role=membership.role,
            status=membership.status,
            is_primary=True,
        )

    before = _membership_audit_dict(membership)
    current_primary = db.scalars(
        select(Membership).where(
            Membership.organization_id == org.id,
            Membership.status == "active",
            Membership.is_primary.is_(True),
        )
    ).first()
    demoted_id: str | None = None
    if current_primary is not None and current_primary.id != membership.id:
        current_primary.is_primary = False
        demoted_id = current_primary.id
        db.flush()  # clear the old primary before setting the new one
    membership.is_primary = True
    db.flush()

    _audit_admin(
        db,
        actor=current,
        action="admin.user.membership_promoted",
        entity_type="membership",
        entity_id=membership.id,
        before=before,
        after=_membership_audit_dict(membership),
        extra_metadata={
            "user_id": user_id,
            "demoted_membership_id": demoted_id,
        },
        request=request,
    )
    db.commit()
    return AdminMembershipResponse(
        user_id=user_id,
        membership_id=membership.id,
        organization_id=membership.organization_id,
        role=membership.role,
        status=membership.status,
        is_primary=True,
    )


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


@router.get("/institutions")
def list_institutions(db: DbSession, current: AdminUser) -> dict:
    """Institution catalog for the requirements form dropdowns."""
    _ = current
    rows = list(db.scalars(select(Institution).order_by(Institution.name.asc())))
    return {
        "items": [{"id": r.id, "code": r.code, "name": r.name} for r in rows]
    }


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
    # Batch the current-version lookup: one tuple-IN over
    # (requirement_id, current_version) instead of a query per row.
    version_by_req: dict[str, RequirementVersion] = {}
    pairs = [(r.id, r.current_version) for r in rows]
    if pairs:
        for v in db.scalars(
            select(RequirementVersion).where(
                tuple_(
                    RequirementVersion.requirement_id,
                    RequirementVersion.version,
                ).in_(pairs)
            )
        ):
            version_by_req[v.requirement_id] = v
    items = [
        _requirement_to_dict(r, version=version_by_req.get(r.id)) for r in rows
    ]
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
    current: PlatformUser,
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
    report_id: str, db: DbSession, current: PlatformUser
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
    current: PlatformUser,
    request: Request,
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
        request=request,
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
    """Real count of export events matching the filter."""
    limit: int
    offset: int


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
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MetadataExportListResponse:
    """List XLSX metadata exports generated by provider uploads.

    ``total`` is the real count of events matching the filter; the
    page's related entities (submission, document, client, vendor,
    requirement) are bulk-loaded with one IN query per entity type
    instead of ~5 ``db.get`` lookups per row.
    """
    _ = current
    filters = [ValidationEvent.event_type == "metadata_table_exported"]
    if result:
        filters.append(ValidationEvent.result == result)
    total = int(
        db.scalar(
            select(func.count()).select_from(ValidationEvent).where(*filters)
        )
        or 0
    )
    stmt = (
        select(ValidationEvent)
        .where(*filters)
        .order_by(ValidationEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = list(db.scalars(stmt))

    # ---- Bulk-load the page's related entities (one IN query each). ----
    submission_ids = {r.submission_id for r in rows if r.submission_id}
    document_ids = {r.document_id for r in rows if r.document_id}
    submissions: dict[str, Submission] = {}
    if submission_ids:
        submissions = {
            s.id: s
            for s in db.scalars(
                select(Submission).where(Submission.id.in_(submission_ids))
            )
        }
    documents: dict[str, Document] = {}
    if document_ids:
        documents = {
            d.id: d
            for d in db.scalars(
                select(Document).where(Document.id.in_(document_ids))
            )
        }
    client_ids = {s.client_id for s in submissions.values() if s.client_id}
    vendor_ids = {s.vendor_id for s in submissions.values() if s.vendor_id}
    requirement_ids = {
        s.requirement_id for s in submissions.values() if s.requirement_id
    }
    clients: dict[str, Client] = {}
    if client_ids:
        clients = {
            c.id: c
            for c in db.scalars(select(Client).where(Client.id.in_(client_ids)))
        }
    vendors: dict[str, Vendor] = {}
    if vendor_ids:
        vendors = {
            v.id: v
            for v in db.scalars(select(Vendor).where(Vendor.id.in_(vendor_ids)))
        }
    requirements: dict[str, Requirement] = {}
    if requirement_ids:
        requirements = {
            r.id: r
            for r in db.scalars(
                select(Requirement).where(Requirement.id.in_(requirement_ids))
            )
        }

    items = []
    for event in rows:
        submission = submissions.get(event.submission_id)
        items.append(
            _build_metadata_export_item(
                event,
                submission=submission,
                document=(
                    documents.get(event.document_id)
                    if event.document_id
                    else None
                ),
                client=(
                    clients.get(submission.client_id) if submission else None
                ),
                vendor=(
                    vendors.get(submission.vendor_id) if submission else None
                ),
                requirement=(
                    requirements.get(submission.requirement_id)
                    if submission
                    else None
                ),
            )
        )
    return MetadataExportListResponse(
        items=items, total=total, limit=limit, offset=offset
    )


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
    if path is not None:
        ensure_local_export(path)
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
    if path is not None:
        ensure_local_export(path)
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
    path = ensure_local_export(_client_master_file_path(client))
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
    path = ensure_local_export(_client_master_file_path(client))
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
    path = ensure_local_export(_client_master_file_path(client))
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
    """Single-event item (detail/preview paths). The list endpoint
    bulk-loads the relations instead — see ``list_metadata_exports``."""
    submission = db.get(Submission, event.submission_id)
    return _build_metadata_export_item(
        event,
        submission=submission,
        document=(
            db.get(Document, event.document_id) if event.document_id else None
        ),
        client=db.get(Client, submission.client_id) if submission else None,
        vendor=db.get(Vendor, submission.vendor_id) if submission else None,
        requirement=(
            db.get(Requirement, submission.requirement_id)
            if submission
            else None
        ),
    )


def _build_metadata_export_item(
    event: ValidationEvent,
    *,
    submission: Submission | None,
    document: Document | None,
    client: Client | None,
    vendor: Vendor | None,
    requirement: Requirement | None,
) -> MetadataExportListItem:
    """Pure item builder over prefetched relations (no db access —
    except the deliberate per-row filesystem ``exists()`` checks)."""
    payload = event.payload or {}
    path = _metadata_export_file_path(event)
    # Optimistic when the durable mirror is on: a completed export that
    # the (ephemeral) local disk lost is still downloadable — the
    # preview/download endpoints re-materialize it on demand. Probing
    # the mirror per row would add a network round-trip per list item.
    file_exists = bool(path and path.exists()) or bool(
        path is not None and mirror_enabled() and event.result == "completed"
    )
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
        master_available=bool(
            client
            and (
                _client_master_file_path(client).exists()
                or (mirror_enabled() and event.result == "completed")
            )
        ),
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
    actor_email: str | None = None
    """Resolved ``User.email`` for ``actor_id`` (null when the actor
    id isn't a user id — e.g. system events or workspace tokens)."""
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
    """Real count of rows matching the filters (not len(items))."""
    limit: int
    offset: int


@router.get("/audit-log", response_model=AuditLogResponse)
def list_audit_log(
    db: DbSession,
    current: PlatformUser,
    actor_id: str | None = None,
    actor_type: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogResponse:
    """Filtered audit-log explorer.

    Newest first. Filters compose as AND. Default limit 50, hard cap
    200; ``offset`` pages through the filtered set and ``total`` is
    the real matching row count (a separate COUNT over the same
    filters), so the UI can render proper pagination.

    ``action`` is a case-insensitive PREFIX match —
    ``action=admin.user`` finds ``admin.user_disabled``,
    ``admin.user.provisioned``, etc. Strictly more forgiving than the
    old exact match (any previously-exact value still matches itself).

    ``actor_email`` is resolved per item by bulk-loading the page's
    distinct actor_ids against ``users`` (one IN query); null when
    the actor_id isn't a user id.
    """
    _ = current
    filters = []
    if actor_id:
        filters.append(AuditLog.actor_id == actor_id)
    if actor_type:
        filters.append(AuditLog.actor_type == actor_type)
    if action:
        filters.append(AuditLog.action.ilike(f"{action}%"))
    if entity_type:
        filters.append(AuditLog.entity_type == entity_type)
    if entity_id:
        filters.append(AuditLog.entity_id == entity_id)
    if date_from:
        filters.append(AuditLog.created_at >= date_from)
    if date_to:
        filters.append(AuditLog.created_at <= date_to)
    count_stmt = select(func.count()).select_from(AuditLog)
    stmt = select(AuditLog)
    if filters:
        count_stmt = count_stmt.where(and_(*filters))
        stmt = stmt.where(and_(*filters))
    total = int(db.scalar(count_stmt) or 0)
    stmt = (
        stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    )
    rows = list(db.scalars(stmt))

    actor_ids = {row.actor_id for row in rows if row.actor_id}
    email_by_user_id: dict[str, str] = {}
    if actor_ids:
        email_by_user_id = {
            user_id: email
            for user_id, email in db.execute(
                select(User.id, User.email).where(User.id.in_(actor_ids))
            )
        }

    items = [
        AuditLogItem(
            id=row.id,
            actor_id=row.actor_id,
            actor_email=(
                email_by_user_id.get(row.actor_id) if row.actor_id else None
            ),
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
    return AuditLogResponse(items=items, total=total, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# User detail (platform rework, Phase 2)
#
# Lives next to the audit-log explorer rather than the other /users
# endpoints because the detail response embeds ``AuditLogItem`` — a
# user's own slice of the audit trail — and Pydantic needs that class
# defined first. The route order is irrelevant to FastAPI; only the
# class-definition order matters.
# ---------------------------------------------------------------------------


class AdminUserMembershipItem(BaseModel):
    membership_id: str
    organization_id: str
    organization_name: str
    organization_kind: str
    role: str
    is_primary: bool
    status: str
    # Seat picture for ``client`` orgs only (the 3-seat model); NULL on
    # internal / vendor orgs which carry no cap.
    seat_limit: int | None = None
    active_seats: int | None = None


class AdminUserDetail(BaseModel):
    user_id: str
    email: str
    full_name: str
    status: str
    must_change_password: bool
    phone: str | None
    last_login_at: str | None
    created_at: str
    updated_at: str
    # Soft-delete provenance (migration 0042). All NULL on a live account.
    deleted_at: str | None
    deleted_by_user_id: str | None
    deleted_by_email: str | None = None
    deletion_reason: str | None
    roles: list[str]
    """Distinct ACTIVE membership roles, sorted (matches the list view)."""
    memberships: list[AdminUserMembershipItem]
    """ALL memberships (active + removed + disabled), active first."""
    recent_activity: list[AuditLogItem]
    """The user's own audit slice: events targeting them OR performed by
    them, newest first. ``activity_total`` is the real count so the UI can
    link to the full audit-log explorer when it overflows the window."""
    activity_total: int


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def get_user_detail(
    user_id: str,
    db: DbSession,
    current: PlatformUser,
    activity_limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AdminUserDetail:
    """Full picture of one account for the platform user-detail page.

    Identity + every membership (with org name/kind, primary flag and a
    seat picture for client orgs) + the user's own slice of the audit
    trail (events targeting them OR performed by them). A soft-deleted
    account is still returned — the detail page is where a restore would
    be initiated — with its deletion provenance populated.
    """
    _ = current
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado."
        )

    # ---- Memberships (all statuses) + their organizations. ----------
    membership_rows = db.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id == user_id)
    ).all()

    # Active-seat counts for the client orgs this user touches, one
    # grouped query rather than a count per membership.
    client_org_ids = [
        org.id for _m, org in membership_rows if org.kind == "client"
    ]
    active_seats_by_org: dict[str, int] = {}
    if client_org_ids:
        active_seats_by_org = {
            org_id: int(count)
            for org_id, count in db.execute(
                select(Membership.organization_id, func.count())
                .where(
                    Membership.organization_id.in_(client_org_ids),
                    Membership.status == "active",
                )
                .group_by(Membership.organization_id)
            )
        }

    # Active memberships first, then most-recently-created.
    def _membership_sort_key(pair: tuple[Membership, Organization]):
        m, _org = pair
        return (0 if m.status == "active" else 1, -(m.created_at.timestamp()))

    memberships = [
        AdminUserMembershipItem(
            membership_id=m.id,
            organization_id=org.id,
            organization_name=org.name,
            organization_kind=org.kind,
            role=m.role,
            is_primary=m.is_primary,
            status=m.status,
            seat_limit=(org.seat_limit if org.kind == "client" else None),
            active_seats=(
                active_seats_by_org.get(org.id, 0)
                if org.kind == "client"
                else None
            ),
        )
        for m, org in sorted(membership_rows, key=_membership_sort_key)
    ]
    roles = sorted(
        {m.role for m, _org in membership_rows if m.status == "active"}
    )

    # ---- The user's own audit slice. --------------------------------
    # Events that TARGET this user (entity) or were PERFORMED by them
    # (actor). Newest first; total is the real matching count.
    activity_filter = or_(
        and_(AuditLog.entity_type == "user", AuditLog.entity_id == user_id),
        AuditLog.actor_id == user_id,
    )
    activity_total = int(
        db.scalar(
            select(func.count()).select_from(AuditLog).where(activity_filter)
        )
        or 0
    )
    activity_rows = list(
        db.scalars(
            select(AuditLog)
            .where(activity_filter)
            .order_by(AuditLog.created_at.desc())
            .limit(activity_limit)
        )
    )
    actor_ids = {row.actor_id for row in activity_rows if row.actor_id}
    email_by_user_id: dict[str, str] = {}
    if actor_ids:
        email_by_user_id = {
            uid: email
            for uid, email in db.execute(
                select(User.id, User.email).where(User.id.in_(actor_ids))
            )
        }
    recent_activity = [
        AuditLogItem(
            id=row.id,
            actor_id=row.actor_id,
            actor_email=(
                email_by_user_id.get(row.actor_id) if row.actor_id else None
            ),
            actor_type=row.actor_type,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            before=row.before,
            after=row.after,
            event_metadata=row.event_metadata,
            created_at=row.created_at,
        )
        for row in activity_rows
    ]

    # Resolve the deleting operator's email for a friendlier display.
    deleted_by_email: str | None = None
    if user.deleted_by_user_id:
        deleted_by_email = db.scalar(
            select(User.email).where(User.id == user.deleted_by_user_id)
        )

    return AdminUserDetail(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        status=user.status,
        must_change_password=user.must_change_password,
        phone=user.phone,
        last_login_at=(
            user.last_login_at.isoformat() if user.last_login_at else None
        ),
        created_at=user.created_at.isoformat() if user.created_at else "",
        updated_at=user.updated_at.isoformat() if user.updated_at else "",
        deleted_at=user.deleted_at.isoformat() if user.deleted_at else None,
        deleted_by_user_id=user.deleted_by_user_id,
        deleted_by_email=deleted_by_email,
        deletion_reason=user.deletion_reason,
        roles=roles,
        memberships=memberships,
        recent_activity=recent_activity,
        activity_total=activity_total,
    )


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


# ───────────────────────────────────────────────────────────────────
# Global search · admin scope (sees every submission)
# ───────────────────────────────────────────────────────────────────


class SearchHitOut(BaseModel):
    submission_id: str
    vendor_id: str
    vendor_name: str
    vendor_rfc: str | None
    client_id: str
    client_name: str
    client_rfc: str | None
    period_key: str | None
    institution_code: str | None
    institution_label: str | None
    requirement_name: str | None
    status: str
    contract_folio: str | None
    matched_by: str
    created_at: str


class SearchResponse(BaseModel):
    query: str
    matched_by: str
    total: int
    items: list[SearchHitOut]


def _hits_to_response(query: str, hits: list[SearchHit]) -> SearchResponse:
    return SearchResponse(
        query=query,
        # Even an empty result reports the detected query type so the
        # UI can render a "we treated this as a periodo" hint.
        matched_by=(hits[0].matched_by if hits else "folio"),
        total=len(hits),
        items=[SearchHitOut(**hit.__dict__) for hit in hits],
    )


@router.get("/search", response_model=SearchResponse)
def admin_search(
    q: Annotated[str, Query(min_length=1, max_length=120)],
    db: DbSession,
    current: AdminUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SearchResponse:
    """Search every submission CheckWise stores by RFC, periodo or folio.

    Reviewers triage across all clients/vendors, so this endpoint
    intentionally has no scope filter. The frontend search bar in the
    admin shell calls this; the result page links each row to the
    /admin/reviewer/{submission_id} detail view.
    """
    _ = current  # auth handled by AdminUser dependency
    hits = search_submissions(db, q, limit=limit)
    return _hits_to_response(q, hits)
