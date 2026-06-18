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

import time
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Annotated, Literal

if TYPE_CHECKING:
    from app.services.audit_package import AuditPackageFilters

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from starlette.background import BackgroundTask

from app.api.v1.auth import CurrentUser, require_any_role
from app.api.v1.portal import (
    _ACTIONABLE_SLOT_STATES,
    _RESOLVED_SLOT_STATES,
    CURRENT_LEGAL_CONSENT_VERSION,
    DashboardAttentionItem,
    DashboardDocumentStateCounts,
    DashboardOnboardingSummary,
    DashboardSemaphore,
    DashboardSuggestedAction,
    DashboardUpcomingDeadline,
    _bucket_document_state,
    _calendar_deadline_iso,
    _compute_attention_today,
    _compute_onboarding_summary,
    _compute_semaphore,
    _compute_suggested_actions,
    _compute_upcoming_deadlines,
    _due_in_days_for_period,
    _empty_document_counts,
)
from app.constants.roles import MembershipRole
from app.constants.statuses import DocumentStatus
from app.core.compliance_catalog import (
    catalog_metadata,
    expediente_for_persona,
    normalize_persona_type,
    recurring_for_year,
)
from app.core.config import settings
from app.core.http_utils import content_disposition_header
from app.core.period_validation import MAX_YEAR, MIN_YEAR, validate_period_key
from app.core.rate_limit import enforce_ai_heavy_rate_limit, enforce_export_rate_limit
from app.core.text_search import normalize_for_search
from app.db.session import get_db
from app.models import (
    Client,
    ClientNotification,
    Document,
    Institution,
    Membership,
    Organization,
    ProviderWorkspace,
    Submission,
    User,
    ValidationEvent,
    Vendor,
)
from app.services.audit_log import add_audit_event
from app.services.calendar_aggregate import aggregate_client_calendar
from app.services.client_metadata import (
    client_master_file_path,
    display_export_path,
    filter_master_by_vendor,
    read_xlsx_preview,
)
from app.services.dashboard_compute import compute_renewal_actions
from app.services.evidence_slots import (
    SlotState,
    SlotView,
    build_workspace_calendar_slots,
    build_workspace_onboarding_slots,
    current_onboarding_submission_for_workspace,
    next_renewal_due_date,
    renewal_anchor_date,
    renewal_status,
)
from app.services.metadata_store import ensure_local_export
from app.services.search_service import SearchHit, search_submissions

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


def _next_renewal_for_workspace(
    db: Session,
    workspace: ProviderWorkspace,
    *,
    today: date,
    prefetched_submissions: list[Submission] | None = None,
) -> ClientVendorNextRenewal | None:
    """Phase 6D — most urgent renewal-bearing slot for the vendor row.

    Walks the renewal-bearing onboarding requirements (CSF / REPSE /
    registro patronal), picks the one with the smallest
    ``days_remaining`` whose ``renewal_status`` is ``due_soon`` or
    ``overdue``, and packages it as a small structured payload for
    the client vendor list pill. Returns ``None`` when nothing is in
    the 30-day window or overdue.
    """
    persona = normalize_persona_type(workspace.persona_type)
    best: ClientVendorNextRenewal | None = None

    for req in expediente_for_persona(persona):
        if req.renewal_frequency_days is None:
            continue
        sub = current_onboarding_submission_for_workspace(
            db,
            workspace=workspace,
            requirement_code=req.code,
            prefetched_submissions=prefetched_submissions,
        )
        anchor = renewal_anchor_date(sub)
        due = next_renewal_due_date(
            anchor=anchor, frequency_days=req.renewal_frequency_days
        )
        status = renewal_status(due, today)
        if status not in ("due_soon", "overdue") or due is None:
            continue
        days_remaining = (due - today).days
        candidate = ClientVendorNextRenewal(
            requirement_code=req.code,
            requirement_name=req.name,
            due_date=due,
            status=status,  # type: ignore[arg-type]
            days_remaining=days_remaining,
        )
        # Smallest days_remaining wins (overdue rows are most-negative).
        if best is None or candidate.days_remaining < best.days_remaining:
            best = candidate
    return best


def _vendor_compliance(
    db: Session,
    workspace: ProviderWorkspace,
    *,
    today: date,
    year: int,
    prefetched_submissions: list[Submission] | None = None,
    institutions_by_id: dict[str, str] | None = None,
) -> dict:
    """Compute compliance summary for one workspace.

    Returns the dict the ``/client/vendors`` list endpoint emits per
    row. Built from the canonical slot service so red/yellow/green
    semantics match the provider dashboard exactly.

    ``prefetched_submissions`` / ``institutions_by_id`` let a portfolio
    caller (``/overview``, ``/vendors``) supply this vendor's submissions
    and a shared institution map so the slot builders don't run a fresh
    full-table scan per vendor. ``None`` keeps the single-vendor path
    (``/vendors/{id}``) querying as before.
    """
    onboarding_slots = build_workspace_onboarding_slots(
        db, workspace, prefetched_submissions=prefetched_submissions
    )
    calendar_slots = build_workspace_calendar_slots(
        db,
        workspace,
        year,
        prefetched_submissions=prefetched_submissions,
        institutions_by_id=institutions_by_id,
    )
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


def _last_activity_timestamps_bulk(
    db: Session, vendor_ids: list[str]
) -> tuple[dict[str, datetime], dict[str, datetime]]:
    """Return ``(last_submission_at, last_review_at)`` maps keyed by
    vendor_id for many vendors at once.

    Two GROUP BY queries for the whole set instead of two scalar
    aggregates per vendor (the per-row version was a 2N N+1 on the
    vendors list). Vendors with no submissions / no reviewer decision are
    simply absent from the corresponding map, so callers use ``.get()``
    and fall back to None exactly as the per-vendor version did.
    """
    last_sub: dict[str, datetime] = {}
    last_review: dict[str, datetime] = {}
    if not vendor_ids:
        return last_sub, last_review
    for vid, ts in db.execute(
        select(Submission.vendor_id, func.max(Submission.created_at))
        .where(Submission.vendor_id.in_(vendor_ids))
        .group_by(Submission.vendor_id)
    ):
        last_sub[vid] = ts
    for vid, ts in db.execute(
        select(Submission.vendor_id, func.max(ValidationEvent.created_at))
        .join(ValidationEvent, ValidationEvent.submission_id == Submission.id)
        .where(
            Submission.vendor_id.in_(vendor_ids),
            ValidationEvent.event_type == "reviewer_decision",
        )
        .group_by(Submission.vendor_id)
    ):
        last_review[vid] = ts
    return last_sub, last_review


def _portfolio_slot_inputs(
    db: Session, client_id: str
) -> tuple[dict[str, list[Submission]], dict[str, str] | None]:
    """Pre-fetch everything the slot builders need for a whole client.

    Returns ``(submissions_by_vendor, institutions_by_id)``:

    * ``submissions_by_vendor`` — every submission for the client in one
      query, bucketed by ``vendor_id``. Feeding each vendor its bucket to
      :func:`_vendor_compliance` turns the old ``2 × N`` per-vendor full
      ``submissions`` scans (the ``/overview`` and ``/vendors`` hot path)
      into a single query, so query count is constant in the vendor
      count.
    * ``institutions_by_id`` — id→code map the recurring-**v2** resolver
      needs; ``None`` under the v1 catalog so we don't query for nothing.

    Both are behaviour-preserving: the slot builders produce identical
    ``SlotView`` output whether fed prefetched rows or querying
    themselves (see :func:`app.services.evidence_slots._workspace_submissions`).
    """
    submissions_by_vendor: dict[str, list[Submission]] = {}
    for sub in db.scalars(
        select(Submission).where(Submission.client_id == client_id)
    ):
        submissions_by_vendor.setdefault(sub.vendor_id, []).append(sub)
    institutions_by_id: dict[str, str] | None = None
    if settings.RECURRING_CATALOG_V2:
        institutions_by_id = _institutions_code_map(db)
    return submissions_by_vendor, institutions_by_id


# The Institution catalog is global and effectively static (the SAT / IMSS /
# INFONAVIT / STPS set), but the id→code map was re-SELECTed on every /overview,
# /vendors, /calendar and Wise call (perf audit P2-4). Cache it process-wide
# with a short TTL so a newly-added institution still appears within minutes
# without a restart. The cached value is a plain str→str dict (no ORM objects),
# safe to share read-only across requests and sessions.
_INSTITUTIONS_CACHE_TTL_SECONDS = 300.0
_institutions_code_map_cache: tuple[float, dict[str, str]] | None = None


def _institutions_code_map(db: Session) -> dict[str, str]:
    global _institutions_code_map_cache
    now = time.monotonic()
    cached = _institutions_code_map_cache
    if cached is not None and now - cached[0] < _INSTITUTIONS_CACHE_TTL_SECONDS:
        return cached[1]
    fresh = {inst.id: inst.code for inst in db.scalars(select(Institution))}
    _institutions_code_map_cache = (now, fresh)
    return fresh


def _submission_slot_key(sub: Submission) -> tuple[str, str, str, str] | None:
    if sub.requirement_code and sub.period_key:
        return ("canonical", sub.vendor_id, sub.requirement_code, sub.period_key)
    if sub.requirement_id and sub.period_id:
        return ("legacy", sub.vendor_id, sub.requirement_id, sub.period_id)
    return None


def _current_submissions_by_returned_row(
    db: Session, *, client_id: str, rows: list[Submission]
) -> dict[str, Submission]:
    """Batch-resolve each returned row's current obligation-slot submission."""
    vendor_ids = {row.vendor_id for row in rows}
    if not vendor_ids:
        return {}
    candidates_by_slot: dict[tuple[str, str, str, str], list[Submission]] = {}
    for sub in db.scalars(
        select(Submission).where(
            Submission.client_id == client_id,
            Submission.vendor_id.in_(vendor_ids),
        )
    ):
        key = _submission_slot_key(sub)
        if key is not None:
            candidates_by_slot.setdefault(key, []).append(sub)

    current_by_slot: dict[tuple[str, str, str, str], Submission] = {}
    for key, candidates in candidates_by_slot.items():
        superseded_ids = {
            c.supersedes_submission_id
            for c in candidates
            if c.supersedes_submission_id
        }
        leaves = [c for c in candidates if c.id not in superseded_ids]
        if not leaves:
            leaves = list(candidates)
        leaves.sort(key=lambda sub: sub.created_at, reverse=True)
        current_by_slot[key] = leaves[0]

    current_by_row: dict[str, Submission] = {}
    for row in rows:
        key = _submission_slot_key(row)
        if key is not None and key in current_by_slot:
            current_by_row[row.id] = current_by_slot[key]
    return current_by_row


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ClientMe(BaseModel):
    user_id: str
    email: str
    roles: list[str]
    visible_client_ids: list[str]
    default_client_id: str | None
    # Client-side legal-consent gate (v2+). The frontend blocks the
    # dashboard until ``legal_consent_version == current_legal_consent_version``.
    # ``current`` is owned by the backend so the client can't claim a
    # different document set than what was rendered.
    legal_consent_accepted_at: str | None = None
    legal_consent_version: str | None = None
    current_legal_consent_version: str = CURRENT_LEGAL_CONSENT_VERSION


class ClientLegalConsentResponse(BaseModel):
    user_id: str
    legal_consent_accepted_at: str
    legal_consent_version: str


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


class ClientVendorNextRenewal(BaseModel):
    """Phase 6D — the most urgent renewal-bearing slot for one vendor.

    ``None`` (omitted at the parent row level) when no renewal is in
    the 30-day window or overdue. ``status`` matches the
    :func:`app.services.evidence_slots.renewal_status` bucket so the
    UI can pick a pill color: yellow for ``due_soon``, red for
    ``overdue``. ``days_remaining`` is signed (negative = overdue).
    """

    requirement_code: str
    requirement_name: str
    due_date: date
    status: Literal["due_soon", "overdue"]
    days_remaining: int


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
    next_renewal: ClientVendorNextRenewal | None = None


class ClientVendorListResponse(BaseModel):
    client_id: str
    items: list[ClientVendorRow]
    total: int
    # ``total`` is the full filtered count; ``has_more`` says whether rows
    # remain past this page (perf audit P1-1 — enables real offset paging
    # instead of a silently truncated cap).
    has_more: bool = False


class ClientVendorContractDoc(BaseModel):
    """One contract-type document attached to a vendor expediente.

    Sources from `Submission` rows where ``requirement_code`` matches an
    onboarding contract requirement (ONB-CONT-001 / 002 / 003 — the
    signed services contract, its modifications, and service orders).
    Surfaced separately from ``recent_submissions`` so the vendor page
    can render a dedicated "contratos" card; the client_admin should
    not have to dig through the audit ZIP just to read the contract.
    """

    submission_id: str
    requirement_code: str
    requirement_name: str
    status: str
    filename: str | None
    submitted_at: datetime
    size_bytes: int | None


class ClientVendorDocumentActionItem(BaseModel):
    id: str
    kind: Literal[
        "missing",
        "rejected",
        "needs_correction",
        "possible_mismatch",
        "expired",
        "due_soon",
    ]
    requirement_code: str | None
    requirement_name: str | None
    institution: str | None
    period_key: str | None
    deadline_iso: str | None
    state: str
    due_in_days: int | None
    # The client monitors compliance; it does not upload the provider's
    # documents. So a client-facing action item carries no upload href — the
    # detail card links to the document itself (submission_id) when one exists.
    href: str | None = None
    submission_id: str | None


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
    contracts: list[ClientVendorContractDoc] = []
    document_action_items: list[ClientVendorDocumentActionItem] = []


class ClientSubmissionItem(BaseModel):
    submission_id: str
    vendor_id: str
    vendor_name: str
    requirement_code: str | None
    requirement_name: str | None
    # Phase 3 / Slice 3A — institution code (``sat``, ``imss``,
    # ``infonavit``, ``stps_repse``, ``interno_cliente``). Surfaced so
    # the client portal table can show an institution column AND so
    # the new ``?institution=`` filter on this endpoint stays
    # round-trippable (filter by value, render the same value back).
    institution: str | None
    period_key: str | None
    status: str
    current_slot_status: str | None
    is_current_for_slot: bool
    filename: str | None
    submitted_at: datetime
    reviewed_at: datetime | None
    reviewer_note: str | None
    supersedes_submission_id: str | None
    superseded_by_submission_id: str | None


class ClientSubmissionsResponse(BaseModel):
    client_id: str
    scope: Literal["submitted_documents"]
    scope_description: str
    items: list[ClientSubmissionItem]
    total: int
    has_more: bool = False


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
    has_more: bool = False


class ClientNotificationItem(BaseModel):
    id: str
    notification_type: str
    # Phase 4 / Slice 4A — semáforo discriminator. ``green`` (approved
    # / complete), ``yellow`` (pending / in review / due soon),
    # ``red`` (rejected / missing / expired), ``info`` (background
    # automation). The frontend swaps row border + Badge color
    # purely on this value, so a future severity-mapping change
    # ships without coordinated UI code.
    severity: Literal["green", "yellow", "red", "info"]
    # Phase 7 / Slice N9b — canonical category for chip filtering.
    # Derived from notification_type at insert time. ``other``
    # is the catch-all when the type doesn't match any known prefix.
    category: Literal[
        "renewal",
        "reporting",
        "verification",
        "account",
        "admin",
        "other",
    ]
    title: str
    body: str
    action_url: str | None
    vendor_id: str | None
    vendor_name: str | None
    submission_id: str | None
    payload: dict | None
    read_at: datetime | None
    created_at: datetime


class ClientNotificationsResponse(BaseModel):
    client_id: str
    items: list[ClientNotificationItem]
    total: int
    unread_count: int
    # Phase 7 / Slice N9b — subset of ``unread_count`` whose severity
    # is ``red`` or ``yellow``. Drives the sidebar bell badge so
    # info-tier rows never inflate it.
    unread_actionable_count: int
    limit: int
    has_more: bool = False


class ClientNotificationSummary(BaseModel):
    client_id: str
    unread_count: int
    unread_actionable_count: int


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
    client_id: str
    client_name: str
    master_available: bool
    master_path: str | None
    documents: list[ClientMetadataDocument]


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
    # Document guidance, mirrored from the provider calendar so the client
    # review surface can show "what the document is, and where to get it"
    # inline instead of forcing a click-through. ``requirement_name`` already
    # carries the document name; these add the supporting detail.
    anatomy: str
    where_to_obtain: str
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


class ClientCalendarProvider(BaseModel):
    """Per-provider rollup for the client calendar.

    Lets the calendar lead with risk (which providers are about to make
    the client non-compliant) instead of month aggregates. ``semaphore_level``
    and ``compliance_pct`` come from the same ``_compute_semaphore`` /
    ``_vendor_compliance`` path the ``/vendors`` list uses, so the calendar's
    provider colors are identical to that screen by construction.
    """

    vendor_id: str
    vendor_name: str
    semaphore_level: str
    compliance_pct: int
    overdue_count: int
    due_soon_count: int
    action_required_count: int
    next_deadline_iso: str | None


class ClientCalendarResponse(BaseModel):
    metadata: dict
    client_id: str
    year: int
    months: list[ClientCalendarMonth]
    # Sorted worst-first (red before yellow before green) so the agenda and
    # risk matrix can render the danger provider at the top without a second
    # sort on the client.
    providers: list[ClientCalendarProvider] = []


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


@router.get("/me", response_model=ClientMe)
def client_me(db: DbSession, current: ClientUser) -> ClientMe:
    """Identity + visible client ids + default + legal-consent state.
    The frontend stores this so it can pick the right scope on every
    subsequent call and gate the dashboard on consent.
    """
    visible = _visible_client_ids_for_user(db, current.user.id)
    user_row = db.get(User, current.user.id)
    accepted_at = (
        user_row.legal_consent_accepted_at.isoformat()
        if user_row and user_row.legal_consent_accepted_at
        else None
    )
    return ClientMe(
        user_id=current.user.id,
        email=current.user.email,
        roles=current.roles,
        visible_client_ids=visible,
        default_client_id=visible[0] if visible else None,
        legal_consent_accepted_at=accepted_at,
        legal_consent_version=user_row.legal_consent_version if user_row else None,
        current_legal_consent_version=CURRENT_LEGAL_CONSENT_VERSION,
    )


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP. Prefers the first ``X-Forwarded-For`` hop
    (Render/Vercel sit behind proxies) and falls back to the socket
    peer. Mirrors ``app.api.v1.portal._client_ip``."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        first = fwd.split(",", 1)[0].strip()
        if first:
            return first
    return request.client.host if request.client else None


@router.post(
    "/legal-consent",
    response_model=ClientLegalConsentResponse,
    status_code=status.HTTP_200_OK,
    summary="Record a client_admin's acceptance of the legal-consent gate",
)
def accept_client_legal_consent(
    request: Request,
    db: DbSession,
    current: ClientUser,
) -> ClientLegalConsentResponse:
    """Persist the client_admin's acceptance of the current legal set.

    Mirrors the provider endpoint (``app.api.v1.portal.accept_legal_consent``)
    but stores acceptance per-user on ``users`` so a client_admin who
    manages several client orgs accepts once per version. Body is empty
    by design: the backend owns ``CURRENT_LEGAL_CONSENT_VERSION``.

    Idempotent within a version. On a version bump the stored version
    differs, so this is treated as a fresh acceptance: the timestamp is
    rebumped and a new ``AuditLog`` row is written with the new version,
    capturing IP + User-Agent. The prior acceptance row stays untouched
    so the audit history shows the full sequence (v1 -> v2).
    """
    user_row = db.get(User, current.user.id)
    if user_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    if (
        user_row.legal_consent_accepted_at is not None
        and user_row.legal_consent_version == CURRENT_LEGAL_CONSENT_VERSION
    ):
        return ClientLegalConsentResponse(
            user_id=user_row.id,
            legal_consent_accepted_at=user_row.legal_consent_accepted_at.isoformat(),
            legal_consent_version=CURRENT_LEGAL_CONSENT_VERSION,
        )

    prior_accepted_at = (
        user_row.legal_consent_accepted_at.isoformat()
        if user_row.legal_consent_accepted_at
        else None
    )
    prior_version = user_row.legal_consent_version

    accepted_at = datetime.now(UTC)
    user_row.legal_consent_accepted_at = accepted_at
    user_row.legal_consent_version = CURRENT_LEGAL_CONSENT_VERSION

    add_audit_event(
        db,
        action="client.legal_consent_accepted",
        entity_type="user",
        entity_id=user_row.id,
        actor_type="client_admin",
        actor_id=user_row.id,
        before=(
            {
                "legal_consent_accepted_at": prior_accepted_at,
                "legal_consent_version": prior_version,
            }
            if prior_accepted_at is not None
            else None
        ),
        after={
            "legal_consent_accepted_at": accepted_at.isoformat(),
            "legal_consent_version": CURRENT_LEGAL_CONSENT_VERSION,
        },
        metadata={
            "version": CURRENT_LEGAL_CONSENT_VERSION,
            "previous_version": prior_version,
            "ip": _client_ip(request),
            "user_agent": request.headers.get("user-agent"),
        },
    )

    db.flush()
    db.commit()
    db.refresh(user_row)
    return ClientLegalConsentResponse(
        user_id=user_row.id,
        legal_consent_accepted_at=user_row.legal_consent_accepted_at.isoformat(),
        legal_consent_version=CURRENT_LEGAL_CONSENT_VERSION,
    )


# ---------------------------------------------------------------------------
# Junta 2026-05-23 — client onboarding profile
# ---------------------------------------------------------------------------


class ClientProfile(BaseModel):
    id: str
    name: str
    rfc: str | None
    email: str | None
    responsible_name: str | None
    industry: str | None
    fiscal_address: str | None
    phone: str | None
    notes: str | None
    onboarding_completed_at: str | None


class ClientProfileUpdate(BaseModel):
    """Fields a client_admin can edit on /client/onboarding.

    Identity columns (``name``/``rfc``/``email``) stay read-only —
    those are set by the admin preload on alta. The page renders
    them above the form as confirmation, not as editable inputs.
    """

    responsible_name: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=120)
    fiscal_address: str | None = None
    phone: str | None = Field(default=None, max_length=30)
    notes: str | None = None
    # Item 8 — T&C acceptance is part of the same first-login screen
    # as the fiscal-data form. The frontend gates onboarding
    # completion on both. The backend persists the acceptance via an
    # ``audit_log`` row (same forensic pattern used for provider-side
    # consent — see ``app.api.v1.portal``).
    terms_accepted: bool | None = None


def _client_profile_payload(row: Client) -> ClientProfile:
    return ClientProfile(
        id=row.id,
        name=row.name,
        rfc=row.rfc,
        email=row.email,
        responsible_name=row.responsible_name,
        industry=row.industry,
        fiscal_address=row.fiscal_address,
        phone=row.phone,
        notes=row.notes,
        onboarding_completed_at=(
            row.onboarding_completed_at.isoformat()
            if row.onboarding_completed_at
            else None
        ),
    )


@router.get("/profile", response_model=ClientProfile)
def client_profile(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
) -> ClientProfile:
    """Return the active client's profile.

    Preloaded fields (name / rfc / email) come from the admin alta;
    the editable fields drive the /client/onboarding page. The
    frontend reads ``onboarding_completed_at`` to decide whether to
    show the soft prompt on the dashboard.
    """
    target_id = _resolve_client_id(db, current, requested=client_id)
    row = db.get(Client, target_id)
    if row is None:  # pragma: no cover — defensive
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado."
        )
    return _client_profile_payload(row)


@router.patch("/profile", response_model=ClientProfile)
def update_client_profile(
    payload: ClientProfileUpdate,
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
) -> ClientProfile:
    """Update the editable onboarding fields on the active client.

    Sets ``onboarding_completed_at`` the first time the endpoint is
    hit so the dashboard banner clears. Subsequent edits do NOT
    reset the timestamp — the page can be revisited to refine the
    profile without re-triggering the "termina tu alta" prompt.

    Writes an ``client.profile_updated`` audit row with a
    before/after diff so a forensic reader can answer who changed
    what and when (the columns can carry operational signals like
    a new compliance officer, so the trail matters).
    """
    target_id = _resolve_client_id(db, current, requested=client_id)
    row = db.get(Client, target_id)
    if row is None:  # pragma: no cover — defensive
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado."
        )

    before = _client_profile_payload(row).model_dump()
    data = payload.model_dump(exclude_unset=True)
    if "responsible_name" in data:
        row.responsible_name = (data["responsible_name"] or "").strip() or None
    if "industry" in data:
        row.industry = (data["industry"] or "").strip() or None
    if "fiscal_address" in data:
        row.fiscal_address = (data["fiscal_address"] or "").strip() or None
    if "phone" in data:
        row.phone = (data["phone"] or "").strip() or None
    if "notes" in data:
        row.notes = (data["notes"] or "").strip() or None

    terms_accepted = bool(data.get("terms_accepted"))
    if terms_accepted:
        # Record the acceptance as its own audit row so a forensic
        # reader can answer "did this client_admin accept the T&C,
        # and when?" without scanning profile diffs. Idempotent — a
        # second tick on the same client just appends another row,
        # which is acceptable for the audit trail.
        add_audit_event(
            db,
            action="client.legal_consent_accepted",
            entity_type="client",
            entity_id=row.id,
            actor_type="client_admin",
            actor_id=current.user.id,
            metadata={
                "client_id": row.id,
                "user_id": current.user.id,
                # Shares the single source of truth with the provider
                # portal so the two paths can't drift; bump the
                # constant in portal.py when legal publishes new copy.
                "legal_consent_version": CURRENT_LEGAL_CONSENT_VERSION,
            },
        )

    just_completed = row.onboarding_completed_at is None
    if just_completed:
        row.onboarding_completed_at = datetime.now(UTC)

    db.flush()
    after = _client_profile_payload(row).model_dump()

    add_audit_event(
        db,
        action="client.profile_updated",
        entity_type="client",
        entity_id=row.id,
        actor_type="client_admin",
        actor_id=current.user.id,
        before=before,
        after=after,
        metadata={
            "just_completed_onboarding": just_completed,
            "terms_accepted": terms_accepted,
        },
    )
    db.commit()
    db.refresh(row)
    return _client_profile_payload(row)


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

# Worst-first ordering for the per-provider rollup. Red providers (something
# is overdue or rejected) sort above yellow (in motion) above green (al día).
_SEMAPHORE_SORT_ORDER = {"red": 0, "yellow": 1, "green": 2}


def _calendar_item_risk(status: str, deadline_iso: str, today: date) -> str:
    """Classify one calendar obligation's current severity.

    Returns a single ordered severity the client agenda bands by and the
    risk matrix colors by, so the frontend never re-derives urgency from raw
    dates. Most-severe wins:

    * ``on_track``        - resolved (aprobado / excepcion legal / no aplica)
    * ``overdue``         - past its deadline (or VENCIDO) and not resolved
    * ``action_required`` - rejected / needs clarification / possible mismatch
    * ``due_soon``        - due within 14 days and not resolved
    * ``in_review``       - submitted, with reviewer (recibido / prevalidado / en revision)
    * ``upcoming``        - not yet submitted, due in 15+ days

    The ``due_soon`` window (<=14 days, >=0) matches the existing
    ``due_soon_total`` convention so the calendar's two surfaces never
    disagree by a few days.
    """
    if status in (
        DocumentStatus.APROBADO.value,
        DocumentStatus.EXCEPCION_LEGAL.value,
        DocumentStatus.NO_APLICA.value,
    ):
        return "on_track"
    try:
        days_until: int | None = (date.fromisoformat(deadline_iso) - today).days
    except ValueError:
        days_until = None
    if status == DocumentStatus.VENCIDO.value or (
        days_until is not None and days_until < 0
    ):
        return "overdue"
    if status in _REJECTED_OR_CORRECTION_STATUSES:
        return "action_required"
    if days_until is not None and 0 <= days_until <= 14:
        return "due_soon"
    if status in (
        DocumentStatus.RECIBIDO.value,
        DocumentStatus.PENDIENTE_REVISION.value,
        DocumentStatus.PREVALIDADO.value,
    ):
        return "in_review"
    return "upcoming"


@router.get("/overview", response_model=ClientOverview)
def client_overview(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    year: Annotated[int | None, Query(ge=MIN_YEAR, le=MAX_YEAR)] = None,
) -> ClientOverview:
    target_id = _resolve_client_id(db, current, requested=client_id)
    target_client = db.get(Client, target_id)
    if target_client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")
    today = date.today()
    selected_year = year or today.year

    workspaces = _scoped_workspaces(db, target_id)
    subs_by_vendor, institutions_by_id = _portfolio_slot_inputs(db, target_id)
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
        summary = _vendor_compliance(
            db,
            ws,
            today=today,
            year=selected_year,
            prefetched_submissions=subs_by_vendor.get(ws.vendor_id, []),
            institutions_by_id=institutions_by_id,
        )
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
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClientVendorListResponse:
    target_id = _resolve_client_id(db, current, requested=client_id)
    today = date.today()
    selected_year = today.year

    workspaces = _scoped_workspaces(db, target_id)
    vendor_ids = [w.vendor_id for w in workspaces]
    vendors = _vendors_by_id(db, vendor_ids)
    last_sub_map, last_review_map = _last_activity_timestamps_bulk(db, vendor_ids)
    subs_by_vendor, institutions_by_id = _portfolio_slot_inputs(db, target_id)

    needle = normalize_for_search(search or "")

    # Apply the cheap filters first (status + name/RFC search). These don't
    # need the compliance projection, so when no semaphore filter is set we can
    # page *before* computing compliance and only project the requested page —
    # instead of computing every vendor then truncating (perf audit P1-1/P2-2).
    candidates: list[ProviderWorkspace] = []
    for ws in workspaces:
        if status_filter and ws.status != status_filter:
            continue
        vendor = vendors.get(ws.vendor_id)
        if vendor is None:
            continue
        if needle and not any(
            needle in normalize_for_search(field)
            for field in (vendor.name, vendor.rfc or "", ws.display_name or "")
        ):
            # Accent-insensitive, matched per-field (no cross-field joins).
            continue
        candidates.append(ws)

    def _compliance(ws: ProviderWorkspace) -> dict:
        return _vendor_compliance(
            db,
            ws,
            today=today,
            year=selected_year,
            prefetched_submissions=subs_by_vendor.get(ws.vendor_id, []),
            institutions_by_id=institutions_by_id,
        )

    def _build_row(ws: ProviderWorkspace, summary: dict) -> ClientVendorRow:
        vendor = vendors[ws.vendor_id]
        return ClientVendorRow(
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
            last_submission_at=last_sub_map.get(vendor.id),
            last_review_at=last_review_map.get(vendor.id),
            next_renewal=_next_renewal_for_workspace(
                db,
                ws,
                today=today,
                prefetched_submissions=subs_by_vendor.get(ws.vendor_id, []),
            ),
        )

    if semaphore_level:
        # The semaphore level is derived from compliance, so it can't be
        # filtered in SQL: compute every candidate to learn the true total,
        # then build full rows only for the matching page.
        matched = [
            (ws, summary)
            for ws in candidates
            if (summary := _compliance(ws))["semaphore_level"] == semaphore_level
        ]
        total = len(matched)
        page = [
            _build_row(ws, summary) for ws, summary in matched[offset : offset + limit]
        ]
    else:
        total = len(candidates)
        page = [
            _build_row(ws, _compliance(ws))
            for ws in candidates[offset : offset + limit]
        ]

    return ClientVendorListResponse(
        client_id=target_id,
        items=page,
        total=total,
        has_more=offset + len(page) < total,
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
            .options(selectinload(Submission.requirement))
            .limit(limit)
        )
    )
    sub_ids = [s.id for s in rows]
    # Batch the per-row document + reverse-lineage lookups into two IN
    # queries instead of 2 per row, and eager-load ``requirement`` above
    # so ``sub.requirement.name`` isn't a third lazy hit per row (audit
    # 2026-06-09, P1-A N+1).
    filename_by_sub: dict[str, str] = {}
    replacement_by_sub: dict[str, str] = {}
    if sub_ids:
        for doc in db.scalars(
            select(Document).where(Document.submission_id.in_(sub_ids))
        ):
            filename_by_sub.setdefault(doc.submission_id, doc.original_filename)
        for superseded_id, repl_id in db.execute(
            select(Submission.supersedes_submission_id, Submission.id).where(
                Submission.supersedes_submission_id.in_(sub_ids)
            )
        ):
            replacement_by_sub.setdefault(superseded_id, repl_id)
    out: list[dict] = []
    for sub in rows:
        out.append(
            {
                "submission_id": sub.id,
                "requirement_code": sub.requirement_code,
                "requirement_name": sub.requirement.name if sub.requirement else None,
                "period_key": sub.period_key,
                "status": sub.status,
                "filename": filename_by_sub.get(sub.id),
                "submitted_at": sub.created_at.isoformat(),
                "supersedes_submission_id": sub.supersedes_submission_id,
                "superseded_by_submission_id": replacement_by_sub.get(sub.id),
            }
        )
    return out


# Onboarding requirement codes for the signed services contract +
# its modifications + service orders. Sourced from
# ``app.core.compliance_catalog._ONBOARDING_MORAL`` (section
# "Contrato"). The lookup intentionally uses ``requirement_code`` so
# the helper does not break if the underlying ``Requirement`` row is
# renamed or re-seeded.
_CONTRACT_REQUIREMENT_CODES: tuple[str, ...] = (
    "ONB-CONT-001",
    "ONB-CONT-002",
    "ONB-CONT-003",
)


def _contracts_for_workspace(
    db: Session, workspace: ProviderWorkspace
) -> list[ClientVendorContractDoc]:
    """Every contract-type submission for ``workspace``, newest first.

    Includes superseded versions so the client_admin can see the full
    history of the contract relationship. Each row carries the
    submission's current status — the UI is free to badge replaced
    rows or hide them behind a "ver historial" affordance.
    """
    rows = list(
        db.scalars(
            select(Submission)
            .where(
                Submission.client_id == workspace.client_id,
                Submission.vendor_id == workspace.vendor_id,
                Submission.requirement_code.in_(_CONTRACT_REQUIREMENT_CODES),
            )
            .order_by(Submission.created_at.desc())
            .options(selectinload(Submission.requirement))
        )
    )
    # Batch the per-row document lookup into one IN query, and eager-load
    # ``requirement`` so the name access isn't lazy per row (audit
    # 2026-06-09, P1-A N+1).
    doc_by_sub: dict[str, Document] = {}
    sub_ids = [s.id for s in rows]
    if sub_ids:
        for d in db.scalars(
            select(Document).where(Document.submission_id.in_(sub_ids))
        ):
            doc_by_sub.setdefault(d.submission_id, d)
    out: list[ClientVendorContractDoc] = []
    for sub in rows:
        doc = doc_by_sub.get(sub.id)
        if doc is None:
            # Submission row exists without a document blob — typically
            # a slot reservation that never received an upload. Skip;
            # there is nothing for the client to view or download.
            continue
        out.append(
            ClientVendorContractDoc(
                submission_id=sub.id,
                requirement_code=sub.requirement_code or "",
                requirement_name=(
                    sub.requirement.name
                    if sub.requirement
                    else (sub.requirement_code or "Contrato")
                ),
                status=sub.status,
                filename=doc.original_filename,
                submitted_at=sub.created_at,
                size_bytes=doc.size_bytes,
            )
        )
    return out


_CLIENT_VENDOR_ACTIONABLE_STATES: dict[SlotState, str] = {
    SlotState.MISSING: "missing",
    SlotState.REJECTED: "rejected",
    SlotState.NEEDS_CORRECTION: "needs_correction",
    SlotState.POSSIBLE_MISMATCH: "possible_mismatch",
    SlotState.EXPIRED: "expired",
}


def _document_action_items_for_workspace(
    workspace: ProviderWorkspace,
    *,
    onboarding_slots: list[SlotView],
    calendar_slots: list[SlotView],
    year: int,
    today: date,
) -> list[ClientVendorDocumentActionItem]:
    """Client-facing flat list of provider documents that need follow-up."""
    items: list[ClientVendorDocumentActionItem] = []

    for view in onboarding_slots:
        if not view.required:
            continue
        kind = _CLIENT_VENDOR_ACTIONABLE_STATES.get(view.state)
        if kind is None:
            continue
        items.append(
            ClientVendorDocumentActionItem(
                id=f"doc-action-{view.requirement_code or 'onb'}-onb",
                kind=kind,  # type: ignore[arg-type]
                requirement_code=view.requirement_code,
                requirement_name=view.requirement_name,
                institution=view.institution,
                period_key=None,
                deadline_iso=None,
                state=view.state.value,
                due_in_days=None,
                submission_id=view.current_submission_id,
            )
        )

    view_by_key: dict[tuple[str | None, str | None], SlotView] = {
        (v.slot_key.requirement_code, v.slot_key.period_key): v
        for v in calendar_slots
    }
    catalog = recurring_for_year(year, normalize_persona_type(workspace.persona_type))
    for req in catalog:
        view = view_by_key.get((req.code, req.period_key))
        if view is None or not view.required:
            continue
        due_in = _due_in_days_for_period(view.period_key, today)
        kind = _CLIENT_VENDOR_ACTIONABLE_STATES.get(view.state)
        if kind is None and due_in is not None and 0 <= due_in <= 14:
            if view.state not in _RESOLVED_SLOT_STATES:
                kind = "due_soon"
        if kind is None:
            continue
        items.append(
            ClientVendorDocumentActionItem(
                id=f"doc-action-{view.requirement_code or req.code}-{view.period_key or 'period'}",
                kind=kind,  # type: ignore[arg-type]
                requirement_code=view.requirement_code,
                requirement_name=view.requirement_name,
                institution=view.institution,
                period_key=view.period_key,
                deadline_iso=_calendar_deadline_iso(year, req.due_month, req.due_day),
                state=view.state.value,
                due_in_days=due_in,
                submission_id=view.current_submission_id,
            )
        )

    urgency = {
        "rejected": 0,
        "needs_correction": 1,
        "possible_mismatch": 2,
        "expired": 3,
        "due_soon": 4,
        "missing": 5,
    }
    items.sort(
        key=lambda item: (
            urgency[item.kind],
            item.due_in_days is None,
            item.due_in_days if item.due_in_days is not None else 9999,
            item.institution or "",
            item.period_key or "",
            item.requirement_name or "",
        )
    )
    return items


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


def _resolve_client_id_for_vendor(
    db: Session,
    current: CurrentUser,
    *,
    vendor_id: str,
    requested: str | None,
) -> tuple[str, Vendor]:
    """Resolve the active client scope when the caller addresses a
    specific vendor.

    Item 5 follow-up — the admin shell links to
    ``/client/vendors/{vendor_id}`` without forcing the user to pick
    a ``?client_id=`` first. For an ``internal_admin`` who supplied
    no ``requested`` value we read the vendor row first and use its
    own ``client_id`` as the scope. ``client_admin`` users keep the
    historical behaviour (must be in their own portfolio; 404
    otherwise to avoid a cross-tenant probe).

    Returns ``(target_client_id, vendor_row)`` so the caller does
    not re-fetch the vendor.
    """
    is_internal_admin = MembershipRole.INTERNAL_ADMIN.value in current.roles
    if requested is None and is_internal_admin:
        vendor = db.get(Vendor, vendor_id)
        if vendor is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="Proveedor no encontrado para este cliente.",
            )
        return vendor.client_id, vendor
    target_id = _resolve_client_id(db, current, requested=requested)
    vendor = db.get(Vendor, vendor_id)
    if vendor is None or vendor.client_id != target_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Proveedor no encontrado para este cliente.",
        )
    return target_id, vendor


# ---------------------------------------------------------------------------
# Item 8 v2 — client adds a provider (auto-emails the invitation)
# ---------------------------------------------------------------------------


class ClientProviderCreate(BaseModel):
    """Body for ``POST /client/providers``. The client-side mirror of
    the admin ``POST /admin/users`` flow with role=provider, but the
    parent client is implicit (taken from the caller's tenant) and the
    plaintext temp password is NEVER returned in the response — the
    provider only sees it in the welcome email."""

    vendor_name: str = Field(min_length=2, max_length=255)
    vendor_rfc: str = Field(min_length=12, max_length=13)
    persona_type: Literal["moral", "fisica"]
    contact_name: str = Field(min_length=2, max_length=255)
    contact_email: EmailStr = Field(...)
    contact_phone: str | None = Field(default=None, max_length=30)


class ClientProviderCreateResponse(BaseModel):
    """Result of ``POST /client/providers``. Carries the email-delivery
    outcome so the UI can warn when SMTP skipped; no plaintext
    credentials (only the admin path returns those)."""

    vendor_id: str
    workspace_id: str
    user_id: str
    contact_email: str
    email_status: str
    email_error: str | None = None


@router.post(
    "/providers",
    response_model=ClientProviderCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Client adds a provider to their portfolio (auto-invitation)",
)
def client_add_provider(
    payload: ClientProviderCreate,
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
) -> ClientProviderCreateResponse:
    """Create a new provider under the caller's client and invite them.

    Same stack the admin ``POST /admin/users role=provider`` builds:
    User + Vendor + ProviderWorkspace(owner_user_id=user.id). Different
    auth surface (client_admin instead of internal_admin) and different
    response contract (no plaintext temp password — the client_admin
    sees only confirmation that the invitation was emailed).

    409 on a duplicate contact email; 409 on a duplicate (client, RFC).
    """
    import secrets as _secrets

    from app.services.auth import generate_temp_password, hash_password
    from app.services.email_delivery import (
        send_welcome_with_temp_password_email,
    )

    target_id = _resolve_client_id(db, current, requested=client_id)
    contact_email = payload.contact_email.strip().lower()
    rfc_value = payload.vendor_rfc.strip().upper()

    existing_user = db.scalar(select(User).where(User.email == contact_email))
    if existing_user is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con ese correo de contacto.",
        )

    temp_password = generate_temp_password()
    user = User(
        email=contact_email,
        password_hash=hash_password(temp_password),
        full_name=payload.contact_name.strip(),
        status="active",
        must_change_password=True,
    )
    db.add(user)
    db.flush()

    vendor = Vendor(
        client_id=target_id,
        name=payload.vendor_name.strip(),
        rfc=rfc_value,
        contact_name=payload.contact_name.strip(),
        contact_email=contact_email,
        contact_phone=(payload.contact_phone or "").strip() or None,
        persona_type=payload.persona_type,
        status="active",
    )
    db.add(vendor)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Ya existe un proveedor con ese RFC en tu cartera.",
        ) from exc

    workspace = ProviderWorkspace(
        client_id=target_id,
        vendor_id=vendor.id,
        persona_type=payload.persona_type,
        display_name=payload.vendor_name.strip(),
        access_token=_secrets.token_urlsafe(32),
        owner_user_id=user.id,
    )
    db.add(workspace)
    db.flush()

    from app.core.config import settings as _settings

    login_url = f"{_settings.FRONTEND_BASE_URL.rstrip('/')}/login"
    delivery = send_welcome_with_temp_password_email(
        to_email=contact_email,
        full_name=payload.contact_name.strip(),
        login_url=login_url,
        temp_password=temp_password,
        role="provider",
        organization_name=payload.vendor_name.strip(),
    )

    add_audit_event(
        db,
        action="client.provider_invited",
        entity_type="vendor",
        entity_id=vendor.id,
        actor_type="client_admin",
        actor_id=current.user.id,
        metadata={
            "client_id": target_id,
            "vendor_id": vendor.id,
            "workspace_id": workspace.id,
            "user_id": user.id,
            "user_email": contact_email,
            "email_delivery_status": delivery.status,
        },
    )

    # Phase 7 cutover (Slice C) — same companion-emit as
    # ``admin.provision_user``. Legacy welcome email already landed;
    # this emit fires the in-app row + SMS confirmation through the
    # unified fabric and never breaks the response on failure.
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
        logging.getLogger("checkwise.client").exception(
            "notif_emit_failed event=account.invitation_sent user=%s", user.id
        )

    db.commit()

    return ClientProviderCreateResponse(
        vendor_id=vendor.id,
        workspace_id=workspace.id,
        user_id=user.id,
        contact_email=contact_email,
        email_status=delivery.status,
        email_error=delivery.error,
    )


@router.get("/vendors/{vendor_id}", response_model=ClientVendorDetail)
def client_vendor_detail(
    vendor_id: str,
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    year: Annotated[int | None, Query(ge=MIN_YEAR, le=MAX_YEAR)] = None,
) -> ClientVendorDetail:
    target_id, vendor = _resolve_client_id_for_vendor(
        db, current, vendor_id=vendor_id, requested=client_id
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
            renewal_actions=compute_renewal_actions(db, workspace, today),
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
        contracts=_contracts_for_workspace(db, workspace),
        document_action_items=_document_action_items_for_workspace(
            workspace,
            onboarding_slots=onboarding_slots,
            calendar_slots=calendar_slots,
            year=selected_year,
            today=today,
        ),
    )


# ---------------------------------------------------------------------------
# Phase 5 / Slice 5C — client-scoped vendor expediente ZIP
# ---------------------------------------------------------------------------


@router.get(
    "/vendors/{vendor_id}/expediente.zip",
    summary="Stream a ZIP of every uploaded document for one vendor",
)
def client_vendor_expediente_zip(
    vendor_id: str,
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    period_key: str | None = None,
    institution: str | None = None,
) -> Response:
    """Stream a vendor's expediente as a ZIP, scoped to the client_admin's portfolio.

    Mirrors the provider-side endpoint
    (``/portal/workspaces/{id}/expediente.zip``) but enters through
    the client portal so a client_admin can pull a vendor's
    documents without minting a workspace session. Same backend
    service composes the archive; same caps; same filter shape.

    Authorization chain:
      1. ``_resolve_client_id`` → the active client scope (raises
         403/404 on mismatch, same as every other ``/client/*``).
      2. The requested vendor MUST belong to that client; otherwise
         404 (never confirms cross-tenant existence).
      3. The vendor MUST have a ``ProviderWorkspace``; otherwise
         404 (no workspace → no provider session ever created
         documents on this vendor).

    Audit: ``client.vendor_expediente_downloaded`` with metadata
    ``{scope, client_id, vendor_id, workspace_id, file_count,
    total_bytes, filters}``. Distinguishable from the
    provider-side ``provider.expediente_downloaded`` action so a
    forensic reader can answer "did the client_admin pull this, or
    did the provider?".
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

    target_id, vendor = _resolve_client_id_for_vendor(
        db, current, vendor_id=vendor_id, requested=client_id
    )
    # Heavy streaming export — throttle per user so it can't be used as a
    # resource-exhaustion lever (perf audit P2-8).
    enforce_export_rate_limit(
        current.user.id,
        per_minute=settings.EXPORT_RATE_LIMIT_PER_MINUTE,
        per_hour=settings.EXPORT_RATE_LIMIT_PER_HOUR,
    )

    workspace = db.scalar(
        select(ProviderWorkspace).where(
            ProviderWorkspace.client_id == target_id,
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
        action="client.vendor_expediente_downloaded",
        entity_type="provider_workspace",
        entity_id=workspace.id,
        actor_type="client_admin",
        actor_id=current.user.id,
        metadata={
            "scope": "client_vendor",
            "client_id": target_id,
            "vendor_id": vendor_id,
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


# ---------------------------------------------------------------------------
# Per-submission document stream (client portal)
# ---------------------------------------------------------------------------


@router.get(
    "/submissions/{submission_id}/document",
    summary="Stream the PDF stored for one submission (client_admin)",
)
def client_get_submission_document(
    submission_id: str,
    db: DbSession,
    current: ClientUser,
    download: bool = False,
    proxy: bool = False,
) -> Response:
    """Serve a submission's PDF inline (default) or as an attachment.

    Mirrors :func:`app.api.v1.reviewer.get_submission_document` but
    runs through the client tenant guard: the submission MUST belong
    to a client the caller can see. ``?download=1`` writes a
    ``client.document_downloaded`` audit row and forces an attachment
    disposition; the default inline mode is unaudited so an iframe
    preview does not flood the audit log.

    Used by the vendor expediente contract card (item 1) and any
    future per-document open/download action in the client portal.
    """
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Envío no encontrado.",
        )

    is_internal_admin = MembershipRole.INTERNAL_ADMIN.value in current.roles
    if not is_internal_admin:
        visible = _visible_client_ids_for_user(db, current.user.id)
        if submission.client_id not in visible:
            # Same 404 shape as cross-tenant vendor lookups — never
            # confirm whether a submission exists in a client the
            # caller cannot see.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Envío no encontrado.",
            )

    document = db.scalar(
        select(Document).where(Document.submission_id == submission.id).limit(1)
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento no encontrado para este envío.",
        )

    disposition_kind = "attachment" if download else "inline"
    disposition_header = content_disposition_header(
        disposition_kind, document.original_filename
    )

    if download:
        add_audit_event(
            db,
            action="client.document_downloaded",
            entity_type="submission",
            entity_id=submission.id,
            actor_type="client_admin",
            actor_id=current.user.id,
            metadata={
                "document_id": document.id,
                "filename": document.original_filename,
                "size_bytes": document.size_bytes,
                "requirement_code": submission.requirement_code,
                "period_key": submission.period_key,
                "client_id": submission.client_id,
                "vendor_id": submission.vendor_id,
            },
        )
        db.commit()

    from app.services.storage import get_storage_service

    storage = get_storage_service()
    presigned = storage.presigned_download_url(
        document.storage_key,
        content_disposition=disposition_header,
    )
    if presigned is not None and not proxy:
        from fastapi.responses import RedirectResponse

        return RedirectResponse(presigned, status_code=status.HTTP_302_FOUND)

    path = storage.open_for_read(document.storage_key)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento no disponible en almacenamiento.",
        )
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=document.original_filename,
        # FILE GAP-6 — sensitive evidence bytes: never cache.
        headers={
            "Content-Disposition": disposition_header,
            "Cache-Control": "no-store, private",
        },
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
    year: Annotated[int | None, Query(ge=MIN_YEAR, le=MAX_YEAR)] = None,
    vendor_ids: Annotated[list[str] | None, Query()] = None,
) -> ClientCalendarResponse:
    """Aggregated client calendar.

    Each month carries the list of obligation items across every
    workspace, with their current state (replacement-aware). Same
    day-17 deadline convention as the provider calendar (SAT annual
    uses day 30 via the catalog override). The convention is
    documented in ``docs/PROVIDER_PORTAL_CANONICAL_READS.md`` and
    re-stated in ``docs/CLIENT_PORTAL_READ_MODEL.md``.

    Item 3 — when ``vendor_ids`` is supplied, the response is narrowed
    to the obligations of those vendors only. Vendors not in the
    client's portfolio are silently dropped (no 403/404 enumeration),
    so an attacker probing for cross-tenant ids cannot tell the
    difference. An empty list or omitted param is treated as
    "all vendors" — the same shape the page used before the filter
    landed.
    """
    target_id = _resolve_client_id(db, current, requested=client_id)
    today = date.today()
    # Omitted year means "the year we are in", same as /overview. The
    # previous hardcoded 2026 default would have gone stale every
    # January.
    year = year or today.year
    # One placement+classification pass per client, shared with the admin
    # calendar grid (``aggregate_client_calendar``) so the two surfaces can
    # never disagree on which month a deadline lands in or its risk. The
    # per-item shape below is unchanged from the inline loop this replaced.
    agg = aggregate_client_calendar(
        db, client_id=target_id, year=year, today=today, vendor_ids=vendor_ids
    )

    months: dict[int, list[ClientCalendarItem]] = defaultdict(list)
    aggregate_vendors_per_month: dict[int, set[str]] = defaultdict(set)
    for ob in agg.obligations:
        months[ob.due_month].append(
            ClientCalendarItem(
                vendor_id=ob.vendor_id,
                workspace_id=ob.workspace_id,
                vendor_name=ob.vendor_name,
                requirement_code=ob.requirement_code,
                requirement_name=ob.requirement_name,
                institution=ob.institution,
                frequency=ob.frequency,
                period_key=ob.period_key,
                period_label=ob.period_label,
                status=ob.status,
                submission_id=ob.submission_id,
                deadline_iso=ob.deadline_iso,
                risk_level=ob.risk_level,
                anatomy=ob.anatomy,
                where_to_obtain=ob.where_to_obtain,
                href=ob.client_href,
            )
        )
        aggregate_vendors_per_month[ob.due_month].add(ob.vendor_id)

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
    # ``agg.providers`` is already sorted worst-first by the shared service.
    providers = [
        ClientCalendarProvider(
            vendor_id=p.vendor_id,
            vendor_name=p.vendor_name,
            semaphore_level=p.semaphore_level,
            compliance_pct=p.compliance_pct,
            overdue_count=p.overdue_count,
            due_soon_count=p.due_soon_count,
            action_required_count=p.action_required_count,
            next_deadline_iso=p.next_deadline_iso,
        )
        for p in agg.providers
    ]
    return ClientCalendarResponse(
        metadata=catalog_metadata(),
        client_id=target_id,
        year=year,
        months=response_months,
        providers=providers,
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
    # Phase 3 / Slice 3A — institution code filter (``sat``, ``imss``,
    # ``infonavit``, ``stps_repse``, ``interno_cliente``). Unknown
    # codes return an empty result set rather than 400 so a future
    # catalog addition can ship before this code is updated.
    institution: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClientSubmissionsResponse:
    # Stage 2.5 (BL-T7) — reject impossible periods at the wire. Same
    # rationale as the portal/admin variants: a stale or hostile
    # ``?period_key=1945-M01`` returns empty silently and looks like a
    # legitimate "no submissions" result. Validate up front.
    validate_period_key(period_key)
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
    if institution:
        # Resolve via the FK rather than relying on a relationship
        # property so the filter stays a single indexed comparison.
        # Unknown codes naturally yield zero rows (no Institution row
        # with that code → no submission with that institution_id).
        inst_id = db.scalar(
            select(Institution.id).where(Institution.code == institution)
        )
        if inst_id is None:
            # Force-empty result without flagging the input as invalid;
            # a typo / future catalog code stays a no-op rather than 400.
            filters.append(Submission.id == "__nonexistent__")
        else:
            filters.append(Submission.institution_id == inst_id)

    # True total for the filtered set so the client can page (perf audit P1-2),
    # rather than inferring it from a silently-capped page length.
    total_count = int(
        db.scalar(select(func.count()).select_from(Submission).where(and_(*filters)))
        or 0
    )
    rows = list(
        db.scalars(
            select(Submission)
            .where(and_(*filters))
            .order_by(Submission.created_at.desc())
            .offset(offset)
            .limit(limit)
            # Eager-load the requirement + institution the serializer reads
            # so they don't lazy-load one round-trip per row.
            .options(
                selectinload(Submission.requirement),
                selectinload(Submission.institution),
            )
        )
    )
    vendor_lookup = _vendors_by_id(db, [s.vendor_id for s in rows])

    # Batch the three remaining per-row lookups (document, replacement
    # pointer, latest reviewer decision) into one query each instead of
    # one-per-submission. The reviewer note is derived from the same
    # latest-review row, dropping a redundant fourth query per row.
    sub_ids = [s.id for s in rows]
    doc_by_sub: dict[str, Document] = {}
    replacement_by_sub: dict[str, str] = {}
    latest_review_by_sub: dict[str, ValidationEvent] = {}
    if sub_ids:
        for d in db.scalars(
            select(Document).where(Document.submission_id.in_(sub_ids))
        ):
            doc_by_sub.setdefault(d.submission_id, d)
        for rep_id, superseded in db.execute(
            select(Submission.id, Submission.supersedes_submission_id).where(
                Submission.supersedes_submission_id.in_(sub_ids)
            )
        ):
            if superseded is not None:
                replacement_by_sub[superseded] = rep_id
        # Newest reviewer_decision per submission: rows arrive newest-first,
        # setdefault keeps the first (latest) seen per submission_id.
        for ev in db.scalars(
            select(ValidationEvent)
            .where(
                ValidationEvent.submission_id.in_(sub_ids),
                ValidationEvent.event_type == "reviewer_decision",
            )
            .order_by(ValidationEvent.created_at.desc())
        ):
            latest_review_by_sub.setdefault(ev.submission_id, ev)

    current_by_row = _current_submissions_by_returned_row(
        db, client_id=target_id, rows=rows
    )
    items: list[ClientSubmissionItem] = []
    for sub in rows:
        vendor = vendor_lookup.get(sub.vendor_id)
        doc = doc_by_sub.get(sub.id)
        latest_review = latest_review_by_sub.get(sub.id)
        note = (
            ((latest_review.message or "").strip() or None)
            if latest_review
            else None
        )
        current_for_slot = current_by_row.get(sub.id)
        items.append(
            ClientSubmissionItem(
                submission_id=sub.id,
                vendor_id=sub.vendor_id,
                vendor_name=vendor.name if vendor else "",
                requirement_code=sub.requirement_code,
                requirement_name=(
                    sub.requirement.name if sub.requirement else None
                ),
                institution=(
                    sub.institution.code if sub.institution else None
                ),
                period_key=sub.period_key,
                status=sub.status,
                current_slot_status=(
                    current_for_slot.status if current_for_slot else None
                ),
                is_current_for_slot=(
                    current_for_slot is not None and current_for_slot.id == sub.id
                ),
                filename=doc.original_filename if doc else None,
                submitted_at=sub.created_at,
                reviewed_at=(latest_review.created_at if latest_review else None),
                reviewer_note=note,
                supersedes_submission_id=sub.supersedes_submission_id,
                superseded_by_submission_id=replacement_by_sub.get(sub.id),
            )
        )
    return ClientSubmissionsResponse(
        client_id=target_id,
        scope="submitted_documents",
        scope_description=(
            "Historial de documentos enviados; el calendario muestra obligaciones "
            "requeridas, incluidas las que todavía no tienen envío."
        ),
        items=items,
        total=total_count,
        has_more=offset + len(items) < total_count,
    )


# ---------------------------------------------------------------------------
# /activity
# ---------------------------------------------------------------------------


# Reviewer decisions the client should see. We intentionally exclude
# the noisy intake/inspection events — the client doesn't need every
# upload_started / pdf_inspected step, just human decisions.
_CLIENT_VISIBLE_EVENTS: frozenset[str] = frozenset(
    {
        "reviewer_decision",
        "submission_replacement_linked",
        "submission_replaced",
        "metadata_table_exported",
    }
)


@router.get("/activity", response_model=ClientActivityResponse)
def client_activity(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
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

    # The feed merges two sorted sources. To page it correctly we need at most
    # ``offset + limit`` rows from EACH source (any item in the global top
    # ``offset+limit`` is in its own source's top ``offset+limit``), then merge,
    # sort, and slice. Bounds the fetch instead of pulling a fixed page from
    # each and truncating (perf audit P1-3).
    window = offset + limit
    upload_filters = [Submission.client_id == target_id]
    event_join_filters = [
        Submission.client_id == target_id,
        ValidationEvent.event_type.in_(_CLIENT_VISIBLE_EVENTS),
    ]
    total_uploads = int(
        db.scalar(
            select(func.count()).select_from(Submission).where(*upload_filters)
        )
        or 0
    )
    total_events = int(
        db.scalar(
            select(func.count())
            .select_from(ValidationEvent)
            .join(Submission, ValidationEvent.submission_id == Submission.id)
            .where(*event_join_filters)
        )
        or 0
    )
    total = total_uploads + total_events

    upload_rows = list(
        db.scalars(
            select(Submission)
            .where(*upload_filters)
            .order_by(Submission.created_at.desc())
            .limit(window)
        )
    )

    event_rows = list(
        db.scalars(
            select(ValidationEvent)
            .join(Submission, ValidationEvent.submission_id == Submission.id)
            .where(*event_join_filters)
            .order_by(ValidationEvent.created_at.desc())
            .limit(window)
        )
    )

    # Reuse the submissions already materialised for the upload rows; only fetch
    # the event submissions we don't already hold (drops the redundant blanket
    # re-fetch the audit flagged).
    event_subs: dict[str, Submission] = {s.id: s for s in upload_rows}
    missing_sub_ids = [
        ev.submission_id
        for ev in event_rows
        if ev.submission_id and ev.submission_id not in event_subs
    ]
    if missing_sub_ids:
        for s in db.scalars(
            select(Submission).where(Submission.id.in_(missing_sub_ids))
        ):
            event_subs[s.id] = s

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
        sub = event_subs.get(ev.submission_id)
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
        elif ev.event_type == "metadata_table_exported":
            summary = (
                f"Metadata actualizada para {sub.requirement_code or 'un documento'}"
                f" de {v.name if v else 'Proveedor'}"
            )
            action = "metadata.ready" if ev.result == "completed" else "metadata.pending"
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
    items = [item for _, item in feed[offset : offset + limit]]
    return ClientActivityResponse(
        client_id=target_id,
        items=items,
        total=total,
        limit=limit,
        has_more=offset + len(items) < total,
    )


# ---------------------------------------------------------------------------
# /notifications
# ---------------------------------------------------------------------------


def _client_unread_counts(db: Session, client_id: str) -> tuple[int, int]:
    """Return ``(unread, unread_actionable)`` for a client in one query.

    ``unread_actionable`` is the red+yellow subset that drives the bell badge
    (N9b): info- and green-tier unread rows show in the feed but never inflate
    the badge. One FILTERed aggregate replaces the two separate COUNTs every
    notifications list/summary used to issue.
    """
    row = db.execute(
        select(
            func.count(ClientNotification.id),
            func.count(ClientNotification.id).filter(
                ClientNotification.severity.in_(("red", "yellow"))
            ),
        ).where(
            ClientNotification.client_id == client_id,
            ClientNotification.read_at.is_(None),
        )
    ).one()
    return int(row[0] or 0), int(row[1] or 0)


@router.get("/notifications/summary", response_model=ClientNotificationSummary)
def client_notification_summary(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
) -> ClientNotificationSummary:
    target_id = _resolve_client_id(db, current, requested=client_id)
    # Bell badge math (N9b): only red+yellow unread contribute to the actionable
    # subset; info/green unread rows show in the feed but never inflate the badge.
    unread_count, unread_actionable_count = _client_unread_counts(db, target_id)
    return ClientNotificationSummary(
        client_id=target_id,
        unread_count=unread_count,
        unread_actionable_count=unread_actionable_count,
    )


@router.get("/notifications", response_model=ClientNotificationsResponse)
def client_notifications(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClientNotificationsResponse:
    target_id = _resolve_client_id(db, current, requested=client_id)
    filters = [ClientNotification.client_id == target_id]
    if unread_only:
        filters.append(ClientNotification.read_at.is_(None))
    # True total for the filtered set so the inbox can page (perf audit P1-6).
    total_count = int(
        db.scalar(
            select(func.count()).select_from(ClientNotification).where(and_(*filters))
        )
        or 0
    )
    rows = list(
        db.scalars(
            select(ClientNotification)
            .where(and_(*filters))
            .order_by(ClientNotification.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    vendor_lookup = _vendors_by_id(db, [row.vendor_id for row in rows if row.vendor_id])
    unread_count, unread_actionable_count = _client_unread_counts(db, target_id)
    return ClientNotificationsResponse(
        client_id=target_id,
        items=[
            _notification_item(row, vendor_lookup.get(row.vendor_id or ""))
            for row in rows
        ],
        total=total_count,
        unread_count=unread_count,
        unread_actionable_count=unread_actionable_count,
        limit=limit,
        has_more=offset + len(rows) < total_count,
    )


@router.post("/notifications/{notification_id}/read", response_model=ClientNotificationItem)
def mark_client_notification_read(
    notification_id: str,
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
) -> ClientNotificationItem:
    target_id = _resolve_client_id(db, current, requested=client_id)
    row = db.get(ClientNotification, notification_id)
    if row is None or row.client_id != target_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Notificacion no encontrada.")
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        # Only audit the first transition unread→read. Idempotent
        # re-calls (notification already marked read) are intentionally
        # silent so a client UI that polls or replays does not flood
        # the audit log.
        add_audit_event(
            db,
            action="client.notification_marked_read",
            entity_type="client_notification",
            entity_id=row.id,
            actor_type="client_admin",
            actor_id=current.user.id,
            after={
                "client_id": target_id,
                "notification_type": row.notification_type,
                "vendor_id": row.vendor_id,
                "submission_id": row.submission_id,
                "read_at": row.read_at.isoformat(),
            },
        )
        db.commit()
        db.refresh(row)
    vendor = db.get(Vendor, row.vendor_id) if row.vendor_id else None
    return _notification_item(row, vendor)


@router.post("/notifications/read-all", response_model=ClientNotificationSummary)
def mark_all_client_notifications_read(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
) -> ClientNotificationSummary:
    target_id = _resolve_client_id(db, current, requested=client_id)
    now = datetime.now(UTC)
    # Capture the ids with a cheap id-only SELECT (no full-row ORM hydration),
    # then flip them all in a single UPDATE instead of loading every unread row
    # into memory and mutating it one by one (a client that never reads
    # notifications can accumulate thousands) — perf audit P2-7. The ids are
    # still recorded in the audit payload for forensic traceability.
    unread_ids = list(
        db.scalars(
            select(ClientNotification.id).where(
                ClientNotification.client_id == target_id,
                ClientNotification.read_at.is_(None),
            )
        )
    )
    if unread_ids:
        db.execute(
            update(ClientNotification)
            .where(ClientNotification.id.in_(unread_ids))
            .values(read_at=now)
            .execution_options(synchronize_session=False)
        )
        # Audit only when at least one notification was actually flipped.
        # A no-op call (everything already read) is intentionally silent
        # — see the per-notification handler above for the same rationale.
        add_audit_event(
            db,
            action="client.notifications_marked_all_read",
            entity_type="client",
            entity_id=target_id,
            actor_type="client_admin",
            actor_id=current.user.id,
            after={
                "marked_count": len(unread_ids),
                "notification_ids": unread_ids,
                "read_at": now.isoformat(),
            },
        )
    db.commit()
    return ClientNotificationSummary(
        client_id=target_id,
        unread_count=0,
        unread_actionable_count=0,
    )


def _notification_item(
    row: ClientNotification, vendor: Vendor | None
) -> ClientNotificationItem:
    # Defensive fallback for both severity and category — N9b's
    # migration backfilled existing rows, but a Literal mismatch
    # would 500 the endpoint, so we coerce any drift to a safe
    # sentinel.
    severity = (
        row.severity if row.severity in {"green", "yellow", "red", "info"} else "info"
    )
    category = (
        row.category
        if row.category
        in {"renewal", "reporting", "verification", "account", "admin", "other"}
        else "other"
    )
    return ClientNotificationItem(
        id=row.id,
        notification_type=row.notification_type,
        severity=severity,  # type: ignore[arg-type]
        category=category,  # type: ignore[arg-type]
        title=row.title,
        body=row.body,
        action_url=row.action_url,
        vendor_id=row.vendor_id,
        vendor_name=vendor.name if vendor else None,
        submission_id=row.submission_id,
        payload=row.payload,
        read_at=row.read_at,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# /metadata
# ---------------------------------------------------------------------------


@router.get("/metadata", response_model=ClientMetadataResponse)
def client_metadata(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
) -> ClientMetadataResponse:
    target_id = _resolve_client_id(db, current, requested=client_id)
    client = db.get(Client, target_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")
    path = ensure_local_export(client_master_file_path(client))
    documents: list[ClientMetadataDocument] = []
    if path.exists():
        sheets = read_xlsx_preview(path, max_rows_per_sheet=500, max_columns=20)
        metadata_sheet = next((sheet for sheet in sheets if sheet.name == "01 Metadata"), None)
        if metadata_sheet and metadata_sheet.rows:
            documents = _client_metadata_documents_from_sheet(metadata_sheet.rows)
    return ClientMetadataResponse(
        client_id=client.id,
        client_name=client.name,
        master_available=path.exists(),
        master_path=display_export_path(str(path)) if path.exists() else None,
        documents=documents,
    )


@router.get("/metadata/download")
def download_client_metadata(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
) -> FileResponse:
    target_id = _resolve_client_id(db, current, requested=client_id)
    client = db.get(Client, target_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")
    path = ensure_local_export(client_master_file_path(client))
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


@router.get("/vendors/{vendor_id}/metadata/download")
def download_client_vendor_metadata(
    vendor_id: str,
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    period_key: str | None = None,
) -> FileResponse:
    """Download the client metadata master filtered to ONE provider (CW-15).

    The all-providers master lives at ``/client/metadata/download``; this
    returns the same workbook with only the requested vendor's rows (optionally
    a single ``period_key``). Tenant-gated: the vendor must belong to the
    client. The filtered copy is a temp file cleaned up after the response.
    """
    target_id, vendor = _resolve_client_id_for_vendor(
        db, current, vendor_id=vendor_id, requested=client_id
    )
    client = db.get(Client, target_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")
    master = ensure_local_export(client_master_file_path(client))
    if not master.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Master de metadata no encontrado para este cliente.",
        )
    filtered = filter_master_by_vendor(
        master, vendor_name=vendor.name, period_key=period_key
    )
    if filtered is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Aún no hay metadata para este proveedor.",
        )
    add_audit_event(
        db,
        action="client.vendor_metadata_downloaded",
        entity_type="vendor",
        entity_id=vendor_id,
        actor_type="client_admin",
        actor_id=current.user.id,
        after={
            "client_id": target_id,
            "vendor_id": vendor_id,
            "period_key": period_key,
        },
    )
    db.commit()
    return FileResponse(
        filtered,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{client.name}_{vendor.name}_metadata.xlsx",
        background=BackgroundTask(filtered.unlink),
    )


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


def _aware(dt: datetime) -> datetime:
    """Ensure ordering works whether SQLite returns naive or aware dts."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


# ---------------------------------------------------------------------------
# Junta 2026-05-23 — audit package (cross-vendor ZIP for on-site auditors)
# ---------------------------------------------------------------------------


class AuditPackagePreviewResponse(BaseModel):
    file_count: int
    total_bytes: int
    vendor_count: int
    institution_breakdown: list[dict]
    vendor_breakdown: list[dict]
    requirement_breakdown: list[dict]
    over_file_cap: bool
    over_bytes_cap: bool
    file_cap: int
    bytes_cap: int


def _build_audit_filters(
    period_from: str | None,
    period_to: str | None,
    institutions: list[str] | None,
    requirement_codes: list[str] | None,
    statuses: list[str] | None,
    vendor_ids: list[str] | None,
    submission_ids: list[str] | None = None,
) -> AuditPackageFilters:
    from app.services.audit_package import AuditPackageFilters as _F

    return _F(
        period_from=period_from or None,
        period_to=period_to or None,
        institutions=tuple(institutions or ()),
        requirement_codes=tuple(requirement_codes or ()),
        statuses=tuple(statuses or ()),
        vendor_ids=tuple(vendor_ids or ()),
        submission_ids=tuple(submission_ids or ()),
    )


@router.get(
    "/audit-package/preview",
    response_model=AuditPackagePreviewResponse,
    summary="Pre-flight count + breakdowns for the audit ZIP",
)
def client_audit_package_preview(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    period_from: str | None = None,
    period_to: str | None = None,
    institutions: Annotated[list[str] | None, Query()] = None,
    requirement_codes: Annotated[list[str] | None, Query()] = None,
    statuses: Annotated[list[str] | None, Query()] = None,
    vendor_ids: Annotated[list[str] | None, Query()] = None,
) -> AuditPackagePreviewResponse:
    """Return file/byte counts plus breakdowns by vendor, institution
    and requirement for a given filter set.

    Powers the live counter on ``/client/auditoria``. Pure read — no
    audit row, no streaming. Same authorization chain as every other
    ``/client/*`` endpoint: ``_resolve_client_id`` enforces the
    tenant boundary.
    """
    from app.services.audit_package import (
        MAX_FILES,
        MAX_TOTAL_BYTES,
        summarize_audit_package,
    )

    target_id = _resolve_client_id(db, current, requested=client_id)
    client_row = db.get(Client, target_id)
    if client_row is None:  # pragma: no cover — defensive
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado."
        )

    filters = _build_audit_filters(
        period_from,
        period_to,
        institutions,
        requirement_codes,
        statuses,
        vendor_ids,
    )
    summary = summarize_audit_package(db, client_row, filters)

    vendor_breakdown = [
        {"vendor_id": vid, "file_count": count}
        for vid, count in sorted(
            summary.vendor_counts.items(), key=lambda kv: -kv[1]
        )
    ]
    institution_breakdown = [
        {"institution": code, "file_count": count}
        for code, count in sorted(
            summary.institution_counts.items(), key=lambda kv: -kv[1]
        )
    ]
    requirement_breakdown = [
        {"requirement_code": code, "file_count": count}
        for code, count in sorted(
            summary.requirement_counts.items(), key=lambda kv: -kv[1]
        )
    ]

    return AuditPackagePreviewResponse(
        file_count=summary.file_count,
        total_bytes=summary.total_bytes,
        vendor_count=len(summary.vendor_counts),
        institution_breakdown=institution_breakdown,
        vendor_breakdown=vendor_breakdown,
        requirement_breakdown=requirement_breakdown,
        over_file_cap=summary.file_count > MAX_FILES,
        over_bytes_cap=summary.total_bytes > MAX_TOTAL_BYTES,
        file_cap=MAX_FILES,
        bytes_cap=MAX_TOTAL_BYTES,
    )


class AuditPackageTreeNode(BaseModel):
    """One leaf in the tree picker — a single document the user can
    tick. Higher-level nodes (vendor, institution, period) are
    composed on the client from the flat list so the backend stays
    cheap and the UI controls aggregation/sort order."""

    submission_id: str
    vendor_id: str
    vendor_name: str
    institution_code: str
    institution_name: str
    period_key: str
    requirement_code: str | None
    requirement_name: str
    filename: str
    size_bytes: int
    status: str
    submitted_at_iso: str | None


class AuditPackageTreeResponse(BaseModel):
    items: list[AuditPackageTreeNode]
    file_count: int
    total_bytes: int
    file_cap: int
    bytes_cap: int


@router.get(
    "/audit-package/tree",
    response_model=AuditPackageTreeResponse,
    summary="Flat list of every document that matches the filter set",
)
def client_audit_package_tree(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    period_from: str | None = None,
    period_to: str | None = None,
    institutions: Annotated[list[str] | None, Query()] = None,
    requirement_codes: Annotated[list[str] | None, Query()] = None,
    statuses: Annotated[list[str] | None, Query()] = None,
    vendor_ids: Annotated[list[str] | None, Query()] = None,
) -> AuditPackageTreeResponse:
    """Item 2 — power the tree picker on ``/client/auditoria``.

    Returns the flat list of resolved documents (one per submission)
    matching the filter set. The frontend composes the Vendor →
    Institution → Period → Document hierarchy and renders the
    cascading checkboxes. The user's selected ``submission_id`` set
    is then posted to ``/audit-package.zip`` to materialise the ZIP.
    """
    from app.services.audit_package import (
        MAX_FILES,
        MAX_TOTAL_BYTES,
        build_entries,
    )

    target_id = _resolve_client_id(db, current, requested=client_id)
    client_row = db.get(Client, target_id)
    if client_row is None:  # pragma: no cover — defensive
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado."
        )

    filters = _build_audit_filters(
        period_from,
        period_to,
        institutions,
        requirement_codes,
        statuses,
        vendor_ids,
    )
    entries = build_entries(db, client_row, filters)

    items = [
        AuditPackageTreeNode(
            submission_id=e.submission_id,
            vendor_id=e.vendor_id,
            vendor_name=e.vendor_name,
            institution_code=e.institution_code,
            institution_name=e.institution_name,
            period_key=e.period_key,
            requirement_code=e.requirement_code,
            requirement_name=e.requirement_name,
            filename=e.filename,
            size_bytes=e.size_bytes,
            status=e.status,
            submitted_at_iso=e.submitted_at_iso,
        )
        for e in entries
        if e.submission_id  # defensive — legacy entries pre-field
    ]
    return AuditPackageTreeResponse(
        items=items,
        file_count=len(items),
        total_bytes=sum(i.size_bytes for i in items),
        file_cap=MAX_FILES,
        bytes_cap=MAX_TOTAL_BYTES,
    )


class AuditPackageZipBody(BaseModel):
    """POST body for the tree-picker download. Mirrors the GET query
    params plus the explicit ``submission_ids`` whitelist."""

    client_id: str | None = None
    period_from: str | None = None
    period_to: str | None = None
    institutions: list[str] | None = None
    requirement_codes: list[str] | None = None
    statuses: list[str] | None = None
    vendor_ids: list[str] | None = None
    submission_ids: list[str] | None = None
    skip_manifest: bool = False


@router.post(
    "/audit-package.zip",
    summary="Stream the audit ZIP with an explicit submission_ids whitelist",
)
def client_audit_package_zip_post(
    body: AuditPackageZipBody,
    db: DbSession,
    current: ClientUser,
) -> Response:
    """Item 2 — POST variant that accepts a body with
    ``submission_ids``. The GET form stays available for the legacy
    filter-only flow (and bookmarks); the POST form is what the tree
    picker posts when the user composes a selection that would blow
    past URL-length limits.
    """
    return _stream_audit_package_zip(
        db=db,
        current=current,
        client_id=body.client_id,
        period_from=body.period_from,
        period_to=body.period_to,
        institutions=body.institutions,
        requirement_codes=body.requirement_codes,
        statuses=body.statuses,
        vendor_ids=body.vendor_ids,
        submission_ids=body.submission_ids,
        skip_manifest=body.skip_manifest,
    )


@router.get(
    "/audit-package.zip",
    summary="Stream the audit-ready ZIP scoped to the active client",
)
def client_audit_package_zip(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    period_from: str | None = None,
    period_to: str | None = None,
    institutions: Annotated[list[str] | None, Query()] = None,
    requirement_codes: Annotated[list[str] | None, Query()] = None,
    statuses: Annotated[list[str] | None, Query()] = None,
    vendor_ids: Annotated[list[str] | None, Query()] = None,
    skip_manifest: bool = False,
) -> Response:
    """Stream a cross-vendor audit ZIP organized by
    ``<proveedor>/<institucion>/<periodo>/<archivo>`` with an
    ``INDICE.pdf`` cover at the root.

    Defaults to approved-only documents; the caller passes
    ``?statuses=...`` to override. Cap pre-flight returns 413 with
    a Spanish message guiding the user to narrow filters. Writes a
    ``client.audit_package_downloaded`` audit row before any bytes
    are yielded so the forensic trail records intent even if the
    download is aborted.

    ``skip_manifest=true`` skips the INDICE.pdf rendering. Useful
    for tests and for environments without Chromium installed
    (e.g. CI that wants to verify the ZIP contents without the
    Playwright dependency). The production path always renders the
    manifest.
    """
    return _stream_audit_package_zip(
        db=db,
        current=current,
        client_id=client_id,
        period_from=period_from,
        period_to=period_to,
        institutions=institutions,
        requirement_codes=requirement_codes,
        statuses=statuses,
        vendor_ids=vendor_ids,
        submission_ids=None,
        skip_manifest=skip_manifest,
    )


def _stream_audit_package_zip(
    *,
    db: Session,
    current: CurrentUser,
    client_id: str | None,
    period_from: str | None,
    period_to: str | None,
    institutions: list[str] | None,
    requirement_codes: list[str] | None,
    statuses: list[str] | None,
    vendor_ids: list[str] | None,
    submission_ids: list[str] | None,
    skip_manifest: bool,
) -> Response:
    """Shared streaming pipeline for the GET and POST audit-zip
    endpoints. The GET form keeps the legacy filter-only contract;
    the POST form additionally carries the tree-picker whitelist.
    """
    from datetime import datetime as _dt

    from fastapi.responses import StreamingResponse

    from app.services.audit_package import (
        MAX_FILES,
        MAX_TOTAL_BYTES,
        AuditPackageTooLargeError,
        build_entries,
        stream_audit_package,
    )

    target_id = _resolve_client_id(db, current, requested=client_id)
    client_row = db.get(Client, target_id)
    if client_row is None:  # pragma: no cover — defensive
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado."
        )
    # Heavy export (multi-vendor ZIP + Chromium INDICE.pdf) — throttle per user
    # so it can't be used as a resource-exhaustion lever (perf audit P2-8).
    enforce_export_rate_limit(
        current.user.id,
        per_minute=settings.EXPORT_RATE_LIMIT_PER_MINUTE,
        per_hour=settings.EXPORT_RATE_LIMIT_PER_HOUR,
    )

    filters = _build_audit_filters(
        period_from,
        period_to,
        institutions,
        requirement_codes,
        statuses,
        vendor_ids,
        submission_ids,
    )

    # Resolve entries once so the cap check and the manifest see the
    # same row set the streaming pass will write.
    entries = build_entries(db, client_row, filters)
    file_count = len(entries)
    total_bytes = sum(e.size_bytes for e in entries)
    if file_count > MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"El paquete tendría {file_count} documentos; el "
                f"límite por descarga es {MAX_FILES}. Filtra por "
                "periodo, institución o proveedor para reducir el "
                "alcance."
            ),
        )
    if total_bytes > MAX_TOTAL_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"El paquete pesaría {total_bytes // (1024 * 1024)} MB; "
                f"el límite por descarga es {MAX_TOTAL_BYTES // (1024 * 1024)} MB. "
                "Filtra por periodo, institución o proveedor para "
                "reducir el alcance."
            ),
        )

    # Render the cover. Skipped in tests / Chromium-less envs so the
    # ZIP composition path can be exercised in CI.
    manifest_pdf: bytes | None = None
    if not skip_manifest:
        try:
            from app.services.audit_package_manifest import render_audit_manifest

            manifest_pdf = render_audit_manifest(
                client=client_row,
                filters=filters,
                entries=entries,
            )
        except Exception as exc:
            # The INDICE.pdf is the auditor-facing table of contents —
            # shipping the ZIP without it used to happen SILENTLY here,
            # so the client handed over an incomplete package without
            # knowing (audit 2026-06-12). Fail loudly instead; callers
            # that explicitly don't want the cover already pass
            # ``skip_manifest`` and never enter this branch.
            import logging

            logging.getLogger("checkwise.audit_package").exception(
                "[audit_package] manifest rendering failed"
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "No pudimos generar el índice (INDICE.pdf) del paquete. "
                    "Vuelve a intentarlo en unos minutos; si el problema "
                    "persiste, contacta a soporte."
                ),
            ) from exc

    add_audit_event(
        db,
        action="client.audit_package_downloaded",
        entity_type="client",
        entity_id=client_row.id,
        actor_type="client_admin",
        actor_id=current.user.id,
        metadata={
            "scope": "client_audit_package",
            "client_id": client_row.id,
            "file_count": file_count,
            "total_bytes": total_bytes,
            "filters": filters.to_audit_dict(),
            "manifest_included": manifest_pdf is not None,
        },
    )
    db.commit()

    try:
        iterator = stream_audit_package(
            db, client_row, filters, manifest_pdf=manifest_pdf
        )
    except AuditPackageTooLargeError as exc:  # pragma: no cover — we
        # already pre-checked above, but keep the guard for race
        # safety.
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc

    safe_rfc = (client_row.rfc or "auditoria").lower()
    safe_rfc = "".join(ch for ch in safe_rfc if ch.isalnum() or ch in "-_") or "auditoria"
    today = _dt.now(UTC).strftime("%Y%m%d")
    filename = f"auditoria-{safe_rfc}-{today}.zip"

    return StreamingResponse(
        iterator,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ───────────────────────────────────────────────────────────────────
# Global search · client scope
# ───────────────────────────────────────────────────────────────────


class ClientSearchHitOut(BaseModel):
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


class ClientSearchResponse(BaseModel):
    query: str
    matched_by: str
    total: int
    items: list[ClientSearchHitOut]


@router.get("/search", response_model=ClientSearchResponse)
def client_search(
    q: Annotated[str, Query(min_length=1, max_length=120)],
    db: DbSession,
    current: ClientUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ClientSearchResponse:
    """Search submissions visible to this client_admin user.

    Scope: every client_id reachable through the user's
    ``client_admin`` memberships (or internal_admin memberships, which
    /client/me already promotes to a primary client). Empty
    membership set short-circuits to zero results — the endpoint
    never leaks data outside the caller's scope.
    """

    client_ids = _visible_client_ids_for_user(db, current.user.id)
    if not client_ids:
        return ClientSearchResponse(
            query=q, matched_by="folio", total=0, items=[]
        )
    hits: list[SearchHit] = search_submissions(
        db, q, client_ids=client_ids, limit=limit
    )
    return ClientSearchResponse(
        query=q,
        matched_by=(hits[0].matched_by if hits else "folio"),
        total=len(hits),
        items=[ClientSearchHitOut(**h.__dict__) for h in hits],
    )


# ---------------------------------------------------------------------------
# Wise copilot — cliente surface (Phase 5, 2026-06-02)
# ---------------------------------------------------------------------------
#
# Parallel to ``/api/v1/portal/workspaces/{id}/wise/{ask,events}``. The
# cliente Wise dock is mounted on every ``/client/*`` route via
# ClientShell and reasons about the buyer's PORTFOLIO of vendors
# (compliance distribution, vendors-at-risk, portfolio-wide
# upcoming deadlines) rather than a single vendor's onboarding state.
#
# Architecture differences vs. the portal Wise routes:
#
#   * Scope: ``client_id`` resolved via ``_resolve_client_id`` (query
#     param fallback + visible-clients guard) rather than a workspace
#     path param.
#   * Context: ``build_client_context`` assembles a portfolio digest;
#     ``ask_wise_for_client`` ships it to Claude Haiku with the
#     cliente-flavoured system rules + ``/client/*`` navigation CTAs.
#   * Events: the ``/wise/events`` route validates + logs but does
#     NOT persist to ``wise_events`` (that table's ``workspace_id``
#     is NOT NULL today). M1-follow-up will either add a nullable
#     ``client_id`` column or land a parallel ``client_wise_events``
#     table; choosing between those needs a separate decision pass.


_CLIENT_WISE_ALLOWED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "wise.first_render",
        "wise.opened",
        "wise.collapsed",
        "wise.suggestion_clicked",
        "wise.suggestion_dismissed",
        "wise.question_asked",
        # P2 (2026-06-13): thumbs up/down on a cliente Wise answer.
        "wise.feedback",
    }
)


class ClientWiseEventCreate(BaseModel):
    event_type: str = Field(..., max_length=80)
    payload: dict | None = None


class ClientWiseEventResponse(BaseModel):
    accepted: bool
    event_type: str


class ClientWiseAskCtaIn(BaseModel):
    id: str = Field(..., max_length=200)
    label: str = Field(..., max_length=120)
    href: str = Field(..., max_length=500)
    description: str = Field(default="", max_length=240)


class ClientWisePageContextIn(BaseModel):
    """Per-request page context shipped by the cliente Wise dock.

    Mirrors ``WisePageContextIn`` from portal.py but with cliente-
    flavoured field names. ``vendor_id`` and ``report_id`` capture the
    two most useful "what's on screen right now" hints for the cliente
    surface (a vendor detail page or a report-editor page).
    """

    route: str = Field(..., max_length=200)
    page_label: str = Field(..., max_length=80)
    vendor_id: str | None = Field(default=None, max_length=80)
    report_id: str | None = Field(default=None, max_length=80)
    period_key: str | None = Field(default=None, max_length=20)


class ClientWiseHistoryTurnIn(BaseModel):
    """P1 (2026-06-12) — one prior cliente dock turn, shipped so Wise can
    resolve follow-ups across the portfolio conversation."""

    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=2000)


class ClientWiseAskRequest(BaseModel):
    prompt: str = Field(..., max_length=500)
    ctas: list[ClientWiseAskCtaIn] = Field(default_factory=list, max_length=20)
    page_context: ClientWisePageContextIn | None = None
    history: list[ClientWiseHistoryTurnIn] = Field(
        default_factory=list, max_length=12
    )


class ClientWiseAskResponse(BaseModel):
    body: str
    cta_label: str | None = None
    cta_href: str | None = None
    source: Literal["llm", "fallback"]


@router.post(
    "/wise/events",
    response_model=ClientWiseEventResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Record a Wise cliente-side interaction event",
    description=(
        "Validates and persists a Wise dock interaction event on the "
        "cliente surface. As of migration 0041 the event is written to "
        "the shared ``wise_events`` table anchored on ``client_id`` "
        "(provider events anchor on ``workspace_id``); the route still "
        "returns 202 and never blocks the dock. A DB write failure is "
        "swallowed so analytics can never break the UI."
    ),
)
def record_client_wise_event(
    payload: ClientWiseEventCreate,
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
) -> ClientWiseEventResponse:
    if payload.event_type not in _CLIENT_WISE_ALLOWED_EVENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unknown event_type '{payload.event_type}'. "
                f"Allowed: {sorted(_CLIENT_WISE_ALLOWED_EVENT_TYPES)}"
            ),
        )
    target_id = _resolve_client_id(db, current, requested=client_id)

    # Persist to the shared ``wise_events`` table, anchored on
    # ``client_id`` (migration 0041 made ``workspace_id`` nullable and
    # added ``client_id`` for exactly this). Analytics must never break
    # the dock, so a DB error is logged and swallowed — the route still
    # returns 202.
    from app.models import WiseEvent

    log = __import__("logging").getLogger("checkwise.wise.client_events")
    try:
        event = WiseEvent(
            workspace_id=None,
            client_id=target_id,
            user_id=current.user.id,
            event_type=payload.event_type,
            payload=payload.payload,
        )
        db.add(event)
        db.commit()
    except Exception:  # noqa: BLE001 — analytics is best-effort
        db.rollback()
        log.warning(
            "wise.client_event.persist_failed",
            extra={
                "event_type": payload.event_type,
                "client_id": target_id,
                "user_id": current.user.id,
            },
        )
    return ClientWiseEventResponse(accepted=True, event_type=payload.event_type)


@router.post(
    "/wise/ask",
    response_model=ClientWiseAskResponse,
    summary="Ask Wise — cliente portfolio free-text reply",
    description=(
        "Routes a free-text prompt through Claude Haiku with the "
        "cliente's PORTFOLIO state digest and a list of allowed CTAs. "
        "Scope-guarded by the same ``_resolve_client_id`` helper every "
        "other ``/client/*`` route uses, so a caller can only ask "
        "about clients reachable through their memberships. Returns a "
        "structured reply (``body``, optional ``cta_label`` + "
        "``cta_href``). On missing API key or model error, returns a "
        "deterministic fallback rather than a 500 so the dock stays "
        "responsive."
    ),
)
def ask_client_wise_endpoint(
    payload: ClientWiseAskRequest,
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
) -> ClientWiseAskResponse:
    target_id = _resolve_client_id(db, current, requested=client_id)
    client_row = db.get(Client, target_id)
    if client_row is None:  # pragma: no cover — _resolve_client_id guards above
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado.",
        )

    # Share the AI-heavy rate-limit bucket with the report endpoints +
    # the portal Wise — both burn Anthropic tokens. Bucket key is the
    # caller's user id so a single client_admin with three clients
    # can't bypass the cap by fanning out across them.
    enforce_ai_heavy_rate_limit(
        current.user.id,
        per_minute=settings.AI_HEAVY_RATE_LIMIT_PER_MINUTE,
        per_hour=settings.AI_HEAVY_RATE_LIMIT_PER_HOUR,
    )

    from app.models import Report
    from app.services.wise.ai import WiseCta, WiseHistoryTurn, WisePageContext
    from app.services.wise.client_ai import ask_wise_for_client
    from app.services.wise.client_context import (
        build_client_context,
        build_vendor_focus,
        render_vendor_focus_block,
    )
    from app.services.wise.context import build_static_context

    portfolio_ctx = build_client_context(db, client_row)
    static_ctx = build_static_context()
    ctas = [
        WiseCta(id=c.id, label=c.label, href=c.href, description=c.description)
        for c in payload.ctas
    ]
    page_ctx: WisePageContext | None = None
    focus_block: str | None = None
    if payload.page_context is not None:
        # P0 grounding (2026-06-12) — resolve the on-screen vendor /
        # report into real names instead of the old piggyback that
        # rendered raw UUIDs under "Documento en contexto". A vendor
        # on screen additionally gets a full "Proveedor en pantalla"
        # block (named slots + states + due dates) so "¿qué le falta a
        # este proveedor?" earns a document-level answer. Both lookups
        # are tenant-guarded; a foreign id silently resolves to None.
        vendor_name: str | None = None
        if payload.page_context.vendor_id:
            focus_ctx = build_vendor_focus(
                db, client_row, payload.page_context.vendor_id
            )
            if focus_ctx is not None:
                vendor_name = focus_ctx.vendor_name
                focus_block = render_vendor_focus_block(focus_ctx)
        report_label: str | None = None
        if payload.page_context.report_id:
            report = db.get(Report, payload.page_context.report_id)
            if report is not None and report.client_id == target_id:
                report_label = f"{report.title} (estado: {report.status})"
        page_ctx = WisePageContext(
            route=payload.page_context.route,
            page_label=payload.page_context.page_label,
            period_key=payload.page_context.period_key,
            vendor_id=payload.page_context.vendor_id,
            vendor_name=vendor_name,
            report_id=payload.page_context.report_id,
            report_label=report_label,
        )

    history = [
        WiseHistoryTurn(role=turn.role, content=turn.content)
        for turn in payload.history
    ]
    result = ask_wise_for_client(
        prompt=payload.prompt,
        client_context=portfolio_ctx,
        static=static_ctx,
        ctas=ctas,
        page_context=page_ctx,
        focus_block=focus_block,
        history=history,
    )
    return ClientWiseAskResponse(
        body=result.body,
        cta_label=result.cta_label,
        cta_href=result.cta_href,
        source=result.source,
    )
