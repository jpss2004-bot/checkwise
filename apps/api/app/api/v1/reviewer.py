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

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth import CurrentUser, require_any_role
from app.constants.roles import MembershipRole
from app.constants.statuses import DocumentStatus, ReviewerAction
from app.db.session import get_db
from app.models import (
    Client,
    Document,
    DocumentStatusHistory,
    Institution,
    Requirement,
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


class DecisionResponse(BaseModel):
    submission_id: str
    previous_status: str
    new_status: str
    action: str
    reason: str | None
    observations: str | None = None
    decided_at: datetime
    reviewer_user_id: str


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
) -> QueueResponse:
    """List submissions waiting on a human decision.

    Default ordering is FIFO (oldest first) — the reviewer should clear
    the queue from the top. ``status`` defaults to *any of* the queue
    statuses; passing one narrows it. ``institution`` is the institution
    code (e.g. ``sat``, ``imss``).
    """

    statuses = (submission_status,) if submission_status else QUEUE_STATUSES
    stmt = (
        select(Submission)
        .where(Submission.status.in_(statuses))
        .order_by(Submission.created_at.asc())
        .limit(limit)
    )
    if institution:
        stmt = stmt.join(Institution, Submission.institution_id == Institution.id).where(
            Institution.code == institution
        )

    submissions = list(db.scalars(stmt))
    total = (
        db.scalar(
            select(__import__("sqlalchemy").func.count(Submission.id)).where(
                Submission.status.in_(statuses)
            )
        )
        or 0
    )

    items: list[QueueItem] = []
    now = utc_now()
    for sub in submissions:
        vendor = db.get(Vendor, sub.vendor_id)
        client = db.get(Client, sub.client_id)
        requirement = (
            db.get(Requirement, sub.requirement_id) if sub.requirement_id else None
        )
        institution_row = (
            db.get(Institution, sub.institution_id) if sub.institution_id else None
        )
        document = db.scalar(
            select(Document).where(Document.submission_id == sub.id).limit(1)
        )
        inspection_mismatch: str | None = None
        if document is not None:
            from app.models import DocumentInspection

            inspection_row = db.scalar(
                select(DocumentInspection)
                .where(DocumentInspection.document_id == document.id)
                .limit(1)
            )
            inspection_mismatch = (
                inspection_row.mismatch_reason if inspection_row else None
            )
        signal_count = (
            db.scalar(
                select(__import__("sqlalchemy").func.count(Validation.id)).where(
                    Validation.submission_id == sub.id,
                    Validation.severity.in_(("warning", "error")),
                )
            )
            or 0
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
                ),
                signal_count=int(signal_count),
                has_mismatch=bool(inspection_mismatch),
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
            select(__import__("sqlalchemy").func.count(Submission.id)).where(
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
            select(__import__("sqlalchemy").func.count(Submission.id)).where(
                Submission.status == DocumentStatus.RECHAZADO.value,
                Submission.updated_at >= cutoff,
            )
        )
        or 0
    )

    return QueueResponse(
        items=items,
        total=int(total),
        approved_last_7d_count=int(approved_count),
        rejected_last_7d_count=int(rejected_count),
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
        SubmissionDocumentSummary,
        SubmissionEvent,
        SubmissionHistoryEntry,
        SubmissionPeriodSummary,
        SubmissionPreviousAttempt,
        SubmissionReason,
        SubmissionRequirementSummary,
        _suggested_action,
    )
    from app.models import DocumentInspection

    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Submission not found")

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
        for prev in db.scalars(previous_query):
            prev_doc = db.scalar(
                select(Document).where(Document.submission_id == prev.id).limit(1)
            )
            previous_attempts.append(
                SubmissionPreviousAttempt(
                    submission_id=prev.id,
                    status=prev.status,
                    submitted_at=prev.created_at.isoformat(),
                    filename=prev_doc.original_filename if prev_doc else None,
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
        "document": (
            SubmissionDocumentSummary(
                document_id=document.id,
                filename=document.original_filename,
                sha256=document.sha256,
                size_bytes=document.size_bytes,
                page_count=inspection.page_count if inspection else None,
                has_text=inspection.has_text if inspection else None,
                is_probably_scanned=(
                    inspection.is_probably_scanned if inspection else None
                ),
                detected_institution=(
                    inspection.detected_institution if inspection else None
                ),
                detected_document_type=(
                    inspection.detected_document_type if inspection else None
                ),
                mismatch_reason=inspection.mismatch_reason if inspection else None,
            ).model_dump()
            if document is not None
            else None
        ),
        "reasons": [r.model_dump() for r in reasons],
        "events": [e.model_dump() for e in events],
        "history": [h.model_dump() for h in history],
        "previous_attempts": [a.model_dump() for a in previous_attempts],
        "supersedes_submission_id": submission.supersedes_submission_id,
        "superseded_by_submission_id": superseded_by_id,
        "suggested_action": _suggested_action(submission.status),
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Submission not found")

    result = apply_reviewer_decision(
        db,
        submission=submission,
        action=payload.action,
        reason=payload.reason,
        observations=payload.observations,
        reviewer_user_id=current.user.id,
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
            detail="Submission no encontrado.",
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
    disposition_header = (
        f'{disposition_kind}; filename="{document.original_filename}"'
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
    if presigned is not None:
        from fastapi.responses import RedirectResponse

        return RedirectResponse(presigned, status_code=status.HTTP_302_FOUND)

    from fastapi.responses import FileResponse

    path = storage.open_for_read(document.storage_key)
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
        headers={"Content-Disposition": disposition_header},
    )
