"""Phase 8 — Client Portal read model.

Client-facing monitoring surface. ``client_admin`` users get
read-only visibility into the vendors / workspaces / submissions
that belong to their client organisation; ``internal_admin`` is
allowed too for support and debugging.

Scope model:
    user -> memberships (role=client_admin)
              -> organization (kind="client", client_id=<X>)
              -> Client(id=<X>)

A ``client_admin`` user is locked to the union of clients
reachable through their memberships. An ``internal_admin`` user
may inspect any client by passing ``?client_id=<X>`` (no
implicit cross-tenant visibility for the default endpoint —
they must pick a client). All endpoints are read-only.

This router reuses the pure dashboard-composition helpers from
``app.api.v1.portal``. They take ``SlotView`` lists and produce
the same shapes the provider dashboard renders, so the client
surface stays in lock-step with the provider experience without
duplicating slot logic.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.api.v1.auth import CurrentUser, require_any_role
from app.api.v1.portal import (
    _ACTIONABLE_SLOT_STATES,
    _RESOLVED_SLOT_STATES,
    DashboardAttentionItem,
    DashboardDocumentStateCounts,
    DashboardOnboardingSummary,
    DashboardSemaphore,
    DashboardSuggestedAction,
    DashboardUpcomingDeadline,
    _bucket_document_state,
    _calendar_deadline_iso,
    _calendar_upload_href,
    _compute_attention_today,
    _compute_onboarding_summary,
    _compute_semaphore,
    _compute_suggested_actions,
    _compute_upcoming_deadlines,
    _due_in_days_for_period,
    _empty_document_counts,
    _latest_reviewer_note,
)
from app.constants.roles import MembershipRole
from app.constants.statuses import DocumentStatus
from app.core.compliance_catalog import (
    catalog_metadata,
    recurring_for_year,
    recurring_required_document,
)
from app.db.session import get_db
from app.models import (
    Client,
    Document,
    Membership,
    Organization,
    ProviderWorkspace,
    Submission,
    ValidationEvent,
    Vendor,
)
from app.services.evidence_slots import (
    SlotState,
    SlotView,
    build_workspace_calendar_slots,
    build_workspace_onboarding_slots,
)

router = APIRouter(prefix="/client", tags=["client"])
DbSession = Annotated[Session, Depends(get_db)]

# ``client_admin`` is the primary role. ``internal_admin`` is allowed
# because LegalShelf staff frequently need to debug a client's view
# without minting a fake client account. Reviewer / provider sessions
# get the standard 403.
ClientUser = Annotated[
    CurrentUser,
    Depends(
        require_any_role(MembershipRole.CLIENT_ADMIN, MembershipRole.INTERNAL_ADMIN)
    ),
]


# ---------------------------------------------------------------------------
# Scope resolution
# ---------------------------------------------------------------------------


def _visible_client_ids_for_user(db: Session, user_id: str) -> list[str]:
    """Return the client ids reachable through ``client_admin`` memberships.

    Walks ``memberships -> organization -> client``. Filters out
    inactive memberships and orgs without a ``client_id`` link
    (e.g. ``kind='internal'`` orgs). Order is deterministic so the
    "default" pick is stable across requests.
    """
    rows = list(
        db.scalars(
            select(Organization.client_id)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(
                Membership.user_id == user_id,
                Membership.role == MembershipRole.CLIENT_ADMIN.value,
                Membership.status == "active",
                Organization.client_id.is_not(None),
            )
            .distinct()
        )
    )
    return [cid for cid in rows if cid]


def _resolve_client_id(
    db: Session,
    current: CurrentUser,
    *,
    requested: str | None,
) -> str:
    """Pick the client_id this request is scoped to.

    Rules:

    * ``client_admin`` users are locked to clients reachable through
      their memberships. ``requested`` must match one of those (or
      be omitted, in which case the first is used).
    * ``internal_admin`` users may pass any existing client id. When
      no ``requested`` value is supplied AND they also hold a
      ``client_admin`` membership somewhere, that client is used as
      default; otherwise a 400 nudges them to specify one explicitly.
    * Anyone else got rejected by the auth dependency already.

    Raises:
        404 if ``requested`` does not exist.
        403 if ``requested`` is not visible to this user.
        400 if no client can be resolved.
    """
    visible = _visible_client_ids_for_user(db, current.user.id)
    is_internal_admin = MembershipRole.INTERNAL_ADMIN.value in current.roles

    if requested:
        target = db.get(Client, requested)
        if target is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado."
            )
        if is_internal_admin:
            return requested
        if requested not in visible:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este cliente.",
            )
        return requested

    if visible:
        return visible[0]
    if is_internal_admin:
        # Internal admin without a default — be explicit instead of
        # silently leaking every client's data.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                "Sin cliente por defecto. Pasa ?client_id=<uuid> para "
                "inspeccionar un cliente específico."
            ),
        )
    raise HTTPException(
        status.HTTP_403_FORBIDDEN, detail="No tienes ningún cliente asignado."
    )


def _scoped_workspaces(db: Session, client_id: str) -> list[ProviderWorkspace]:
    return list(
        db.scalars(
            select(ProviderWorkspace)
            .where(ProviderWorkspace.client_id == client_id)
            .order_by(ProviderWorkspace.created_at.desc())
        )
    )


def _vendors_by_id(db: Session, vendor_ids: list[str]) -> dict[str, Vendor]:
    if not vendor_ids:
        return {}
    rows = db.scalars(select(Vendor).where(Vendor.id.in_(vendor_ids)))
    return {v.id: v for v in rows}


# ---------------------------------------------------------------------------
# Helpers — per-vendor compliance summary
# ---------------------------------------------------------------------------


def _vendor_compliance(
    db: Session,
    workspace: ProviderWorkspace,
    *,
    today: date,
    year: int,
) -> dict:
    """Compute compliance summary for one workspace.

    Returns the dict the ``/client/vendors`` list endpoint emits per
    row. Built from the canonical slot service so red/yellow/green
    semantics match the provider dashboard exactly.
    """
    onboarding_slots = build_workspace_onboarding_slots(db, workspace)
    calendar_slots = build_workspace_calendar_slots(db, workspace, year)
    counts = _empty_document_counts()
    for view in onboarding_slots + calendar_slots:
        _bucket_document_state(counts, view.state)
    semaphore = _compute_semaphore(onboarding_slots, calendar_slots)
    required = [s for s in onboarding_slots if s.required] + [
        s for s in calendar_slots if s.required
    ]
    missing_required = sum(1 for s in required if s.state is SlotState.MISSING)
    rejected_or_correction = sum(
        1 for s in required if s.state in _ACTIONABLE_SLOT_STATES
    )
    pending_reviews = sum(
        1
        for s in required
        if s.state in (SlotState.IN_REVIEW, SlotState.UPLOADED)
    )
    due_soon = 0
    for s in calendar_slots:
        if not s.required:
            continue
        if s.state in _RESOLVED_SLOT_STATES:
            continue
        due_in = _due_in_days_for_period(s.period_key, today)
        if due_in is not None and 0 <= due_in <= 14:
            due_soon += 1
    return {
        "compliance_pct": semaphore.compliance_pct,
        "semaphore_level": semaphore.level,
        "counts": counts.model_dump(),
        "missing_required_count": missing_required,
        "rejected_or_correction_count": rejected_or_correction,
        "pending_reviews_count": pending_reviews,
        "due_soon_count": due_soon,
        "onboarding_slots": onboarding_slots,
        "calendar_slots": calendar_slots,
        "semaphore": semaphore,
    }


def _last_activity_timestamps(
    db: Session, vendor_id: str
) -> tuple[datetime | None, datetime | None]:
    """Return (last_submission_at, last_review_at) for one vendor."""
    last_sub = db.scalar(
        select(func.max(Submission.created_at)).where(Submission.vendor_id == vendor_id)
    )
    last_review = db.scalar(
        select(func.max(ValidationEvent.created_at))
        .join(Submission, ValidationEvent.submission_id == Submission.id)
        .where(
            Submission.vendor_id == vendor_id,
            ValidationEvent.event_type == "reviewer_decision",
        )
    )
    return last_sub, last_review


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ClientMe(BaseModel):
    user_id: str
    email: str
    roles: list[str]
    visible_client_ids: list[str]
    default_client_id: str | None


class ClientOverview(BaseModel):
    client_id: str
    client_name: str
    vendors_total: int
    active_workspaces_total: int
    compliance_pct: int
    green_count: int
    yellow_count: int
    red_count: int
    pending_reviews_total: int
    rejected_or_correction_total: int
    missing_required_total: int
    due_soon_total: int
    recent_submissions_total: int
    last_activity_at: datetime | None


class ClientVendorRow(BaseModel):
    vendor_id: str
    workspace_id: str
    vendor_name: str
    vendor_rfc: str | None
    persona_type: str | None
    workspace_status: str
    compliance_pct: int
    semaphore_level: Literal["green", "yellow", "red"]
    pending_reviews_count: int
    missing_required_count: int
    rejected_or_correction_count: int
    due_soon_count: int
    last_submission_at: datetime | None
    last_review_at: datetime | None


class ClientVendorListResponse(BaseModel):
    client_id: str
    items: list[ClientVendorRow]
    total: int


class ClientVendorDetail(BaseModel):
    client_id: str
    vendor_id: str
    workspace_id: str
    vendor: dict
    workspace: dict
    onboarding_summary: DashboardOnboardingSummary
    document_state_counts: DashboardDocumentStateCounts
    semaphore: DashboardSemaphore
    suggested_actions: list[DashboardSuggestedAction]
    attention_today: list[DashboardAttentionItem]
    upcoming_deadlines: list[DashboardUpcomingDeadline]
    recent_submissions: list[dict]
    recent_reviewer_notes: list[dict]


class ClientSubmissionItem(BaseModel):
    submission_id: str
    vendor_id: str
    vendor_name: str
    requirement_code: str | None
    requirement_name: str | None
    period_key: str | None
    status: str
    filename: str | None
    submitted_at: datetime
    reviewed_at: datetime | None
    reviewer_note: str | None
    supersedes_submission_id: str | None
    superseded_by_submission_id: str | None


class ClientSubmissionsResponse(BaseModel):
    client_id: str
    items: list[ClientSubmissionItem]
    total: int


class ClientActivityItem(BaseModel):
    id: str
    occurred_at: datetime
    actor_type: str
    action: str
    entity_type: str
    entity_id: str
    vendor_id: str | None
    vendor_name: str | None
    summary: str


class ClientActivityResponse(BaseModel):
    client_id: str
    items: list[ClientActivityItem]
    total: int
    limit: int


class ClientCalendarItem(BaseModel):
    vendor_id: str
    workspace_id: str
    vendor_name: str
    requirement_code: str | None
    requirement_name: str
    institution: str
    frequency: str
    period_key: str | None
    period_label: str
    status: str
    submission_id: str | None
    deadline_iso: str
    risk_level: str | None
    href: str


class ClientCalendarMonth(BaseModel):
    month: int
    month_label: str
    vendors_total: int
    due_total: int
    approved_total: int
    pending_total: int
    rejected_or_correction_total: int
    missing_total: int
    due_soon_total: int
    items: list[ClientCalendarItem]


class ClientCalendarResponse(BaseModel):
    metadata: dict
    client_id: str
    year: int
    months: list[ClientCalendarMonth]


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


@router.get("/me", response_model=ClientMe)
def client_me(db: DbSession, current: ClientUser) -> ClientMe:
    """Identity + visible client ids + default. The frontend stores
    this so it can pick the right scope on every subsequent call.
    """
    visible = _visible_client_ids_for_user(db, current.user.id)
    return ClientMe(
        user_id=current.user.id,
        email=current.user.email,
        roles=current.roles,
        visible_client_ids=visible,
        default_client_id=visible[0] if visible else None,
    )


# ---------------------------------------------------------------------------
# /overview
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


@router.get("/overview", response_model=ClientOverview)
def client_overview(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    year: int | None = None,
) -> ClientOverview:
    target_id = _resolve_client_id(db, current, requested=client_id)
    target_client = db.get(Client, target_id)
    if target_client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")
    today = date.today()
    selected_year = year or today.year

    workspaces = _scoped_workspaces(db, target_id)
    vendors_total = int(
        db.scalar(select(func.count(Vendor.id)).where(Vendor.client_id == target_id))
        or 0
    )
    active_workspaces_total = sum(1 for w in workspaces if w.status == "active")

    green = yellow = red = 0
    pending_reviews_total = 0
    rejected_or_correction_total = 0
    missing_required_total = 0
    due_soon_total = 0
    weighted_pct_sum = 0
    weighted_count = 0
    for ws in workspaces:
        summary = _vendor_compliance(db, ws, today=today, year=selected_year)
        level = summary["semaphore_level"]
        if level == "green":
            green += 1
        elif level == "yellow":
            yellow += 1
        else:
            red += 1
        pending_reviews_total += summary["pending_reviews_count"]
        rejected_or_correction_total += summary["rejected_or_correction_count"]
        missing_required_total += summary["missing_required_count"]
        due_soon_total += summary["due_soon_count"]
        weighted_pct_sum += summary["compliance_pct"]
        weighted_count += 1

    compliance_pct = (
        round(weighted_pct_sum / weighted_count) if weighted_count else 100
    )

    recent_submissions_total = int(
        db.scalar(
            select(func.count(Submission.id)).where(Submission.client_id == target_id)
        )
        or 0
    )
    last_activity_at = db.scalar(
        select(func.max(Submission.created_at)).where(
            Submission.client_id == target_id
        )
    )

    return ClientOverview(
        client_id=target_id,
        client_name=target_client.name,
        vendors_total=vendors_total,
        active_workspaces_total=active_workspaces_total,
        compliance_pct=compliance_pct,
        green_count=green,
        yellow_count=yellow,
        red_count=red,
        pending_reviews_total=pending_reviews_total,
        rejected_or_correction_total=rejected_or_correction_total,
        missing_required_total=missing_required_total,
        due_soon_total=due_soon_total,
        recent_submissions_total=min(recent_submissions_total, 200),
        last_activity_at=last_activity_at,
    )


# ---------------------------------------------------------------------------
# /vendors
# ---------------------------------------------------------------------------


@router.get("/vendors", response_model=ClientVendorListResponse)
def client_vendors(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    semaphore_level: Literal["green", "yellow", "red"] | None = None,
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ClientVendorListResponse:
    target_id = _resolve_client_id(db, current, requested=client_id)
    today = date.today()
    selected_year = today.year

    workspaces = _scoped_workspaces(db, target_id)
    vendor_ids = [w.vendor_id for w in workspaces]
    vendors = _vendors_by_id(db, vendor_ids)

    needle = (search or "").strip().lower()
    rows: list[ClientVendorRow] = []
    for ws in workspaces:
        if status_filter and ws.status != status_filter:
            continue
        vendor = vendors.get(ws.vendor_id)
        if vendor is None:
            continue
        if needle:
            haystack = " ".join(
                v.lower()
                for v in [vendor.name, vendor.rfc or "", ws.display_name or ""]
            )
            if needle not in haystack:
                continue
        summary = _vendor_compliance(db, ws, today=today, year=selected_year)
        if semaphore_level and summary["semaphore_level"] != semaphore_level:
            continue
        last_sub, last_review = _last_activity_timestamps(db, vendor.id)
        rows.append(
            ClientVendorRow(
                vendor_id=vendor.id,
                workspace_id=ws.id,
                vendor_name=vendor.name,
                vendor_rfc=vendor.rfc,
                persona_type=vendor.persona_type,
                workspace_status=ws.status,
                compliance_pct=summary["compliance_pct"],
                semaphore_level=summary["semaphore_level"],
                pending_reviews_count=summary["pending_reviews_count"],
                missing_required_count=summary["missing_required_count"],
                rejected_or_correction_count=summary["rejected_or_correction_count"],
                due_soon_count=summary["due_soon_count"],
                last_submission_at=last_sub,
                last_review_at=last_review,
            )
        )
        if len(rows) >= limit:
            break
    return ClientVendorListResponse(
        client_id=target_id, items=rows, total=len(rows)
    )


# ---------------------------------------------------------------------------
# /vendors/{vendor_id}
# ---------------------------------------------------------------------------


def _workspace_public(ws: ProviderWorkspace) -> dict:
    """Workspace serializer for client surfaces.

    NEVER exposes ``access_token`` — that's the provider's session
    credential. The Phase 1 guard depends on it staying hidden.
    """
    return {
        "id": ws.id,
        "client_id": ws.client_id,
        "vendor_id": ws.vendor_id,
        "contract_id": ws.contract_id,
        "persona_type": ws.persona_type,
        "display_name": ws.display_name,
        "filial_name": ws.filial_name,
        "status": ws.status,
        "onboarding_completed_at": (
            ws.onboarding_completed_at.isoformat()
            if ws.onboarding_completed_at
            else None
        ),
        "created_at": ws.created_at.isoformat() if ws.created_at else None,
    }


def _vendor_public(v: Vendor) -> dict:
    return {
        "id": v.id,
        "client_id": v.client_id,
        "name": v.name,
        "rfc": v.rfc,
        "contact_name": v.contact_name,
        "contact_email": v.contact_email,
        "repse_id": v.repse_id,
        "persona_type": v.persona_type,
        "status": v.status,
    }


def _recent_submissions_for_workspace(
    db: Session, workspace: ProviderWorkspace, *, limit: int
) -> list[dict]:
    rows = list(
        db.scalars(
            select(Submission)
            .where(Submission.vendor_id == workspace.vendor_id)
            .order_by(Submission.created_at.desc())
            .limit(limit)
        )
    )
    out: list[dict] = []
    for sub in rows:
        doc = db.scalar(
            select(Document).where(Document.submission_id == sub.id).limit(1)
        )
        replacement_id = db.scalar(
            select(Submission.id).where(
                Submission.supersedes_submission_id == sub.id
            )
        )
        out.append(
            {
                "submission_id": sub.id,
                "requirement_code": sub.requirement_code,
                "requirement_name": sub.requirement.name if sub.requirement else None,
                "period_key": sub.period_key,
                "status": sub.status,
                "filename": doc.original_filename if doc else None,
                "submitted_at": sub.created_at.isoformat(),
                "supersedes_submission_id": sub.supersedes_submission_id,
                "superseded_by_submission_id": replacement_id,
            }
        )
    return out


def _recent_reviewer_notes_for_workspace(
    db: Session, workspace: ProviderWorkspace, *, limit: int
) -> list[dict]:
    rows = list(
        db.scalars(
            select(ValidationEvent)
            .join(Submission, ValidationEvent.submission_id == Submission.id)
            .where(
                Submission.vendor_id == workspace.vendor_id,
                ValidationEvent.event_type == "reviewer_decision",
            )
            .order_by(ValidationEvent.created_at.desc())
            .limit(limit)
        )
    )
    out: list[dict] = []
    for ev in rows:
        out.append(
            {
                "submission_id": ev.submission_id,
                "result": ev.result,
                "message": ev.message,
                "occurred_at": ev.created_at.isoformat(),
            }
        )
    return out


@router.get("/vendors/{vendor_id}", response_model=ClientVendorDetail)
def client_vendor_detail(
    vendor_id: str,
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    year: int | None = None,
) -> ClientVendorDetail:
    target_id = _resolve_client_id(db, current, requested=client_id)
    vendor = db.get(Vendor, vendor_id)
    if vendor is None or vendor.client_id != target_id:
        # Same shape for not-found and cross-client to avoid a tenant probe.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Proveedor no encontrado para este cliente.",
        )
    workspace = db.scalar(
        select(ProviderWorkspace)
        .where(
            ProviderWorkspace.client_id == target_id,
            ProviderWorkspace.vendor_id == vendor_id,
        )
        .limit(1)
    )
    if workspace is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Este proveedor no tiene un workspace registrado.",
        )

    today = date.today()
    selected_year = year or today.year
    onboarding_slots = build_workspace_onboarding_slots(db, workspace)
    calendar_slots = build_workspace_calendar_slots(db, workspace, selected_year)
    counts = _empty_document_counts()
    for view in onboarding_slots + calendar_slots:
        _bucket_document_state(counts, view.state)

    return ClientVendorDetail(
        client_id=target_id,
        vendor_id=vendor.id,
        workspace_id=workspace.id,
        vendor=_vendor_public(vendor),
        workspace=_workspace_public(workspace),
        onboarding_summary=_compute_onboarding_summary(onboarding_slots, workspace),
        document_state_counts=counts,
        semaphore=_compute_semaphore(onboarding_slots, calendar_slots),
        suggested_actions=_compute_suggested_actions(
            onboarding_slots,
            calendar_slots,
            today,
            onboarding_completed=workspace.onboarding_completed_at is not None,
        ),
        attention_today=_compute_attention_today(
            onboarding_slots, calendar_slots, today
        ),
        upcoming_deadlines=_compute_upcoming_deadlines(calendar_slots, today),
        recent_submissions=_recent_submissions_for_workspace(
            db, workspace, limit=10
        ),
        recent_reviewer_notes=_recent_reviewer_notes_for_workspace(
            db, workspace, limit=10
        ),
    )


# ---------------------------------------------------------------------------
# /calendar
# ---------------------------------------------------------------------------


_MONTH_LABELS_ES = [
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]


@router.get("/calendar", response_model=ClientCalendarResponse)
def client_calendar(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    year: int = 2026,
) -> ClientCalendarResponse:
    """Aggregated client calendar.

    Each month carries the list of obligation items across every
    workspace, with their current state (replacement-aware). Same
    day-17 deadline convention as the provider calendar (SAT annual
    uses day 30 via the catalog override). The convention is
    documented in ``docs/PROVIDER_PORTAL_CANONICAL_READS.md`` and
    re-stated in ``docs/CLIENT_PORTAL_READ_MODEL.md``.
    """
    target_id = _resolve_client_id(db, current, requested=client_id)
    today = date.today()
    workspaces = _scoped_workspaces(db, target_id)
    vendor_lookup = _vendors_by_id(db, [w.vendor_id for w in workspaces])

    # Per workspace, walk the canonical recurring catalog so we have
    # ``due_month`` + ``period_label`` (the slot view alone doesn't
    # carry them). For each catalog item, look up the matching slot
    # view to read the current state.
    months: dict[int, list[ClientCalendarItem]] = defaultdict(list)
    aggregate_vendors_per_month: dict[int, set[str]] = defaultdict(set)
    for ws in workspaces:
        vendor = vendor_lookup.get(ws.vendor_id)
        if vendor is None:
            continue
        slot_views = build_workspace_calendar_slots(db, ws, year)
        view_by_key: dict[tuple[str | None, str | None], SlotView] = {
            (v.slot_key.requirement_code, v.slot_key.period_key): v for v in slot_views
        }
        catalog = recurring_for_year(year, ws.persona_type)  # type: ignore[arg-type]
        for req in catalog:
            view = view_by_key.get((req.code, req.period_key))
            item_status = (
                view.current_status if view and view.current_status else "pendiente"
            )
            deadline_iso = _calendar_deadline_iso(year, req.due_month, req.due_day)
            href = _calendar_upload_href(
                year=year, code=req.code, period_key=req.period_key
            )
            months[req.due_month].append(
                ClientCalendarItem(
                    vendor_id=vendor.id,
                    workspace_id=ws.id,
                    vendor_name=vendor.name,
                    requirement_code=req.code,
                    requirement_name=recurring_required_document(req),
                    institution=req.institution,
                    frequency=req.frequency,
                    period_key=req.period_key,
                    period_label=req.period_label,
                    status=item_status,
                    submission_id=view.current_submission_id if view else None,
                    deadline_iso=deadline_iso,
                    risk_level=None,
                    href=href,
                )
            )
            aggregate_vendors_per_month[req.due_month].add(vendor.id)

    response_months: list[ClientCalendarMonth] = []
    for month in range(1, 13):
        items = months.get(month, [])
        due_total = len(items)
        approved_total = sum(
            1
            for i in items
            if i.status
            in (
                DocumentStatus.APROBADO.value,
                DocumentStatus.EXCEPCION_LEGAL.value,
                DocumentStatus.NO_APLICA.value,
            )
        )
        pending_total = sum(
            1
            for i in items
            if i.status
            in (
                DocumentStatus.PENDIENTE_REVISION.value,
                DocumentStatus.PREVALIDADO.value,
                DocumentStatus.RECIBIDO.value,
                DocumentStatus.PENDIENTE.value,
                "pendiente",
            )
        )
        rejected_or_correction_total = sum(
            1
            for i in items
            if i.status in _REJECTED_OR_CORRECTION_STATUSES
        )
        missing_total = sum(
            1
            for i in items
            if i.status == DocumentStatus.PENDIENTE.value or i.status == "pendiente"
        )
        due_soon_total = sum(
            1
            for i in items
            if (_due_in_days_for_period(i.period_key, today) or 9999) <= 14
            and (_due_in_days_for_period(i.period_key, today) or -1) >= 0
            and i.status
            not in (
                DocumentStatus.APROBADO.value,
                DocumentStatus.EXCEPCION_LEGAL.value,
                DocumentStatus.NO_APLICA.value,
            )
        )
        response_months.append(
            ClientCalendarMonth(
                month=month,
                month_label=_MONTH_LABELS_ES[month - 1],
                vendors_total=len(aggregate_vendors_per_month.get(month, set())),
                due_total=due_total,
                approved_total=approved_total,
                pending_total=pending_total,
                rejected_or_correction_total=rejected_or_correction_total,
                missing_total=missing_total,
                due_soon_total=due_soon_total,
                items=items,
            )
        )
    return ClientCalendarResponse(
        metadata=catalog_metadata(),
        client_id=target_id,
        year=year,
        months=response_months,
    )


# ---------------------------------------------------------------------------
# /submissions
# ---------------------------------------------------------------------------


@router.get("/submissions", response_model=ClientSubmissionsResponse)
def client_submissions(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    vendor_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    requirement_code: str | None = None,
    period_key: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ClientSubmissionsResponse:
    target_id = _resolve_client_id(db, current, requested=client_id)
    if vendor_id:
        # Validate the vendor belongs to this client BEFORE leaking.
        vendor_check = db.get(Vendor, vendor_id)
        if vendor_check is None or vendor_check.client_id != target_id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="Proveedor no encontrado para este cliente.",
            )

    filters = [Submission.client_id == target_id]
    if vendor_id:
        filters.append(Submission.vendor_id == vendor_id)
    if status_filter:
        filters.append(Submission.status == status_filter)
    if requirement_code:
        filters.append(Submission.requirement_code == requirement_code)
    if period_key:
        filters.append(Submission.period_key == period_key)

    rows = list(
        db.scalars(
            select(Submission)
            .where(and_(*filters))
            .order_by(Submission.created_at.desc())
            .limit(limit)
        )
    )
    vendor_lookup = _vendors_by_id(db, [s.vendor_id for s in rows])

    items: list[ClientSubmissionItem] = []
    for sub in rows:
        vendor = vendor_lookup.get(sub.vendor_id)
        doc = db.scalar(
            select(Document).where(Document.submission_id == sub.id).limit(1)
        )
        replacement_id = db.scalar(
            select(Submission.id).where(
                Submission.supersedes_submission_id == sub.id
            )
        )
        latest_review = db.scalar(
            select(ValidationEvent)
            .where(
                ValidationEvent.submission_id == sub.id,
                ValidationEvent.event_type == "reviewer_decision",
            )
            .order_by(ValidationEvent.created_at.desc())
            .limit(1)
        )
        items.append(
            ClientSubmissionItem(
                submission_id=sub.id,
                vendor_id=sub.vendor_id,
                vendor_name=vendor.name if vendor else "",
                requirement_code=sub.requirement_code,
                requirement_name=(
                    sub.requirement.name if sub.requirement else None
                ),
                period_key=sub.period_key,
                status=sub.status,
                filename=doc.original_filename if doc else None,
                submitted_at=sub.created_at,
                reviewed_at=(latest_review.created_at if latest_review else None),
                reviewer_note=_latest_reviewer_note(db, sub.id),
                supersedes_submission_id=sub.supersedes_submission_id,
                superseded_by_submission_id=replacement_id,
            )
        )
    return ClientSubmissionsResponse(
        client_id=target_id, items=items, total=len(items)
    )


# ---------------------------------------------------------------------------
# /activity
# ---------------------------------------------------------------------------


# Reviewer decisions the client should see. We intentionally exclude
# the noisy intake/inspection events — the client doesn't need every
# upload_started / pdf_inspected step, just human decisions.
_CLIENT_VISIBLE_EVENTS: frozenset[str] = frozenset(
    {"reviewer_decision", "submission_replacement_linked", "submission_replaced"}
)


@router.get("/activity", response_model=ClientActivityResponse)
def client_activity(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ClientActivityResponse:
    """Sanitised, client-scoped activity feed.

    Composed from ``submissions.created_at`` (uploads) and
    ``validation_events.event_type='reviewer_decision'`` (human
    decisions). Internal-only audit metadata (e.g. admin operations
    rows) is excluded. The feed is read-only.
    """
    target_id = _resolve_client_id(db, current, requested=client_id)
    workspaces = _scoped_workspaces(db, target_id)
    vendor_ids = [w.vendor_id for w in workspaces]
    vendor_lookup = _vendors_by_id(db, vendor_ids)
    if not vendor_ids:
        return ClientActivityResponse(
            client_id=target_id, items=[], total=0, limit=limit
        )

    upload_rows = list(
        db.scalars(
            select(Submission)
            .where(Submission.client_id == target_id)
            .order_by(Submission.created_at.desc())
            .limit(limit)
        )
    )

    event_rows = list(
        db.scalars(
            select(ValidationEvent)
            .join(Submission, ValidationEvent.submission_id == Submission.id)
            .where(
                Submission.client_id == target_id,
                ValidationEvent.event_type.in_(_CLIENT_VISIBLE_EVENTS),
            )
            .order_by(ValidationEvent.created_at.desc())
            .limit(limit)
        )
    )

    feed: list[tuple[datetime, ClientActivityItem]] = []
    for sub in upload_rows:
        v = vendor_lookup.get(sub.vendor_id)
        feed.append(
            (
                _aware(sub.created_at),
                ClientActivityItem(
                    id=f"upload-{sub.id}",
                    occurred_at=sub.created_at,
                    actor_type="supplier",
                    action="submission.uploaded",
                    entity_type="submission",
                    entity_id=sub.id,
                    vendor_id=sub.vendor_id,
                    vendor_name=v.name if v else None,
                    summary=(
                        f"{v.name if v else 'Proveedor'} subió"
                        f" {sub.requirement_code or 'un documento'}"
                        f" ({sub.status})"
                    ),
                ),
            )
        )
    for ev in event_rows:
        sub = db.get(Submission, ev.submission_id)
        if sub is None or sub.client_id != target_id:
            continue
        v = vendor_lookup.get(sub.vendor_id) if sub else None
        if ev.event_type == "reviewer_decision":
            summary = (
                f"Decisión '{ev.result}' sobre {sub.requirement_code or 'un documento'}"
                f" de {v.name if v else 'Proveedor'}"
            )
            action = "reviewer.decision"
        elif ev.event_type == "submission_replacement_linked":
            summary = (
                f"{v.name if v else 'Proveedor'} reemplazó una entrega anterior"
                f" de {sub.requirement_code or 'un documento'}"
            )
            action = "submission.replacement_linked"
        else:
            summary = (
                f"La entrega previa de {sub.requirement_code or 'un documento'} de"
                f" {v.name if v else 'Proveedor'} fue reemplazada"
            )
            action = "submission.replaced"
        feed.append(
            (
                _aware(ev.created_at),
                ClientActivityItem(
                    id=f"event-{ev.id}",
                    occurred_at=ev.created_at,
                    actor_type=ev.actor_type,
                    action=action,
                    entity_type="submission",
                    entity_id=sub.id,
                    vendor_id=sub.vendor_id,
                    vendor_name=v.name if v else None,
                    summary=summary,
                ),
            )
        )
    feed.sort(key=lambda r: r[0], reverse=True)
    items = [item for _, item in feed[:limit]]
    return ClientActivityResponse(
        client_id=target_id, items=items, total=len(items), limit=limit
    )


def _aware(dt: datetime) -> datetime:
    """Ensure ordering works whether SQLite returns naive or aware dts."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
