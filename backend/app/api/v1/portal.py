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
from datetime import date
from typing import Annotated, Final, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.auth import CurrentUser, _claims_from_header, get_current_user
from app.constants.statuses import DocumentStatus
from app.core.catalogs import DOCUMENT_STATUSES, INSTITUTIONS, LOAD_TYPES
from app.core.compliance_catalog import (
    RecurringRequirement,
    catalog_metadata,
    expediente_for_persona,
    is_v2_recurring_code,
    onboarding_anatomy,
    onboarding_common_errors,
    onboarding_format,
    onboarding_where_to_obtain,
    onboarding_why,
    recurring_accepted_documents,
    recurring_anatomy,
    recurring_common_errors,
    recurring_for_year,
    recurring_for_year_v2,
    recurring_required_document,
    recurring_where_to_obtain,
)
from app.core.config import settings
from app.core.period_validation import (
    MAX_YEAR,
    MIN_YEAR,
    validate_period_key,
)
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
from app.models.entities import utc_now
from app.schemas.submissions import MultiSubmissionResponse, SubmissionResponse
from app.services.contact_service import hash_ip
from app.services.correction_request_service import (
    TIER_B_FIELD_LABEL_ES,
    TIER_B_FIELDS,
    create_correction_request,
)
from app.services.correction_request_service import (
    deliver_to_slack as deliver_correction_to_slack,
)
from app.services.correction_request_service import (
    record_and_check_rate as record_and_check_correction_rate,
)
from app.services.correction_request_service import (
    slack_payload_snapshot as correction_slack_payload_snapshot,
)
from app.services.evidence_slots import (
    SlotState,
    SlotView,
    build_workspace_calendar_slots,
    build_workspace_onboarding_slots,
)
from app.services.portal_session import (
    PortalSessionError,
    issue_portal_session_token,
    verify_portal_session_token,
)
from app.services.requirement_service import resolve_period, resolve_requirement
from app.services.storage import get_storage_service
from app.services.submission_service import (
    INTAKE_SOURCE_WORKSPACE_PORTAL,
    assert_pdf_upload,
    finalize_intake_submission,
    finalize_multi_document_submission,
    get_or_create_institution,
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
    # Derived expediente lifecycle marker. The frontend uses this to
    # decide whether to send the user to /portal/onboarding (when not
    # complete) or directly to /portal/dashboard (when complete).
    # Values:
    #   * "complete"     — onboarding_completed_at is set; dashboard unlocked.
    #   * "in_progress"  — at least one submission exists but the
    #                      expediente has not been marked complete yet.
    #   * "not_started"  — zero submissions and no completion timestamp.
    expediente_status: Literal["not_started", "in_progress", "complete"]


class WorkspaceSummary(BaseModel):
    workspace_id: str
    persona_type: str
    client_name: str
    vendor_name: str
    vendor_rfc: str
    filial_name: str | None
    contract_reference: str | None
    onboarding_completed_at: str | None
    expediente_status: Literal["not_started", "in_progress", "complete"]


class CompleteOnboardingResponse(BaseModel):
    workspace_id: str
    onboarding_completed_at: str
    expediente_status: Literal["complete"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 5 — UX enrichment helpers (state-driven)
# ---------------------------------------------------------------------------
#
# The "next_action" and "suggested_action" strings are functions of the
# slot's current state, not the catalog row. They used to live in
# frontend mocks; centralising them server-side means every consumer
# (provider portal, future client portal, future reports) sees the same
# copy without re-implementing the state machine.


def _onboarding_next_action(status: str | None, required: bool) -> str:
    """Plain-language next step for an onboarding card, by current status."""
    if status is None or status in {DocumentStatus.PENDIENTE.value}:
        return (
            "Sube este documento para destrabar tu expediente inicial."
            if required
            else "Si tu actividad lo requiere, sube el documento. "
            "Si no aplica, déjalo así."
        )
    if status == DocumentStatus.RECIBIDO.value:
        return "Recibimos tu documento. Va a la cola de revisión."
    if status in {
        DocumentStatus.PENDIENTE_REVISION.value,
        DocumentStatus.PREVALIDADO.value,
    }:
        return (
            "Tu documento está en revisión humana. Te avisaremos por correo "
            "en menos de 24 horas hábiles."
        )
    if status == DocumentStatus.APROBADO.value:
        return "Listo. Lo revisaremos por vigencia el próximo periodo."
    if status == DocumentStatus.RECHAZADO.value:
        return (
            "Tu documento fue rechazado. Revisa la nota del revisor y sube una "
            "versión corregida."
        )
    if status == DocumentStatus.REQUIERE_ACLARACION.value:
        return (
            "El revisor pidió una aclaración. Responde la observación o sube "
            "una versión corregida."
        )
    if status == DocumentStatus.POSIBLE_MISMATCH.value:
        return (
            "Detectamos una posible inconsistencia con el requisito. Verifica "
            "el archivo y vuelve a subir si fue equivocado."
        )
    if status == DocumentStatus.VENCIDO.value:
        return "El documento venció. Sube la versión vigente."
    if status == DocumentStatus.EXCEPCION_LEGAL.value:
        return "Aprobado bajo excepción legal. Sin acción adicional."
    if status == DocumentStatus.NO_APLICA.value:
        return "Este requisito no aplica para tu caso. Sin acción."
    return "Sube este documento desde el wizard."


def _calendar_suggested_action(status: str | None) -> str:
    """Plain-language next step for a calendar item, by current status."""
    if status is None or status == DocumentStatus.PENDIENTE.value:
        return "Sube este documento cuando esté disponible."
    if status == DocumentStatus.RECIBIDO.value:
        return "Recibimos tu documento. Está en cola de revisión."
    if status in {
        DocumentStatus.PENDIENTE_REVISION.value,
        DocumentStatus.PREVALIDADO.value,
    }:
        return "Tu documento está en revisión humana."
    if status == DocumentStatus.APROBADO.value:
        return "Aprobado. Sin acción inmediata."
    if status == DocumentStatus.RECHAZADO.value:
        return "El revisor pidió que vuelvas a subir el documento corregido."
    if status == DocumentStatus.REQUIERE_ACLARACION.value:
        return "Responde la observación o sube una versión corregida."
    if status == DocumentStatus.POSIBLE_MISMATCH.value:
        return "Verifica el archivo. Si fue equivocado, vuelve a subir."
    if status == DocumentStatus.VENCIDO.value:
        return "Documento vencido. Sube la versión vigente."
    if status == DocumentStatus.EXCEPCION_LEGAL.value:
        return "Aprobado bajo excepción legal."
    if status == DocumentStatus.NO_APLICA.value:
        return "No aplica para este periodo."
    return "Sube este documento desde el wizard."


def _latest_reviewer_note(db: Session, submission_id: str | None) -> str | None:
    """Return the message of the most recent ``reviewer_decision`` event.

    The reviewer's reason was already persisted by the workflow service
    (`apply_reviewer_decision`) as a ``ValidationEvent`` with
    ``event_type='reviewer_decision'`` and ``actor_type='reviewer'``.
    Looking it up here gives the provider portal a stable "reviewer's
    note" string without inventing a new column. Returns None when no
    reviewer decision exists yet (typical for fresh uploads).
    """
    if not submission_id:
        return None
    event = db.scalar(
        select(ValidationEvent)
        .where(
            ValidationEvent.submission_id == submission_id,
            ValidationEvent.event_type == "reviewer_decision",
        )
        .order_by(ValidationEvent.created_at.desc())
        .limit(1)
    )
    if event is None:
        return None
    msg = (event.message or "").strip()
    return msg or None


def _calendar_deadline_iso(year: int, due_month: int, due_day: int) -> str:
    """Compute the conventional REPSE deadline as an ISO date string.

    Conventional day-17 cutoff for monthly / bimestral / cuatrimestral
    slots (mirrors the legacy frontend adapter). The SAT annual slot
    carries an explicit ``due_day=30`` in the catalog.
    """
    return f"{year:04d}-{due_month:02d}-{due_day:02d}"


def _calendar_upload_href(
    *,
    year: int,
    code: str,
    period_key: str,
    v2_mode: bool = False,
) -> str:
    """Build the canonical upload URL for a calendar item.

    Keeps the frontend stable: every calendar entry can offer a
    "Subir" link without inventing a URL convention per surface.

    Session 3 (2026-05-21) — when ``v2_mode`` is True (the catalog
    row carries an ``accepts_documents`` list), the URL appends
    ``&v2=1`` so the wizard knows to render the alternatives radio
    picker instead of the legacy single-doc flow. The signal lives
    in the URL rather than in a fetch-on-mount roundtrip so v1
    behavior stays a zero-fetch path.
    """
    href = (
        f"/portal/upload?requirement_code={code}"
        f"&period_key={period_key}"
        f"&period_label={year}-{period_key.split('-', 1)[-1] if '-' in period_key else period_key}"
    )
    if v2_mode:
        href = f"{href}&v2=1"
    return href


# Phase 4 — the legacy ``_match_submission`` fuzzy matcher was removed
# after onboarding and calendar adopted ``evidence_slots``. Canonical
# ``(requirement_code, period_key)`` matching now happens inside the
# slot service, which is also lineage-aware (a superseded prior never
# wins over its replacement). If a future surface needs a fuzzy fallback
# again, prefer extending ``evidence_slots`` over re-introducing
# name-based heuristics.


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


def _expediente_status(
    db: Session, workspace: ProviderWorkspace
) -> Literal["not_started", "in_progress", "complete"]:
    """Derive the expediente lifecycle status from workspace state.

    Single source of truth used by every endpoint that exposes
    ``expediente_status``. Order matters:

      1. ``onboarding_completed_at`` set → ``complete``. Dashboard
         unlocked. The provider has finished initial setup (either by
         clicking the explicit complete CTA or via admin override).
      2. Any submission row exists for the (client, vendor) pair →
         ``in_progress``. The provider has started uploading.
      3. Otherwise → ``not_started``. Empty expediente, fresh provider.

    Status is derived (not stored as a column) so it stays in sync if
    submissions are added or deleted out-of-band.
    """
    if workspace.onboarding_completed_at is not None:
        return "complete"
    has_submission = db.scalar(
        select(Submission.id)
        .where(
            Submission.client_id == workspace.client_id,
            Submission.vendor_id == workspace.vendor_id,
        )
        .limit(1)
    )
    return "in_progress" if has_submission else "not_started"


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
        expediente_status=_expediente_status(db, workspace),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def portal_logout(response: Response) -> None:
    """Clear the portal session cookie."""
    _clear_portal_session_cookie(response)


@router.post(
    "/workspaces/{workspace_id}/complete-onboarding",
    response_model=CompleteOnboardingResponse,
    status_code=status.HTTP_200_OK,
)
def complete_onboarding(
    workspace_id: str,
    db: DbSession,
    workspace: Annotated[ProviderWorkspace, Depends(current_portal_workspace)],
) -> CompleteOnboardingResponse:
    """Mark the provider's initial expediente as complete.

    Authorization: same chain as every other ``/portal/workspaces/{id}/*``
    endpoint — the caller must own this workspace (enforced by
    ``current_portal_workspace`` via JWT or cookie). The path's
    ``workspace_id`` is matched against the resolved workspace, so a
    user cannot complete another company's expediente by guessing IDs.

    Idempotent: re-calling on an already-completed workspace returns
    the existing timestamp (does not move it forward).
    """
    _ = workspace_id  # tenant guard already enforced by dependency
    if workspace.onboarding_completed_at is None:
        workspace.onboarding_completed_at = utc_now()
        db.flush()
        db.commit()
    return CompleteOnboardingResponse(
        workspace_id=workspace.id,
        onboarding_completed_at=workspace.onboarding_completed_at.isoformat(),
        expediente_status="complete",
    )


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
        expediente_status=_expediente_status(db, workspace),
    )


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceSummary)
def get_workspace(
    workspace_id: str,
    db: DbSession,
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
        expediente_status=_expediente_status(db, workspace),
    )


# ---------------------------------------------------------------------------
# Stage 2.7-a — Provider correction requests
# ---------------------------------------------------------------------------
#
# Tier B fields (contact_email / contact_phone / contact_name) are the
# only fields a provider may request changes to from inside the portal.
# RFC, razón social, contract reference, and every other tenant-locked
# attribute stay support-only — those go through email/Slack to a
# CheckWise admin who edits them in the database. The endpoint enforces
# the Tier B list and returns 422 with a plain-Spanish "contact support"
# message for anything outside it.
#
# Storage: a single ``audit_log`` row with action
# ``correction_request.submitted`` and ``actor_type=provider``. The row
# id IS the correction-request id surfaced to the provider as a folio.
#
# Delivery: best-effort Slack POST to ``SLACK_CORRECTION_WEBHOOK_URL`` as
# a BackgroundTask. Webhook unset → audit_log persistence only, no error
# (matches contact-form behavior).


class CorrectionRequestCreate(BaseModel):
    field: Literal["contact_email", "contact_phone", "contact_name", "other"] = Field(
        ...,
        description=(
            "Tier B field key. ``other`` is reserved for the form's "
            "free-text catch-all and is rejected here — providers must "
            "route those through support."
        ),
    )
    current_value: str = Field(default="", max_length=512)
    proposed_value: str = Field(..., min_length=1, max_length=512)
    reason: str = Field(..., min_length=4, max_length=2000)
    message: str | None = Field(default=None, max_length=4000)


class CorrectionRequestResponse(BaseModel):
    id: str
    field: str
    status: Literal["pending"]
    created_at_iso: str


def _client_ip(request: Request) -> str | None:
    """Resolve the calling client IP, preferring proxy headers."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    if request.client and request.client.host:
        return request.client.host
    return None


@router.post(
    "/workspaces/{workspace_id}/correction-requests",
    response_model=CorrectionRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a Tier B correction request from the provider portal",
)
def post_correction_request(
    workspace_id: str,
    payload: CorrectionRequestCreate,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    workspace: Annotated[ProviderWorkspace, Depends(current_portal_workspace)],
) -> CorrectionRequestResponse:
    _ = workspace_id  # tenant guard already enforced by dependency

    # Tier B contract — anything outside the locked field list is
    # support-only. The form ships an "other" option for catch-all
    # cases; those must route through email so we explicitly reject
    # them here.
    if payload.field not in TIER_B_FIELDS:
        labels = ", ".join(TIER_B_FIELD_LABEL_ES.values())
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Solo aceptamos solicitudes de corrección para "
                f"{labels}. Para otros datos (RFC, razón social, "
                "contrato), escríbenos a soporte@checkwise.mx."
            ),
        )

    proposed = payload.proposed_value.strip()
    current = (payload.current_value or "").strip()
    if not proposed or proposed == current:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Captura un valor distinto al actual.",
        )

    reason = payload.reason.strip()
    if len(reason) < 4:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Captura una razón breve. Los cambios sensibles requieren contexto.",
        )

    user_id = workspace.owner_user_id
    if user_id is None:
        # ``current_portal_workspace`` accepts a legacy X-Workspace-Token
        # path that does not carry a user identity. Correction requests
        # need an actor; reject the legacy path explicitly.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inicia sesión para enviar una solicitud de corrección.",
        )

    if not record_and_check_correction_rate(user_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Has enviado varias solicitudes recientemente. "
                "Inténtalo de nuevo en una hora."
            ),
        )

    user_email: str | None = None
    user = db.get(User, user_id)
    if user is not None:
        user_email = user.email

    ip_hash = hash_ip(_client_ip(request))
    user_agent_raw = request.headers.get("user-agent")
    user_agent = (user_agent_raw or "")[:512] or None

    row = create_correction_request(
        db,
        workspace_id=workspace.id,
        user_id=user_id,
        user_email=user_email,
        field=payload.field,
        current_value=current,
        proposed_value=proposed,
        reason=reason,
        message=(payload.message.strip() if payload.message else None),
        ip_hash=ip_hash,
        user_agent=user_agent,
    )

    snapshot = correction_slack_payload_snapshot(
        workspace_id=workspace.id,
        user_id=user_id,
        user_email=user_email,
        field=payload.field,
        current_value=current,
        proposed_value=proposed,
        reason=reason,
        message=(payload.message.strip() if payload.message else None),
    )
    background.add_task(deliver_correction_to_slack, row.id, snapshot)

    return CorrectionRequestResponse(
        id=row.id,
        field=payload.field,
        status="pending",
        created_at_iso=row.created_at.isoformat(),
    )


@router.get("/workspaces/{workspace_id}/onboarding")
def get_workspace_onboarding(
    workspace_id: str,
    db: DbSession,
    workspace: Annotated[ProviderWorkspace, Depends(current_portal_workspace)],
) -> dict:
    """Workspace onboarding view (Phase 4 — consumes evidence_slots).

    Tenant guard runs in ``current_portal_workspace``. Per-slot
    "current submission" comes from ``build_workspace_onboarding_slots``,
    which walks the replacement-lineage chain so a superseded rejection
    never dominates a slot once the provider has uploaded a replacement.
    Response shape is preserved exactly so the frontend's existing
    onboarding page keeps working without changes.
    """
    _ = workspace_id  # tenant guard already enforced by dependency

    slots = build_workspace_onboarding_slots(db, workspace)
    slot_by_code: dict[str, SlotView] = {
        view.slot_key.requirement_code: view
        for view in slots
        if view.slot_key.requirement_code is not None
    }

    # Pre-fetch document filenames for the "current" submissions only
    # (one row per slot — superseded attempts are intentionally omitted).
    current_ids = [
        view.current_submission_id for view in slots if view.current_submission_id
    ]
    filename_by_submission: dict[str, str] = {}
    if current_ids:
        rows = db.execute(
            select(Document.submission_id, Document.original_filename).where(
                Document.submission_id.in_(current_ids)
            )
        ).all()
        # If a submission has multiple documents the latest insertion
        # wins — correct enough for the card label.
        for sub_id, fname in rows:
            filename_by_submission[sub_id] = fname

    expediente = expediente_for_persona(workspace.persona_type)  # type: ignore[arg-type]
    sections: dict[str, dict] = {}
    received_required = 0
    total_required = 0
    for req in expediente:
        view = slot_by_code.get(req.code)
        section = sections.setdefault(
            req.section,
            {"section": req.section, "items": [], "received": 0, "required": 0},
        )
        item_status = view.current_status if (view and view.current_status) else "pendiente"
        current_submission_id = view.current_submission_id if view else None
        item = {
            "code": req.code,
            "name": req.name,
            "institution": req.institution,
            "required": req.required,
            "note": req.note,
            "status": item_status,
            "submission_id": current_submission_id,
            "submitted_at": view.submitted_at_iso if view else None,
            "filename": (
                filename_by_submission.get(current_submission_id)
                if current_submission_id
                else None
            ),
            # Phase 5 — UX enrichment that used to live in the frontend
            # mock. The why/format strings are static catalog data; the
            # next_action + reviewer_note vary with slot state so they
            # are computed against the current submission (lineage-aware
            # by way of the slot view).
            "why": onboarding_why(req),
            "format": onboarding_format(req),
            # Stage 2 (BL-002, 2026-05-20) — first-upload guidance.
            # Anatomy describes what the document contains, where_to_obtain
            # explains where to get it, common_errors lists the pitfalls
            # the tester (jluna@legalshelf.mx) called out on F1/F2.
            "anatomy": onboarding_anatomy(req),
            "where_to_obtain": onboarding_where_to_obtain(req),
            "common_errors": list(onboarding_common_errors(req)),
            "next_action": _onboarding_next_action(item_status, req.required),
            "reviewer_note": _latest_reviewer_note(db, current_submission_id),
        }
        section["items"].append(item)
        if req.required:
            section["required"] += 1
            total_required += 1
            if current_submission_id is not None:
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
    year: Annotated[int, Query(ge=MIN_YEAR, le=MAX_YEAR)] = 2026,
) -> dict:
    """Workspace calendar view (Phase 4 — consumes evidence_slots).

    Same tenant guard + same response shape as before. The leaf-of-the-
    lineage-chain selection now lives in
    ``build_workspace_calendar_slots`` so a rejected/clarification
    submission that has been replaced no longer counts as the current
    submission for its slot.
    """
    _ = workspace_id  # tenant guard already enforced by dependency

    slots = build_workspace_calendar_slots(db, workspace, year)
    slot_by_key: dict[tuple[str | None, str | None], SlotView] = {
        (view.slot_key.requirement_code, view.slot_key.period_key): view
        for view in slots
    }

    # Session 2 (2026-05-21) — pick the catalog shape the slot resolver
    # used. Keeping them in lockstep matters: the resolver iterates v2
    # rows when the flag is on, so the endpoint must too, or the row
    # → slot lookup misses for every row.
    recurring: list[RecurringRequirement] = (
        list(recurring_for_year_v2(year, workspace.persona_type))  # type: ignore[arg-type]
        if settings.RECURRING_CATALOG_V2
        else list(recurring_for_year(year, workspace.persona_type))  # type: ignore[arg-type]
    )
    months: dict[int, dict] = {
        m: {"month": m, "institutions": {}, "received": 0, "expected": 0}
        for m in range(1, 13)
    }
    for req in recurring:
        view = slot_by_key.get((req.code, req.period_key))
        bucket = months[req.due_month]["institutions"]
        inst = bucket.setdefault(
            req.institution,
            {"institution": req.institution, "items": [], "received": 0, "expected": 0},
        )
        item_status = view.current_status if (view and view.current_status) else "pendiente"
        # Phase 5 — UX enrichment that used to live in the calendar mock.
        deadline_iso = _calendar_deadline_iso(year, req.due_month, req.due_day)
        # Session 3 (2026-05-21) — flag the upload URL as v2-mode when
        # the row carries alternatives so the wizard knows to render
        # the radio picker. ``bool(req.accepts_documents)`` is True
        # exactly when this is a v2 row regardless of the global flag
        # state (a v2 generator only emits rows with non-empty
        # accepts_documents).
        href = _calendar_upload_href(
            year=year,
            code=req.code,
            period_key=req.period_key,
            v2_mode=bool(req.accepts_documents),
        )
        # Session 2 — when this is a v2 row, surface the rich
        # per-accepted-doc list AND keep the legacy single-doc
        # guidance fields populated with placeholders so the frontend
        # can branch on accepts_documents.length without breaking
        # callers that still read anatomy/where/common_errors as
        # strings. v1 rows continue to emit the single-doc shape.
        accepted_docs = recurring_accepted_documents(req)
        inst["items"].append(
            {
                "code": req.code,
                "name": req.name,
                "frequency": req.frequency,
                "period_label": req.period_label,
                "period_key": req.period_key,
                "status": item_status,
                "submission_id": view.current_submission_id if view else None,
                "required_document": recurring_required_document(req),
                "due_month": req.due_month,
                "deadline_iso": deadline_iso,
                "suggested_action": _calendar_suggested_action(item_status),
                "href": href,
                # Stage 2.7 (T5 parity, 2026-05-20) — single-doc
                # first-upload guidance. On v2 rows these will fall
                # back to institution defaults because req.name is the
                # obligation label, not a doc name; the rich
                # accepts_documents list below is the canonical source
                # of truth in v2 mode.
                "anatomy": recurring_anatomy(req),
                "where_to_obtain": recurring_where_to_obtain(req),
                "common_errors": list(recurring_common_errors(req)),
                # Session 2 (2026-05-21) — accepted-doc-type
                # alternatives. Empty list on v1 rows (no behavior
                # change for legacy frontends). Non-empty on v2 rows,
                # one entry per acceptable doc type with anatomy /
                # where_to_obtain / common_errors keyed by
                # (institution, doc_name) — Stage 2.7's
                # _RECURRING_DOC_OVERRIDES map.
                "accepts_documents": accepted_docs,
                "minimum_documents": req.minimum_documents,
            }
        )
        inst["expected"] += 1
        months[req.due_month]["expected"] += 1
        if view and view.current_submission_id is not None:
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
    # Phase 4 — replacement lineage pointers. Provider UI uses these to
    # link "Reemplaza intento anterior" / "Reemplazado por intento más
    # reciente" affordances. Both may be ``None``.
    #   * ``supersedes_submission_id`` — set when this submission was
    #     filed as an explicit replacement for a prior submission.
    #   * ``superseded_by_submission_id`` — set when a later submission
    #     declared this one as the prior it replaces.
    supersedes_submission_id: str | None = None
    superseded_by_submission_id: str | None = None


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

    # Phase 4 — reverse-lineage lookup. The forward pointer
    # (``supersedes_submission_id``) is on the row itself. The reverse
    # ("what replaced me?") is a single targeted query.
    superseded_by_id: str | None = None
    if submission.status is not None:
        replacement = db.scalar(
            select(Submission.id).where(
                Submission.supersedes_submission_id == submission.id,
                Submission.client_id == workspace.client_id,
                Submission.vendor_id == workspace.vendor_id,
            )
        )
        superseded_by_id = replacement

    return SubmissionDetailResponse(
        submission_id=submission.id,
        workspace_id=workspace.id,
        status=submission.status,
        load_type=submission.load_type,
        submitted_at=submission.created_at.isoformat(),
        comments=submission.comments,
        supersedes_submission_id=submission.supersedes_submission_id,
        superseded_by_submission_id=superseded_by_id,
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


# ---------------------------------------------------------------------------
# Workspace-scoped provider upload (Phase 1 — tenant-safe intake)
# ---------------------------------------------------------------------------


_VALID_DOCUMENT_STATUSES = frozenset(item["code"] for item in DOCUMENT_STATUSES)
_VALID_LOAD_TYPES = frozenset(item["code"] for item in LOAD_TYPES)
_VALID_INSTITUTION_CODES = frozenset(item["code"] for item in INSTITUTIONS)


# Statuses a prior submission must be in for a provider to replace it.
# Anything else is either still in flight (``recibido`` / ``pendiente_revision``
# / ``prevalidado``), already approved (``aprobado``), or otherwise
# closed (``excepcion_legal`` / ``no_aplica``). The provider does not get
# to bypass those by uploading a "replacement."
_REPLACEMENT_ELIGIBLE_STATUSES: frozenset[str] = frozenset(
    {
        DocumentStatus.RECHAZADO.value,
        DocumentStatus.REQUIERE_ACLARACION.value,
        DocumentStatus.POSIBLE_MISMATCH.value,
        DocumentStatus.VENCIDO.value,
    }
)


def _resolve_supersedes_submission(
    db: Session,
    *,
    workspace: ProviderWorkspace,
    prior_id: str | None,
    new_requirement_code: str | None,
    new_period_key: str | None,
) -> Submission | None:
    """Validate a caller-supplied ``supersedes_submission_id`` (or return None).

    Phase 3 contract:

    * ``404`` if the prior id does not exist, or exists but belongs to a
      different client/vendor (workspace tenant guard — never confirm
      cross-tenant existence).
    * ``409`` if the prior is not in a replacement-eligible status
      (``rechazado`` / ``requiere_aclaracion`` / ``posible_mismatch`` /
      ``vencido``).
    * ``409`` if both submissions carry canonical slot keys
      (``requirement_code`` / ``period_key``) and any of them mismatch.
      Legacy rows without canonical keys skip the slot check rather than
      blocking the upload — they are tracked through their existing
      requirement/period FKs.

    No auto-linking: when ``prior_id`` is empty / None this function
    returns None and the new submission stands alone.
    """
    if not prior_id:
        return None

    prior = db.get(Submission, prior_id)
    if prior is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission previa no encontrada para este workspace.",
        )
    if prior.client_id != workspace.client_id or prior.vendor_id != workspace.vendor_id:
        # Never reveal that the row exists in another tenant.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission previa no encontrada para este workspace.",
        )

    if prior.status not in _REPLACEMENT_ELIGIBLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"La submission previa no puede reemplazarse desde el estado "
                f"'{prior.status}'."
            ),
        )

    # Canonical slot check. When both sides carry both keys, they MUST
    # match — otherwise the provider would be using a rejection from one
    # obligation to absolve a different one. When the prior is a legacy
    # row without canonical keys we skip the check (no way to compare
    # safely) and trust the explicit referencing.
    if (
        new_requirement_code
        and prior.requirement_code
        and new_requirement_code != prior.requirement_code
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "El nuevo documento corresponde a un requirement_code distinto "
                "del que se intenta reemplazar."
            ),
        )
    if (
        new_period_key
        and prior.period_key
        and new_period_key != prior.period_key
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "El nuevo documento corresponde a un period_key distinto del "
                "que se intenta reemplazar."
            ),
        )

    return prior


@router.post(
    "/workspaces/{workspace_id}/submissions",
    response_model=SubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["submissions"],
    summary="Workspace-scoped provider upload",
    description=(
        "Tenant-safe replacement for the legacy `POST /api/v1/submissions`. "
        "Identity (client, vendor, contract) is derived from the authenticated "
        "`ProviderWorkspace`. Browser-posted client / vendor / RFC / contract "
        "fields are NOT accepted and have no effect — a spoofed form cannot "
        "redirect the submission to another tenant."
    ),
)
async def create_workspace_submission(
    workspace_id: str,
    file: Annotated[UploadFile, File()],
    period_code: Annotated[str, Form(min_length=4)],
    load_type: Annotated[str, Form()],
    institution_code: Annotated[str, Form()],
    requirement_name: Annotated[str, Form(min_length=2)],
    db: DbSession,
    workspace: Annotated[ProviderWorkspace, Depends(current_portal_workspace)],
    comments: Annotated[str | None, Form()] = None,
    initial_status: Annotated[str, Form()] = DocumentStatus.PENDIENTE_REVISION.value,
    requirement_code: Annotated[str | None, Form()] = None,
    period_key: Annotated[str | None, Form()] = None,
    supersedes_submission_id: Annotated[str | None, Form()] = None,
) -> SubmissionResponse:
    """Create a submission scoped to the authenticated provider workspace.

    Tenant guard runs in ``current_portal_workspace``:
      * Authorization: Bearer JWT (primary, cross-origin-safe path).
      * Portal session cookie.
      * Legacy ``X-Workspace-Token`` header (transition aid).

    Returns 401 when no valid session is presented, 403 when the
    session does not own the path's ``workspace_id``, 404 when the
    workspace does not exist.

    Tenant identity (client / vendor / contract) is read from the
    workspace row — NOT from form fields. The endpoint deliberately
    does not declare `client_name`, `vendor_name`, `vendor_rfc`, or
    `contract_reference` so a spoofed form body has no effect: FastAPI
    drops undeclared fields silently and the submission still binds to
    `workspace.client_id` / `workspace.vendor_id`.
    """
    _ = workspace_id  # tenant guard already enforced by dependency

    assert_pdf_upload(file)

    # Stage 2.5 (BL-T7) — reject impossible periods at the wire. A
    # ``period_key`` like "1945-M01" is structurally invalid for REPSE
    # (which began in 2021); accepting it lets stale or malicious
    # writes succeed and pollute the audit trail. ``validate_period_key``
    # is a no-op when the caller did not supply one — the existing
    # downstream logic still drives the canonical resolution.
    validate_period_key(period_key)

    if initial_status != DocumentStatus.PENDIENTE_REVISION:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La carga inicial debe comenzar en pendiente_revision.",
        )
    if initial_status not in _VALID_DOCUMENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Estado inválido.",
        )
    if load_type not in _VALID_LOAD_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Tipo de carga inválido.",
        )
    if institution_code not in _VALID_INSTITUTION_CODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Institución inválida.",
        )

    # Phase 3 — replacement lineage. Resolve + validate the prior
    # submission BEFORE persisting any of the new upload's side
    # effects (storage write, DB rows). A bogus reference must reject
    # the request without leaving an orphaned PDF on disk.
    supersedes_submission = _resolve_supersedes_submission(
        db,
        workspace=workspace,
        prior_id=(supersedes_submission_id or "").strip() or None,
        new_requirement_code=(requirement_code or "").strip() or None,
        new_period_key=(period_key or "").strip() or None,
    )

    storage = get_storage_service()
    try:
        stored_file = await storage.save_upload(file)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    try:
        # Tenant identity is authoritative here — derived from the
        # ProviderWorkspace tied to the authenticated session. Browser
        # cannot influence these values.
        client = workspace.client
        vendor = workspace.vendor
        contract = workspace.contract

        institution = get_or_create_institution(db, institution_code)
        resolved_requirement = resolve_requirement(
            db,
            requirement_code=(requirement_code or "").strip() or None,
            requirement_name=requirement_name.strip(),
            institution_id=institution.id,
            institution_code=institution.code,
            load_type=load_type,
        )
        resolved_period = resolve_period(
            db,
            period_key=(period_key or "").strip() or None,
            period_code=period_code.strip(),
            load_type=load_type,
        )

        return finalize_intake_submission(
            db,
            stored_file=stored_file,
            client=client,
            vendor=vendor,
            contract=contract,
            institution=institution,
            resolved_requirement=resolved_requirement,
            resolved_period=resolved_period,
            load_type=load_type,
            period_code=period_code.strip(),
            comments=comments,
            submitted_by=f"workspace:{workspace.id}",
            intake_source=INTAKE_SOURCE_WORKSPACE_PORTAL,
            extra_audit_metadata={"workspace_id": workspace.id},
            supersedes_submission=supersedes_submission,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No fue posible registrar la carga documental.",
        ) from exc


# ---------------------------------------------------------------------------
# Stage 2.7-b — Multi-document submission (flag-gated)
# ---------------------------------------------------------------------------
#
# The data model has supported ``Submission`` → N ``Document`` rows
# since Phase 2 (``backend/app/models/entities.py:222``). The provider
# wizard at ``/portal/upload`` accepts only one file today; the
# multi-file path lives behind ``settings.MULTI_FILE_UPLOAD_ENABLED``
# so the new shape can be rolled back without a redeploy.
#
# Caps (locked decision, 2026-05-20):
#   * ``MULTI_FILE_MAX_FILES``    — N ≤ 5 files per submission
#   * ``MULTI_FILE_TOTAL_BYTES_CAP`` — ≤ 30 MB aggregate per submission
#
# Atomicity: storage saves run sequentially. If aggregate size cap is
# breached or any file fails inspection downstream, the router rolls
# back the DB transaction and removes the storage files written so far
# — no half-persisted submissions, no orphaned PDFs.


MULTI_FILE_MAX_FILES: Final[int] = 5
MULTI_FILE_TOTAL_BYTES_CAP: Final[int] = 30 * 1024 * 1024  # 30 MB


@router.post(
    "/workspaces/{workspace_id}/submissions/batch",
    response_model=MultiSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["submissions"],
    summary="Multi-document workspace-scoped provider upload (flag-gated)",
)
async def create_workspace_submission_batch(
    workspace_id: str,
    files: Annotated[list[UploadFile], File()],
    period_code: Annotated[str, Form(min_length=4)],
    load_type: Annotated[str, Form()],
    institution_code: Annotated[str, Form()],
    requirement_name: Annotated[str, Form(min_length=2)],
    db: DbSession,
    workspace: Annotated[ProviderWorkspace, Depends(current_portal_workspace)],
    comments: Annotated[str | None, Form()] = None,
    initial_status: Annotated[str, Form()] = DocumentStatus.PENDIENTE_REVISION.value,
    requirement_code: Annotated[str | None, Form()] = None,
    period_key: Annotated[str | None, Form()] = None,
    supersedes_submission_id: Annotated[str | None, Form()] = None,
) -> MultiSubmissionResponse:
    """Create a single Submission with up to N Documents under it.

    Behavior matches ``create_workspace_submission`` for tenant guard,
    period validation, replacement-lineage resolution, and persistence
    of the audit trail — only the document count differs. Returns the
    Submission's worst-case status (matching the single-file
    derivation) plus a per-document detail list.
    """
    _ = workspace_id  # tenant guard already enforced by dependency

    if not settings.MULTI_FILE_UPLOAD_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "La carga de varios archivos en una sola entrega aún no "
                "está disponible. Sube un documento a la vez."
            ),
        )

    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Adjunta al menos un archivo.",
        )
    if len(files) > MULTI_FILE_MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Solo se permiten hasta {MULTI_FILE_MAX_FILES} archivos por entrega. "
                f"Recibimos {len(files)}."
            ),
        )

    for upload in files:
        assert_pdf_upload(upload)

    validate_period_key(period_key)

    if initial_status != DocumentStatus.PENDIENTE_REVISION:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La carga inicial debe comenzar en pendiente_revision.",
        )
    if initial_status not in _VALID_DOCUMENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Estado inválido.",
        )
    if load_type not in _VALID_LOAD_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Tipo de carga inválido.",
        )
    if institution_code not in _VALID_INSTITUTION_CODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Institución inválida.",
        )

    supersedes_submission = _resolve_supersedes_submission(
        db,
        workspace=workspace,
        prior_id=(supersedes_submission_id or "").strip() or None,
        new_requirement_code=(requirement_code or "").strip() or None,
        new_period_key=(period_key or "").strip() or None,
    )

    storage = get_storage_service()
    stored_files: list = []
    aggregate_size = 0
    try:
        for upload in files:
            try:
                stored = await storage.save_upload(upload)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc
            stored_files.append(stored)
            aggregate_size += stored.size_bytes
            if aggregate_size > MULTI_FILE_TOTAL_BYTES_CAP:
                cap_mb = MULTI_FILE_TOTAL_BYTES_CAP // (1024 * 1024)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=(
                        f"Los archivos suman más de {cap_mb} MB en total. "
                        "Reduce el tamaño o sube en varias entregas."
                    ),
                )

        client = workspace.client
        vendor = workspace.vendor
        contract = workspace.contract

        institution = get_or_create_institution(db, institution_code)
        resolved_requirement = resolve_requirement(
            db,
            requirement_code=(requirement_code or "").strip() or None,
            requirement_name=requirement_name.strip(),
            institution_id=institution.id,
            institution_code=institution.code,
            load_type=load_type,
        )
        resolved_period = resolve_period(
            db,
            period_key=(period_key or "").strip() or None,
            period_code=period_code.strip(),
            load_type=load_type,
        )

        return finalize_multi_document_submission(
            db,
            stored_files=stored_files,
            client=client,
            vendor=vendor,
            contract=contract,
            institution=institution,
            resolved_requirement=resolved_requirement,
            resolved_period=resolved_period,
            load_type=load_type,
            period_code=period_code.strip(),
            comments=comments,
            submitted_by=f"workspace:{workspace.id}",
            intake_source=INTAKE_SOURCE_WORKSPACE_PORTAL,
            extra_audit_metadata={"workspace_id": workspace.id},
            supersedes_submission=supersedes_submission,
        )
    except HTTPException:
        # Roll back any DB writes that finalize_multi_document_submission
        # might have started before the failure, and clean up storage
        # writes so we don't leave orphaned PDFs.
        db.rollback()
        _cleanup_partial_storage(stored_files)
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        _cleanup_partial_storage(stored_files)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No fue posible registrar la carga documental.",
        ) from exc


def _cleanup_partial_storage(stored_files: list) -> None:
    """Delete storage entries written before a rollback.

    Called from the multi-file batch endpoint's exception handlers
    (HTTPException + SQLAlchemyError) so a partial batch never leaves
    orphan bytes in storage. ``StorageService.delete`` is itself
    idempotent and best-effort — it never raises — so this loop is a
    thin orchestration layer over it. The outer try/except guards
    against the unlikely case where the backend factory itself fails
    (e.g. S3 credentials revoked mid-request); we still want the
    original rollback exception to surface in that case.
    """
    if not stored_files:
        return
    try:
        storage = get_storage_service()
    except Exception:  # noqa: BLE001 — keep the original rollback error in view
        return
    for stored in stored_files:
        storage.delete(stored.storage_key)


# ---------------------------------------------------------------------------
# Provider dashboard (Phase 4 — backend-owned read model)
# ---------------------------------------------------------------------------


class DashboardOnboardingSummary(BaseModel):
    total_required: int
    completed: int
    in_review: int
    needs_action: int
    optional_pending: int
    completion_pct: int
    is_gate_satisfied: bool


class DashboardDocumentStateCounts(BaseModel):
    approved: int
    in_review: int
    uploaded: int
    pending: int
    needs_review: int
    rejected: int
    expired: int
    exception: int


class DashboardSemaphore(BaseModel):
    level: Literal["green", "yellow", "red"]
    label: str
    reason: str
    compliance_pct: int
    total_tracked: int
    on_track: int


class DashboardSuggestedAction(BaseModel):
    id: str
    type: Literal[
        "complete_onboarding",
        "reupload",
        "verify_mismatch",
        "clarify",
        "upcoming",
        # P1-c (2026-05-20): EXPIRED required slots emit a "regularize"
        # action so the provider sees the missed obligation as a real
        # next step instead of it sitting silently as VENCIDO only on
        # the slot resolver.
        "regularize",
    ]
    title: str
    body: str
    priority: Literal["low", "medium", "high"]
    href: str
    requirement_code: str | None = None
    period_key: str | None = None


class DashboardAttentionItem(BaseModel):
    id: str
    title: str
    institution: str
    state: str
    due_in_days: int | None = None
    href: str


class DashboardUpcomingDeadline(BaseModel):
    id: str
    title: str
    institution: str
    period_key: str | None
    due_month: int
    state: str
    href: str
    # Days until the conventional 17th-of-period_month deadline.
    # Added in P1.6 so /portal/reports can render an urgency timeline
    # without re-parsing the period_key on the client. Always >= 0
    # because `_compute_upcoming_deadlines` filters overdue rows.
    due_in_days: int | None = None


class DashboardResponse(BaseModel):
    workspace_id: str
    persona_type: str
    onboarding_summary: DashboardOnboardingSummary
    document_state_counts: DashboardDocumentStateCounts
    semaphore: DashboardSemaphore
    suggested_actions: list[DashboardSuggestedAction]
    attention_today: list[DashboardAttentionItem]
    upcoming_deadlines: list[DashboardUpcomingDeadline]


# ``SlotState`` values that mean "the provider must act now."
_ACTIONABLE_SLOT_STATES: frozenset[SlotState] = frozenset(
    {SlotState.REJECTED, SlotState.NEEDS_CORRECTION, SlotState.POSSIBLE_MISMATCH}
)

# ``SlotState`` values that count as "resolved / no action needed."
_RESOLVED_SLOT_STATES: frozenset[SlotState] = frozenset(
    {SlotState.APPROVED, SlotState.EXCEPTION, SlotState.NOT_APPLICABLE}
)


def _empty_document_counts() -> DashboardDocumentStateCounts:
    return DashboardDocumentStateCounts(
        approved=0,
        in_review=0,
        uploaded=0,
        pending=0,
        needs_review=0,
        rejected=0,
        expired=0,
        exception=0,
    )


def _bucket_document_state(
    counts: DashboardDocumentStateCounts, state: SlotState
) -> None:
    """Bump the count bucket for a slot's coarse state.

    ``MISSING`` → pending. ``NEEDS_CORRECTION`` and ``POSSIBLE_MISMATCH``
    → needs_review (matches the UI bucket the frontend already uses).
    ``NOT_APPLICABLE`` is intentionally not counted as a document
    (the slot has no document at all).
    """
    if state is SlotState.APPROVED:
        counts.approved += 1
    elif state is SlotState.IN_REVIEW:
        counts.in_review += 1
    elif state is SlotState.UPLOADED:
        counts.uploaded += 1
    elif state is SlotState.MISSING:
        counts.pending += 1
    elif state in (SlotState.NEEDS_CORRECTION, SlotState.POSSIBLE_MISMATCH):
        counts.needs_review += 1
    elif state is SlotState.REJECTED:
        counts.rejected += 1
    elif state is SlotState.EXPIRED:
        counts.expired += 1
    elif state is SlotState.EXCEPTION:
        counts.exception += 1
    # NOT_APPLICABLE: skip — no document is expected.


def _compute_onboarding_summary(
    slots: list[SlotView], workspace: ProviderWorkspace
) -> DashboardOnboardingSummary:
    required_views = [view for view in slots if view.required]
    total_required = len(required_views)
    completed = sum(
        1 for view in required_views if view.state in _RESOLVED_SLOT_STATES
    )
    in_review = sum(
        1 for view in required_views if view.state in (SlotState.IN_REVIEW, SlotState.UPLOADED)
    )
    _NEEDS_ACTION_STATES = _ACTIONABLE_SLOT_STATES | {SlotState.MISSING, SlotState.EXPIRED}
    needs_action = sum(
        1 for view in required_views if view.state in _NEEDS_ACTION_STATES
    )
    optional_pending = sum(
        1
        for view in slots
        if not view.required and view.state is not SlotState.APPROVED
    )
    completion_pct = (
        100
        if total_required == 0
        else round(((completed + in_review) / total_required) * 100)
    )
    # The onboarding gate flips once the provider has either explicitly
    # completed onboarding (workspace.onboarding_completed_at set) or
    # left zero required slots needing action. Mirrors the frontend's
    # gate logic.
    is_gate_satisfied = (
        workspace.onboarding_completed_at is not None or needs_action == 0
    )
    return DashboardOnboardingSummary(
        total_required=total_required,
        completed=completed,
        in_review=in_review,
        needs_action=needs_action,
        optional_pending=optional_pending,
        completion_pct=completion_pct,
        is_gate_satisfied=is_gate_satisfied,
    )


def _compute_semaphore(
    onboarding_slots: list[SlotView], calendar_slots: list[SlotView]
) -> DashboardSemaphore:
    required = [s for s in onboarding_slots if s.required] + [
        s for s in calendar_slots if s.required
    ]
    total_tracked = len(required)
    on_track = sum(1 for s in required if s.state in _RESOLVED_SLOT_STATES)
    compliance_pct = (
        100 if total_tracked == 0 else round(on_track / total_tracked * 100)
    )
    has_blocking = any(s.state in _ACTIONABLE_SLOT_STATES for s in required)
    has_pending = any(
        s.state in (SlotState.MISSING, SlotState.IN_REVIEW, SlotState.UPLOADED, SlotState.EXPIRED)
        for s in required
    )
    no_progress = total_tracked > 0 and on_track == 0
    if has_blocking:
        level: Literal["green", "yellow", "red"] = "red"
        label = "Rojo · obligaciones críticas"
        reason = (
            "Hay documentos rechazados o con observaciones que necesitas atender "
            "antes de seguir avanzando."
        )
    elif no_progress:
        # P1.1 (2026-05-20): 0/N on track shouldn't read "in progress".
        level = "red"
        label = "Rojo · sin avance"
        reason = (
            "Tu expediente tiene obligaciones pendientes y ninguna aprobada "
            "todavía. Sube el primer documento para arrancar el conteo."
        )
    elif has_pending:
        level = "yellow"
        label = "Amarillo · puntos por atender"
        reason = (
            "Tu expediente está en marcha, pero todavía quedan documentos por "
            "subir o por revisar."
        )
    else:
        level = "green"
        label = "Verde · al día"
        reason = "Todas tus obligaciones obligatorias están aprobadas."
    return DashboardSemaphore(
        level=level,
        label=label,
        reason=reason,
        compliance_pct=compliance_pct,
        total_tracked=total_tracked,
        on_track=on_track,
    )


def _onboarding_reupload_href(view: SlotView) -> str:
    parts = [f"requirement_code={view.requirement_code}"]
    if view.current_submission_id and view.state in _ACTIONABLE_SLOT_STATES:
        parts.append(f"replaces={view.current_submission_id}")
    parts.append("from=onboarding")
    return "/portal/upload?" + "&".join(parts)


def _calendar_reupload_href(view: SlotView) -> str:
    parts: list[str] = []
    if view.requirement_code:
        parts.append(f"requirement_code={view.requirement_code}")
    if view.period_key:
        parts.append(f"period_key={view.period_key}")
        parts.append(f"period_label={view.period_key}")
    if view.current_submission_id and view.state in _ACTIONABLE_SLOT_STATES:
        parts.append(f"replaces={view.current_submission_id}")
    # Session 3 audit fix (2026-05-21) — dashboard suggested-action
    # CTAs route through this builder. Without ``v2=1`` the wizard
    # would mount in v1 mode against a v2 row's collapsed code and
    # the alternatives picker wouldn't render. Detect from the code
    # shape; SlotView doesn't carry accepts_documents so we can't ask
    # the row directly.
    if view.requirement_code and is_v2_recurring_code(view.requirement_code):
        parts.append("v2=1")
    qs = "&".join(parts)
    return f"/portal/upload?{qs}" if qs else "/portal/upload"


def _compute_suggested_actions(
    onboarding_slots: list[SlotView],
    calendar_slots: list[SlotView],
    today: date,
    *,
    onboarding_completed: bool = False,
) -> list[DashboardSuggestedAction]:
    """Build the dashboard's prioritized-action list.

    P1.3 (2026-05-20): once a workspace's ``onboarding_completed_at``
    is set, suppress the "complete onboarding" suggestions. Surfacing
    onboarding docs on a workspace whose initial expediente is already
    closed misleads providers into thinking they regressed. Actionable
    states (rejected / needs_correction / possible_mismatch) on
    onboarding slots still surface in pass 1 — that's a real problem,
    not a "next step".
    """
    actions: list[DashboardSuggestedAction] = []
    # 1. Rejected / clarification / mismatch — high priority.
    for view in onboarding_slots + calendar_slots:
        if not view.required:
            continue
        if view.state not in _ACTIONABLE_SLOT_STATES:
            continue
        is_onboarding = view.slot_key.period_key is None
        actions.append(
            DashboardSuggestedAction(
                id=f"act-{view.requirement_code}-{view.period_key or 'onb'}",
                type=(
                    "verify_mismatch"
                    if view.state is SlotState.POSSIBLE_MISMATCH
                    else "clarify"
                    if view.state is SlotState.NEEDS_CORRECTION
                    else "reupload"
                ),
                title=_action_title_for_state(view),
                body=_action_body_for_state(view),
                priority="high",
                href=(
                    _onboarding_reupload_href(view)
                    if is_onboarding
                    else _calendar_reupload_href(view)
                ),
                requirement_code=view.requirement_code,
                period_key=view.period_key,
            )
        )
    # 2. Missing required onboarding slots — medium priority.
    #    Suppressed when the workspace's onboarding is already complete.
    if not onboarding_completed:
        for view in onboarding_slots:
            if not view.required or view.state is not SlotState.MISSING:
                continue
            actions.append(
                DashboardSuggestedAction(
                    id=f"act-{view.requirement_code}-missing",
                    type="complete_onboarding",
                    title=f"Sube tu documento: {view.requirement_name}",
                    body=(
                        "Este documento es obligatorio para terminar tu expediente "
                        "inicial."
                    ),
                    priority="medium",
                    href=_onboarding_reupload_href(view),
                    requirement_code=view.requirement_code,
                    period_key=None,
                )
            )
    # 2.5. Expired (vencido) calendar slots — high priority
    # "regularización" prompt. P1-c (2026-05-20): the catalog deadline
    # already passed, so this is more urgent than an upcoming-deadline
    # warning but distinct from a rejection (the provider didn't fail
    # a reviewer call — they simply missed the SAT/IMSS window). The
    # CTA still routes to the upload page so the provider can attach
    # a late acuse + work with their contador on regularización.
    for view in calendar_slots:
        if not view.required or view.state is not SlotState.EXPIRED:
            continue
        actions.append(
            DashboardSuggestedAction(
                id=f"act-{view.requirement_code}-{view.period_key}-expired",
                type="regularize",
                title=f"Regulariza el documento vencido: {view.requirement_name}",
                body=(
                    "El plazo de esta obligación pasó sin que se subiera "
                    "el acuse. Trabaja con tu contador para regularizarla "
                    "y carga el comprobante aquí."
                ),
                priority="high",
                href=_calendar_reupload_href(view),
                requirement_code=view.requirement_code,
                period_key=view.period_key,
            )
        )
    # 3. Calendar slots due within 14 days — low/medium depending on urgency.
    for view in calendar_slots:
        if not view.required or view.state is not SlotState.MISSING:
            continue
        due_in = _due_in_days_for_period(view.period_key, today)
        if due_in is None or due_in < 0 or due_in > 14:
            continue
        actions.append(
            DashboardSuggestedAction(
                id=f"act-{view.requirement_code}-{view.period_key}-upcoming",
                type="upcoming",
                title=f"Próximo vencimiento: {view.requirement_name}",
                body=(
                    f"Tienes {due_in} día(s) para subir este documento del "
                    f"periodo {view.period_key}."
                ),
                priority="medium" if due_in <= 5 else "low",
                href=_calendar_reupload_href(view),
                requirement_code=view.requirement_code,
                period_key=view.period_key,
            )
        )
    return actions[:5]


def _action_title_for_state(view: SlotView) -> str:
    if view.state is SlotState.REJECTED:
        return f"Corrige el documento rechazado: {view.requirement_name}"
    if view.state is SlotState.NEEDS_CORRECTION:
        return f"Aclara el documento: {view.requirement_name}"
    if view.state is SlotState.POSSIBLE_MISMATCH:
        return f"Verifica el documento: {view.requirement_name}"
    return view.requirement_name or "Acción requerida"


def _action_body_for_state(view: SlotView) -> str:
    if view.state is SlotState.REJECTED:
        return (
            "El revisor rechazó esta entrega. Vuelve a cargar una versión "
            "corregida; CheckWise enlazará la nueva carga con la anterior."
        )
    if view.state is SlotState.NEEDS_CORRECTION:
        return (
            "El revisor pidió una aclaración. Sube una nueva versión o "
            "responde la observación."
        )
    if view.state is SlotState.POSSIBLE_MISMATCH:
        return (
            "Las señales automáticas detectaron una posible inconsistencia. "
            "Verifica el archivo y vuelve a cargar si fue equivocado."
        )
    return ""


def _due_in_days_for_period(period_key: str | None, today: date) -> int | None:
    """Estimate days-to-deadline from a canonical period_key.

    The catalog encodes deadlines as "due in month X of year Y" with a
    conventional 17th-of-month cutoff (mirroring the legacy frontend
    adapter). We can't recover the exact `due_month` from the slot
    view, so we use the period_key's own month/year as a conservative
    proxy: the document is due in the same period it covers, give or
    take a few weeks. Returns None if the key isn't parseable.
    """
    if not period_key:
        return None
    try:
        year = int(period_key[:4])
    except ValueError:
        return None
    month: int | None = None
    if "-M" in period_key:
        try:
            month = int(period_key.split("-M", 1)[1])
        except ValueError:
            month = None
    elif "-B" in period_key:
        try:
            bm = int(period_key.split("-B", 1)[1])
        except ValueError:
            bm = None
        if bm is not None:
            month = bm * 2
    elif "-Q" in period_key:
        try:
            q = int(period_key.split("-Q", 1)[1])
        except ValueError:
            q = None
        if q is not None:
            month = q * 4
    elif period_key.endswith("-A"):
        month = 12
    if month is None or not 1 <= month <= 12:
        return None
    try:
        deadline = date(year, month, 17)
    except ValueError:
        return None
    return (deadline - today).days


def _compute_attention_today(
    onboarding_slots: list[SlotView],
    calendar_slots: list[SlotView],
    today: date,
) -> list[DashboardAttentionItem]:
    items: list[DashboardAttentionItem] = []
    # Required slots needing action — always surface, regardless of date.
    for view in onboarding_slots + calendar_slots:
        if not view.required:
            continue
        if view.state not in _ACTIONABLE_SLOT_STATES and view.state is not SlotState.EXPIRED:
            continue
        is_onboarding = view.slot_key.period_key is None
        href = (
            _onboarding_reupload_href(view)
            if is_onboarding
            else _calendar_reupload_href(view)
        )
        items.append(
            DashboardAttentionItem(
                id=f"att-{view.requirement_code}-{view.period_key or 'onb'}",
                title=view.requirement_name or view.requirement_code or "Obligación",
                institution=view.institution or "—",
                state=view.state.value,
                due_in_days=_due_in_days_for_period(view.period_key, today),
                href=href,
            )
        )
    # Calendar slots due within 14 days that are still MISSING/in-review.
    for view in calendar_slots:
        if not view.required:
            continue
        if view.state in _ACTIONABLE_SLOT_STATES or view.state is SlotState.EXPIRED:
            continue  # already added above
        if view.state in (SlotState.APPROVED, SlotState.EXCEPTION, SlotState.NOT_APPLICABLE):
            continue
        due_in = _due_in_days_for_period(view.period_key, today)
        if due_in is None or due_in < 0 or due_in > 14:
            continue
        items.append(
            DashboardAttentionItem(
                id=f"att-{view.requirement_code}-{view.period_key}",
                title=view.requirement_name or view.requirement_code or "Obligación",
                institution=view.institution or "—",
                state=view.state.value,
                due_in_days=due_in,
                href=_calendar_reupload_href(view),
            )
        )
    # Sort overdue first, then ascending by due_in_days, missing days at the end.
    items.sort(
        key=lambda i: (
            i.due_in_days is None,
            i.due_in_days if i.due_in_days is not None else 0,
        )
    )
    return items[:10]


def _compute_upcoming_deadlines(
    calendar_slots: list[SlotView], today: date
) -> list[DashboardUpcomingDeadline]:
    rows: list[tuple[int, DashboardUpcomingDeadline]] = []
    for view in calendar_slots:
        if not view.required:
            continue
        if view.state in _RESOLVED_SLOT_STATES:
            continue
        due_in = _due_in_days_for_period(view.period_key, today)
        if due_in is None or due_in < 0:
            continue
        # Parse the deadline's month for the response.
        deadline_month = today.month
        if view.period_key and "-M" in view.period_key:
            try:
                deadline_month = int(view.period_key.split("-M", 1)[1])
            except ValueError:
                deadline_month = today.month
        rows.append(
            (
                due_in,
                DashboardUpcomingDeadline(
                    id=f"due-{view.requirement_code}-{view.period_key}",
                    title=view.requirement_name or view.requirement_code or "Obligación",
                    institution=view.institution or "—",
                    period_key=view.period_key,
                    due_month=deadline_month,
                    state=view.state.value,
                    href=_calendar_reupload_href(view),
                    due_in_days=due_in,
                ),
            )
        )
    rows.sort(key=lambda r: r[0])
    return [r[1] for r in rows[:5]]


@router.get(
    "/workspaces/{workspace_id}/dashboard",
    response_model=DashboardResponse,
    summary="Provider dashboard read model",
    description=(
        "Backend-owned dashboard aggregate. Composes evidence-slot state "
        "(replacement-lineage aware) into the semaphore, document counts, "
        "suggested actions, attention items, and upcoming deadlines. "
        "Computed read-only — no persisted suggested_actions yet."
    ),
)
def get_workspace_dashboard(
    workspace_id: str,
    db: DbSession,
    workspace: Annotated[ProviderWorkspace, Depends(current_portal_workspace)],
    year: Annotated[int | None, Query(ge=MIN_YEAR, le=MAX_YEAR)] = None,
) -> DashboardResponse:
    """Provider dashboard composed from the canonical evidence-slot service."""
    _ = workspace_id  # tenant guard already enforced by dependency
    today = date.today()
    target_year = year or today.year

    onboarding_slots = build_workspace_onboarding_slots(db, workspace)
    calendar_slots = build_workspace_calendar_slots(db, workspace, target_year)

    # Document counts span every tracked slot (onboarding + calendar).
    counts = _empty_document_counts()
    for view in onboarding_slots + calendar_slots:
        _bucket_document_state(counts, view.state)

    return DashboardResponse(
        workspace_id=workspace.id,
        persona_type=workspace.persona_type,
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
    )
