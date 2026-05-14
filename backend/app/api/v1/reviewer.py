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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth import CurrentUser, require_any_role
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
from app.services.validation_events import add_validation_event

router = APIRouter(prefix="/reviewer", tags=["reviewer"])
DbSession = Annotated[Session, Depends(get_db)]
ReviewerDep = Annotated[CurrentUser, Depends(require_any_role("reviewer", "internal_admin"))]


# Statuses that need a reviewer decision. ``requiere_aclaracion`` is
# already a decision (the ball is back in the provider's court) so it
# is intentionally not in the default queue.
QUEUE_STATUSES: tuple[str, ...] = (
    "recibido",
    "pendiente_revision",
    "prevalidado",
    "posible_mismatch",
)

# Statuses that count as a "resolved" decision (terminal until a new
# submission arrives for the same slot).
RESOLVED_STATUSES: tuple[str, ...] = ("aprobado", "rechazado", "excepcion_legal")


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


DECISION_ACTIONS: tuple[str, ...] = (
    "approve",
    "reject",
    "request_clarification",
    "mark_exception",
)


_ACTION_TO_STATUS: dict[str, str] = {
    "approve": "aprobado",
    "reject": "rechazado",
    "request_clarification": "requiere_aclaracion",
    "mark_exception": "excepcion_legal",
}


_ACTION_REQUIRES_REASON: set[str] = {
    "reject",
    "request_clarification",
    "mark_exception",
}


class DecisionRequest(BaseModel):
    action: Literal["approve", "reject", "request_clarification", "mark_exception"]
    reason: str | None = Field(default=None, max_length=2000)


class DecisionResponse(BaseModel):
    submission_id: str
    previous_status: str
    new_status: str
    action: str
    reason: str | None
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

    return QueueResponse(items=items, total=int(total))


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
    """Record a reviewer decision.

    Writes:
    - ``Submission.status`` -> the new status mapped from ``action``.
    - ``DocumentStatusHistory`` row (``from`` -> ``to`` with the reason
      and ``actor="reviewer:<user_id>"``).
    - ``ValidationEvent`` (``event_type="reviewer_decision"``,
      ``result=action``, ``message=reason``, ``actor_type="reviewer"``).

    Rejects:
    - Unknown submission -> 404.
    - Already-resolved submission (``aprobado`` / ``rechazado`` /
      ``excepcion_legal``) -> 409. Re-deciding requires the provider
      to submit a new attempt; this avoids accidental double-clicks
      mutating a settled audit record.
    - ``reject`` / ``request_clarification`` / ``mark_exception``
      without a ``reason`` -> 422.
    """

    reason = (payload.reason or "").strip() or None
    if payload.action in _ACTION_REQUIRES_REASON and not reason:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"'{payload.action}' requires a 'reason'.",
        )

    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Submission not found")
    if submission.status in RESOLVED_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Submission already resolved as '{submission.status}'.",
        )

    previous_status = submission.status
    new_status = _ACTION_TO_STATUS[payload.action]
    submission.status = new_status
    submission.updated_at = utc_now()

    document = db.scalar(
        select(Document).where(Document.submission_id == submission.id).limit(1)
    )

    history_row = DocumentStatusHistory(
        submission_id=submission.id,
        document_id=document.id if document else None,
        from_status=previous_status,
        to_status=new_status,
        reason=reason,
        actor=f"reviewer:{current.user.id}",
    )
    db.add(history_row)

    add_validation_event(
        db,
        submission_id=submission.id,
        document_id=document.id if document else None,
        event_type="reviewer_decision",
        result=payload.action,
        severity="info" if payload.action == "approve" else "warning",
        message=reason,
        actor_type="reviewer",
    )

    db.commit()
    db.refresh(submission)

    return DecisionResponse(
        submission_id=submission.id,
        previous_status=previous_status,
        new_status=new_status,
        action=payload.action,
        reason=reason,
        decided_at=submission.updated_at,
        reviewer_user_id=current.user.id,
    )
