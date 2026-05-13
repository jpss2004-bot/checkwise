"""Provider portal endpoints (V1.2 demo).

These endpoints support the provider-facing journey: a demo-grade access flow,
an onboarding view that compares the regulatory Expediente Corporativo against
existing submissions, and a yearly compliance calendar that overlays the
recurring Árbol against actual submissions.

⚠️  This is **not** authentication. Workspaces issue an opaque ``access_token``
that the frontend stores in localStorage and sends on subsequent calls. Anyone
with the token can read the workspace. V1.3 must replace this with real auth
(roles, ownership, session expiry).
"""

from __future__ import annotations

import secrets
import unicodedata
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.endpoints import (
    _get_or_create_client,
    _get_or_create_contract,
    _get_or_create_vendor,
)
from app.core.compliance_catalog import (
    catalog_metadata,
    expediente_for_persona,
    recurring_for_year,
)
from app.db.session import get_db
from app.models import (
    Document,
    DocumentInspection,
    DocumentStatusHistory,
    ProviderWorkspace,
    Submission,
    Validation,
    ValidationEvent,
)

router = APIRouter(prefix="/portal", tags=["portal"])
DbSession = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AccessRequest(BaseModel):
    client_name: str = Field(..., min_length=2, max_length=255)
    filial_name: str | None = Field(default=None, max_length=255)
    vendor_name: str = Field(..., min_length=2, max_length=255)
    vendor_rfc: str = Field(..., min_length=12, max_length=13)
    persona_type: Literal["moral", "fisica"]
    contract_reference: str | None = Field(default=None, max_length=120)


class AccessResponse(BaseModel):
    workspace_id: str
    access_token: str
    persona_type: str
    client_name: str
    vendor_name: str
    vendor_rfc: str
    filial_name: str | None
    contract_reference: str | None
    onboarding_completed_at: str | None
    note: str = (
        "Acceso de demostración. No es autenticación de producción. "
        "Guarda el access_token en localStorage como sesión demo."
    )


class WorkspaceSummary(BaseModel):
    workspace_id: str
    persona_type: str
    client_name: str
    vendor_name: str
    vendor_rfc: str
    filial_name: str | None
    contract_reference: str | None
    onboarding_completed_at: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    n = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return " ".join(n.split())


def _match_submission(
    expected_name: str,
    expected_institution: str,
    submissions: list[Submission],
    *,
    period_label: str | None = None,
    requirement_code: str | None = None,
    period_key: str | None = None,
) -> Submission | None:
    """Return the best matching submission for an expected requirement.

    Preferred path: exact match on ``(institution, requirement_code, period_key)``
    when both canonical keys are provided and the stored submission carries
    them. Falls back to the legacy name + year heuristic so historic
    submissions written before canonical keys still light up the dashboard.
    """
    expected_norm = _normalize(expected_name)
    period_year = ""
    if period_label:
        digits = "".join(c for c in period_label if c.isdigit() or c in "-/ ")
        period_year = digits.strip()
    candidates: list[tuple[int, Submission]] = []
    for sub in submissions:
        inst_code = sub.institution.code if sub.institution else ""
        if inst_code != expected_institution:
            continue

        # Canonical-code fast path. When both the catalog row and the stored
        # submission carry canonical keys, that pair is the truth.
        if requirement_code and getattr(sub, "requirement_code", None) == requirement_code:
            if period_key is None or getattr(sub, "period_key", None) == period_key:
                candidates.append((200, sub))
                continue

        req_name = sub.requirement.name if sub.requirement else ""
        name_score = 0
        if _normalize(req_name) == expected_norm:
            name_score = 100
        elif expected_norm in _normalize(req_name) or _normalize(req_name) in expected_norm:
            name_score = 60
        if name_score == 0:
            continue
        period_score = 0
        if period_key and getattr(sub, "period_key", None) == period_key:
            period_score = 50
        elif period_year and sub.period and sub.period.code:
            if period_year[:4] and period_year[:4] in sub.period.code:
                period_score = 10
        candidates.append((name_score + period_score, sub))
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1] if candidates else None


def _load_workspace(db: Session, workspace_id: str, access_token: str) -> ProviderWorkspace:
    workspace = db.scalar(
        select(ProviderWorkspace).where(ProviderWorkspace.id == workspace_id).limit(1)
    )
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace no encontrado."
        )
    if not secrets.compare_digest(workspace.access_token, access_token or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token inválido."
        )
    return workspace


def _workspace_submissions(db: Session, workspace: ProviderWorkspace) -> list[Submission]:
    stmt = (
        select(Submission)
        .where(
            Submission.client_id == workspace.client_id,
            Submission.vendor_id == workspace.vendor_id,
        )
        .order_by(Submission.created_at.desc())
    )
    return list(db.scalars(stmt))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/access", response_model=AccessResponse, status_code=status.HTTP_201_CREATED)
def create_or_resume_access(payload: AccessRequest, db: DbSession) -> AccessResponse:
    """Create (or resume) a demo provider workspace and return an access token."""

    normalized_rfc = payload.vendor_rfc.strip().upper()
    client = _get_or_create_client(db, payload.client_name.strip())
    vendor = _get_or_create_vendor(
        db, client_id=client.id, name=payload.vendor_name.strip(), rfc=normalized_rfc
    )
    if vendor.persona_type != payload.persona_type:
        vendor.persona_type = payload.persona_type

    contract = _get_or_create_contract(
        db,
        client_id=client.id,
        vendor_id=vendor.id,
        external_reference=(payload.contract_reference or "").strip() or None,
    )

    # Reuse an existing workspace for the same (client, vendor, contract) tuple
    # so a returning provider continues with the same identity. We rotate the
    # token on each access to keep the demo at least token-aware.
    stmt = select(ProviderWorkspace).where(
        ProviderWorkspace.client_id == client.id,
        ProviderWorkspace.vendor_id == vendor.id,
    )
    if contract is None:
        stmt = stmt.where(ProviderWorkspace.contract_id.is_(None))
    else:
        stmt = stmt.where(ProviderWorkspace.contract_id == contract.id)
    workspace = db.scalar(stmt.limit(1))

    new_token = secrets.token_urlsafe(32)
    if workspace is None:
        workspace = ProviderWorkspace(
            client_id=client.id,
            vendor_id=vendor.id,
            contract_id=contract.id if contract else None,
            filial_name=(payload.filial_name or "").strip() or None,
            persona_type=payload.persona_type,
            display_name=vendor.name,
            access_token=new_token,
        )
        db.add(workspace)
    else:
        workspace.access_token = new_token
        workspace.persona_type = payload.persona_type
        workspace.filial_name = (payload.filial_name or "").strip() or None
        workspace.display_name = vendor.name

    db.flush()
    db.commit()

    return AccessResponse(
        workspace_id=workspace.id,
        access_token=workspace.access_token,
        persona_type=workspace.persona_type,
        client_name=client.name,
        vendor_name=vendor.name,
        vendor_rfc=vendor.rfc,
        filial_name=workspace.filial_name,
        contract_reference=(contract.external_reference if contract else None),
        onboarding_completed_at=(
            workspace.onboarding_completed_at.isoformat()
            if workspace.onboarding_completed_at
            else None
        ),
    )


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceSummary)
def get_workspace(
    workspace_id: str,
    db: DbSession,
    x_workspace_token: Annotated[str, Header(alias="X-Workspace-Token")] = "",
) -> WorkspaceSummary:
    workspace = _load_workspace(db, workspace_id, x_workspace_token)
    return WorkspaceSummary(
        workspace_id=workspace.id,
        persona_type=workspace.persona_type,
        client_name=workspace.client.name,
        vendor_name=workspace.vendor.name,
        vendor_rfc=workspace.vendor.rfc,
        filial_name=workspace.filial_name,
        contract_reference=(
            workspace.contract.external_reference if workspace.contract else None
        ),
        onboarding_completed_at=(
            workspace.onboarding_completed_at.isoformat()
            if workspace.onboarding_completed_at
            else None
        ),
    )


@router.get("/workspaces/{workspace_id}/onboarding")
def get_workspace_onboarding(
    workspace_id: str,
    db: DbSession,
    x_workspace_token: Annotated[str, Header(alias="X-Workspace-Token")] = "",
) -> dict:
    workspace = _load_workspace(db, workspace_id, x_workspace_token)
    subs = _workspace_submissions(db, workspace)
    expediente = expediente_for_persona(workspace.persona_type)  # type: ignore[arg-type]

    sections: dict[str, dict] = {}
    received_required = 0
    total_required = 0
    for req in expediente:
        match = _match_submission(
            req.name,
            req.institution,
            subs,
            requirement_code=req.code,
        )
        section = sections.setdefault(
            req.section,
            {"section": req.section, "items": [], "received": 0, "required": 0},
        )
        item_status = match.status if match else "pendiente"
        item = {
            "code": req.code,
            "name": req.name,
            "institution": req.institution,
            "required": req.required,
            "note": req.note,
            "status": item_status,
            "submission_id": match.id if match else None,
            "submitted_at": match.created_at.isoformat() if match else None,
        }
        section["items"].append(item)
        if req.required:
            section["required"] += 1
            total_required += 1
            if match is not None:
                section["received"] += 1
                received_required += 1

    completed = received_required == total_required and total_required > 0
    return {
        "metadata": catalog_metadata(),
        "workspace_id": workspace.id,
        "persona_type": workspace.persona_type,
        "sections": list(sections.values()),
        "summary": {
            "received_required": received_required,
            "total_required": total_required,
            "completion_pct": (
                round(received_required / total_required * 100) if total_required else 0
            ),
            "completed": completed,
            "onboarding_completed_at": (
                workspace.onboarding_completed_at.isoformat()
                if workspace.onboarding_completed_at
                else None
            ),
        },
    }


@router.get("/workspaces/{workspace_id}/calendar")
def get_workspace_calendar(
    workspace_id: str,
    db: DbSession,
    year: int = 2026,
    x_workspace_token: Annotated[str, Header(alias="X-Workspace-Token")] = "",
) -> dict:
    workspace = _load_workspace(db, workspace_id, x_workspace_token)
    subs = _workspace_submissions(db, workspace)
    recurring = recurring_for_year(year, workspace.persona_type)  # type: ignore[arg-type]

    months: dict[int, dict] = {
        m: {"month": m, "institutions": {}, "received": 0, "expected": 0} for m in range(1, 13)
    }
    for req in recurring:
        match = _match_submission(
            req.name,
            req.institution,
            subs,
            period_label=req.period_label,
            requirement_code=req.code,
            period_key=req.period_key,
        )
        bucket = months[req.due_month]["institutions"]
        inst = bucket.setdefault(
            req.institution,
            {"institution": req.institution, "items": [], "received": 0, "expected": 0},
        )
        item_status = match.status if match else "pendiente"
        inst["items"].append(
            {
                "code": req.code,
                "name": req.name,
                "frequency": req.frequency,
                "period_label": req.period_label,
                "period_key": req.period_key,
                "status": item_status,
                "submission_id": match.id if match else None,
            }
        )
        inst["expected"] += 1
        months[req.due_month]["expected"] += 1
        if match is not None:
            inst["received"] += 1
            months[req.due_month]["received"] += 1

    return {
        "metadata": catalog_metadata(),
        "workspace_id": workspace.id,
        "year": year,
        "persona_type": workspace.persona_type,
        "months": [
            {
                "month": m["month"],
                "expected": m["expected"],
                "received": m["received"],
                "institutions": list(m["institutions"].values()),
            }
            for m in months.values()
        ],
    }


# ---------------------------------------------------------------------------
# Submission detail (correction flow)
# ---------------------------------------------------------------------------


class SubmissionRequirementSummary(BaseModel):
    code: str | None
    name: str | None
    institution: str | None
    load_type: str | None
    requirement_code: str | None
    requirement_version: int | None


class SubmissionPeriodSummary(BaseModel):
    code: str | None
    period_key: str | None
    period_type: str | None


class SubmissionDocumentSummary(BaseModel):
    document_id: str
    filename: str
    sha256: str
    size_bytes: int
    page_count: int | None
    has_text: bool | None
    is_probably_scanned: bool | None
    detected_institution: str | None
    detected_document_type: str | None
    mismatch_reason: str | None


class SubmissionReason(BaseModel):
    rule_code: str
    severity: str
    message: str | None
    requires_human_review: bool


class SubmissionEvent(BaseModel):
    event_type: str
    result: str
    severity: str
    message: str | None
    confidence: float | None
    actor_type: str
    occurred_at: str


class SubmissionHistoryEntry(BaseModel):
    from_status: str | None
    to_status: str
    reason: str | None
    actor: str
    occurred_at: str


class SubmissionPreviousAttempt(BaseModel):
    submission_id: str
    status: str
    submitted_at: str
    filename: str | None


class SubmissionDetailResponse(BaseModel):
    submission_id: str
    workspace_id: str
    status: str
    load_type: str
    submitted_at: str
    comments: str | None
    requirement: SubmissionRequirementSummary
    period: SubmissionPeriodSummary
    document: SubmissionDocumentSummary | None
    reasons: list[SubmissionReason]
    events: list[SubmissionEvent]
    history: list[SubmissionHistoryEntry]
    previous_attempts: list[SubmissionPreviousAttempt]
    suggested_action: Literal[
        "reupload", "wait_for_review", "no_action", "verify_and_reupload"
    ]


# Statuses that mean "you, the provider, must act now."
_ACTIONABLE_STATUSES: set[str] = {
    "rechazado",
    "vencido",
    "posible_mismatch",
    "requiere_aclaracion",
}
# Statuses that resolve the slot.
_RESOLVED_STATUSES: set[str] = {"aprobado", "excepcion_legal", "no_aplica"}


def _suggested_action(status: str) -> str:
    if status == "posible_mismatch":
        return "verify_and_reupload"
    if status in _ACTIONABLE_STATUSES:
        return "reupload"
    if status in _RESOLVED_STATUSES:
        return "no_action"
    return "wait_for_review"


@router.get(
    "/workspaces/{workspace_id}/submissions/{submission_id}",
    response_model=SubmissionDetailResponse,
)
def get_workspace_submission(
    workspace_id: str,
    submission_id: str,
    db: DbSession,
    x_workspace_token: Annotated[str, Header(alias="X-Workspace-Token")] = "",
) -> SubmissionDetailResponse:
    workspace = _load_workspace(db, workspace_id, x_workspace_token)
    submission = db.scalar(
        select(Submission).where(Submission.id == submission_id).limit(1)
    )
    if submission is None or submission.client_id != workspace.client_id or (
        submission.vendor_id != workspace.vendor_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission no encontrado para este workspace.",
        )

    # Document + inspection.
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

    # Reasons: filter validations to the ones a provider should see.
    validations = list(
        db.scalars(
            select(Validation)
            .where(Validation.submission_id == submission.id)
            .order_by(Validation.created_at.asc())
        )
    )
    reasons: list[SubmissionReason] = []
    for v in validations:
        if v.severity in {"warning", "error"} or v.requires_human_review:
            reasons.append(
                SubmissionReason(
                    rule_code=v.rule_code,
                    severity=v.severity,
                    message=v.message,
                    requires_human_review=v.requires_human_review,
                )
            )

    # Events: chronological, full.
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

    # Status history.
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

    # Previous attempts on the same canonical slot for the same provider.
    previous_attempts: list[SubmissionPreviousAttempt] = []
    if submission.requirement_code and submission.period_key:
        previous_query = (
            select(Submission)
            .where(
                Submission.client_id == workspace.client_id,
                Submission.vendor_id == workspace.vendor_id,
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

    return SubmissionDetailResponse(
        submission_id=submission.id,
        workspace_id=workspace.id,
        status=submission.status,
        load_type=submission.load_type,
        submitted_at=submission.created_at.isoformat(),
        comments=submission.comments,
        requirement=SubmissionRequirementSummary(
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
        ),
        period=SubmissionPeriodSummary(
            code=submission.period.code if submission.period else None,
            period_key=submission.period_key
            or (submission.period.period_key if submission.period else None),
            period_type=submission.period.period_type if submission.period else None,
        ),
        document=(
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
            )
            if document is not None
            else None
        ),
        reasons=reasons,
        events=events,
        history=history,
        previous_attempts=previous_attempts,
        suggested_action=_suggested_action(submission.status),  # type: ignore[arg-type]
    )
