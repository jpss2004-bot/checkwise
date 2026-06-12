"""Reviewer queue + decision endpoints (Patch 7).

LegalShelf staff workflow: list submissions waiting on a human decision,
inspect each one, and record an approve / reject / clarify / exception
decision. Reuses ``ValidationEvent`` + ``DocumentStatusHistory`` so the
decision shows up in the existing audit trail and the provider's
correction-flow timeline without a new table.

RBAC: any of ``reviewer`` or ``internal_admin`` can read the queue and
file decisions. Patch 6's ``require_any_role`` does the gating.

Tenant scope: cross-tenant — the queue is global for internal users.
Per-client scoping arrives with Patch 8 (client_admin role).
"""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.v1.auth import CurrentUser, require_any_role
from app.constants.roles import MembershipRole
from app.constants.statuses import DocumentStatus, ReviewerAction
from app.core.config import settings
from app.db.session import get_db
from app.models import (
    Client,
    Document,
    DocumentStatusHistory,
    Institution,
    Submission,
    Validation,
    ValidationEvent,
    Vendor,
)
from app.models.entities import utc_now
from app.services.audit_log import add_audit_event
from app.services.storage import get_storage_service
from app.services.submission_workflow import apply_reviewer_decision

router = APIRouter(prefix="/reviewer", tags=["reviewer"])
DbSession = Annotated[Session, Depends(get_db)]
ReviewerDep = Annotated[
    CurrentUser,
    Depends(require_any_role(MembershipRole.REVIEWER, MembershipRole.INTERNAL_ADMIN)),
]


# Statuses that need a reviewer decision. ``requiere_aclaracion`` is
# already a decision (the ball is back in the provider's court) so it
# is intentionally not in the default queue.
QUEUE_STATUSES: tuple[str, ...] = (
    DocumentStatus.RECIBIDO.value,
    DocumentStatus.PENDIENTE_REVISION.value,
    DocumentStatus.PREVALIDADO.value,
    DocumentStatus.POSIBLE_MISMATCH.value,
)

# Terminal-status gating now lives in ``submission_workflow.is_terminal_status``;
# the local tuple this module used to export has been removed.


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class QueueRequirement(BaseModel):
    requirement_code: str | None
    name: str | None
    institution: str | None


class QueuePeriod(BaseModel):
    period_key: str | None
    code: str | None


class QueueProvider(BaseModel):
    vendor_name: str
    vendor_rfc: str | None
    client_name: str
    # Item 5 follow-up — surface the ids so the reviewer queue can
    # render the vendor name as a link to ``/client/vendors/{id}?client_id=…``.
    # Optional/nullable so older client builds that ignore them stay
    # compatible.
    vendor_id: str | None = None
    client_id: str | None = None


class QueueItem(BaseModel):
    submission_id: str
    status: str
    submitted_at: datetime
    age_hours: int
    requirement: QueueRequirement
    period: QueuePeriod
    provider: QueueProvider
    signal_count: int
    has_mismatch: bool
    # Phase A — document-revalidation authenticity verdict from the
    # intake forensics pass ("clean" | "suspicious" | "high_risk").
    # ``None`` means not analyzed (legacy rows / analyzer failure), so
    # older client builds that ignore the field stay compatible.
    authenticity_risk: str | None = None
    rfc_alignment: str | None = None


class QueueResponse(BaseModel):
    items: list[QueueItem]
    total: int
    next_cursor: str | None = None
    # Phase 9 / Slice 9A — terminal-state counters surfaced as a
    # small stat strip above the actionable queue. Window is a
    # rolling 7 days against ``Submission.updated_at`` so the
    # numbers reflect recent reviewer activity (not lifetime
    # totals). The queue itself stays actionable-only; these are
    # context for "what got cleared this week", not part of the
    # filter set.
    approved_last_7d_count: int = 0
    rejected_last_7d_count: int = 0


class QueueFacetClient(BaseModel):
    id: str
    name: str


class QueueFacetVendor(BaseModel):
    id: str
    client_id: str
    name: str
    rfc: str | None


class QueueFacetsResponse(BaseModel):
    clients: list[QueueFacetClient]
    vendors: list[QueueFacetVendor]


DECISION_ACTIONS: tuple[str, ...] = tuple(action.value for action in ReviewerAction)


class DecisionRequest(BaseModel):
    action: Literal["approve", "reject", "request_clarification", "mark_exception"]
    reason: str | None = Field(default=None, max_length=2000)
    # Phase 9 / Slice 9A — optional "observaciones para el proveedor"
    # rendered as a distinct line in the notification body alongside
    # the formal reason. The formal reason stays unique in
    # DocumentStatusHistory.reason / ValidationEvent.message so the
    # audit timeline keeps reading cleanly; observations go into
    # AuditLog.metadata + the notification body only.
    observations: str | None = Field(default=None, max_length=2000)
    # Phase E — suggestion-acceptance telemetry. When the detail
    # endpoint showed an ``approval_suggestion`` and the UI knows
    # whether the reviewer followed it, it reports that here. The flag
    # only lands in the decision's audit-log metadata (acceptance-rate
    # measurement for the auto-approve unlock case); it never changes
    # decision behavior. ``None`` (the default) means "no suggestion
    # interaction reported" and writes nothing.
    accepted_suggestion: bool | None = None


class DecisionResponse(BaseModel):
    submission_id: str
    previous_status: str
    new_status: str
    action: str
    reason: str | None
    observations: str | None = None
    decided_at: datetime
    reviewer_user_id: str
    # Reviewer-flow ergonomics — id of the oldest submission still
    # waiting in the queue after this decision, so the UI can offer a
    # "siguiente pendiente" jump without an extra round-trip. ``None``
    # when the queue is empty.
    next_pending_submission_id: str | None = None


# ---------------------------------------------------------------------------
# Queue cursor (keyset pagination)
# ---------------------------------------------------------------------------


def _encode_queue_cursor(created_at: datetime, submission_id: str) -> str:
    """Opaque keyset cursor: base64 of ``"<created_at isoformat>|<id>"``."""
    raw = f"{created_at.isoformat()}|{submission_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_queue_cursor(cursor: str) -> tuple[datetime, str]:
    """Inverse of :func:`_encode_queue_cursor`; 422 on garbage input."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        created_raw, sep, submission_id = raw.partition("|")
        if not sep or not submission_id:
            raise ValueError("malformed cursor payload")
        return datetime.fromisoformat(created_raw), submission_id
    except (ValueError, binascii.Error, UnicodeError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cursor de paginación inválido.",
        ) from exc


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


@router.get("/queue", response_model=QueueResponse)
def get_queue(
    db: DbSession,
    current: ReviewerDep,  # noqa: ARG001 - enforces RBAC
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    institution: Annotated[str | None, Query()] = None,
    submission_status: Annotated[str | None, Query(alias="status")] = None,
    risk: Annotated[
        Literal["clean", "suspicious", "high_risk"] | None, Query()
    ] = None,
    client_id: Annotated[str | None, Query()] = None,
    vendor_id: Annotated[str | None, Query()] = None,
    rfc: Annotated[
        Literal["match", "homoclave_mismatch", "mismatch", "absent", "no_expected"]
        | None,
        Query(),
    ] = None,
    cursor: Annotated[str | None, Query()] = None,
) -> QueueResponse:
    """List submissions waiting on a human decision.

    Default ordering is FIFO (oldest first) — the reviewer should clear
    the queue from the top. ``status`` defaults to *any of* the queue
    statuses; passing one narrows it. ``institution`` is the institution
    code (e.g. ``sat``, ``imss``). ``risk`` narrows to submissions whose
    document carries that authenticity verdict from the intake
    forensics pass. ``cursor`` is the opaque keyset cursor from a
    previous page's ``next_cursor``; pass it back to get the next page
    under the same FIFO ordering.
    """

    # Imported locally (matching the batch-lookup below) to dodge a
    # circular dependency through the API package's router init order.
    from app.models import DocumentInspection

    statuses = (submission_status,) if submission_status else QUEUE_STATUSES
    # Eager-load every relationship the per-row build touches so the queue
    # is a handful of batched queries instead of ~7 lookups per submission
    # (the original N+1 made the page seconds-slow on a networked DB).
    # ``id`` is the deterministic tiebreak for equal ``created_at`` so the
    # keyset cursor never skips or repeats rows.
    stmt = (
        select(Submission)
        .where(Submission.status.in_(statuses))
        .order_by(Submission.created_at.asc(), Submission.id.asc())
        .options(
            selectinload(Submission.vendor),
            selectinload(Submission.client),
            selectinload(Submission.requirement),
            selectinload(Submission.institution),
            selectinload(Submission.period),
            selectinload(Submission.documents),
            selectinload(Submission.validations),
        )
    )
    # ``count(distinct …)`` so the optional risk filter's join through
    # Document never double-counts a multi-document submission; without
    # joins it is equivalent to ``count(id)``.
    count_stmt = select(func.count(func.distinct(Submission.id))).where(
        Submission.status.in_(statuses)
    )
    if institution:
        stmt = stmt.join(Institution, Submission.institution_id == Institution.id).where(
            Institution.code == institution
        )
        count_stmt = count_stmt.join(
            Institution, Submission.institution_id == Institution.id
        ).where(Institution.code == institution)

    if client_id:
        stmt = stmt.where(Submission.client_id == client_id)
        count_stmt = count_stmt.where(Submission.client_id == client_id)

    if vendor_id:
        stmt = stmt.where(Submission.vendor_id == vendor_id)
        count_stmt = count_stmt.where(Submission.vendor_id == vendor_id)

    inspection_filters = []
    if risk:
        inspection_filters.append(DocumentInspection.authenticity_risk == risk)
    if rfc:
        inspection_filters.append(DocumentInspection.rfc_alignment == rfc)
    if inspection_filters:
        # Server-side document-inspection filters: join through the
        # submission's documents to their inspection verdicts.
        # ``distinct()`` guards against duplicate rows when a multi-file
        # submission has more than one matching document.
        stmt = (
            stmt.join(Document, Document.submission_id == Submission.id)
            .join(
                DocumentInspection,
                DocumentInspection.document_id == Document.id,
            )
            .where(*inspection_filters)
            .distinct()
        )
        count_stmt = (
            count_stmt.join(Document, Document.submission_id == Submission.id)
            .join(
                DocumentInspection,
                DocumentInspection.document_id == Document.id,
            )
            .where(*inspection_filters)
        )

    if cursor:
        cursor_created_at, cursor_id = _decode_queue_cursor(cursor)
        # Keyset filter: strictly after (created_at, id). Spelled as the
        # OR expansion (instead of a row-value tuple comparison) so the
        # SQLite test backend evaluates it identically to Postgres.
        stmt = stmt.where(
            or_(
                Submission.created_at > cursor_created_at,
                and_(
                    Submission.created_at == cursor_created_at,
                    Submission.id > cursor_id,
                ),
            )
        )

    # Fetch one extra row past ``limit``: a cheap "is there a next page"
    # probe without a second COUNT under the cursor filter.
    rows = list(db.scalars(stmt.limit(limit + 1)))
    has_more = len(rows) > limit
    submissions = rows[:limit]

    # ``total`` is the real number of rows matching the current filters
    # (status/institution), independent of limit/cursor.
    total = db.scalar(count_stmt) or 0

    next_cursor: str | None = None
    if has_more and submissions:
        last = submissions[-1]
        next_cursor = _encode_queue_cursor(last.created_at, last.id)

    # Batch the document-inspection lookup: collect the first document per
    # queued submission, then fetch all their inspections in one IN query
    # (was one SELECT per row). The row carries both the mismatch reason
    # and the Phase-A authenticity verdict.
    first_doc_by_sub: dict[str, Document] = {
        sub.id: sub.documents[0] for sub in submissions if sub.documents
    }
    inspection_by_doc: dict[str, DocumentInspection] = {}
    if first_doc_by_sub:
        doc_ids = [doc.id for doc in first_doc_by_sub.values()]
        for insp in db.scalars(
            select(DocumentInspection).where(
                DocumentInspection.document_id.in_(doc_ids)
            )
        ):
            inspection_by_doc.setdefault(insp.document_id, insp)

    items: list[QueueItem] = []
    now = utc_now()
    for sub in submissions:
        vendor = sub.vendor
        client = sub.client
        requirement = sub.requirement
        institution_row = sub.institution
        document = first_doc_by_sub.get(sub.id)
        inspection = (
            inspection_by_doc.get(document.id) if document is not None else None
        )
        inspection_mismatch: str | None = (
            inspection.mismatch_reason if inspection is not None else None
        )
        signal_count = sum(
            1 for v in sub.validations if v.severity in ("warning", "error")
        )

        created_at = sub.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        age_seconds = (now - created_at).total_seconds()
        items.append(
            QueueItem(
                submission_id=sub.id,
                status=sub.status,
                submitted_at=sub.created_at,
                age_hours=max(0, int(age_seconds // 3600)),
                requirement=QueueRequirement(
                    requirement_code=sub.requirement_code
                    or (requirement.code if requirement else None),
                    name=requirement.name if requirement else None,
                    institution=institution_row.code if institution_row else None,
                ),
                period=QueuePeriod(
                    period_key=sub.period_key,
                    code=sub.period.code if sub.period else None,
                ),
                provider=QueueProvider(
                    vendor_name=vendor.name if vendor else "—",
                    vendor_rfc=vendor.rfc if vendor else None,
                    client_name=client.name if client else "—",
                    vendor_id=vendor.id if vendor else None,
                    client_id=client.id if client else None,
                ),
                signal_count=int(signal_count),
                has_mismatch=bool(inspection_mismatch),
                authenticity_risk=(
                    inspection.authenticity_risk if inspection is not None else None
                ),
                rfc_alignment=(
                    inspection.rfc_alignment if inspection is not None else None
                ),
            )
        )

    # Slice 9A — rolling-7-day counters for the stat strip above the
    # queue. Counts terminal-state submissions whose ``updated_at`` is
    # within the window, which under the workflow service tracks the
    # decision time (``Submission.updated_at`` is bumped on each
    # transition). Approved + Excepción legal both fold into the
    # "approved" bucket — they both resolve the slot positively from
    # the operator's perspective.
    from datetime import timedelta

    cutoff = utc_now() - timedelta(days=7)
    approved_count = (
        db.scalar(
            select(func.count(Submission.id)).where(
                Submission.status.in_((
                    DocumentStatus.APROBADO.value,
                    DocumentStatus.EXCEPCION_LEGAL.value,
                )),
                Submission.updated_at >= cutoff,
            )
        )
        or 0
    )
    rejected_count = (
        db.scalar(
            select(func.count(Submission.id)).where(
                Submission.status == DocumentStatus.RECHAZADO.value,
                Submission.updated_at >= cutoff,
            )
        )
        or 0
    )

    return QueueResponse(
        items=items,
        total=int(total),
        next_cursor=next_cursor,
        approved_last_7d_count=int(approved_count),
        rejected_last_7d_count=int(rejected_count),
    )


@router.get("/queue/facets", response_model=QueueFacetsResponse)
def get_queue_facets(
    db: DbSession,
    current: ReviewerDep,  # noqa: ARG001 - enforces RBAC
) -> QueueFacetsResponse:
    """Return client/provider filter options scoped to actionable queue rows."""

    client_rows = db.execute(
        select(Client.id, Client.name)
        .join(Submission, Submission.client_id == Client.id)
        .where(Submission.status.in_(QUEUE_STATUSES))
        .distinct()
        .order_by(Client.name.asc())
    ).all()
    vendor_rows = db.execute(
        select(Vendor.id, Vendor.client_id, Vendor.name, Vendor.rfc)
        .join(Submission, Submission.vendor_id == Vendor.id)
        .where(Submission.status.in_(QUEUE_STATUSES))
        .distinct()
        .order_by(Vendor.name.asc())
    ).all()
    return QueueFacetsResponse(
        clients=[QueueFacetClient(id=row.id, name=row.name) for row in client_rows],
        vendors=[
            QueueFacetVendor(
                id=row.id,
                client_id=row.client_id,
                name=row.name,
                rfc=row.rfc,
            )
            for row in vendor_rows
        ],
    )


# ---------------------------------------------------------------------------
# Detail (reuses portal's SubmissionDetailResponse shape, but accessed via
# JWT so cross-tenant reviewers can read it without a workspace token).
# ---------------------------------------------------------------------------


@router.get("/submissions/{submission_id}")
def get_submission(
    submission_id: str,
    db: DbSession,
    current: ReviewerDep,  # noqa: ARG001 - enforces RBAC
) -> dict:
    """Reviewer-side full submission detail.

    Returns the same structural payload as the provider's
    ``GET /portal/.../submissions/{id}`` so the reviewer detail page
    can reuse the rendering primitives. The difference: no
    ``X-Workspace-Token`` requirement; the reviewer JWT plus the
    ``reviewer`` (or ``internal_admin``) role is enough.
    """
    # Import locally to dodge a circular dependency through the API
    # package's ``router.py`` initialisation order.
    from app.api.v1.portal import (
        SubmissionEvent,
        SubmissionHistoryEntry,
        SubmissionPeriodSummary,
        SubmissionPreviousAttempt,
        SubmissionReason,
        SubmissionRequirementSummary,
        _suggested_action,
    )
    from app.models import DocumentInspection, ProviderWorkspace

    submission = db.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .options(
            selectinload(Submission.vendor),
            selectinload(Submission.client),
            selectinload(Submission.requirement),
            selectinload(Submission.institution),
            selectinload(Submission.period),
            selectinload(Submission.requirement_version),
        )
    )
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Envío no encontrado.")

    # Vendor identity context — the EXPECTED RFC the frontend compares
    # against the OCR-detected one, plus the ids needed to deep-link
    # into the client/vendor admin views. One scalar lookup resolves the
    # workspace tying this vendor to this client (no per-field N+1).
    vendor = submission.vendor
    client = submission.client
    workspace_id = db.scalar(
        select(ProviderWorkspace.id)
        .where(
            ProviderWorkspace.vendor_id == submission.vendor_id,
            ProviderWorkspace.client_id == submission.client_id,
        )
        .limit(1)
    )

    document = db.scalar(
        select(Document).where(Document.submission_id == submission.id).limit(1)
    )
    inspection = None
    if document is not None:
        inspection = db.scalar(
            select(DocumentInspection)
            .where(DocumentInspection.document_id == document.id)
            .limit(1)
        )

    validations = list(
        db.scalars(
            select(Validation)
            .where(Validation.submission_id == submission.id)
            .order_by(Validation.created_at.asc())
        )
    )
    reasons = [
        SubmissionReason(
            rule_code=v.rule_code,
            severity=v.severity,
            message=v.message,
            requires_human_review=v.requires_human_review,
        )
        for v in validations
        if v.severity in {"warning", "error"} or v.requires_human_review
    ]

    events = [
        SubmissionEvent(
            event_type=ev.event_type,
            result=ev.result,
            severity=ev.severity,
            message=ev.message,
            confidence=ev.confidence,
            actor_type=ev.actor_type,
            occurred_at=ev.created_at.isoformat(),
        )
        for ev in db.scalars(
            select(ValidationEvent)
            .where(ValidationEvent.submission_id == submission.id)
            .order_by(ValidationEvent.created_at.asc())
        )
    ]
    history = [
        SubmissionHistoryEntry(
            from_status=h.from_status,
            to_status=h.to_status,
            reason=h.reason,
            actor=h.actor,
            occurred_at=h.created_at.isoformat(),
        )
        for h in db.scalars(
            select(DocumentStatusHistory)
            .where(DocumentStatusHistory.submission_id == submission.id)
            .order_by(DocumentStatusHistory.created_at.asc())
        )
    ]

    previous_attempts: list[SubmissionPreviousAttempt] = []
    if submission.requirement_code and submission.period_key:
        previous_query = (
            select(Submission)
            .where(
                Submission.client_id == submission.client_id,
                Submission.vendor_id == submission.vendor_id,
                Submission.requirement_code == submission.requirement_code,
                Submission.period_key == submission.period_key,
                Submission.id != submission.id,
            )
            .order_by(Submission.created_at.desc())
            .limit(10)
        )
        prev_subs = list(db.scalars(previous_query))
        # One batched lookup for the first document of each prior attempt,
        # instead of a query per attempt (audit 2026-06-09, P1-A N+1).
        prev_filename_by_sub: dict[str, str] = {}
        if prev_subs:
            for doc in db.scalars(
                select(Document).where(
                    Document.submission_id.in_([p.id for p in prev_subs])
                )
            ):
                prev_filename_by_sub.setdefault(
                    doc.submission_id, doc.original_filename
                )
        for prev in prev_subs:
            previous_attempts.append(
                SubmissionPreviousAttempt(
                    submission_id=prev.id,
                    status=prev.status,
                    submitted_at=prev.created_at.isoformat(),
                    filename=prev_filename_by_sub.get(prev.id),
                )
            )

    # Phase 4 — replacement lineage pointers. Same shape as the
    # provider-side detail endpoint so the reviewer UI can render the
    # same "replaces" / "replaced by" affordances.
    superseded_by_id = db.scalar(
        select(Submission.id).where(
            Submission.supersedes_submission_id == submission.id,
            Submission.client_id == submission.client_id,
            Submission.vendor_id == submission.vendor_id,
        )
    )

    return {
        "submission_id": submission.id,
        "workspace_id": "",  # not workspace-scoped here
        "status": submission.status,
        "load_type": submission.load_type,
        "submitted_at": submission.created_at.isoformat(),
        "comments": submission.comments,
        "vendor": {
            "vendor_id": vendor.id if vendor else None,
            "vendor_name": vendor.name if vendor else None,
            # Expected RFC — the frontend compares this against the
            # OCR-detected RFC from the document inspection.
            "vendor_rfc": vendor.rfc if vendor else None,
            "persona_type": vendor.persona_type if vendor else None,
            "client_id": client.id if client else None,
            "client_name": client.name if client else None,
            "workspace_id": workspace_id,
        },
        "requirement": SubmissionRequirementSummary(
            code=submission.requirement.code if submission.requirement else None,
            name=submission.requirement.name if submission.requirement else None,
            institution=submission.institution.code if submission.institution else None,
            load_type=submission.load_type,
            requirement_code=submission.requirement_code,
            requirement_version=(
                submission.requirement_version.version
                if submission.requirement_version
                else None
            ),
        ).model_dump(),
        "period": SubmissionPeriodSummary(
            code=submission.period.code if submission.period else None,
            period_key=submission.period_key,
            period_type=submission.period.period_type if submission.period else None,
        ).model_dump(),
        "document": _build_reviewer_document_payload(document, inspection),
        "reasons": [r.model_dump() for r in reasons],
        "events": [e.model_dump() for e in events],
        "history": [h.model_dump() for h in history],
        "previous_attempts": [a.model_dump() for a in previous_attempts],
        "supersedes_submission_id": submission.supersedes_submission_id,
        "superseded_by_submission_id": superseded_by_id,
        "suggested_action": _suggested_action(submission.status),
        # Phase A — document-revalidation authenticity block. Reviewer-
        # facing only (the provider portal never exposes it). ``analyzed``
        # is False for legacy rows or when the forensics pass failed open
        # at intake; the UI renders that as "sin analizar".
        "authenticity": {
            "risk": inspection.authenticity_risk if inspection else None,
            "reasons": list(inspection.risk_reasons or []) if inspection else [],
            "forensics": inspection.forensics if inspection else None,
            "analyzed": bool(
                inspection is not None and inspection.authenticity_risk is not None
            ),
        },
        # Phase B — QR/folio verification anchors. Reviewer-facing only.
        # ``analyzed`` is False for legacy rows (NULL column) — the UI
        # renders that as "sin analizar". The verification risk reasons
        # already live inside ``authenticity.reasons`` (merged at
        # intake); this block carries the extracted anchors themselves.
        "verification": _build_verification_payload(inspection),
        # Phase 2 — shadow-analysis comparison block. Only present on
        # this reviewer endpoint; the provider-facing portal endpoint
        # never exposes shadow data. ``shadow.completed_at IS None``
        # signals "análisis pendiente" to the UI; the heuristic block
        # is a denormalized copy of the inspection columns so the
        # comparison card can render before the shadow call finishes.
        "shadow_analysis": _build_shadow_analysis_payload(inspection),
        # Phase E — advisory approval suggestion. Computed from data
        # already loaded above (no extra queries). ``None`` only when
        # there is no inspection row at all; otherwise the block always
        # carries the per-criterion flags so the UI can explain WHY a
        # document is (not) suggested. Reviewer-facing and advisory
        # only — it never changes a status.
        "approval_suggestion": _build_approval_suggestion(submission, inspection),
    }


def _build_reviewer_document_payload(document, inspection) -> dict | None:  # noqa: ANN001
    from app.api.v1.portal import SubmissionDocumentSummary

    if document is None:
        return None
    payload = SubmissionDocumentSummary(
        document_id=document.id,
        filename=document.original_filename,
        sha256=document.sha256,
        size_bytes=document.size_bytes,
        page_count=inspection.page_count if inspection else None,
        has_text=inspection.has_text if inspection else None,
        is_probably_scanned=(inspection.is_probably_scanned if inspection else None),
        detected_institution=(inspection.detected_institution if inspection else None),
        detected_document_type=(
            inspection.detected_document_type if inspection else None
        ),
        mismatch_reason=inspection.mismatch_reason if inspection else None,
    ).model_dump()
    payload.update(
        {
            "detected_rfcs": list(inspection.detected_rfcs or [])
            if inspection
            else [],
            "expected_rfc": inspection.expected_rfc if inspection else None,
            "rfc_alignment": inspection.rfc_alignment if inspection else None,
        }
    )
    return payload


def _build_approval_suggestion(submission, inspection) -> dict | None:  # noqa: ANN001
    """Shape the Phase-E approval-suggestion block for the reviewer detail.

    ``suggested`` is True only when ALL of:

    * best available confidence (shadow preferred, heuristic fallback)
      ≥ ``AUTO_APPROVE_SUGGEST_CONFIDENCE``;
    * the authenticity verdict is an explicit ``clean`` (NULL = not
      analyzed = not suggestible);
    * the requirement cadence is recurring (mensual/…/anual — never
      alta_inicial / unica_vez / evento);
    * the submission is still in a reviewable queue status.

    Legacy rows without an inspection return ``None``.
    """
    from app.services.auto_approval import (
        best_confidence,
        is_recurring_cadence,
        resolve_submission_cadence,
    )

    if inspection is None:
        return None

    confidence, confidence_source = best_confidence(inspection)
    match_ok = (
        confidence is not None
        and confidence >= settings.AUTO_APPROVE_SUGGEST_CONFIDENCE
    )
    risk_clean = inspection.authenticity_risk == "clean"
    recurring = is_recurring_cadence(resolve_submission_cadence(submission))
    in_queue = submission.status in QUEUE_STATUSES
    suggested = match_ok and risk_clean and recurring and in_queue

    if suggested:
        source_label = "IA" if confidence_source == "shadow" else "heurística"
        detail_es = (
            f"Coincidencia {round(confidence * 100)}% ({source_label}), "
            "autenticidad limpia y documento recurrente — sugerimos aprobar."
        )
    else:
        missing: list[str] = []
        if not match_ok:
            missing.append(
                "confianza de coincidencia insuficiente"
                if confidence is not None
                else "sin confianza de coincidencia disponible"
            )
        if not risk_clean:
            missing.append("autenticidad no verificada como limpia")
        if not recurring:
            missing.append("el documento no es recurrente")
        if not in_queue:
            missing.append("el envío ya no está en cola de revisión")
        detail_es = "Sin sugerencia de aprobación: " + "; ".join(missing) + "."

    return {
        "suggested": suggested,
        "confidence": confidence,
        "confidence_source": confidence_source,
        "criteria": {
            "match_ok": match_ok,
            "risk_clean": risk_clean,
            "recurring": recurring,
        },
        "detail_es": detail_es,
    }


def _build_verification_payload(inspection) -> dict:  # noqa: ANN001
    """Shape the Phase-B QR/folio block for the reviewer detail.

    Legacy rows (no inspection, or inspection without the
    ``verification`` column populated) come back empty with
    ``analyzed=False``.
    """
    verification = inspection.verification if inspection is not None else None
    if not verification:
        return {"qr_codes": [], "folios": [], "analyzed": False}
    return {
        "qr_codes": list(verification.get("qr_codes") or []),
        "folios": list(verification.get("folios") or []),
        "analyzed": True,
    }


def _build_shadow_analysis_payload(inspection) -> dict | None:  # noqa: ANN001
    """Shape the shadow-mode comparison payload for the admin UI.

    Returns ``None`` when no inspection row exists (defensive — every
    intake creates one, but reviewer tooling sometimes inspects
    historical rows that predate the Phase-2 columns).

    The payload is intentionally flat-ish so the React card can render
    a single object without juggling nested optionals.
    """
    if inspection is None:
        return None
    return {
        "heuristic": {
            "provider_id": "heuristic:v1",
            "completed_at": inspection.updated_at.isoformat()
            if getattr(inspection, "updated_at", None)
            else None,
            "signals": {
                "detected_institution": inspection.detected_institution,
                "detected_document_type": inspection.detected_document_type,
                "detected_rfcs": list(inspection.detected_rfcs or []),
                "expected_rfc": inspection.expected_rfc,
                "rfc_alignment": inspection.rfc_alignment,
                "detected_dates": list(inspection.detected_dates or []),
                "period_mentions": list(inspection.period_mentions or []),
                "requirement_match_confidence": inspection.requirement_match_confidence,
                "mismatch_reason": inspection.mismatch_reason,
            },
        },
        "shadow": {
            "provider_id": inspection.shadow_provider_id,
            "prompt_version": inspection.shadow_prompt_version,
            "completed_at": inspection.shadow_completed_at.isoformat()
            if inspection.shadow_completed_at
            else None,
            "latency_ms": inspection.shadow_latency_ms,
            "error": inspection.shadow_error,
            "confidence": inspection.shadow_confidence,
            "signals": inspection.shadow_signals,
        },
    }


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


@router.post(
    "/submissions/{submission_id}/decision",
    response_model=DecisionResponse,
)
def submit_decision(
    submission_id: str,
    payload: DecisionRequest,
    db: DbSession,
    current: ReviewerDep,
) -> DecisionResponse:
    """Record a reviewer decision via the workflow state machine.

    Thin wrapper over :func:`app.services.submission_workflow.apply_reviewer_decision`.
    Validation, status mutation, ``DocumentStatusHistory``,
    ``ValidationEvent`` and ``AuditLog`` writes all live in the workflow
    service so the same transition logic runs for every caller. Errors
    bubble up from the service:

    - Unknown submission -> 404.
    - Submission already in a terminal status -> 409.
    - Decision attempted from an unsupported source status -> 409.
    - ``reject`` / ``request_clarification`` / ``mark_exception``
      without a ``reason`` -> 422.
    """
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Envío no encontrado.")

    result = apply_reviewer_decision(
        db,
        submission=submission,
        action=payload.action,
        reason=payload.reason,
        observations=payload.observations,
        reviewer_user_id=current.user.id,
        accepted_suggestion=payload.accepted_suggestion,
    )

    # Phase 7 cutover (Slice C) — fire the unified-fabric envelope
    # alongside the legacy notifications the workflow service
    # already wrote. The emit handles its own idempotency via
    # ``notification_dispatch`` so a retry against the same
    # submission+action is a no-op. Failures never break the
    # decision response — the workflow row + history already landed.
    try:
        import logging

        from app.services.notifications import emit_reviewer_decision

        emit_reviewer_decision(
            db,
            submission=submission,
            action=payload.action,
            reason=payload.reason,
            mode="active",
        )
        db.flush()
    except Exception:  # pragma: no cover — defensive during cutover
        logging.getLogger("checkwise.reviewer").exception(
            "notif_emit_failed event=submission.reviewer_decision submission=%s",
            submission_id,
        )

    # "Siguiente pendiente" pointer — the oldest submission still
    # waiting in the queue (FIFO, same ordering as GET /reviewer/queue),
    # excluding the row just decided. One cheap scalar query; ``None``
    # means the queue is empty and the UI can celebrate.
    next_pending_id = db.scalar(
        select(Submission.id)
        .where(
            Submission.status.in_(QUEUE_STATUSES),
            Submission.id != submission.id,
        )
        .order_by(Submission.created_at.asc(), Submission.id.asc())
        .limit(1)
    )

    return DecisionResponse(
        submission_id=result.submission_id,
        previous_status=result.previous_status,
        new_status=result.new_status,
        action=result.action,
        reason=result.reason,
        observations=result.observations,
        decided_at=result.decided_at,
        reviewer_user_id=result.reviewer_user_id,
        next_pending_submission_id=next_pending_id,
    )


@router.get(
    "/submissions/{submission_id}/document",
    summary="Stream the PDF stored for a submission (reviewer/admin)",
)
def get_submission_document(
    submission_id: str,
    db: DbSession,
    current: ReviewerDep,
    download: bool = False,
    proxy: bool = False,
) -> Response:
    """Serve the PDF a provider uploaded so the reviewer can see it
    inline before deciding.

    Mirrors :func:`app.api.v1.portal.get_workspace_submission_document`
    but with a reviewer/admin gate instead of the per-workspace tenant
    guard. ``?download=1`` emits the attachment disposition and writes
    a ``reviewer.document_downloaded`` audit row; the default inline
    mode is unaudited so iframe reloads do not flood the audit log.
    """
    submission = db.get(Submission, submission_id)
    if submission is None:
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
    disposition_header = _content_disposition_header(
        disposition_kind,
        document.original_filename,
    )

    if download:
        add_audit_event(
            db,
            action="reviewer.document_downloaded",
            entity_type="submission",
            entity_id=submission.id,
            actor_type="reviewer",
            actor_id=current.user.id,
            metadata={
                "document_id": document.id,
                "filename": document.original_filename,
                "size_bytes": document.size_bytes,
                "requirement_code": submission.requirement_code,
                "period_key": submission.period_key,
            },
        )
        db.commit()

    storage = get_storage_service()
    presigned = storage.presigned_download_url(
        document.storage_key,
        content_disposition=disposition_header,
    )
    if presigned is not None and not proxy:
        from fastapi.responses import RedirectResponse

        return RedirectResponse(presigned, status_code=status.HTTP_302_FOUND)

    from fastapi.responses import FileResponse

    try:
        path = storage.open_for_read(document.storage_key)
    except Exception as exc:  # noqa: BLE001 - storage backends raise backend-specific errors
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento no disponible en almacenamiento.",
        ) from exc
    # Match the portal endpoint: a missing storage artifact (orphaned
    # key from a seed fixture or a restore drift) degrades to a clean
    # 404 instead of leaking a 500 stack trace into the iframe.
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento no disponible en almacenamiento.",
        )
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=document.original_filename,
        content_disposition_type=disposition_kind,
    )


def _content_disposition_header(disposition_kind: str, filename: str) -> str:
    """Build an ASCII-safe Content-Disposition value for signed storage URLs."""
    safe_fallback = "".join(
        char if 32 <= ord(char) < 127 and char not in {'"', "\\", ";"} else "_"
        for char in filename
    ).strip() or "documento.pdf"
    return (
        f'{disposition_kind}; filename="{safe_fallback}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
