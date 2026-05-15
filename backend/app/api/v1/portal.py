"""Provider portal endpoints.

These endpoints support the provider-facing journey: an authenticated
workspace-entry flow that mints an httpOnly cookie tied to the
authenticated user, an onboarding view that compares the regulatory
Expediente Corporativo against existing submissions, and a yearly
compliance calendar that overlays the recurring Árbol against
actual submissions.

CheckWise 1.8 — Session model
-----------------------------
The legacy anonymous ``POST /portal/access`` endpoint has been removed.
The only way to obtain a portal session cookie is now ``POST
/portal/enter``, which requires:

1. A valid bearer JWT from ``POST /api/v1/auth/login``.
2. The authenticated user's ``user.id`` to match
   ``ProviderWorkspace.owner_user_id`` for the requested workspace.

After verification, the endpoint sets the same httpOnly signed-JWT
cookie (``checkwise_portal_session``). All other portal endpoints
continue to read that cookie and enforce the tenant guard.

The legacy ``X-Workspace-Token`` header is still accepted by reads as
a transition aid for tests and integration scripts, but it cannot mint
a new session — the cookie can only be issued by ``/portal/enter``.
"""

from __future__ import annotations

import secrets
import unicodedata
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth import CurrentUser, _claims_from_header, get_current_user
from app.constants.statuses import DocumentStatus
from app.core.compliance_catalog import (
    catalog_metadata,
    expediente_for_persona,
    recurring_for_year,
)
from app.core.config import settings
from app.db.session import get_db
from app.models import (
    Document,
    DocumentInspection,
    DocumentStatusHistory,
    ProviderWorkspace,
    Submission,
    User,
    Validation,
    ValidationEvent,
)
from app.services.portal_session import (
    PortalSessionError,
    issue_portal_session_token,
    verify_portal_session_token,
)

router = APIRouter(prefix="/portal", tags=["portal"])
DbSession = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------


def _set_portal_session_cookie(
    response: Response, *, workspace_id: str, access_token: str
) -> None:
    """Issue + attach the portal session cookie."""
    token, expires_at = issue_portal_session_token(
        workspace_id=workspace_id, access_token=access_token
    )
    response.set_cookie(
        key=settings.PORTAL_SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.PORTAL_SESSION_EXPIRES_MINUTES * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )


def _clear_portal_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.PORTAL_SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
    )


def _session_from_request(
    request: Request,
    *,
    legacy_header: str = "",
) -> tuple[str, str]:
    """Resolve (workspace_id, access_token) from cookie or legacy header.

    Cookie wins. Falls back to ``X-Workspace-Token`` for callers that
    haven't migrated yet (e.g. integration tests, the legacy reviewer
    queue UI which doesn't use this router but might share helpers).
    Returns ("", "") when neither is present so the caller raises the
    right 401 with workspace context.
    """
    cookie_token = request.cookies.get(settings.PORTAL_SESSION_COOKIE_NAME, "")
    if cookie_token:
        try:
            claims = verify_portal_session_token(cookie_token)
            return claims.workspace_id, claims.access_token
        except PortalSessionError:
            # fall through to legacy header below
            pass
    if legacy_header:
        # Caller passed an X-Workspace-Token. We don't know the
        # workspace_id from the header alone — the path must carry it.
        return "", legacy_header
    return "", ""


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class EnterRequest(BaseModel):
    """Body for POST /portal/enter.

    The user is already authenticated via Authorization: Bearer.
    They identify which of their assigned workspaces they want to
    enter. Today every provider user owns exactly one workspace, so
    ``workspace_id`` is optional — the backend resolves it from the
    user's ownership when omitted. We keep it on the schema so the
    client can be explicit when a user owns multiple workspaces in
    the future.
    """

    workspace_id: str | None = Field(default=None, max_length=64)


class EnterResponse(BaseModel):
    workspace_id: str
    persona_type: str
    client_name: str
    vendor_name: str
    vendor_rfc: str
    filial_name: str | None
    contract_reference: str | None
    onboarding_completed_at: str | None


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
    """Internal: load + verify by raw (workspace_id, access_token) pair.

    Prefer ``current_portal_workspace`` from path-bound endpoints — this
    raw helper is kept for /access resumption + tests.
    """
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


def _resolve_workspace_via_jwt(
    db: Session, authorization: str | None, *, workspace_id: str | None
) -> ProviderWorkspace | None:
    """Resolve the caller's owned workspace via Authorization: Bearer.

    Returns ``None`` if there is no Authorization header or the JWT
    does not map to a valid user. Raises 403 if the JWT's user does
    not own the path's ``workspace_id``.

    This path exists because the portal session cookie is a
    third-party cookie in production (Vercel ↔ Render are different
    eTLD+1 origins) and modern browsers (Safari ITP, Chrome Privacy
    Sandbox) frequently refuse to store or send it. The bearer JWT
    sidesteps that entirely.
    """
    if not authorization:
        return None
    try:
        claims = _claims_from_header(authorization)
    except HTTPException:
        return None
    user = db.get(User, claims.user_id)
    if user is None or user.status != "active":
        return None

    if workspace_id is not None:
        workspace = db.scalar(
            select(ProviderWorkspace)
            .where(ProviderWorkspace.id == workspace_id)
            .limit(1)
        )
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace no encontrado.",
            )
        if workspace.owner_user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Esta sesión no tiene acceso a este workspace.",
            )
        return workspace

    owned = list(
        db.scalars(
            select(ProviderWorkspace).where(
                ProviderWorkspace.owner_user_id == user.id
            )
        )
    )
    if len(owned) == 1:
        return owned[0]
    if len(owned) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tienes varios espacios disponibles. Indica workspace_id.",
        )
    return None


def current_portal_workspace(
    request: Request,
    db: DbSession,
    workspace_id: str | None = None,
    x_workspace_token: Annotated[str, Header(alias="X-Workspace-Token")] = "",
    authorization: Annotated[str | None, Header()] = None,
) -> ProviderWorkspace:
    """Resolve the workspace for the current request.

    Resolution order:
      1. ``Authorization: Bearer <jwt>`` — the cross-origin-safe path.
         Decodes the JWT, looks up the user's owned workspace, and
         enforces the path's ``workspace_id`` if any.
      2. ``checkwise_portal_session`` cookie — preferred when the
         browser allows third-party cookies.
      3. Legacy ``X-Workspace-Token`` header — kept for tests and
         integration scripts.

    Raises:
        401 if no valid session is present.
        403 if the JWT user (or cookie) does not own the path's workspace.
        404 if the workspace_id does not exist.
    """
    via_jwt = _resolve_workspace_via_jwt(db, authorization, workspace_id=workspace_id)
    if via_jwt is not None:
        return via_jwt

    cookie_ws, cookie_tok = _session_from_request(request, legacy_header=x_workspace_token)

    # Determine effective workspace_id for the lookup.
    if workspace_id is None:
        target_ws = cookie_ws
    else:
        target_ws = workspace_id
        # Tenant guard: if cookie has its own workspace_id, it must match.
        if cookie_ws and cookie_ws != workspace_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Esta sesión no tiene acceso a este workspace.",
            )

    if not target_ws or not cookie_tok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión de portal requerida.",
        )

    return _load_workspace(db, target_ws, cookie_tok)


def _scope_from_path(workspace_id: str) -> str:
    """Tiny helper that exists so each route declares its tenant scope
    explicitly in code (auditable). The string is unused at runtime."""
    return f"portal.workspaces.{workspace_id}"


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


@router.post("/enter", response_model=EnterResponse, status_code=status.HTTP_200_OK)
def enter_workspace(
    payload: EnterRequest,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    db: DbSession,
    response: Response,
) -> EnterResponse:
    """Mint the portal session cookie for an authenticated user.

    Authorization model:
      * Caller MUST present a valid bearer JWT (issued by /auth/login).
      * Caller MUST own the workspace (provider_workspaces.owner_user_id
        == current.user.id). Anonymous workspaces (owner_user_id IS NULL)
        cannot be entered through this endpoint — they're either legacy
        rows or admin-created without an owner yet.

    Behavior:
      * If ``payload.workspace_id`` is provided, that specific workspace
        is loaded and the ownership check is enforced.
      * If omitted, the backend looks up the unique workspace owned by
        the current user. 409 if the user owns multiple (caller must
        disambiguate); 404 if they own none.

    On success, rotates the workspace's ``access_token`` (so previous
    cookies stop working) and sets the new httpOnly session cookie.
    """

    if payload.workspace_id:
        workspace = db.scalar(
            select(ProviderWorkspace)
            .where(ProviderWorkspace.id == payload.workspace_id)
            .limit(1)
        )
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace no encontrado.",
            )
        if (
            workspace.owner_user_id is None
            or workspace.owner_user_id != current.user.id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para entrar a este workspace.",
            )
    else:
        owned = list(
            db.scalars(
                select(ProviderWorkspace).where(
                    ProviderWorkspace.owner_user_id == current.user.id
                )
            )
        )
        if not owned:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No tienes ningún espacio asignado todavía.",
            )
        if len(owned) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Tienes varios espacios disponibles. Indica workspace_id."
                ),
            )
        workspace = owned[0]

    # Rotate the access token so any prior cookie tied to this
    # workspace becomes invalid the moment the user re-enters.
    workspace.access_token = secrets.token_urlsafe(32)
    db.flush()
    db.commit()

    _set_portal_session_cookie(
        response,
        workspace_id=workspace.id,
        access_token=workspace.access_token,
    )

    return EnterResponse(
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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def portal_logout(response: Response) -> None:
    """Clear the portal session cookie."""
    _clear_portal_session_cookie(response)


@router.get("/me", response_model=WorkspaceSummary)
def get_portal_me(
    request: Request,
    db: DbSession,
    x_workspace_token: Annotated[str, Header(alias="X-Workspace-Token")] = "",
    authorization: Annotated[str | None, Header()] = None,
) -> WorkspaceSummary:
    """Return the workspace summary for the current session.

    Resolution order matches ``current_portal_workspace``:
      1. ``Authorization: Bearer`` JWT (cross-origin safe).
      2. ``checkwise_portal_session`` cookie.
      3. Legacy ``X-Workspace-Token`` header.
    """
    workspace = _resolve_workspace_via_jwt(db, authorization, workspace_id=None)
    if workspace is None:
        workspace_id, access_token = _session_from_request(
            request, legacy_header=x_workspace_token
        )
        if not access_token or not workspace_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sesión de portal requerida.",
            )
        workspace = _load_workspace(db, workspace_id, access_token)

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


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceSummary)
def get_workspace(
    workspace_id: str,
    workspace: Annotated[ProviderWorkspace, Depends(current_portal_workspace)],
) -> WorkspaceSummary:
    _ = workspace_id  # tenant guard already enforced by current_portal_workspace
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
    workspace: Annotated[ProviderWorkspace, Depends(current_portal_workspace)],
) -> dict:
    _ = workspace_id  # tenant guard already enforced by dependency
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
    workspace: Annotated[ProviderWorkspace, Depends(current_portal_workspace)],
    year: int = 2026,
) -> dict:
    _ = workspace_id  # tenant guard already enforced by dependency
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
    DocumentStatus.RECHAZADO.value,
    DocumentStatus.VENCIDO.value,
    DocumentStatus.POSIBLE_MISMATCH.value,
    DocumentStatus.REQUIERE_ACLARACION.value,
}
# Statuses that resolve the slot.
_RESOLVED_STATUSES: set[str] = {
    DocumentStatus.APROBADO.value,
    DocumentStatus.EXCEPCION_LEGAL.value,
    DocumentStatus.NO_APLICA.value,
}


def _suggested_action(status: str) -> str:
    if status == DocumentStatus.POSIBLE_MISMATCH:
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
    workspace: Annotated[ProviderWorkspace, Depends(current_portal_workspace)],
) -> SubmissionDetailResponse:
    _ = workspace_id  # tenant guard already enforced by dependency
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


# ---------------------------------------------------------------------------
# Duplicate pre-check (Guided upload — Patch 4)
# ---------------------------------------------------------------------------


class DuplicateCheckResponse(BaseModel):
    """Result of a client-side SHA-256 pre-check against this workspace."""

    exists: bool
    submission_id: str | None = None
    status: str | None = None
    submitted_at: str | None = None
    requirement_name: str | None = None
    period_label: str | None = None
    filename: str | None = None


@router.get(
    "/workspaces/{workspace_id}/duplicate-check",
    response_model=DuplicateCheckResponse,
)
def check_workspace_duplicate(
    workspace_id: str,
    sha256: str,
    db: DbSession,
    workspace: Annotated[ProviderWorkspace, Depends(current_portal_workspace)],
) -> DuplicateCheckResponse:
    """Return whether ``sha256`` already exists for this workspace's submissions.

    Wizard-side pre-check: the browser computes the SHA-256 of the selected
    file, sends it here, and we look for any prior submission by the same
    provider with that same file hash. The goal is to *warn before submit*
    rather than detecting duplicates after the upload pipeline runs.
    """
    _ = workspace_id  # tenant guard already enforced by dependency
    if not sha256 or len(sha256) != 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sha256 inválido (se esperan 64 caracteres hex).",
        )

    row = db.execute(
        select(Submission, Document)
        .join(Document, Document.submission_id == Submission.id)
        .where(
            Submission.client_id == workspace.client_id,
            Submission.vendor_id == workspace.vendor_id,
            Document.sha256 == sha256.lower(),
        )
        .order_by(Submission.created_at.desc())
        .limit(1)
    ).first()

    if row is None:
        return DuplicateCheckResponse(exists=False)

    sub, doc = row
    return DuplicateCheckResponse(
        exists=True,
        submission_id=sub.id,
        status=sub.status,
        submitted_at=sub.created_at.isoformat(),
        requirement_name=sub.requirement.name if sub.requirement else None,
        period_label=sub.period.code if sub.period else None,
        filename=doc.original_filename,
    )
