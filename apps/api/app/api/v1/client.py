"""Phase 8 — Client Portal (read-mostly surface).

Client-facing monitoring surface. ``client_admin`` users get
visibility into the vendors / workspaces / submissions that
belong to their client organisation; ``internal_admin`` is
allowed too for support and debugging.

Scope model:
    user -> memberships (role=client_admin)
              -> organization (kind="client", client_id=<X>)
              -> Client(id=<X>)

A ``client_admin`` user is locked to the union of clients
reachable through their memberships. An ``internal_admin`` user
may inspect any client by passing ``?client_id=<X>`` (no
implicit cross-tenant visibility for the default endpoint —
they must pick a client). Such cross-tenant ``internal_admin``
access is treated as break-glass support and is audit-logged
(``client.cross_tenant_access``) inside ``_resolve_client_id``.

The surface is read-mostly, but NOT read-only: it carries a
small, deliberately-scoped set of audited mutations — add a
provider (``POST /providers``), edit the company profile
(``PATCH /profile``), accept legal consent
(``POST /legal-consent``), mark notifications read, generate a
report from a preset, plus client seat management under
``/client/users``. Evidence downloads (expediente / audit
package / metadata) are likewise audit-logged.

This router reuses the pure dashboard-composition helpers from
``app.api.v1.portal``. They take ``SlotView`` lists and produce
the same shapes the provider dashboard renders, so the client
surface stays in lock-step with the provider experience without
duplicating slot logic.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Literal

if TYPE_CHECKING:
    from app.services.audit_package import AuditPackageFilters

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
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
from app.constants.plans import PLAN_LABELS_ES, Capability
from app.constants.roles import STAFF_ROLES, MembershipRole
from app.constants.statuses import ClientAcceptance, DocumentStatus, VendorStatus
from app.core.compliance_catalog import (
    catalog_metadata,
    expediente_for_persona,
    normalize_persona_type,
    recurring_for_year,
    recurring_for_year_v2,
    recurring_required_document,
)
from app.core.config import settings
from app.core.http_utils import content_disposition_header
from app.core.period_validation import MAX_YEAR, MIN_YEAR, validate_period_key
from app.core.rate_limit import enforce_ai_heavy_rate_limit, enforce_export_rate_limit
from app.core.text_search import normalize_for_search
from app.core.time import today_mx
from app.db.session import get_db
from app.models import (
    AuditLog,
    Client,
    ClientNotification,
    Contract,
    Document,
    DocumentInspection,
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
from app.services.calendar_risk import (
    REJECTED_OR_CORRECTION_STATUSES as _REJECTED_OR_CORRECTION_STATUSES,
)
from app.services.calendar_risk import (
    calendar_item_risk as _calendar_item_risk,
)
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
from app.services.reports.insights import (
    approval_trend_points,
    approval_trend_points_by_vendor,
)
from app.services.search_service import SearchHit, search_submissions
from app.services.submission_workflow import apply_client_decision
from app.services.subscription import (
    active_provider_count,
    assert_capability,
    assert_provider_capacity,
    capabilities_for_org,
    org_for_client,
    plan_for_org,
    provider_limit_for_org,
)

router = APIRouter(prefix="/client", tags=["client"])
DbSession = Annotated[Session, Depends(get_db)]

# Read / export gate (Phase 4). Every client seat — Approver
# (``client_admin``) or Viewer (``client_viewer``) — plus internal support
# (LegalShelf staff debugging a client view without a fake account) may READ
# and EXPORT. Viewers are oversight users: they see everything and can pull
# evidence, but the dependency below blocks them from the portfolio-mutating
# routes (which use ``ClientApprover``). Reviewer / provider sessions get 403.
ClientUser = Annotated[
    CurrentUser,
    Depends(
        require_any_role(
            MembershipRole.CLIENT_ADMIN,
            MembershipRole.CLIENT_VIEWER,
            # CheckWise staff (review team + superadmin) read cross-tenant
            # for oversight / break-glass support.
            MembershipRole.PLATFORM_ADMIN,
            MembershipRole.OPERATIONS_ADMIN,
        )
    ),
]

# Write gate (the "Approver" tier). Portfolio-changing routes (add /
# archive providers, edit the company profile) require an Approver; a
# ``client_viewer`` is 403'd here at the dependency layer, so the
# restriction is explicit and visible in the route-policy manifest.
# CheckWise staff may also mutate cross-tenant for support.
ClientApprover = Annotated[
    CurrentUser,
    Depends(
        require_any_role(
            MembershipRole.CLIENT_ADMIN,
            MembershipRole.PLATFORM_ADMIN,
            MembershipRole.OPERATIONS_ADMIN,
        )
    ),
]


# ---------------------------------------------------------------------------
# Scope resolution
# ---------------------------------------------------------------------------


def _visible_client_ids_for_user(db: Session, user_id: str) -> list[str]:
    """Return the client ids reachable through this user's client seats.

    Walks ``memberships -> organization -> client`` over BOTH client
    seat tiers — ``client_admin`` (Approver) and ``client_viewer``
    (Phase 4) — so a Viewer can resolve and read their own client.
    Filters out inactive memberships and orgs without a ``client_id``
    link (e.g. ``kind='internal'`` orgs). Order is deterministic so the
    "default" pick is stable across requests.
    """
    rows = list(
        db.scalars(
            select(Organization.client_id)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(
                Membership.user_id == user_id,
                Membership.role.in_(
                    (
                        MembershipRole.CLIENT_ADMIN.value,
                        MembershipRole.CLIENT_VIEWER.value,
                    )
                ),
                Membership.status == "active",
                Organization.client_id.is_not(None),
            )
            .distinct()
        )
    )
    return [cid for cid in rows if cid]


# Break-glass: collapse a support session of many cross-tenant reads to
# one forensic access row per (admin, client) inside this window, rather
# than flooding the audit log with a row per API call.
_CROSS_TENANT_AUDIT_WINDOW = timedelta(minutes=30)


def _audit_cross_tenant_access(db: Session, current: CurrentUser, client_id: str) -> None:
    """Record that an ``internal_admin`` reached a client tenant they do
    NOT belong to, via the client portal (break-glass support access).

    Closes the "which staff member viewed which client, and when" gap:
    before this, an internal admin browsing a client's portal left no
    trail because the reads were unaudited. Deduplicated to one row per
    (actor, client) per ``_CROSS_TENANT_AUDIT_WINDOW``. Committed here
    because most callers are read endpoints whose session is otherwise
    never committed (``get_db`` only closes).
    """
    window_start = datetime.now(UTC) - _CROSS_TENANT_AUDIT_WINDOW
    already_logged = db.execute(
        select(AuditLog.id)
        .where(
            AuditLog.actor_id == current.user.id,
            AuditLog.action == "client.cross_tenant_access",
            AuditLog.entity_id == client_id,
            AuditLog.created_at >= window_start,
        )
        .limit(1)
    ).first()
    if already_logged is not None:
        return
    add_audit_event(
        db,
        action="client.cross_tenant_access",
        entity_type="client",
        entity_id=client_id,
        actor_type=(
            MembershipRole.OPERATIONS_ADMIN.value
            if MembershipRole.OPERATIONS_ADMIN.value in current.roles
            else MembershipRole.PLATFORM_ADMIN.value
        ),
        actor_id=current.user.id,
        metadata={
            "admin_email": current.user.email,
            "via": "client_portal_break_glass",
            "dedup_window_minutes": int(
                _CROSS_TENANT_AUDIT_WINDOW.total_seconds() // 60
            ),
        },
    )
    db.commit()


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
        404 if ``requested`` is not resolvable for this caller. For a
            non-internal_admin this is a UNIFORM 404 whether the row is
            missing OR lives in another tenant — returning 403 only when the
            row exists elsewhere would be a cross-tenant existence oracle
            (mirrors ``_resolve_client_id_for_vendor`` /
            ``client_get_submission_document``). Only internal_admin, who may
            address any client, gets the distinct missing-row 404.
        400 if no client can be resolved.
    """
    visible = _visible_client_ids_for_user(db, current.user.id)
    is_internal_admin = bool(STAFF_ROLES & set(current.roles))

    if requested:
        if is_internal_admin:
            target = db.get(Client, requested)
            if target is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado."
                )
            if requested not in visible:
                # Internal admin reaching a tenant they don't belong to:
                # break-glass support access — leave a forensic trail.
                _audit_cross_tenant_access(db, current, requested)
            return requested
        if requested not in visible:
            # Same 404 shape whether the client row is missing or belongs to
            # another tenant — never confirm a client's existence to a caller
            # who cannot see it.
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado."
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


def _holds_live_approver_seat(
    db: Session, current: CurrentUser, client_id: str
) -> bool:
    """Whether the caller may currently WRITE / decide for this client.

    The ``ClientApprover`` dependency authorizes from the JWT's role claims,
    which stay stale for up to a token lifetime (24h) after a demotion — so a
    just-demoted Approver could keep mutating the portfolio or recording
    acceptance decisions until their token expires. This re-checks the LIVE
    membership: CheckWise staff bypass (they reach client tenants via audited
    break-glass), otherwise the caller must STILL hold an active
    ``client_admin`` (Approver) seat in this client's organization.
    """
    if bool(STAFF_ROLES & set(current.roles)):
        return True
    org = org_for_client(db, client_id)
    seat = db.scalar(
        select(Membership.id).where(
            Membership.organization_id == org.id,
            Membership.user_id == current.user.id,
            Membership.role == MembershipRole.CLIENT_ADMIN.value,
            Membership.status == "active",
        )
    )
    return seat is not None


def _assert_live_client_approver(
    db: Session, current: CurrentUser, client_id: str
) -> None:
    """Raise 403 unless the caller holds a live Approver seat (or is staff).
    Call AFTER the tenant id is resolved, on every portfolio-mutating and
    acceptance-decision route, to close the stale-JWT demotion window."""
    if not _holds_live_approver_seat(db, current, client_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=(
                "Tu acceso de Aprobador cambió. Vuelve a iniciar sesión para "
                "continuar."
            ),
        )


def _scoped_workspaces(
    db: Session, client_id: str, *, active_only: bool = False
) -> list[ProviderWorkspace]:
    """Workspaces (providers) under a client.

    ``active_only`` drops soft-archived providers (``status='inactive'``,
    set by ``_set_provider_archival``). Active-compliance surfaces — the
    dashboard pool and the calendar — pass it so an archived provider
    truly leaves the live counts, matching what the UI promises. The
    vendor *list* keeps the default (all) so archived rows stay visible
    and restorable.
    """
    stmt = (
        select(ProviderWorkspace)
        .where(ProviderWorkspace.client_id == client_id)
        .order_by(ProviderWorkspace.created_at.desc())
    )
    if active_only:
        stmt = stmt.where(ProviderWorkspace.status == "active")
    return list(db.scalars(stmt))


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
    overdue = 0
    for s in calendar_slots:
        if not s.required:
            continue
        if s.state in _RESOLVED_SLOT_STATES:
            continue
        due_in = _due_in_days_for_period(s.period_key, today, deadline_iso=s.deadline_iso)
        if due_in is None:
            continue
        if due_in < 0:
            # Past its deadline and still unresolved = a lapsed obligation,
            # the highest-liability state. Tracked separately from due_soon
            # so the dashboard can surface "Vencidos" distinctly.
            overdue += 1
        elif due_in <= 14:
            due_soon += 1
    return {
        "compliance_pct": semaphore.compliance_pct,
        "semaphore_level": semaphore.level,
        "counts": counts.model_dump(),
        "missing_required_count": missing_required,
        "rejected_or_correction_count": rejected_or_correction,
        "pending_reviews_count": pending_reviews,
        "due_soon_count": due_soon,
        "overdue_count": overdue,
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


class ClientRiskVendor(BaseModel):
    """One provider on the dashboard's "Requieren tu atención" worklist.

    ``top_reason`` is a short Spanish phrase naming the dominant problem
    (vencidos > por corregir > faltantes > en revisión) so the exec sees
    *why* a provider is flagged without leaving the dashboard.
    """

    vendor_id: str
    vendor_name: str
    semaphore_level: Literal["green", "yellow", "red"]
    compliance_pct: int
    overdue_count: int
    missing_required_count: int
    rejected_or_correction_count: int
    top_reason: str
    # Phase 2 — per-vendor month-over-month approval-rate momentum (points;
    # most recent active month − the one before). None until two active
    # months exist. Lets the worklist distinguish "bad but improving" from
    # "sliding into red". Populated only for the worst-first top slice so the
    # overview stays O(1) extra queries in the vendor count.
    momentum_delta: int | None = None


class ClientExposure(BaseModel):
    """The single highest legal/tax-liability obligation across the portfolio.

    Answers the executive's first question — "what's my biggest problem right
    now?" — with one named provider + obligation, scored by severity ×
    institution weight (SAT/IMSS/STPS) × contract materiality (headcount,
    expiry) × how long it's been overdue. ``None`` when nothing is overdue or
    needs correction, so the card simply hides.
    """

    vendor_id: str
    vendor_name: str
    requirement_name: str
    institution: str
    period_label: str | None = None
    deadline_iso: str | None = None
    days_overdue: int = 0
    # "Opinión de Cumplimiento (SAT) vencida hace 23 días" — the headline.
    headline: str
    # The liability rationale ("Riesgo de deducibilidad y responsabilidad
    # solidaria") so the number carries its "so what".
    reason: str
    # Optional contract context ("48 trabajadores · contrato vence en 18 días").
    detail: str | None = None
    href: str


class ClientFailurePattern(BaseModel):
    """The dominant recurring failure across the portfolio (root-cause line)."""

    requirement_name: str
    institution: str
    vendor_count: int
    obligation_count: int


class ClientOverview(BaseModel):
    client_id: str
    client_name: str
    vendors_total: int
    active_workspaces_total: int
    # CANONICAL headline metric (truth-in-data, 2026-06-19): the pooled,
    # obligation-level "% of obligations already due that are al día" —
    # numerator/denominator summed across the portfolio (NOT a mean-of-means),
    # and future-period obligations excluded from the denominator so a quiet
    # November doesn't depress the score. Derived from the SAME authoritative
    # deadlines the calendar uses, so the surfaces can no longer disagree.
    compliance_pct: int
    # The raw numerator/denominator behind ``compliance_pct`` so the hero can
    # render "236 de 248" and the figure is auditable.
    obligations_on_track_total: int = 0
    obligations_due_total: int = 0
    # Month-over-month approval-rate momentum in points (most recent active
    # month − the one before), reused from the report engine. None when
    # there aren't two active months yet. Answers the CFO's "better or
    # worse than last month?" without faking a historical snapshot.
    compliance_trend_delta: int | None = None
    green_count: int
    yellow_count: int
    red_count: int
    pending_reviews_total: int
    rejected_or_correction_total: int
    missing_required_total: int
    due_soon_total: int
    # Lapsed obligations across the portfolio — the highest-liability state,
    # previously folded silently into the red bucket.
    overdue_total: int = 0
    # Obligations not yet due (future periods) — surfaced as "Próximas" so the
    # date-correct buckets stop conflating "overdue-and-missing" with
    # "not-yet-due", which is why the old "Faltantes" number alarmed.
    proxima_total: int = 0
    recent_submissions_total: int
    last_activity_at: datetime | None
    # The single biggest legal/tax exposure right now (or None → hide card).
    biggest_exposure: ClientExposure | None = None
    # Phase 3 — count of in-queue documents an extra (AI) pass flagged for the
    # client's attention. 0 (the default for every non-pilot client) → the UI
    # hides the indicator entirely; it never asserts "AI vetted" what it never
    # saw. The human reviewer's verdict always stays the source of truth.
    ia_revisar_total: int = 0
    # Phase 3 — the most common failure across the portfolio (one requirement
    # failing across many providers), so the client fixes a systemic gap once
    # instead of chasing every vendor. None when there's no clear cluster.
    top_failure_pattern: ClientFailurePattern | None = None
    # Worst-first ranked attention list (top 5) so the flagship screen
    # answers "which providers" / "what next", not just "how many".
    top_risk_vendors: list[ClientRiskVendor] = []


class ClientTrajectoryPoint(BaseModel):
    """One month on the period-anchored compliance trajectory."""

    period: str  # "2026-03"
    label: str  # "mar"
    due_total: int
    on_track: int
    compliance_pct: int


class ClientTrajectory(BaseModel):
    """Period-anchored compliance coverage over the trailing months.

    The ONLY honest historical line on this data: for each past month we take
    the obligations whose authoritative deadline fell in that month and were
    already due, and compute resolved/total. Anchored to the obligation's own
    period (not "today" or reviewer-click time), so re-uploads can't rewrite
    the past. ``has_history`` is False (and ``points`` empty) until a tenant
    has ≥3 active months, so a brand-new client never sees a misleading stub.
    The 85% target is a fixed reference line — never an extrapolated forecast.
    """

    points: list[ClientTrajectoryPoint] = []
    target_pct: int = 85
    has_history: bool = False


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


class VendorComplianceBreakdown(BaseModel):
    """Two reconciled compliance lenses for one vendor (2nd-review note 2.4).

    ``year_to_date_*`` mirrors the dashboard worklist's per-vendor math
    EXACTLY (every obligation whose deadline has already passed this year),
    so the detail page and the dashboard never disagree. ``current_period_*``
    is the narrower "are they current right now" view: only the latest
    already-due cycle of each recurring obligation, plus the always-due
    onboarding expediente. ``*_due == 0`` means there's nothing to measure
    yet (the FE shows "—" rather than a hollow 100%).
    """

    year: int
    current_period_pct: int
    current_period_on_track: int
    current_period_due: int
    year_to_date_pct: int
    year_to_date_on_track: int
    year_to_date_due: int


class ClientVendorDetail(BaseModel):
    client_id: str
    vendor_id: str
    workspace_id: str
    vendor: dict
    workspace: dict
    onboarding_summary: DashboardOnboardingSummary
    document_state_counts: DashboardDocumentStateCounts
    semaphore: DashboardSemaphore
    compliance_breakdown: VendorComplianceBreakdown
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
    # Distinguishes a recurring obligation (mensual/bimestral/…) from a
    # one-time onboarding/expediente piece (``alta_inicial``). One-time docs
    # legitimately have a null ``period_key``; the FE uses this to render a
    # "Único" label instead of an ambiguous "—" (2nd-review note 4.1).
    load_type: str | None
    status: str
    current_slot_status: str | None
    is_current_for_slot: bool
    filename: str | None
    submitted_at: datetime
    reviewed_at: datetime | None
    reviewer_note: str | None
    supersedes_submission_id: str | None
    superseded_by_submission_id: str | None
    # Phase 5 / Axis 2 — the client's business-acceptance verdict, orthogonal
    # to ``status`` (Axis 1). ``client_decided_at`` is the decision time;
    # ``client_decision_reason`` is populated for override decisions.
    client_acceptance: str = ClientAcceptance.PENDING.value
    client_decided_at: datetime | None = None
    client_decision_reason: str | None = None


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


class ClientCalendarAcceptedDoc(BaseModel):
    """One acceptable document for a v2 obligation that ANY single member of
    satisfies (e.g. IMSS monthly = comprobante bancario OR CFDI OR cédula).
    Mirrors the provider calendar's accepted-doc shape so the client review
    surface can explain "cualquiera de estos satisface la obligación". Empty
    on v1 obligations (no alternatives)."""

    name: str
    anatomy: str
    where_to_obtain: str
    common_errors: list[str]


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
    # Server-owned next step in the client's oversight voice (chase/wait,
    # never "upload"), computed once by ``_client_suggested_action`` so the
    # card instruction can't drift from the cell's risk color.
    suggested_action: str
    # Oversight evidence: what the provider already delivered and when, plus
    # the reviewer's reason when the obligation bounced — so the client can
    # decide chase-vs-wait and relay the exact motive without first clicking
    # into the expediente. ``filename`` / ``submitted_at`` are null until a
    # submission exists; ``reviewer_note`` is only populated on rejected /
    # needs-clarification / mismatch items that carry a reviewer message.
    filename: str | None
    submitted_at: str | None
    reviewer_note: str | None
    # Document guidance, mirrored from the provider calendar so the client
    # review surface can show "what the document is, where to get it, and the
    # common pitfalls to verify" inline instead of forcing a click-through.
    # ``accepts_documents`` is non-empty only for v2 obligations satisfiable
    # by any one of several documents.
    anatomy: str
    where_to_obtain: str
    common_errors: list[str]
    accepts_documents: list[ClientCalendarAcceptedDoc]
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
    # Past-deadline, unresolved obligations (VENCIDO / lapsed). Defaulted so
    # the field is optional-safe for any older consumer; the buckets now
    # partition every obligation so they reconcile with ``due_total``.
    overdue_total: int = 0
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
    current: ClientApprover,
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
    _assert_live_client_approver(db, current, target_id)
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
# ``_REJECTED_OR_CORRECTION_STATUSES`` + ``_calendar_item_risk`` now live in
# ``app.services.calendar_risk`` (imported above under their legacy private
# names) so the client, provider, and admin calendars share one risk classifier.
# The three raw statuses that all display to the client as "En revisión".
# Used by the submissions ``status=en_revision`` collapsed filter.
_EN_REVISION_STATUSES = (
    DocumentStatus.RECIBIDO.value,
    DocumentStatus.PENDIENTE_REVISION.value,
    DocumentStatus.PREVALIDADO.value,
)

# Worst-first ordering for the per-provider rollup. Red providers (something
# is overdue or rejected) sort above yellow (in motion) above green (al día).
_SEMAPHORE_SORT_ORDER = {"red": 0, "yellow": 1, "green": 2}


def _client_suggested_action(risk_level: str, has_submission: bool) -> str:
    """Plain-Spanish next step for the CLIENT on one calendar obligation.

    The client-portal analog of the provider's ``_calendar_suggested_action``
    (``app.api.v1.portal``), but in the oversight voice: a hiring company can
    never upload on a provider's behalf, so every step is "chase the provider"
    or "wait on the reviewer" — never an upload instruction. This is the
    server-side source of truth the calendar's obligation card consumes; the
    frontend keeps a byte-for-byte matching ``nextActionFor`` fallback so a
    stale backend (rolling deploy) still renders a sensible step.

    Keyed off the already-computed ``risk_level`` (see ``_calendar_item_risk``)
    rather than the raw status so the next step can never disagree with the
    cell color the same obligation shows.
    """
    if risk_level == "action_required":
        return "Pídele al proveedor que corrija y reemplace el documento."
    if risk_level == "in_review":
        return "En revisión por el equipo. No requiere acción de tu parte."
    if risk_level == "on_track":
        return "Al día. Sin acción pendiente."
    # overdue / due_soon / upcoming
    return (
        "Da seguimiento con el proveedor."
        if has_submission
        else "Pídele al proveedor que suba el documento."
    )


def _risk_top_reason(summary: dict) -> str:
    """Short Spanish phrase naming a vendor's dominant problem, worst-first.

    Priority mirrors compliance liability: lapsed > to-correct > missing >
    in-review > due-soon. Drives the dashboard "Requieren tu atención" list.
    """
    overdue = summary.get("overdue_count", 0)
    if overdue:
        return "1 obligación vencida" if overdue == 1 else f"{overdue} obligaciones vencidas"
    rejected = summary.get("rejected_or_correction_count", 0)
    if rejected:
        return "1 documento por corregir" if rejected == 1 else f"{rejected} por corregir"
    missing = summary.get("missing_required_count", 0)
    if missing:
        return "1 documento faltante" if missing == 1 else f"{missing} faltantes"
    pending = summary.get("pending_reviews_count", 0)
    if pending:
        return "1 en revisión" if pending == 1 else f"{pending} en revisión"
    due_soon = summary.get("due_soon_count", 0)
    if due_soon:
        return "1 por vencer" if due_soon == 1 else f"{due_soon} por vencer"
    return "Requiere seguimiento"


def _overview_recurring_rows(
    workspace: ProviderWorkspace,
    calendar_slots: list,
    *,
    year: int,
    today: date,
) -> list[dict]:
    """Authoritative per-obligation rows for one workspace's recurring calendar.

    Mirrors :func:`app.services.calendar_aggregate.aggregate_client_calendar`'s
    inner placement loop EXACTLY — same catalog selection, same
    ``_calendar_deadline_iso`` deadline, same :func:`_calendar_item_risk`
    classification — so the dashboard's overdue / due-soon / próxima counts
    equal the calendar's by construction (truth-in-data, 2026-06-19). The slot
    status comes from the prefetched ``calendar_slots`` (built once by
    :func:`_vendor_compliance`), so this adds only an in-memory catalog walk —
    no extra query.
    """
    persona = normalize_persona_type(workspace.persona_type)
    catalog = (
        recurring_for_year_v2(year, persona)
        if settings.RECURRING_CATALOG_V2
        else recurring_for_year(year, persona)
    )
    view_by_key = {
        (v.slot_key.requirement_code, v.slot_key.period_key): v for v in calendar_slots
    }
    rows: list[dict] = []
    for req in catalog:
        view = view_by_key.get((req.code, req.period_key))
        status = (
            view.current_status if view and view.current_status else "pendiente"
        )
        deadline_iso = _calendar_deadline_iso(year, req.due_month, req.due_day)
        risk = _calendar_item_risk(status, deadline_iso, today)
        try:
            deadline_date: date | None = date.fromisoformat(deadline_iso)
        except ValueError:
            deadline_date = None
        rows.append(
            {
                "requirement_code": req.code,
                "requirement_name": recurring_required_document(req),
                "institution": req.institution,
                "period_label": req.period_label,
                "deadline_iso": deadline_iso,
                "deadline_date": deadline_date,
                "risk": risk,
                "submission_id": view.current_submission_id if view else None,
            }
        )
    return rows


def _vendor_compliance_breakdown(
    recurring_rows: list[dict],
    onboarding_slots: list,
    *,
    year: int,
    today: date,
) -> VendorComplianceBreakdown:
    """Year-to-date + current-period compliance for one vendor.

    ``recurring_rows`` come from :func:`_overview_recurring_rows` (same
    deadlines/classification as the calendar). The year-to-date numerator/
    denominator are computed the SAME way as the dashboard headline
    (``v_rec_*`` + onboarding at the overview loop), so the two surfaces
    reconcile by construction. Current-period collapses each recurring
    requirement to its latest already-due cycle so an old miss doesn't keep
    dragging the "right now" figure once a later cycle is filed.
    """
    onb_required = [s for s in onboarding_slots if s.required]
    onb_due = len(onb_required)
    onb_sat = sum(1 for s in onb_required if s.state in _RESOLVED_SLOT_STATES)

    ytd_rec_due = ytd_rec_sat = 0
    # requirement_code -> (latest deadline_date, on_track) among due cycles.
    latest_by_req: dict[str | None, tuple[date, bool]] = {}
    for r in recurring_rows:
        deadline_date = r["deadline_date"]
        if deadline_date is None or deadline_date > today:
            continue
        on_track = r["risk"] == "on_track"
        ytd_rec_due += 1
        if on_track:
            ytd_rec_sat += 1
        code = r["requirement_code"]
        prev = latest_by_req.get(code)
        if prev is None or deadline_date > prev[0]:
            latest_by_req[code] = (deadline_date, on_track)

    ytd_due = ytd_rec_due + onb_due
    ytd_sat = ytd_rec_sat + onb_sat
    cur_due = len(latest_by_req) + onb_due
    cur_sat = sum(1 for _d, ok in latest_by_req.values() if ok) + onb_sat

    return VendorComplianceBreakdown(
        year=year,
        current_period_pct=round(cur_sat / cur_due * 100) if cur_due else 100,
        current_period_on_track=cur_sat,
        current_period_due=cur_due,
        year_to_date_pct=round(ytd_sat / ytd_due * 100) if ytd_due else 100,
        year_to_date_on_track=ytd_sat,
        year_to_date_due=ytd_due,
    )


def _active_contracts_by_vendor(db: Session, client_id: str) -> dict[str, Contract]:
    """One representative contract per vendor (active preferred) for the
    exposure-materiality weighting. One query for the whole client."""
    out: dict[str, Contract] = {}
    for c in db.scalars(
        select(Contract).where(Contract.client_id == client_id)
    ).all():
        existing = out.get(c.vendor_id)
        if existing is None or (existing.status != "active" and c.status == "active"):
            out[c.vendor_id] = c
    return out


def _exposure_institution_weight(institution: str) -> float:
    """Liability weight by authority — SAT carries the highest peso risk
    (CFDI deduction + IVA acreditamiento), then the social-security /
    registry authorities (cuotas + responsabilidad solidaria)."""
    inst = (institution or "").upper()
    if "SAT" in inst:
        return 3.0
    if "IMSS" in inst or "INFONAVIT" in inst or "STPS" in inst or "REPSE" in inst:
        return 2.0
    return 1.0


def _exposure_reason(institution: str) -> str:
    inst = (institution or "").upper()
    if "SAT" in inst:
        return "Riesgo de deducibilidad y responsabilidad solidaria"
    if "IMSS" in inst:
        return "Cuotas obrero-patronales y responsabilidad solidaria"
    if "INFONAVIT" in inst:
        return "Aportaciones de vivienda y responsabilidad solidaria"
    if "STPS" in inst or "REPSE" in inst:
        return "Cumplimiento ante la STPS y registro REPSE"
    return "Obligación de cumplimiento pendiente"


def _pick_biggest_exposure(
    candidates: list[dict],
    *,
    contracts_by_vendor: dict[str, Contract],
    today: date,
) -> ClientExposure | None:
    """Score every real liability (overdue / needs-correction) and return the
    single worst, weighting severity × authority × contract materiality × age.
    ``None`` when there's nothing overdue or to correct, so the card hides."""
    best: tuple[float, dict, int] | None = None
    for c in candidates:
        risk = c["risk"]
        severity = 3.0 if risk == "overdue" else 2.0  # action_required
        days_overdue = 0
        age_mult = 1.0
        deadline_date = c.get("deadline_date")
        if deadline_date is not None and deadline_date < today:
            days_overdue = (today - deadline_date).days
            age_mult = 1.0 + min(days_overdue, 180) / 180.0
        materiality = 1.0
        contract = contracts_by_vendor.get(c["vendor_id"])
        if contract is not None:
            workers = contract.estimated_workers or 0
            if workers >= 50:
                materiality *= 1.5
            elif workers >= 10:
                materiality *= 1.2
            if (
                contract.end_date is not None
                and (contract.end_date - today).days <= 30
            ):
                materiality *= 1.3
            if not contract.repse_folio:
                materiality *= 1.15
        score = severity * _exposure_institution_weight(c["institution"]) * materiality * age_mult
        if best is None or score > best[0] or (score == best[0] and days_overdue > best[2]):
            best = (score, c, days_overdue)
    if best is None:
        return None
    _score, c, days_overdue = best
    if c["risk"] == "overdue" and days_overdue > 0:
        when = f"vencida hace {days_overdue} día" + ("s" if days_overdue != 1 else "")
    elif c["risk"] == "action_required":
        when = "requiere corrección"
    else:
        when = "pendiente"
    headline = f"{c['requirement_name']} ({c['institution']}) {when}"
    detail_parts: list[str] = []
    contract = contracts_by_vendor.get(c["vendor_id"])
    if contract is not None:
        if contract.estimated_workers:
            detail_parts.append(
                f"{contract.estimated_workers} trabajador"
                + ("es" if contract.estimated_workers != 1 else "")
            )
        if contract.end_date is not None:
            days_to_end = (contract.end_date - today).days
            if days_to_end < 0:
                detail_parts.append("contrato vencido")
            elif days_to_end <= 30:
                detail_parts.append(
                    f"contrato vence en {days_to_end} día"
                    + ("s" if days_to_end != 1 else "")
                )
    focus = "rejected" if c["risk"] == "action_required" else "missing"
    return ClientExposure(
        vendor_id=c["vendor_id"],
        vendor_name=c["vendor_name"],
        requirement_name=c["requirement_name"],
        institution=c["institution"],
        period_label=c.get("period_label"),
        deadline_iso=c.get("deadline_iso"),
        days_overdue=days_overdue,
        headline=headline,
        reason=_exposure_reason(c["institution"]),
        detail=" · ".join(detail_parts) if detail_parts else None,
        href=f"/client/vendors/{c['vendor_id']}?focus={focus}#documentos",
    )


_MONTH_ABBR_ES = (
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
)

# In-queue statuses where a human reviewer has NOT yet ruled — the load-bearing
# guard that keeps an AI flag advisory: once a human approves/rejects, the
# document leaves this set and its AI flag stops counting.
_REVIEWABLE_STATUSES = (
    DocumentStatus.RECIBIDO.value,
    DocumentStatus.PENDIENTE_REVISION.value,
    DocumentStatus.PREVALIDADO.value,
    DocumentStatus.POSIBLE_MISMATCH.value,
)


def _ia_revisar_total(db: Session, client_id: str) -> int:
    """Count in-queue documents an extra AI pass flagged for the client.

    A document counts only when it is BOTH (a) still awaiting a human decision
    (status in :data:`_REVIEWABLE_STATUSES`) and (b) carries a non-clean AI
    signal (suspicious/high-risk authenticity, or a not_satisfied/partial
    comprehension verdict). Returns 0 for every non-pilot client — their
    ``shadow_*`` columns are empty — so the UI hides the indicator entirely
    rather than asserting the AI vetted documents it never saw.

    The comprehension-verdict half is Postgres-only (JSON path); on SQLite
    (tests) it degrades to the authenticity signal, mirroring the dialect-aware
    SQL the admin rollup already uses.
    """
    ai_flag = DocumentInspection.authenticity_risk.in_(("suspicious", "high_risk"))
    if db.get_bind().dialect.name == "postgresql":
        # ``shadow_signals`` maps to a JSONB column. Its SQLAlchemy type is the
        # generic ``JSON`` (so ``[...].astext`` isn't available and the
        # ``json_*`` text helpers don't match a jsonb arg) — cast to JSONB and
        # use ``jsonb_extract_path_text`` to pull the nested verdict as text.
        verdict = func.jsonb_extract_path_text(
            cast(DocumentInspection.shadow_signals, JSONB),
            "comprehension",
            "obligation_satisfaction",
            "verdict",
        )
        ai_flag = or_(ai_flag, verdict.in_(("not_satisfied", "partial")))
    stmt = (
        select(func.count(func.distinct(Document.id)))
        .select_from(Submission)
        .join(Document, Document.submission_id == Submission.id)
        .join(DocumentInspection, DocumentInspection.document_id == Document.id)
        .where(
            Submission.client_id == client_id,
            Submission.status.in_(_REVIEWABLE_STATUSES),
            DocumentInspection.shadow_completed_at.isnot(None),
            ai_flag,
        )
    )
    return int(db.scalar(stmt) or 0)


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
    today = today_mx()
    selected_year = year or today.year

    # Active portfolio only: soft-archived providers must not weigh on the
    # dashboard pool, semaphore tallies, exposure or risk list (they are
    # presented as "fuera de los conteos" on the client surface).
    workspaces = _scoped_workspaces(db, target_id, active_only=True)
    subs_by_vendor, institutions_by_id = _portfolio_slot_inputs(db, target_id)
    vendors_by_id = {
        v.id: v
        for v in db.scalars(
            select(Vendor).where(
                Vendor.client_id == target_id, Vendor.status == "active"
            )
        ).all()
    }
    vendors_total = len(vendors_by_id)
    active_workspaces_total = sum(1 for w in workspaces if w.status == "active")

    contracts_by_vendor = _active_contracts_by_vendor(db, target_id)

    green = yellow = red = 0
    pending_reviews_total = 0
    rejected_or_correction_total = 0
    missing_required_total = 0
    due_soon_total = 0
    overdue_total = 0
    proxima_total = 0
    # Canonical pooled metric: numerator/denominator summed across the whole
    # portfolio (truth-in-data) — NOT a mean of per-vendor percentages.
    obligations_due_total = 0
    obligations_on_track_total = 0
    # Real liabilities (overdue / needs-correction) for the exposure pick, and
    # a (requirement, institution) → {vendors, count} map for the root-cause
    # cluster line.
    exposure_candidates: list[dict] = []
    failure_clusters: dict[tuple[str, str], dict] = {}
    # Collected per-vendor so we can rank the worst-first attention list
    # without a second pass over the (expensive) slot computation.
    risk_candidates: list[ClientRiskVendor] = []
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

        vendor = vendors_by_id.get(ws.vendor_id)
        vendor_name = vendor.name if vendor else "Proveedor"

        # Authoritative recurring obligations (same deadlines/classification as
        # the calendar). Recurring "missing" splits into overdue / due_soon /
        # próxima here — no more date-blind "Faltantes" bucket.
        rows = _overview_recurring_rows(
            ws, summary["calendar_slots"], year=selected_year, today=today
        )
        v_overdue = v_due_soon = v_action = v_in_review = v_proxima = 0
        v_rec_due = v_rec_sat = 0
        for r in rows:
            risk = r["risk"]
            if risk == "overdue":
                v_overdue += 1
            elif risk == "due_soon":
                v_due_soon += 1
            elif risk == "action_required":
                v_action += 1
            elif risk == "in_review":
                v_in_review += 1
            elif risk == "upcoming":
                v_proxima += 1
            deadline_date = r["deadline_date"]
            if deadline_date is not None and deadline_date <= today:
                v_rec_due += 1
                if risk == "on_track":
                    v_rec_sat += 1
            if risk in ("overdue", "action_required"):
                exposure_candidates.append(
                    {**r, "vendor_id": ws.vendor_id, "vendor_name": vendor_name}
                )
                key = (r["requirement_name"], r["institution"])
                cluster = failure_clusters.setdefault(
                    key, {"vendors": set(), "count": 0}
                )
                cluster["vendors"].add(ws.vendor_id)
                cluster["count"] += 1

        # Onboarding (foundational expediente) is always "due" — fold it into
        # the canonical numerator/denominator so a missing REPSE registration
        # still drags the headline down, and surface its gap count as the
        # worklist's "missing" reason.
        onb_required = [s for s in summary["onboarding_slots"] if s.required]
        onb_due = len(onb_required)
        onb_sat = sum(1 for s in onb_required if s.state in _RESOLVED_SLOT_STATES)
        onb_missing = sum(
            1 for s in onb_required if s.state is SlotState.MISSING
        )

        overdue_total += v_overdue
        due_soon_total += v_due_soon
        rejected_or_correction_total += v_action
        pending_reviews_total += v_in_review
        proxima_total += v_proxima
        missing_required_total += onb_missing
        v_due_total = v_rec_due + onb_due
        v_sat_total = v_rec_sat + onb_sat
        obligations_due_total += v_due_total
        obligations_on_track_total += v_sat_total
        v_pct = round(v_sat_total / v_due_total * 100) if v_due_total else 100

        if level in ("red", "yellow"):
            risk_candidates.append(
                ClientRiskVendor(
                    vendor_id=ws.vendor_id,
                    vendor_name=vendor_name,
                    semaphore_level=level,
                    compliance_pct=v_pct,
                    overdue_count=v_overdue,
                    missing_required_count=onb_missing,
                    rejected_or_correction_count=v_action,
                    top_reason=_risk_top_reason(
                        {
                            "overdue_count": v_overdue,
                            "rejected_or_correction_count": v_action,
                            "missing_required_count": onb_missing,
                            "pending_reviews_count": v_in_review,
                            "due_soon_count": v_due_soon,
                        }
                    ),
                )
            )

    # Worst-first: red before yellow, then lowest compliance %, then the
    # most open problems. Top 5 keeps the dashboard panel scannable.
    risk_candidates.sort(
        key=lambda r: (
            _SEMAPHORE_SORT_ORDER.get(r.semaphore_level, 9),
            r.compliance_pct,
            -(
                r.overdue_count
                + r.rejected_or_correction_count
                + r.missing_required_count
            ),
        )
    )
    top_risk_vendors = risk_candidates[:5]
    # Per-vendor momentum from ONE batched query (constant in vendor count, so
    # the portfolio N+1 contract holds): distinguishes "bad but improving" from
    # "sliding into red".
    momentum_by_vendor = approval_trend_points_by_vendor(
        db, today, client_id=target_id
    )
    for rv in top_risk_vendors:
        rv.momentum_delta = momentum_by_vendor.get(rv.vendor_id)

    compliance_pct = (
        round(obligations_on_track_total / obligations_due_total * 100)
        if obligations_due_total
        else 100
    )
    compliance_trend_delta = approval_trend_points(db, today, client_id=target_id)
    ia_revisar_total = _ia_revisar_total(db, target_id)
    biggest_exposure = _pick_biggest_exposure(
        exposure_candidates, contracts_by_vendor=contracts_by_vendor, today=today
    )
    # Root cause: the single (requirement, institution) failing across the most
    # providers — needs ≥2 providers to count as a "pattern" worth fixing once.
    top_failure_pattern: ClientFailurePattern | None = None
    if failure_clusters:
        (req_name, inst), cl = max(
            failure_clusters.items(),
            key=lambda kv: (len(kv[1]["vendors"]), kv[1]["count"]),
        )
        if len(cl["vendors"]) >= 2:
            top_failure_pattern = ClientFailurePattern(
                requirement_name=req_name,
                institution=inst,
                vendor_count=len(cl["vendors"]),
                obligation_count=cl["count"],
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
        obligations_on_track_total=obligations_on_track_total,
        obligations_due_total=obligations_due_total,
        compliance_trend_delta=compliance_trend_delta,
        green_count=green,
        yellow_count=yellow,
        red_count=red,
        pending_reviews_total=pending_reviews_total,
        rejected_or_correction_total=rejected_or_correction_total,
        missing_required_total=missing_required_total,
        due_soon_total=due_soon_total,
        overdue_total=overdue_total,
        proxima_total=proxima_total,
        recent_submissions_total=min(recent_submissions_total, 200),
        last_activity_at=last_activity_at,
        biggest_exposure=biggest_exposure,
        ia_revisar_total=ia_revisar_total,
        top_failure_pattern=top_failure_pattern,
        top_risk_vendors=top_risk_vendors,
    )


@router.get("/overview/trajectory", response_model=ClientTrajectory)
def client_overview_trajectory(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    months: Annotated[int, Query(ge=3, le=12)] = 8,
) -> ClientTrajectory:
    """Period-anchored compliance coverage over the trailing months.

    For each of the last ``months`` calendar months, take the obligations whose
    authoritative deadline fell in that month and were already due, and report
    resolved/total. Lazy (separate from the hot ``/overview`` call) and reuses
    the SAME ``aggregate_client_calendar`` pass the calendar uses, so the line
    can never disagree with the grid. Empty until ≥3 active months exist.
    """
    target_id = _resolve_client_id(db, current, requested=client_id)
    if db.get(Client, target_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")
    today = today_mx()

    # Trailing month-buckets, chronological.
    wanted: list[tuple[int, int]] = []
    y, m = today.year, today.month
    for _ in range(months):
        wanted.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    wanted.reverse()

    # Aggregate each needed year once; bucket obligations by their deadline
    # month (only those already due as of today).
    by_month: dict[tuple[int, int], list] = {}
    for yr in sorted({yy for yy, _ in wanted}):
        agg = aggregate_client_calendar(
            db, client_id=target_id, year=yr, today=today
        )
        for ob in agg.obligations:
            try:
                deadline = date.fromisoformat(ob.deadline_iso)
            except ValueError:
                continue
            if deadline > today:
                continue
            by_month.setdefault((deadline.year, deadline.month), []).append(ob)

    points: list[ClientTrajectoryPoint] = []
    for yy, mm in wanted:
        obs = by_month.get((yy, mm))
        if not obs:
            continue
        total = len(obs)
        on_track = sum(1 for o in obs if o.risk_level == "on_track")
        points.append(
            ClientTrajectoryPoint(
                period=f"{yy:04d}-{mm:02d}",
                label=_MONTH_ABBR_ES[mm - 1],
                due_total=total,
                on_track=on_track,
                compliance_pct=round(on_track / total * 100) if total else 100,
            )
        )

    has_history = len(points) >= 3
    return ClientTrajectory(
        points=points if has_history else [],
        target_pct=85,
        has_history=has_history,
    )


# ---------------------------------------------------------------------------
# /vendors
# ---------------------------------------------------------------------------


def _sort_vendor_pairs(
    pairs: list[tuple[ProviderWorkspace, dict]],
    sort: str,
    vendors: dict,
) -> list[tuple[ProviderWorkspace, dict]]:
    """Order (workspace, compliance-summary) pairs for the vendor list.

    ``risk`` (default) is worst-first: red→yellow→green, then lowest
    compliance %, then most open problems — the ranking the portfolio
    screen exists to provide. Name is the stable tiebreak.
    """

    def name_of(ws: ProviderWorkspace) -> str:
        v = vendors.get(ws.vendor_id)
        return normalize_for_search(v.name if v else "")

    if sort == "compliance_asc":
        key = lambda p: (p[1]["compliance_pct"], name_of(p[0]))  # noqa: E731
    elif sort == "compliance_desc":
        key = lambda p: (-p[1]["compliance_pct"], name_of(p[0]))  # noqa: E731
    elif sort == "missing_desc":
        key = lambda p: (  # noqa: E731
            -(p[1]["missing_required_count"] + p[1]["rejected_or_correction_count"]),
            name_of(p[0]),
        )
    else:  # risk (default)
        key = lambda p: (  # noqa: E731
            _SEMAPHORE_SORT_ORDER.get(p[1]["semaphore_level"], 9),
            p[1]["compliance_pct"],
            -(
                p[1].get("overdue_count", 0)
                + p[1]["rejected_or_correction_count"]
                + p[1]["missing_required_count"]
            ),
            name_of(p[0]),
        )
    return sorted(pairs, key=key)


def _sort_candidates_cheap(
    candidates: list[ProviderWorkspace],
    sort: str,
    vendors: dict,
    last_sub_map: dict,
) -> list[ProviderWorkspace]:
    """Order candidates by a cheap row attribute (no compliance projection)."""
    if sort == "name":
        return sorted(
            candidates,
            key=lambda ws: normalize_for_search(
                vendors.get(ws.vendor_id).name if vendors.get(ws.vendor_id) else ""
            ),
        )
    # recent: most recent submission first; vendors with none sort last.
    return sorted(
        candidates,
        key=lambda ws: (
            last_sub_map.get(ws.vendor_id) is None,
            -(last_sub_map.get(ws.vendor_id).timestamp())
            if last_sub_map.get(ws.vendor_id)
            else 0.0,
        ),
    )


@router.get("/vendors", response_model=ClientVendorListResponse)
def client_vendors(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    semaphore_level: Literal["green", "yellow", "red"] | None = None,
    search: str | None = None,
    sort: Annotated[
        Literal[
            "risk", "compliance_asc", "compliance_desc", "missing_desc", "name", "recent"
        ],
        Query(),
    ] = "risk",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClientVendorListResponse:
    target_id = _resolve_client_id(db, current, requested=client_id)
    today = today_mx()
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

    # ``risk`` (default) and the compliance/missing sorts are derived from the
    # slot projection, so they can't be ordered in SQL: compute every
    # candidate, sort, then build rows for the requested page only. ``name`` /
    # ``recent`` are cheap row attributes, so we keep the fast path (page first,
    # project only the page) the perf pass introduced.
    needs_full_compute = bool(semaphore_level) or sort in (
        "risk",
        "compliance_asc",
        "compliance_desc",
        "missing_desc",
    )
    if needs_full_compute:
        pairs = [(ws, _compliance(ws)) for ws in candidates]
        if semaphore_level:
            pairs = [
                p for p in pairs if p[1]["semaphore_level"] == semaphore_level
            ]
        pairs = _sort_vendor_pairs(pairs, sort, vendors)
        total = len(pairs)
        page = [
            _build_row(ws, summary)
            for ws, summary in pairs[offset : offset + limit]
        ]
    else:
        ordered = _sort_candidates_cheap(candidates, sort, vendors, last_sub_map)
        total = len(ordered)
        page = [
            _build_row(ws, _compliance(ws))
            for ws in ordered[offset : offset + limit]
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
                # Phase 5 / Axis 2 — client-acceptance verdict (orthogonal to status).
                "client_acceptance": sub.client_acceptance,
                "client_decided_at": (
                    sub.client_decided_at.isoformat() if sub.client_decided_at else None
                ),
                "client_decision_reason": sub.client_decision_reason,
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
        due_in = _due_in_days_for_period(view.period_key, today, deadline_iso=view.deadline_iso)
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
    is_internal_admin = bool(STAFF_ROLES & set(current.roles))
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
    current: ClientApprover,
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

    # Throttle per caller BEFORE any DB write or outbound email/SMS. This
    # endpoint provisions a User+Vendor+ProviderWorkspace and fires a
    # welcome email + in-app/SMS invitation to a caller-supplied
    # email/phone, so without a cap a single client_admin can mass-create
    # accounts and mail-bomb/SMS-bomb arbitrary recipients. The export
    # bucket is reused (segregated from AI cost) with the standard export
    # caps — generous enough for legitimate onboarding bursts, tight
    # enough to stop a flood. Raises 429 on breach.
    enforce_export_rate_limit(
        current.user.id,
        per_minute=settings.EXPORT_RATE_LIMIT_PER_MINUTE,
        per_hour=settings.EXPORT_RATE_LIMIT_PER_HOUR,
    )

    target_id = _resolve_client_id(db, current, requested=client_id)
    _assert_live_client_approver(db, current, target_id)
    contact_email = payload.contact_email.strip().lower()
    rfc_value = payload.vendor_rfc.strip().upper()
    is_internal = bool(STAFF_ROLES & set(current.roles))

    # Lock the org row BEFORE counting active providers so two concurrent
    # adds cannot both observe the last free slot (the seat-cap discipline).
    org = org_for_client(db, target_id, for_update=True)

    # "Restore instead of re-create": a duplicate (client, RFC) that is
    # ARCHIVED should route the client to reactivate, not hit an opaque 409.
    archived_dupe = db.scalar(
        select(Vendor).where(
            Vendor.client_id == target_id,
            Vendor.rfc == rfc_value,
            Vendor.status == VendorStatus.ARCHIVED.value,
        )
    )
    if archived_dupe is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "provider_archived",
                "vendor_id": archived_dupe.id,
                "message": (
                    "Ya tienes un proveedor archivado con ese RFC. "
                    "Reactívalo para volver a usarlo."
                ),
            },
        )

    # Hard cap for client self-service; internal_admin may exceed (audited
    # via over_limit_override below).
    capacity = assert_provider_capacity(db, org, is_internal=is_internal)

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
    # Concurrent invites with the same contact_email both clear the
    # ``existing_user`` pre-check above, then the second flush hits the
    # ``uq_users_email`` unique constraint. Catch that race and surface the
    # same 409 the pre-check returns, mirroring the vendor-flush guard below.
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con ese correo de contacto.",
        ) from exc

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
            "provider_limit": capacity.limit,
            "active_after": capacity.used + 1,
            "over_limit_override": capacity.over_limit,
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


# ---------------------------------------------------------------------------
# Phase 3 — client archives / restores a provider in their portfolio
# ---------------------------------------------------------------------------


class ClientProviderStatusResponse(BaseModel):
    """Result of deactivate / reactivate. ``status`` is the vendor's new
    archival state (``active`` | ``inactive``); ``changed`` is False when
    the provider was already in the target state (idempotent no-op)."""

    vendor_id: str
    status: str
    changed: bool


def _set_provider_archival(
    db: Session,
    current: CurrentUser,
    request: Request,
    *,
    vendor_id: str,
    requested_client_id: str | None,
    target_status: str,
) -> ClientProviderStatusResponse:
    """Flip a vendor + its client-scoped workspace(s) to ``target_status``.

    Soft, reversible archival — never a delete. All history, documents
    and audit rows survive; the provider's own portal access is untouched
    (auth keys on ``User.status``, not the workspace), so a mis-archive
    strands nobody. Idempotent: a no-op when already in ``target_status``.
    """
    target_id, vendor = _resolve_client_id_for_vendor(
        db, current, vendor_id=vendor_id, requested=requested_client_id
    )
    _assert_live_client_approver(db, current, target_id)
    # Archive/restore the vendor + its client-scoped workspace(s) in
    # lock-step so the vendor list, compliance counts and calendar all
    # move together.
    workspaces = list(
        db.scalars(
            select(ProviderWorkspace).where(
                ProviderWorkspace.vendor_id == vendor.id,
                ProviderWorkspace.client_id == target_id,
            )
        )
    )
    # No-op only when the WHOLE provider already sits at the target. Keying
    # the early return on the vendor alone would let a workspace created
    # while the vendor was archived drift out of lock-step forever.
    already_set = vendor.status == target_status and all(
        ws.status == target_status for ws in workspaces
    )
    if already_set:
        return ClientProviderStatusResponse(
            vendor_id=vendor.id, status=target_status, changed=False
        )

    # Restoring re-consumes a slot — re-check the plan cap (a client at the
    # limit cannot reactivate without first archiving another; internal_admin
    # may exceed). Deactivation always frees a slot, so it is never gated.
    reactivate_capacity = None
    if target_status == VendorStatus.ACTIVE.value:
        reactivate_internal = bool(STAFF_ROLES & set(current.roles))
        reactivate_org = org_for_client(db, target_id, for_update=True)
        reactivate_capacity = assert_provider_capacity(
            db, reactivate_org, is_internal=reactivate_internal
        )

    before_status = vendor.status
    vendor.status = target_status
    for ws in workspaces:
        ws.status = target_status

    if MembershipRole.OPERATIONS_ADMIN.value in current.roles:
        actor_type = MembershipRole.OPERATIONS_ADMIN.value
    elif bool(STAFF_ROLES & set(current.roles)):
        actor_type = MembershipRole.PLATFORM_ADMIN.value
    else:
        actor_type = MembershipRole.CLIENT_ADMIN.value
    ua = request.headers.get("user-agent")
    add_audit_event(
        db,
        action=(
            "client.provider_deactivated"
            if target_status == "inactive"
            else "client.provider_reactivated"
        ),
        entity_type="vendor",
        entity_id=vendor.id,
        actor_type=actor_type,
        actor_id=current.user.id,
        ip_address=_client_ip(request),
        user_agent=ua[:512] if ua else None,
        before={"status": before_status},
        after={
            "status": target_status,
            "client_id": target_id,
            "workspace_ids": [w.id for w in workspaces],
        },
        # Reactivation re-consumes a slot; flag an internal_admin over-cap
        # restore so a billing bypass is detectable — in event_metadata,
        # uniform with the add / admin-create doors.
        metadata=(
            {
                "provider_limit": reactivate_capacity.limit,
                "active_after": reactivate_capacity.used + 1,
                "over_limit_override": reactivate_capacity.over_limit,
            }
            if reactivate_capacity is not None
            else None
        ),
    )
    db.commit()
    return ClientProviderStatusResponse(
        vendor_id=vendor.id, status=target_status, changed=True
    )


@router.post(
    "/vendors/{vendor_id}/deactivate",
    response_model=ClientProviderStatusResponse,
    summary="Archive a provider in the client's portfolio (reversible)",
)
def client_deactivate_provider(
    vendor_id: str,
    db: DbSession,
    current: ClientApprover,
    request: Request,
    client_id: str | None = None,
) -> ClientProviderStatusResponse:
    """Soft-deactivate (archive) a provider from the caller's portfolio.

    Drops the vendor + its workspace(s) out of the active compliance view
    and counts without deleting anything; reversible via ``/reactivate``.
    Any ``client_admin`` in the tenant may do this today (mirrors add-
    provider); Phase 4 narrows it to the Approver role.
    """
    return _set_provider_archival(
        db,
        current,
        request,
        vendor_id=vendor_id,
        requested_client_id=client_id,
        target_status="inactive",
    )


@router.post(
    "/vendors/{vendor_id}/reactivate",
    response_model=ClientProviderStatusResponse,
    summary="Restore a previously archived provider",
)
def client_reactivate_provider(
    vendor_id: str,
    db: DbSession,
    current: ClientApprover,
    request: Request,
    client_id: str | None = None,
) -> ClientProviderStatusResponse:
    """Reverse a ``/deactivate``: restore the provider to ``active``."""
    return _set_provider_archival(
        db,
        current,
        request,
        vendor_id=vendor_id,
        requested_client_id=client_id,
        target_status="active",
    )


# ---------------------------------------------------------------------------
# Phase A — subscription plan + provider-usage meter
# ---------------------------------------------------------------------------


class ClientPlanResponse(BaseModel):
    """The caller's subscription plan, provider usage and capabilities —
    powers the plan badge, the "X of Y providers" meter, the demo countdown
    and (Phase B) export gating. ``provider_limit`` / ``providers_available``
    are null when the plan is uncapped (legacy / enterprise)."""

    client_id: str
    organization_id: str
    plan: str
    plan_label: str
    provider_limit: int | None
    providers_used: int
    providers_available: int | None
    demo_expires_at: str | None
    capabilities: dict[str, bool]
    can_manage: bool
    """Whether the requesting user may change the plan / manage seats
    (primary owner or internal staff) — mirrors the seats surface."""


@router.get(
    "/plan",
    response_model=ClientPlanResponse,
    summary="The caller's subscription plan, provider usage and capabilities",
)
def client_plan(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = Query(default=None),
) -> ClientPlanResponse:
    """Read-only plan snapshot for the client portal. ``providers_used`` is
    the active (non-archived) vendor count — exactly what the cap counts."""
    cid = _resolve_client_id(db, current, requested=client_id)
    org = org_for_client(db, cid)
    plan = plan_for_org(org)
    limit = provider_limit_for_org(org)
    used = active_provider_count(db, cid)
    is_internal = bool(STAFF_ROLES & set(current.roles))
    holds_primary = db.scalar(
        select(Membership.id).where(
            Membership.organization_id == org.id,
            Membership.user_id == current.user.id,
            Membership.status == "active",
            Membership.is_primary.is_(True),
        )
    )
    return ClientPlanResponse(
        client_id=cid,
        organization_id=org.id,
        plan=plan.value,
        plan_label=PLAN_LABELS_ES[plan],
        provider_limit=limit,
        providers_used=used,
        providers_available=None if limit is None else max(0, limit - used),
        demo_expires_at=(
            org.demo_expires_at.isoformat() if org.demo_expires_at else None
        ),
        capabilities=capabilities_for_org(db, org),
        can_manage=is_internal or holds_primary is not None,
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

    today = today_mx()
    selected_year = year or today.year
    onboarding_slots = build_workspace_onboarding_slots(db, workspace)
    calendar_slots = build_workspace_calendar_slots(db, workspace, selected_year)
    counts = _empty_document_counts()
    for view in onboarding_slots + calendar_slots:
        _bucket_document_state(counts, view.state)
    # Year-to-date (reconciles with the dashboard) + current-period lenses.
    recurring_rows = _overview_recurring_rows(
        workspace, calendar_slots, year=selected_year, today=today
    )
    compliance_breakdown = _vendor_compliance_breakdown(
        recurring_rows, onboarding_slots, year=selected_year, today=today
    )

    return ClientVendorDetail(
        client_id=target_id,
        vendor_id=vendor.id,
        workspace_id=workspace.id,
        vendor=_vendor_public(vendor),
        workspace=_workspace_public(workspace),
        onboarding_summary=_compute_onboarding_summary(onboarding_slots, workspace),
        document_state_counts=counts,
        semaphore=_compute_semaphore(onboarding_slots, calendar_slots),
        compliance_breakdown=compliance_breakdown,
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
    # Demo plans cannot pull a multi-document expediente ZIP (Phase B gate).
    assert_capability(db, target_id, Capability.BULK_EXPORT.value)

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

    is_internal_admin = bool(STAFF_ROLES & set(current.roles))
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
        # Phase D — the download (attachment) action is gated by the
        # ``download_documents`` capability. It defaults granted on EVERY tier
        # (demo included), so this only bites when an admin explicitly REVOKES
        # it for a tenant via the entitlement table — making the admin toggle
        # honest instead of a no-op. Inline preview (``download=False``) stays
        # open; the capability names the download/save action specifically.
        assert_capability(
            db, submission.client_id, Capability.DOWNLOAD_DOCUMENTS.value
        )
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
    today = today_mx()
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
                suggested_action=ob.suggested_action,
                filename=ob.filename,
                submitted_at=ob.submitted_at,
                reviewer_note=ob.reviewer_note,
                anatomy=ob.anatomy,
                where_to_obtain=ob.where_to_obtain,
                common_errors=ob.common_errors,
                accepts_documents=ob.accepts_documents,
                href=ob.client_href,
            )
        )
        aggregate_vendors_per_month[ob.due_month].add(ob.vendor_id)

    response_months: list[ClientCalendarMonth] = []
    for month in range(1, 13):
        items = months.get(month, [])
        due_total = len(items)
        # Buckets classify by raw status so "missing" (never uploaded,
        # status PENDIENTE) stays distinct from "overdue" (uploaded then
        # lapsed). VENCIDO previously matched NO bucket, so the sub-totals
        # failed to sum to ``due_total`` and lapsed obligations vanished from
        # the month summary — give it an explicit ``overdue_total`` so every
        # status maps to exactly one bucket and the totals reconcile.
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
            1 for i in items if i.status in _REJECTED_OR_CORRECTION_STATUSES
        )
        overdue_total = sum(
            1 for i in items if i.status == DocumentStatus.VENCIDO.value
        )
        missing_total = sum(
            1 for i in items if i.status == DocumentStatus.PENDIENTE.value
        )
        # ``due_soon`` uses the already-computed risk tier (true catalog
        # deadline), not raw status — it's an informational overlay, not a
        # partition bucket.
        due_soon_total = sum(1 for i in items if i.risk_level == "due_soon")
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
                overdue_total=overdue_total,
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
# /submissions — client acceptance axis (Phase 5)
# ---------------------------------------------------------------------------


class ClientDecisionRequest(BaseModel):
    """Axis-2 decision a client Approver records on a submission.

    ``reason`` is required when the decision overrides CheckWise's validity
    verdict (accepting a non-valid doc, or rejecting a valid one) — enforced
    server-side in ``apply_client_decision`` (422 on violation).
    """

    action: Literal["accept", "reject", "reset"]
    reason: str | None = Field(default=None, max_length=2000)


class ClientDecisionResponse(BaseModel):
    submission_id: str
    previous_acceptance: str
    new_acceptance: str
    action: str
    reason: str | None
    # True when the decision contradicted the compliance verdict.
    override: bool
    decided_at: datetime
    decided_by_user_id: str


@router.post(
    "/submissions/{submission_id}/decision",
    response_model=ClientDecisionResponse,
    summary="Record the client's acceptance-axis decision on a submission",
)
def client_submission_decision(
    submission_id: str,
    payload: ClientDecisionRequest,
    db: DbSession,
    current: ClientApprover,
) -> ClientDecisionResponse:
    """Accept / reject (Axis 2) a submission as the client.

    Approver-only — the ``ClientApprover`` dependency 403s a ``client_viewer``
    at the gate (acceptance is a write). Tenant-scoped: the submission must
    belong to a client the caller can see, else a uniform 404 (no cross-tenant
    existence oracle). Orthogonal to the compliance verdict — never mutates
    ``Submission.status``.
    """
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Envío no encontrado."
        )
    is_internal_admin = bool(STAFF_ROLES & set(current.roles))
    visible = _visible_client_ids_for_user(db, current.user.id)
    if submission.client_id not in visible:
        if not is_internal_admin:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Envío no encontrado."
            )
        # internal_admin break-glass: a state-changing write on a tenant they
        # don't belong to leaves the same forensic trail as every other
        # cross-tenant client write.
        _audit_cross_tenant_access(db, current, submission.client_id)

    _assert_live_client_approver(db, current, submission.client_id)
    result = apply_client_decision(
        db,
        submission=submission,
        action=payload.action,
        reason=payload.reason,
        client_user_id=current.user.id,
    )
    return ClientDecisionResponse(
        submission_id=result.submission_id,
        previous_acceptance=result.previous_acceptance,
        new_acceptance=result.new_acceptance,
        action=result.action,
        reason=result.reason,
        override=result.was_override,
        decided_at=result.decided_at,
        decided_by_user_id=result.client_user_id,
    )


class ClientBulkDecisionRequest(BaseModel):
    """Apply one acceptance-axis action to many submissions at once.

    The common case is "accept every compliance-valid doc for a vendor": the
    frontend collects those submission ids and sends them here. Items that
    would be an override without a shared ``reason`` fail individually and are
    reported back — they do not abort the rest of the batch.
    """

    submission_ids: list[str] = Field(min_length=1, max_length=500)
    action: Literal["accept", "reject", "reset"]
    reason: str | None = Field(default=None, max_length=2000)


class ClientBulkDecisionItemError(BaseModel):
    submission_id: str
    detail: str


class ClientBulkDecisionResponse(BaseModel):
    decided: list[str]
    failed: list[ClientBulkDecisionItemError]
    decided_count: int
    failed_count: int


@router.post(
    "/submissions/bulk-decision",
    response_model=ClientBulkDecisionResponse,
    summary="Apply a client acceptance-axis decision to many submissions",
)
def client_bulk_submission_decision(
    payload: ClientBulkDecisionRequest,
    db: DbSession,
    current: ClientApprover,
) -> ClientBulkDecisionResponse:
    """Bulk accept / reject / reset (Axis 2). Approver-only, tenant-scoped.

    Partial success: each submission is decided independently (override-reason
    violations, cross-tenant / missing ids surface per-item) and the whole
    batch commits once at the end. De-dupes the id list while preserving order.
    """
    is_internal_admin = bool(STAFF_ROLES & set(current.roles))
    visible = set(_visible_client_ids_for_user(db, current.user.id))

    seen: set[str] = set()
    # Live-Approver cache per client (the JWT-claims gate can be stale after a
    # demotion; re-check the DB once per client_id encountered).
    approver_ok: dict[str, bool] = {}
    decided: list[str] = []
    failed: list[ClientBulkDecisionItemError] = []
    for sub_id in payload.submission_ids:
        if sub_id in seen:
            continue
        seen.add(sub_id)
        submission = db.get(Submission, sub_id)
        if submission is None:
            failed.append(
                ClientBulkDecisionItemError(
                    submission_id=sub_id, detail="Envío no encontrado."
                )
            )
            continue
        if submission.client_id not in visible:
            if not is_internal_admin:
                failed.append(
                    ClientBulkDecisionItemError(
                        submission_id=sub_id, detail="Envío no encontrado."
                    )
                )
                continue
            # internal_admin break-glass — dedup'd to one row per (admin,
            # client) per 30-min window, so per-item calls are safe.
            _audit_cross_tenant_access(db, current, submission.client_id)
        if not is_internal_admin:
            cid = submission.client_id
            if cid not in approver_ok:
                approver_ok[cid] = _holds_live_approver_seat(db, current, cid)
            if not approver_ok[cid]:
                failed.append(
                    ClientBulkDecisionItemError(
                        submission_id=sub_id,
                        detail=(
                            "Tu acceso de Aprobador cambió. Vuelve a iniciar "
                            "sesión para continuar."
                        ),
                    )
                )
                continue
        try:
            apply_client_decision(
                db,
                submission=submission,
                action=payload.action,
                reason=payload.reason,
                client_user_id=current.user.id,
                commit=False,
            )
            decided.append(sub_id)
        except HTTPException as exc:
            failed.append(
                ClientBulkDecisionItemError(
                    submission_id=sub_id, detail=str(exc.detail)
                )
            )

    db.commit()
    return ClientBulkDecisionResponse(
        decided=decided,
        failed=failed,
        decided_count=len(decided),
        failed_count=len(failed),
    )


class ClientAcceptancePrefsResponse(BaseModel):
    auto_accept_valid: bool


class ClientAcceptancePrefsRequest(BaseModel):
    auto_accept_valid: bool


@router.get(
    "/acceptance-preferences",
    response_model=ClientAcceptancePrefsResponse,
    summary="Read the client's acceptance-axis preferences",
)
def client_get_acceptance_prefs(
    db: DbSession,
    current: ClientUser,
    client_id: str | None = Query(default=None),
) -> ClientAcceptancePrefsResponse:
    """Read-only — any client seat (Viewer included) may see the setting."""
    resolved = _resolve_client_id(db, current, requested=client_id)
    client = db.get(Client, resolved)
    return ClientAcceptancePrefsResponse(
        auto_accept_valid=bool(client and client.auto_accept_valid)
    )


@router.patch(
    "/acceptance-preferences",
    response_model=ClientAcceptancePrefsResponse,
    summary="Toggle auto-accept-on-valid for the client",
)
def client_set_acceptance_prefs(
    payload: ClientAcceptancePrefsRequest,
    db: DbSession,
    current: ClientApprover,
    client_id: str | None = Query(default=None),
) -> ClientAcceptancePrefsResponse:
    """Approver-only. Turning this on does NOT retroactively accept the
    existing backlog — it applies to validity decisions made from here on
    (the reviewer-path hook). Bulk-accept covers catching up the backlog."""
    resolved = _resolve_client_id(db, current, requested=client_id)
    _assert_live_client_approver(db, current, resolved)
    client = db.get(Client, resolved)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado."
        )
    before = client.auto_accept_valid
    client.auto_accept_valid = payload.auto_accept_valid
    if before != payload.auto_accept_valid:
        add_audit_event(
            db,
            action="client.auto_accept_valid_changed",
            entity_type="client",
            entity_id=resolved,
            actor_type="client_admin",
            actor_id=current.user.id,
            before={"auto_accept_valid": before},
            after={"auto_accept_valid": payload.auto_accept_valid},
        )
    db.commit()
    return ClientAcceptancePrefsResponse(auto_accept_valid=client.auto_accept_valid)


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
    # Phase 5 / Axis 2 — filter by the client-acceptance state
    # (``pending`` | ``accepted`` | ``rejected``). Powers the "what needs my
    # acceptance" worklist + the bulk-accept flow. Unknown values force an
    # empty result rather than 400 (mirrors the institution filter).
    client_acceptance: Annotated[str | None, Query(alias="client_acceptance")] = None,
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
        # "En revisión" is a collapsed label: three raw statuses
        # (recibido / pendiente_revision / prevalidado) all display as
        # "En revisión" to the client, so the filter must match all three
        # — an exact match on pendiente_revision silently hid ~2/3 of the
        # in-review queue (audit P2.11).
        if status_filter == "en_revision":
            filters.append(Submission.status.in_(_EN_REVISION_STATUSES))
        else:
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
    if client_acceptance:
        # Validate against the enum; an unknown value force-empties rather
        # than silently equality-matching a typo (which would read as "none
        # pending"). Uses the (client_id, client_acceptance) index from 0059.
        valid_acceptance = {a.value for a in ClientAcceptance}
        if client_acceptance not in valid_acceptance:
            filters.append(Submission.id == "__nonexistent__")
        else:
            filters.append(Submission.client_acceptance == client_acceptance)

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
                load_type=sub.load_type,
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
                client_acceptance=sub.client_acceptance,
                client_decided_at=sub.client_decided_at,
                client_decision_reason=sub.client_decision_reason,
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
    # Resolve scope from the NOTIFICATION ITSELF, not from a (possibly
    # absent) ?client_id. A client_admin managing multiple clients must be
    # able to mark read a notification belonging to any of their clients
    # without first selecting one. Mirrors ``client_get_submission_document``.
    row = db.get(ClientNotification, notification_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Notificacion no encontrada.")
    is_internal_admin = bool(STAFF_ROLES & set(current.roles))
    if not is_internal_admin:
        visible = _visible_client_ids_for_user(db, current.user.id)
        if row.client_id not in visible:
            # Same 404 shape as cross-tenant lookups — never confirm a
            # notification exists in a client the caller cannot see.
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Notificacion no encontrada."
            )
    target_id = row.client_id
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
    # Resolve the scope. When ?client_id is explicit we honor it (and the
    # guards in ``_resolve_client_id``). When it is omitted, a client_admin
    # managing multiple clients should clear ALL of their clients' unread
    # rows — not just the first — so we mark across every visible client id.
    target_id = _resolve_client_id(db, current, requested=client_id)
    if client_id:
        scope_ids = [target_id]
    else:
        is_internal_admin = bool(STAFF_ROLES & set(current.roles))
        visible = _visible_client_ids_for_user(db, current.user.id)
        # Internal admins without a default land here only via the
        # ``_resolve_client_id`` 400 above, so ``visible`` is non-empty for
        # the multi-client client_admin case we are fixing.
        scope_ids = visible if visible else [target_id]
        if is_internal_admin and not visible:
            scope_ids = [target_id]
    now = datetime.now(UTC)
    # Capture the ids with a cheap id-only SELECT (no full-row ORM hydration),
    # then flip them all in a single UPDATE instead of loading every unread row
    # into memory and mutating it one by one (a client that never reads
    # notifications can accumulate thousands) — perf audit P2-7. The ids are
    # still recorded in the audit payload for forensic traceability.
    unread_ids = list(
        db.scalars(
            select(ClientNotification.id).where(
                ClientNotification.client_id.in_(scope_ids),
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
                "scope_client_ids": scope_ids,
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
    assert_capability(db, target_id, Capability.BULK_EXPORT.value)
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
    assert_capability(db, target_id, Capability.BULK_EXPORT.value)
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
    # Demo plans cannot pull the full audit package (Phase B capability gate).
    assert_capability(db, target_id, Capability.EXPORT_AUDIT_PACKAGE.value)

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
            db, client_row, filters, manifest_pdf=manifest_pdf, entries=entries
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
