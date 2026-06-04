"""Reports API endpoints — Phase 3.1.

Shape (the ones that land in 3.1; the rest land in 3.2-3.7):
    POST   /api/v1/reports                              create
    GET    /api/v1/reports                              list (filterable)
    GET    /api/v1/reports/{report_id}                  read + latest version
    PATCH  /api/v1/reports/{report_id}                  metadata update
    POST   /api/v1/reports/{report_id}/versions         manual save
    GET    /api/v1/reports/{report_id}/versions         version history
    GET    /api/v1/reports/{report_id}/versions/{n}     specific version

The endpoints delegate all rule-enforcement to the service layer.
This module is the wire/HTTP translator: parse body → call service →
catch domain errors → render HTTP.
"""

from __future__ import annotations

import json as _json
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth import CurrentUser, get_current_user
from app.constants.reports import (
    ConversationRole,
    ReportAudience,
    ReportStatus,
    ReportVersionOrigin,
)
from app.core.config import settings
from app.core.rate_limit import enforce_ai_heavy_rate_limit
from app.db.session import SessionLocal, get_db
from app.models.entities import Report, ReportExport, ReportShare, ReportVersion
from app.schemas.reports import (
    CreateFromPresetRequest,
    PlannedBlockResponse,
    PlanReportRequest,
    PlanReportResponse,
    ReportCreate,
    ReportList,
    ReportPatch,
    ReportPresetList,
    ReportPresetSummary,
    ReportRead,
    ReportSummary,
    ReportVersionCreate,
    ReportVersionList,
    ReportVersionRead,
    ReportVersionSummary,
)
from app.services.report_service import (
    ReportActor,
    ReportNotFoundError,
    ReportPermissionError,
    ReportScopeError,
    ReportVersionNotFoundError,
    create_report,
    create_version,
    get_report,
    get_version,
    list_reports,
    list_versions,
    patch_report,
)
from app.services.reports.context import ReportScope, assemble_context
from app.services.reports.conversation import (
    append_turn,
    error_turn,
    list_conversation,
    recent_messages_for_llm,
    text_turn,
)
from app.services.reports.copilot import chat_completion, explain_block
from app.services.reports.copilot_suggest import suggest_blocks
from app.services.reports.executor import execute_plan
from app.services.reports.export import (
    ReportExportError,
    run_report_export,
    start_report_export,
)
from app.services.reports.llm import LLMError, get_llm_client
from app.services.reports.planner import plan_report
from app.services.reports.sharing import mint_share, revoke_share
from app.services.reports.templates import get_preset, presets_for_roles
from app.services.storage import get_storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])
DbSession = Annotated[Session, Depends(get_db)]


# ─── Helpers ─────────────────────────────────────────────────────


def _enforce_ai_budget(current: CurrentUser) -> None:
    """Apply the M3 per-user LLM-budget cap.

    All six AI-heavy POST endpoints (plan, generate, conversation,
    explain, regenerate, refresh-data) call this before reaching the
    Anthropic client. Centralised so a future bucket tweak (e.g. a
    per-role multiplier) lives in one place.

    Both limits come from ``settings``. Either at 0 disables that
    bucket entirely — useful in tests and as a kill switch if the
    cap blocks a legitimate batch operation in prod.
    """
    enforce_ai_heavy_rate_limit(
        current.user.id,
        per_minute=settings.AI_HEAVY_RATE_LIMIT_PER_MINUTE,
        per_hour=settings.AI_HEAVY_RATE_LIMIT_PER_HOUR,
    )


def _actor_from(current: CurrentUser, db: Session | None = None) -> ReportActor:
    """Build a tenant-scoping ReportActor from the request principal.

    The workspace lookup fires whenever a DB session is provided —
    regardless of whether the caller also carries internal roles. The
    earlier gate (``not current.roles``) was a perf shortcut that
    caused BL-001: a provider whose JWT happens to carry any
    non-internal role (e.g. a seed-time ``provider`` Membership) lost
    access to their own vendor-facing presets because
    ``workspace_vendor_id`` was never populated, leaving
    ``is_workspace_owner`` permanently False. The cost is one extra
    indexed query per reports request; the benefit is a truthful actor
    for every code path.

    If an ``Organization`` exists with the same ``client_id`` as the
    workspace, the actor also gains that org in ``organization_ids``
    so ``create_report``'s owning-org resolution still works.

    ``db`` is optional for back-compat — callers that don't need the
    workspace branch (e.g. lightweight reads in the AI pipeline that
    already have the actor pre-built) can omit it.
    """
    workspace_vendor_id: str | None = None
    workspace_client_id: str | None = None
    org_ids: list[str] = list(current.organization_ids)

    if db is not None:
        from app.models.entities import (  # local import to avoid cycle
            Organization,
            ProviderWorkspace,
        )

        # Deterministic pick when a user owns more than one workspace:
        # order by id so the same user resolves to the same workspace
        # every request. Multi-workspace visibility (seeing reports
        # across two vendors at once) is a deferred follow-up; until
        # then the lowest-id workspace wins.
        ws = db.scalar(
            select(ProviderWorkspace)
            .where(
                ProviderWorkspace.owner_user_id == current.user.id,
                ProviderWorkspace.status == "active",
            )
            .order_by(ProviderWorkspace.id)
            .limit(1)
        )
        if ws is not None:
            workspace_vendor_id = ws.vendor_id
            workspace_client_id = ws.client_id
            # Find the org that represents the workspace's client so the
            # owning-org resolution path keeps working for provider-
            # authored reports. If none exists, providers can still
            # read but writes will surface a clear error.
            ws_org_id = db.scalar(
                select(Organization.id)
                .where(Organization.client_id == ws.client_id)
                .limit(1)
            )
            if ws_org_id and ws_org_id not in org_ids:
                org_ids.append(ws_org_id)

    actor = ReportActor(
        user_id=current.user.id,
        organization_ids=tuple(org_ids),
        roles=tuple(current.roles),
        workspace_vendor_id=workspace_vendor_id,
        workspace_client_id=workspace_client_id,
    )
    logger.debug(
        "report-actor built user_id=%s roles=%s workspace_vendor_id=%s",
        actor.user_id,
        actor.roles,
        actor.workspace_vendor_id,
    )
    return actor


def _summary(report: Report) -> ReportSummary:
    return ReportSummary(
        id=report.id,
        title=report.title,
        description=report.description,
        audience=report.audience,        # type: ignore[arg-type]
        status=report.status,            # type: ignore[arg-type]
        organization_id=report.organization_id,
        client_id=report.client_id,
        vendor_id=report.vendor_id,
        current_version_id=report.current_version_id,
        created_by_user_id=report.created_by_user_id,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


def _version_summary(v: ReportVersion) -> ReportVersionSummary:
    return ReportVersionSummary(
        id=v.id,
        report_id=v.report_id,
        version_number=v.version_number,
        label=v.label,
        parent_version_id=v.parent_version_id,
        generated_by=v.generated_by,     # type: ignore[arg-type]
        created_by_user_id=v.created_by_user_id,
        created_at=v.created_at,
    )


def _version_read(v: ReportVersion) -> ReportVersionRead:
    return ReportVersionRead(
        **_version_summary(v).model_dump(),
        content_json=v.content_json,
        plan_json=v.plan_json,
        source_snapshot_id=v.source_snapshot_id,
        llm_metadata=v.llm_metadata,
    )


def _read(report: Report, current: ReportVersion | None) -> ReportRead:
    return ReportRead(
        **_summary(report).model_dump(),
        current_version=_version_read(current) if current is not None else None,
    )


# ─── Endpoints ───────────────────────────────────────────────────


class ReportsEngineInfo(BaseModel):
    """Tells the frontend which LLM backend is currently wired up.

    Used by the editor to surface an honest banner when the
    deterministic mock is active (no ``ANTHROPIC_API_KEY`` configured)
    so the operator never confuses canned text with real AI output.
    """

    backend: str
    planner_model: str
    content_model: str


@router.get(
    "/_engine",
    response_model=ReportsEngineInfo,
    summary="Active LLM backend for reports (mock vs anthropic)",
)
def get_engine(
    _current: Annotated[CurrentUser, Depends(get_current_user)],
) -> ReportsEngineInfo:
    """Return the active LLM client's identifier + default models.

    Cheap: no DB hit, no LLM call. Auth-gated so anonymous callers
    can't enumerate engine state. The static ``/_engine`` segment is
    deliberately leading-underscore so it can never collide with a
    real report id (report ids are UUID-shaped).
    """
    llm = get_llm_client()
    return ReportsEngineInfo(
        backend=llm.name,
        planner_model=llm.planner_model,
        content_model=llm.content_model,
    )


@router.get(
    "/_presets",
    response_model=ReportPresetList,
    summary="List report presets the caller may use",
)
def get_presets(
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> ReportPresetList:
    """Return the registry filtered by the caller's roles.

    Empty list is a valid, non-error response. P1 adds a workspace-owner
    branch: role-less providers owning a ``ProviderWorkspace`` see the
    three vendor-facing presets.
    """
    actor = _actor_from(current, db)
    presets = presets_for_roles(
        tuple(current.roles),
        is_workspace_owner=actor.is_workspace_owner,
    )
    # Diagnostic: presets coming back empty in production is almost always
    # an account-setup gap (no ProviderWorkspace bound to the caller), not
    # a code bug. Log at INFO so Render's default-level logs capture it —
    # the empty-state in the UI is intentionally generic, and we need a
    # paper trail to triage support tickets without DB access.
    if not presets:
        logger.info(
            "reports.presets_empty user_id=%s roles=%s is_workspace_owner=%s",
            current.user.id,
            list(current.roles),
            actor.is_workspace_owner,
        )
    return ReportPresetList(
        items=[
            ReportPresetSummary(
                id=p.id,
                title=p.title,
                description=p.description,
                audience=p.audience,
                recommended_prompt=p.recommended_prompt,
            )
            for p in presets
        ]
    )


@router.post(
    "/from-preset",
    response_model=ReportRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a report from a preset",
)
def post_from_preset(
    payload: CreateFromPresetRequest,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    organization_id: Annotated[str | None, Query()] = None,
) -> ReportRead:
    """Instantiate a report from a registered preset.

    Pre-fills title / description / audience from the preset. Does
    NOT run AI generation — the editor opens with the recommended
    prompt pre-populated and the user hits "Generate" to fill in
    the blocks via the existing pipeline.
    """
    preset = get_preset(payload.preset_id)
    if preset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown preset.")

    # Build the actor once and reuse for both the role-gate check and
    # the scope auto-resolve below — saves a duplicate workspace lookup.
    actor = _actor_from(current, db)

    # Role gate: never let a caller instantiate a preset they couldn't
    # even see in the list endpoint. The workspace-owner branch lets
    # role-less providers (P1) reach the vendor_facing presets.
    allowed = {
        p.id
        for p in presets_for_roles(
            tuple(current.roles),
            is_workspace_owner=actor.is_workspace_owner,
        )
    }
    if preset.id not in allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Role cannot instantiate this preset.",
        )

    # client_facing / vendor_facing presets require a scoping id per the
    # _validate_scope rule. Auto-resolve when the caller did not supply
    # one explicitly. internal_admin staff who use a client preset must
    # pass client_id in the body (no implicit anchor).
    client_id = payload.client_id
    vendor_id = payload.vendor_id
    # Resolve the caller's client_id for any client_facing preset when not
    # supplied — including per-provider reports (client-vendor-detail) that
    # carry a vendor_id, so the report stays anchored to the client's org and
    # appears in their reports list.
    if (
        preset.audience == ReportAudience.CLIENT_FACING
        and client_id is None
    ):
        from app.models.entities import Membership, Organization  # local import

        client_id = db.scalar(
            select(Organization.client_id)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(
                Membership.user_id == current.user.id,
                Membership.status == "active",
                Organization.client_id.isnot(None),
            )
            .limit(1)
        )
    elif preset.audience == ReportAudience.VENDOR_FACING:
        # P1: for workspace-owning providers, auto-fill vendor_id +
        # client_id from their ProviderWorkspace. Internal staff using
        # a vendor preset must supply at least vendor_id in the body.
        if vendor_id is None and actor.workspace_vendor_id is not None:
            vendor_id = actor.workspace_vendor_id
        if client_id is None and actor.workspace_client_id is not None:
            client_id = actor.workspace_client_id

        # P1.1 safety: a workspace-owning provider must not be able to
        # author a vendor_facing report against a *different* vendor by
        # passing its id in the body. Internal staff still may
        # (cross-tenant authorship is part of their role).
        if (
            actor.is_workspace_owner
            and vendor_id is not None
            and vendor_id != actor.workspace_vendor_id
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Cannot create a report for a vendor outside your workspace.",
            )

    # P1.8 (2026-05-20): qualify the from-preset title with the
    # workspace's display name when the actor is a workspace owner
    # so a provider doesn't end up with multiple identically-titled
    # reports the moment they click "Generar reporte actualizado"
    # twice. Mirrors the manually-seeded "<Preset> · <Vendor>"
    # pattern. Internal staff keep the bare preset title because they
    # operate across many workspaces and rename per-report.
    qualified_title = preset.title
    if actor.is_workspace_owner and actor.workspace_vendor_id:
        from app.models.entities import ProviderWorkspace, Vendor  # local import

        ws_name = db.scalar(
            select(ProviderWorkspace.display_name).where(
                ProviderWorkspace.vendor_id == actor.workspace_vendor_id,
                ProviderWorkspace.status == "active",
            )
        )
        if not ws_name:
            ws_name = db.scalar(
                select(Vendor.name).where(Vendor.id == actor.workspace_vendor_id)
            )
        if ws_name:
            qualified_title = f"{preset.title} · {ws_name}"
    elif vendor_id and qualified_title == preset.title:
        # Per-provider report authored by a client/internal user: name the
        # provider in the title so the reports list isn't full of identical
        # "Reporte por proveedor" rows.
        from app.models.entities import Vendor  # local import

        v_name = db.scalar(select(Vendor.name).where(Vendor.id == vendor_id))
        if v_name:
            qualified_title = f"{preset.title} · {v_name}"

    try:
        report, version = create_report(
            db,
            actor=actor,
            title=qualified_title,
            description=preset.description,
            audience=preset.audience,
            organization_id=organization_id,
            client_id=client_id,
            vendor_id=vendor_id,
            initial_content_json={
                "schema_version": 1,
                "blocks": [],
                "global": {"preset_id": preset.id, "recommended_prompt": preset.recommended_prompt},
            },
        )
    except ReportScopeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except ReportPermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    # Pick-template → generate flow: produce the first populated version inline
    # (hybrid AI-with-deterministic-fallback) so the caller can route straight
    # to a finished, read-only report. The deterministic registry is the floor,
    # so this never leaves the report empty even with no AI key.
    if payload.auto_generate:
        from app.services.reports.generate import generate_initial_version

        try:
            version = generate_initial_version(
                db,
                actor=actor,
                report=report,
                preset_id=preset.id,
                recommended_prompt=preset.recommended_prompt,
            )
        except ReportPermissionError as exc:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    return _read(report, version)


@router.post(
    "",
    response_model=ReportRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a report",
)
def post_report(
    payload: ReportCreate,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    organization_id: Annotated[str | None, Query()] = None,
) -> ReportRead:
    """Create a report and seed it with an initial v1 version.

    If the caller has exactly one organization membership, that's the
    owning org. Otherwise ``organization_id`` query param is required.
    """
    try:
        report, version = create_report(
            db,
            actor=_actor_from(current, db),
            title=payload.title,
            description=payload.description,
            audience=payload.audience,
            organization_id=organization_id,
            client_id=payload.client_id,
            vendor_id=payload.vendor_id,
            initial_content_json=payload.initial_content_json,
        )
    except ReportScopeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except ReportPermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return _read(report, version)


@router.get(
    "",
    response_model=ReportList,
    summary="List reports visible to the caller",
)
def get_reports(
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    organization_id: Annotated[str | None, Query()] = None,
    report_status: Annotated[ReportStatus | None, Query(alias="status")] = None,
    audience: Annotated[ReportAudience | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReportList:
    """List reports visible to the caller.

    ``audience`` narrows the list to a single audience. Server-side
    ``visible_audiences()`` is the security boundary — if a caller
    requests an audience they cannot see, the list returns empty
    rather than 403, mirroring the not-found semantics elsewhere in
    this router (avoids enumeration).
    """
    try:
        rows, total = list_reports(
            db,
            actor=_actor_from(current, db),
            organization_id=organization_id,
            status=report_status,
            audience=audience,
            limit=limit,
            offset=offset,
        )
    except ReportPermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return ReportList(items=[_summary(r) for r in rows], total=total)


@router.get(
    "/{report_id}",
    response_model=ReportRead,
    summary="Read a report + its latest version",
)
def get_one_report(
    report_id: str,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> ReportRead:
    try:
        report, version = get_report(db, actor=_actor_from(current, db), report_id=report_id)
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _read(report, version)


@router.patch(
    "/{report_id}",
    response_model=ReportRead,
    summary="Update report metadata",
)
def patch_one_report(
    report_id: str,
    payload: ReportPatch,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> ReportRead:
    try:
        report = patch_report(
            db,
            actor=_actor_from(current, db),
            report_id=report_id,
            title=payload.title,
            description=payload.description,
            audience=payload.audience,
            status=payload.status,
            client_id=payload.client_id,
            vendor_id=payload.vendor_id,
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ReportPermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ReportScopeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    # Re-fetch with the version so the response is symmetric to GET.
    _, version = get_report(db, actor=_actor_from(current, db), report_id=report.id)
    return _read(report, version)


@router.post(
    "/{report_id}/versions",
    response_model=ReportVersionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Save a new version",
)
def post_version(
    report_id: str,
    payload: ReportVersionCreate,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> ReportVersionRead:
    try:
        version = create_version(
            db,
            actor=_actor_from(current, db),
            report_id=report_id,
            content_json=payload.content_json,
            label=payload.label,
            plan_json=payload.plan_json,
            generated_by=payload.generated_by,
            parent_version_id=payload.parent_version_id,
            source_snapshot_id=payload.source_snapshot_id,
            llm_metadata=payload.llm_metadata,
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ReportPermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return _version_read(version)


@router.get(
    "/{report_id}/versions",
    response_model=ReportVersionList,
    summary="List versions of a report",
)
def get_versions(
    report_id: str,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> ReportVersionList:
    try:
        rows = list_versions(db, actor=_actor_from(current, db), report_id=report_id)
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ReportVersionList(items=[_version_summary(r) for r in rows], total=len(rows))


@router.get(
    "/{report_id}/versions/{version_number}",
    response_model=ReportVersionRead,
    summary="Read a specific version",
)
def get_one_version(
    report_id: str,
    version_number: int,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> ReportVersionRead:
    try:
        version = get_version(
            db,
            actor=_actor_from(current, db),
            report_id=report_id,
            version_number=version_number,
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ReportVersionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _version_read(version)


# ─── Phase 3.3a — Plan ───────────────────────────────────────────


@router.post(
    "/{report_id}/plan",
    response_model=PlanReportResponse,
    summary="Generate a structured plan for a report (no execution)",
)
def post_plan(
    report_id: str,
    payload: PlanReportRequest,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> PlanReportResponse:
    """Translate a natural-language request into a structured plan.

    Steps:
        1. Confirm the caller can read the report (404 otherwise).
        2. Assemble tenant-scoped context. Persists a
           ComplianceSnapshot row capturing exactly what the LLM
           was shown.
        3. Call the planner (LLM with tool-use catalog).
        4. Return the validated plan + the snapshot id.

    The plan is NOT saved as a ReportVersion here. That's a Phase
    3.3b decision (the streaming execution endpoint persists a
    version once the per-block content is generated).
    """
    _enforce_ai_budget(current)
    actor = _actor_from(current, db)

    try:
        report, _ = get_report(db, actor=actor, report_id=report_id)
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    scope = ReportScope(
        organization_id=report.organization_id,
        audience=ReportAudience(report.audience),
        client_id=report.client_id,
        vendor_id=report.vendor_id,
        period=payload.period,
    )

    try:
        context = assemble_context(db, actor=actor, scope=scope)
    except ReportPermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    llm = get_llm_client()
    try:
        plan = plan_report(llm=llm, context=context, user_prompt=payload.prompt)
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return PlanReportResponse(
        blocks=[
            PlannedBlockResponse(id=b.id, type=b.type, config=b.config)
            for b in plan.blocks
        ],
        rationale=plan.rationale,
        audience=ReportAudience(plan.audience),
        scope_hint=plan.scope_hint,
        model=plan.model,
        stop_reason=plan.stop_reason,
        usage=plan.usage,
        snapshot_id=plan.snapshot_id,
        llm_backend=llm.name,
    )


# ─── Phase 3.3b — Streaming generation ───────────────────────────


@router.post(
    "/{report_id}/generate",
    summary="Stream a full AI-generated report version (SSE)",
)
def post_generate(
    report_id: str,
    payload: PlanReportRequest,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> StreamingResponse:
    """End-to-end report generation, streamed as Server-Sent Events.

    Pipeline:
        1. Plan the report (3.3a) using the user's natural-language
           prompt. Same Context Assembler, same audience guards.
        2. Execute the plan block-by-block, fetching tenant-scoped
           data and streaming per-block AI summaries.
        3. Persist a new ReportVersion when generation completes.

    Event protocol (see docs/REPORTS_ARCHITECTURE.md §8):
        event: plan
        event: block_start
        event: block_data
        event: ai_summary_delta   (zero or more)
        event: block_complete
        event: version_saved
        event: done
        event: error              (zero or more, non-fatal per-block)

    The client should treat any non-`done` final state as a partial
    generation. On `done` the persisted version is canonical and the
    canvas can switch from streaming-mode to editable-mode.
    """
    _enforce_ai_budget(current)
    actor = _actor_from(current, db)

    try:
        report, _ = get_report(db, actor=actor, report_id=report_id)
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    scope = ReportScope(
        organization_id=report.organization_id,
        audience=ReportAudience(report.audience),
        client_id=report.client_id,
        vendor_id=report.vendor_id,
        period=payload.period,
    )

    try:
        context = assemble_context(db, actor=actor, scope=scope)
    except ReportPermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    llm = get_llm_client()

    try:
        plan = plan_report(llm=llm, context=context, user_prompt=payload.prompt)
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    def _sse_iter() -> Annotated[any, 'sse']:
        try:
            for event_name, data in execute_plan(
                db=db,
                actor=actor,
                report=report,
                plan=plan,
                context=context,
                llm=llm,
            ):
                yield _sse_frame(event_name, data)
        except Exception as exc:  # pragma: no cover — defensive
            yield _sse_frame(
                "error",
                {"code": "execution_failed", "message": str(exc)},
            )

    return StreamingResponse(
        _sse_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # disable Nginx/Vercel proxy buffering
        },
    )


def _sse_frame(event_name: str, data: dict) -> str:
    """Format a single Server-Sent Event frame.

    The SSE spec wants ``event: <name>\\ndata: <payload>\\n\\n``.
    Multi-line JSON is fine because we serialize without newlines.
    """
    return f"event: {event_name}\ndata: {_json.dumps(data, default=str)}\n\n"


# ─── Phase 3.3c — Copilot ────────────────────────────────────────


class ConversationTurnPayload(BaseModel):
    id: str
    turn_number: int
    role: ConversationRole
    content: dict
    created_at: datetime


class ConversationList(BaseModel):
    items: list[ConversationTurnPayload]


@router.get(
    "/{report_id}/conversation",
    response_model=ConversationList,
    summary="Read the full conversation for a report",
)
def get_conversation(
    report_id: str,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> ConversationList:
    actor = _actor_from(current, db)
    try:
        get_report(db, actor=actor, report_id=report_id)
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    turns = list_conversation(db, report_id=report_id)
    return ConversationList(
        items=[
            ConversationTurnPayload(
                id=t.id,
                turn_number=t.turn_number,
                role=ConversationRole(t.role),
                content=t.content_json,
                created_at=t.created_at,
            )
            for t in turns
        ]
    )


class ConversationSendRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    canvas_summary: dict | None = None


@router.post(
    "/{report_id}/conversation",
    summary="Send a chat message; copilot replies via SSE",
)
def post_conversation(
    report_id: str,
    payload: ConversationSendRequest,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> StreamingResponse:
    """Stream the copilot's reply to a user message.

    Pipeline:
        1. Append the user turn (text-shaped) to report_conversations.
        2. Assemble fresh context (cheap — same Context Assembler).
        3. Stream the assistant's reply token-by-token via SSE.
        4. Append the full assistant turn at end of stream.

    Event protocol:
        event: turn_start    { role: 'assistant' }
        event: delta         { text }                (0..N)
        event: turn_complete { turn: ConversationTurn }
        event: done          { }
        event: error         { code, message }       (terminal)
    """
    _enforce_ai_budget(current)
    actor = _actor_from(current, db)

    try:
        report, _ = get_report(db, actor=actor, report_id=report_id)
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    scope = ReportScope(
        organization_id=report.organization_id,
        audience=ReportAudience(report.audience),
        client_id=report.client_id,
        vendor_id=report.vendor_id,
    )

    try:
        context = assemble_context(db, actor=actor, scope=scope)
    except ReportPermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    # Persist the user turn BEFORE streaming the reply so the
    # conversation history is correct even if the stream is cancelled.
    user_turn = append_turn(
        db,
        report_id=report_id,
        role=ConversationRole.USER,
        content=text_turn(payload.message),
        actor=actor,
    )

    history = list(recent_messages_for_llm(db, report_id=report_id))
    canvas_summary = payload.canvas_summary or {}
    llm = get_llm_client()

    def _sse_iter():
        yield _sse_frame("turn_start", {"role": "assistant"})
        accumulated = ""
        try:
            for chunk in chat_completion(
                llm=llm,
                context=context,
                canvas_summary=canvas_summary,
                history=history,
                user_message=payload.message,
            ):
                accumulated += chunk
                yield _sse_frame("delta", {"text": chunk})
        except Exception as exc:  # pragma: no cover — defensive
            yield _sse_frame(
                "error", {"code": "chat_failed", "message": str(exc)}
            )
            # Persist an error turn so the next request can see it.
            append_turn(
                db,
                report_id=report_id,
                role=ConversationRole.ASSISTANT,
                content=error_turn("chat_failed", str(exc)),
                actor=actor,
            )
            return

        # Persist the assistant turn with the full text.
        assistant_turn = append_turn(
            db,
            report_id=report_id,
            role=ConversationRole.ASSISTANT,
            content=text_turn(accumulated),
            actor=actor,
        )
        yield _sse_frame(
            "turn_complete",
            {
                "turn": {
                    "id": assistant_turn.id,
                    "turn_number": assistant_turn.turn_number,
                    "role": assistant_turn.role,
                    "content": assistant_turn.content_json,
                    "created_at": assistant_turn.created_at.isoformat(),
                }
            },
        )
        yield _sse_frame(
            "done", {"user_turn_id": user_turn.id, "snapshot_id": context.snapshot_id}
        )

    return StreamingResponse(
        _sse_iter(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


class BlockExplainRequest(BaseModel):
    question: str | None = Field(default=None, max_length=2000)


class BlockExplainResponse(BaseModel):
    block_id: str
    explanation: str
    llm_backend: str


@router.post(
    "/{report_id}/blocks/{block_id}/explain",
    response_model=BlockExplainResponse,
    summary="Generate a focused explanation for one block",
)
def post_explain_block(
    report_id: str,
    block_id: str,
    payload: BlockExplainRequest,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> BlockExplainResponse:
    """Return a short narrative explaining one block of the current
    report version. Synchronous (not SSE) — explanations are short.
    """
    _enforce_ai_budget(current)
    actor = _actor_from(current, db)
    try:
        report, current_version = get_report(
            db, actor=actor, report_id=report_id
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    if current_version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report has no version yet.")

    blocks = current_version.content_json.get("blocks") or []
    block = next((b for b in blocks if b.get("id") == block_id), None)
    if block is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Block {block_id} not found.")

    scope = ReportScope(
        organization_id=report.organization_id,
        audience=ReportAudience(report.audience),
        client_id=report.client_id,
        vendor_id=report.vendor_id,
    )
    try:
        context = assemble_context(db, actor=actor, scope=scope)
    except ReportPermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    llm = get_llm_client()
    chunks: list[str] = []
    try:
        for chunk in explain_block(
            llm=llm,
            context=context,
            block_type=block.get("type", "unknown"),
            block_data=block.get("data"),
            audience=ReportAudience(report.audience),
            question=payload.question,
        ):
            chunks.append(chunk)
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return BlockExplainResponse(
        block_id=block_id,
        explanation="".join(chunks),
        llm_backend=llm.name,
    )


# ─── Copilot — block-composition suggestions (R6) ─────────────────


class SuggestBlocksRequest(BaseModel):
    """Body for the suggest-blocks endpoint.

    ``intent`` is the user's natural-language request that triggers
    the suggestion. The frontend's "Sugerir bloques" button sends a
    canned prompt; power users can wire a custom intent later.
    ``canvas_summary`` mirrors the shape the chat copilot already
    sends — block types currently on the canvas + key signals — so
    the model can dedup against what's already rendered.
    """

    intent: str = Field(min_length=1, max_length=2000)
    canvas_summary: dict | None = None


class BlockSuggestionPayload(BaseModel):
    type: str
    config: dict
    rationale: str


class SuggestBlocksResponse(BaseModel):
    suggestions: list[BlockSuggestionPayload]
    llm_backend: str
    model: str


@router.post(
    "/{report_id}/copilot/suggest-blocks",
    response_model=SuggestBlocksResponse,
    summary="Copilot returns structured block proposals the user can apply",
)
def post_suggest_blocks(
    report_id: str,
    payload: SuggestBlocksRequest,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> SuggestBlocksResponse:
    """Return up to ``MAX_SUGGESTIONS`` block drafts the user can
    apply with one click. Synchronous — suggestions are short and the
    UI renders a card per result, not a stream.
    """
    _enforce_ai_budget(current)
    actor = _actor_from(current, db)

    try:
        report, _ = get_report(db, actor=actor, report_id=report_id)
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    scope = ReportScope(
        organization_id=report.organization_id,
        audience=ReportAudience(report.audience),
        client_id=report.client_id,
        vendor_id=report.vendor_id,
    )

    try:
        context = assemble_context(db, actor=actor, scope=scope)
    except ReportPermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    llm = get_llm_client()
    try:
        result = suggest_blocks(
            llm=llm,
            context=context,
            canvas_summary=payload.canvas_summary or {},
            intent=payload.intent,
        )
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return SuggestBlocksResponse(
        suggestions=[
            BlockSuggestionPayload(
                type=s.type, config=s.config, rationale=s.rationale
            )
            for s in result.suggestions
        ],
        llm_backend=llm.name,
        model=result.model,
    )


class BlockRegenerateRequest(BaseModel):
    """No body fields required; the regenerate uses the block's stored
    config + the current scope. Reserved for future overrides."""

    pass


class BlockRegenerateResponse(BaseModel):
    block_id: str
    ai_summary_text: str
    model: str
    llm_backend: str
    version_id: str
    version_number: int


@router.post(
    "/{report_id}/blocks/{block_id}/regenerate",
    response_model=BlockRegenerateResponse,
    summary="Regenerate the AI summary for one block (persists a new version)",
)
def post_regenerate_block(
    report_id: str,
    block_id: str,
    _payload: BlockRegenerateRequest,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> BlockRegenerateResponse:
    """Re-run the per-block AI summary generator for one block.

    Persists a new ReportVersion with the regenerated summary
    embedded. The rest of the content is copied from the current
    version. The block must already exist in the current version.
    """
    _enforce_ai_budget(current)
    from app.services.reports.blocks.ai_summaries import (
        collect_summary,
        has_ai_summary,
    )

    actor = _actor_from(current, db)
    try:
        report, current_version = get_report(db, actor=actor, report_id=report_id)
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    if current_version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report has no version yet.")

    blocks = list(current_version.content_json.get("blocks") or [])
    target_idx = next(
        (i for i, b in enumerate(blocks) if b.get("id") == block_id), None
    )
    if target_idx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Block {block_id} not found.")
    target = blocks[target_idx]
    block_type = target.get("type", "")
    if not has_ai_summary(block_type):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Block type '{block_type}' has no AI summary to regenerate.",
        )

    scope = ReportScope(
        organization_id=report.organization_id,
        audience=ReportAudience(report.audience),
        client_id=report.client_id,
        vendor_id=report.vendor_id,
    )
    try:
        context = assemble_context(db, actor=actor, scope=scope)
    except ReportPermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    llm = get_llm_client()
    try:
        new_text = collect_summary(
            block_type=block_type,
            config=target.get("config") or {},
            data=target.get("data"),
            audience=ReportAudience(report.audience),
            llm=llm,
        )
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    blocks[target_idx] = {
        **target,
        "ai_summary": {
            "text": new_text,
            "model": llm.content_model,
            "prompt_hash": context.snapshot_hash,
            "generated_at": datetime.utcnow().isoformat(),
            "source_snapshot_id": context.snapshot_id,
        },
    }

    new_content = {
        **current_version.content_json,
        "blocks": blocks,
    }
    new_version = create_version(
        db,
        actor=actor,
        report_id=report_id,
        content_json=new_content,
        label=f"Regenerated {block_type}",
        plan_json=current_version.plan_json,
        generated_by=ReportVersionOrigin.AI_REFINED,
        parent_version_id=current_version.id,
        source_snapshot_id=context.snapshot_id,
        llm_metadata={
            "backend": llm.name,
            "model": llm.content_model,
            "regenerated_block_id": block_id,
        },
    )

    return BlockRegenerateResponse(
        block_id=block_id,
        ai_summary_text=new_text,
        model=llm.content_model,
        llm_backend=llm.name,
        version_id=new_version.id,
        version_number=new_version.version_number,
    )


# ─── P1.7 — Refresh report data (no LLM) ────────────────────────


class RefreshDataRequest(BaseModel):
    """No body fields required. Reserved for future overrides (e.g.
    selectively refreshing a subset of block types)."""

    pass


class RefreshedBlockSummary(BaseModel):
    block_id: str
    block_type: str
    refreshed: bool


class RefreshDataResponse(BaseModel):
    version_id: str
    version_number: int
    refreshed_blocks: list[RefreshedBlockSummary]
    fetched_at: str


@router.post(
    "/{report_id}/refresh-data",
    response_model=RefreshDataResponse,
    summary=(
        "Refresh deterministic block data without re-prompting the LLM. "
        "P1.7: 'Actualizar con datos de hoy'."
    ),
)
def post_refresh_report_data(
    report_id: str,
    _payload: RefreshDataRequest,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> RefreshDataResponse:
    """Re-run every block's data fetcher against today's snapshot.

    For each block in the current version:

    - ``text`` / ``divider`` / any block whose fetcher returns ``None``
      → passes through unchanged.
    - ``ai_recommendation`` → unchanged. Its ``data`` carries the
      upstream block summaries baked in at generation time; refreshing
      without re-prompting would desynchronize the prose from its
      grounding.
    - Everything else (``compliance_state``, ``attention_list``,
      ``upcoming_deadlines``, ``prioritized_actions``,
      ``executive_summary``, ``kpi_strip``, ``vendor_risk_matrix``)
      → ``block["data"]`` is replaced with the fresh, audience-sanitized
      fetch. ``block["ai_summary"]`` is preserved verbatim — the LLM is
      never consulted in this path.

    Persists a new ``ReportVersion`` labeled ``Datos actualizados``,
    advances ``current_version_id`` and returns the per-block refresh
    summary so the editor can light up freshness indicators.
    """
    from app.services.reports.blocks.data_fetchers import fetch_for_block
    from app.services.reports.executor import _redact_for_audience

    # Shares the AI-heavy budget because a runaway client can still
    # drive a lot of DB work per request even though no LLM call is
    # made (every block re-fetches against today's snapshot).
    _enforce_ai_budget(current)

    actor = _actor_from(current, db)
    try:
        report, current_version = get_report(db, actor=actor, report_id=report_id)
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    if current_version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report has no version yet.")

    audience = ReportAudience(report.audience)
    scope = ReportScope(
        organization_id=report.organization_id,
        audience=audience,
        client_id=report.client_id,
        vendor_id=report.vendor_id,
    )
    try:
        context = assemble_context(db, actor=actor, scope=scope)
    except ReportPermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    fetched_at = datetime.utcnow().isoformat() + "Z"
    blocks_in = list(current_version.content_json.get("blocks") or [])
    blocks_out: list[dict] = []
    summary: list[RefreshedBlockSummary] = []

    for block in blocks_in:
        block_type = block.get("type", "")
        block_id = block.get("id", "")
        # ai_recommendation's data is the LLM grounding — refreshing it
        # without re-prompting would break the contract. Pass through.
        if block_type == "ai_recommendation":
            blocks_out.append(block)
            summary.append(
                RefreshedBlockSummary(
                    block_id=block_id, block_type=block_type, refreshed=False
                )
            )
            continue
        try:
            fresh_data = fetch_for_block(
                block_type=block_type,
                config=block.get("config") or {},
                scope=scope,
                db=db,
            )
        except Exception as exc:  # noqa: BLE001 — fetcher failure shouldn't 500 the whole refresh
            logger.exception(
                "[reports.refresh] fetch failed for block_type=%s", block_type
            )
            del exc
            blocks_out.append(block)
            summary.append(
                RefreshedBlockSummary(
                    block_id=block_id, block_type=block_type, refreshed=False
                )
            )
            continue
        if fresh_data is None:
            # text / divider / unknown — keep as-is.
            blocks_out.append(block)
            summary.append(
                RefreshedBlockSummary(
                    block_id=block_id, block_type=block_type, refreshed=False
                )
            )
            continue
        sanitized = _redact_for_audience(block_type, fresh_data, audience)
        blocks_out.append({**block, "data": sanitized})
        summary.append(
            RefreshedBlockSummary(
                block_id=block_id, block_type=block_type, refreshed=True
            )
        )

    new_content = {**current_version.content_json, "blocks": blocks_out}
    new_version = create_version(
        db,
        actor=actor,
        report_id=report_id,
        content_json=new_content,
        label="Datos actualizados",
        plan_json=current_version.plan_json,
        generated_by=ReportVersionOrigin.AI_REFINED,
        parent_version_id=current_version.id,
        source_snapshot_id=context.snapshot_id,
        llm_metadata={
            "backend": "none",
            "model": "data_refresh",
            "refreshed_block_count": sum(1 for s in summary if s.refreshed),
        },
    )

    return RefreshDataResponse(
        version_id=new_version.id,
        version_number=new_version.version_number,
        refreshed_blocks=summary,
        fetched_at=fetched_at,
    )


# ──────────────────────────────────────────────────────────────────
# Phase 10A — Report exports
# ──────────────────────────────────────────────────────────────────
#
# Three endpoints back the export pipeline:
#   POST /reports/{report_id}/exports         → create + schedule
#   GET  /reports/exports/{export_id}         → poll status
#   GET  /reports/exports/{export_id}/download → stream / redirect
#
# All three reuse the existing ``get_report`` permission helper as
# the authorization gate (no enumeration: cross-tenant ids return
# 404, never 403). The download endpoint prefers an S3 presigned
# URL when the backend supports it; LocalStorageService streams the
# file via ``FileResponse``.
#
# Slice 10A ships HTML only. The dispatcher in
# ``app.services.reports.export.run_report_export`` is the single
# spot 10B (PDF) and 10C (Excel) will extend.


class CreateReportExportPayload(BaseModel):
    """Request body for ``POST /reports/{report_id}/exports``.

    ``version_id`` is optional — when omitted, the report's current
    version is used. Pinning a specific version is supported so a
    future "export this old version" UI can pass an explicit value.
    """

    format: str = Field(..., description="Export format. 10A supports 'html' only.")
    version_id: str | None = Field(
        default=None,
        description="Version to export. Defaults to the report's current_version_id.",
    )


class ReportExportRead(BaseModel):
    """Public shape of a ``ReportExport`` row.

    Slice 10A does not expose ``storage_key`` or ``error_text`` to
    non-staff readers — both can leak internal layout. The status +
    bytes + timestamps are enough for the polling UI; the actual
    bytes flow through the dedicated /download endpoint.
    """

    id: str
    report_id: str
    version_id: str
    format: str
    status: str
    bytes: int | None
    requested_at: datetime
    ready_at: datetime | None
    error_text: str | None


def _read_export(row: ReportExport) -> ReportExportRead:
    return ReportExportRead(
        id=row.id,
        report_id=row.report_id,
        version_id=row.version_id,
        format=row.format,
        status=row.status,
        bytes=row.bytes,
        requested_at=row.requested_at,
        ready_at=row.ready_at,
        error_text=row.error_text,
    )


def _run_report_export_with_fresh_session(export_id: str) -> None:
    """BackgroundTask entry point that owns its own DB session.

    The request session is closed by the time the background task
    fires (FastAPI's ``get_db`` dependency cleans up on response).
    A fresh ``SessionLocal()`` keeps the worker's writes independent
    of the request lifecycle and matches the pattern the existing
    Slack-delivery and audit-log paths use.
    """
    db = SessionLocal()
    try:
        run_report_export(db, export_id)
        db.commit()
    finally:
        db.close()


@router.post(
    "/{report_id}/exports",
    response_model=ReportExportRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start an asynchronous export of a report version",
)
def post_report_export(
    report_id: str,
    payload: CreateReportExportPayload,
    db: DbSession,
    background_tasks: BackgroundTasks,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> ReportExportRead:
    """Create a ``ReportExport`` row and schedule the renderer.

    The renderer runs as a FastAPI ``BackgroundTask`` so the request
    returns immediately. Callers should poll
    ``GET /reports/exports/{export_id}`` until ``status == "ready"``
    (or ``"failed"``) before requesting the download.
    """
    try:
        report, current_version = get_report(
            db, actor=_actor_from(current, db), report_id=report_id
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    # Resolve the version to export. Default = the report's current
    # version (set on the Report row). Explicit version_id must belong
    # to this report or we 404 — never confirm cross-report ids.
    if payload.version_id is not None:
        version = db.get(ReportVersion, payload.version_id)
        if version is None or version.report_id != report.id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="Versión no encontrada.",
            )
    else:
        version = current_version
        if version is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El reporte no tiene una versión actual para exportar.",
            )

    try:
        row = start_report_export(
            db,
            report=report,
            version=version,
            format=payload.format,
            requested_by_user_id=current.user.id,
        )
    except ReportExportError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    db.commit()
    db.refresh(row)
    background_tasks.add_task(_run_report_export_with_fresh_session, row.id)
    return _read_export(row)


def _load_export_for_user(
    db: Session, *, export_id: str, current: CurrentUser
) -> ReportExport:
    """Look up an export and confirm the caller may see it.

    Reuses ``get_report`` so we never have to duplicate the audience
    / tenant scoping logic. A 404 covers both "row doesn't exist" and
    "caller can't see the parent report" — no enumeration.
    """
    row = db.get(ReportExport, export_id)
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Exportación no encontrada."
        )
    try:
        get_report(db, actor=_actor_from(current, db), report_id=row.report_id)
    except ReportNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Exportación no encontrada."
        ) from exc
    return row


@router.get(
    "/exports/{export_id}",
    response_model=ReportExportRead,
    summary="Poll the status of an export",
)
def get_report_export(
    export_id: str,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> ReportExportRead:
    row = _load_export_for_user(db, export_id=export_id, current=current)
    return _read_export(row)


@router.get(
    "/exports/{export_id}/download",
    summary="Stream (or redirect to) the rendered export artifact",
)
def get_report_export_download(
    export_id: str,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
):
    row = _load_export_for_user(db, export_id=export_id, current=current)
    if row.status != "ready" or not row.storage_key:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"Export en estado '{row.status}'. Espera a que sea 'ready'."
            ),
        )
    storage = get_storage_service()
    # Per-format media type. Falls back to application/octet-stream
    # for any unrecognised value so the browser still treats the
    # response as a file (rather than rendering it inline).
    media_type = {
        "html": "text/html; charset=utf-8",
        "pdf": "application/pdf",
    }.get(row.format, "application/octet-stream")
    download_name = f"checkwise-report-{row.report_id}-v{row.version_id}.{row.format}"
    disposition = f'attachment; filename="{download_name}"'

    # Prefer presigned URL when the backend supports it (S3/R2) — same
    # pattern the document-download path uses. LocalStorageService
    # returns None here and we stream via FileResponse.
    presigned = storage.presigned_download_url(
        row.storage_key, content_disposition=disposition
    )
    if presigned is not None:
        return RedirectResponse(presigned, status_code=status.HTTP_302_FOUND)

    path = storage.open_for_read(row.storage_key)
    if not path.exists():
        # Orphaned storage key — clean 404 (matches the document path).
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Artefacto no disponible en almacenamiento.",
        )
    return FileResponse(
        path=str(path),
        media_type=media_type,
        filename=download_name,
    )


# ──────────────────────────────────────────────────────────────────
# Phase 10D — Report shares
# ──────────────────────────────────────────────────────────────────
#
# Three bearer-auth endpoints for managing share links:
#   POST   /reports/{id}/shares      → mint a token (returned once)
#   GET    /reports/{id}/shares      → list active shares
#   DELETE /reports/shares/{id}      → revoke a share
#
# The PUBLIC consume route lives in app.api.v1.shares (different
# prefix `/r/`, different security model — no auth, just token).
# Permission gate here is `get_report`: cross-tenant report ids
# return 404 (no enumeration), shares listed/revoked by id are
# always re-checked against the parent report's gate so a leaked
# share id can't be revoked across tenants.


class CreateReportSharePayload(BaseModel):
    """Body for ``POST /reports/{id}/shares``.

    ``expires_at`` is optional — caller-supplied. The frontend
    defaults to now + 30 days unless the sender picks "no expiry"
    or a custom date. Past timestamps return 422; we never mint
    a pre-expired token.

    ``password`` is also optional. When set, the recipient must
    present it before the consume endpoint returns the rendered
    HTML. The password itself is bcrypt-hashed before storage; the
    raw value never lives anywhere except this request body.

    ``version_id`` is optional — defaults to the report's current
    version.
    """

    version_id: str | None = None
    expires_at: datetime | None = None
    password: str | None = Field(default=None, min_length=4)


class ReportShareRead(BaseModel):
    """Public shape of a ReportShare row.

    Tokens / password hashes are NEVER returned. The raw token is
    only available once, in the response to the mint endpoint, via
    :class:`MintReportShareResponse`.
    """

    id: str
    report_id: str
    version_id: str
    audience: str
    expires_at: datetime | None
    revoked_at: datetime | None
    last_accessed_at: datetime | None
    access_count: int
    has_password: bool
    created_at: datetime


class MintReportShareResponse(BaseModel):
    """One-time response carrying the freshly-minted raw token.

    ``url`` is the absolute consume URL ready to copy/paste into an
    email. The frontend should display it and ``token`` in the
    success modal, then never fetch them again — re-opening the
    share dialog only ever lists the existing rows via the
    no-token-fields ``ReportShareRead`` shape.
    """

    share: ReportShareRead
    token: str
    url: str


class ReportShareList(BaseModel):
    items: list[ReportShareRead]


def _read_share(row: ReportShare) -> ReportShareRead:
    return ReportShareRead(
        id=row.id,
        report_id=row.report_id,
        version_id=row.version_id,
        audience=row.audience,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        last_accessed_at=row.last_accessed_at,
        access_count=row.access_count,
        has_password=row.password_hash is not None,
        created_at=row.created_at,
    )


def _share_consume_url(token: str) -> str:
    """Build the absolute URL the recipient opens.

    Prefers ``settings.PUBLIC_BASE_URL`` (configured per environment
    in render.yaml / .env). Falls back to a relative path so dev
    setups without that var still produce a usable token + path
    pair — the frontend can prepend window.location.origin.
    """
    from app.core.config import settings as cfg

    base = getattr(cfg, "PUBLIC_BASE_URL", None) or getattr(cfg, "API_BASE_URL", None)
    path = f"/api/v1/r/{token}"
    if base:
        return f"{base.rstrip('/')}{path}"
    return path


@router.post(
    "/{report_id}/shares",
    response_model=MintReportShareResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mint a public share link for a report version",
)
def post_report_share(
    report_id: str,
    payload: CreateReportSharePayload,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> MintReportShareResponse:
    """Create a public share link. The raw token is returned ONCE.

    Reuses ``get_report`` for the permission gate so cross-tenant
    report ids return 404 (no enumeration).
    """
    try:
        report, current_version = get_report(
            db, actor=_actor_from(current, db), report_id=report_id
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    if payload.version_id is not None:
        version = db.get(ReportVersion, payload.version_id)
        if version is None or version.report_id != report.id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Versión no encontrada."
            )
    else:
        version = current_version
        if version is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El reporte no tiene una versión actual para compartir.",
            )

    if payload.expires_at is not None:
        # Normalize tz-naive datetimes to UTC so the comparison
        # against utc_now() (tz-aware) doesn't raise. Past
        # timestamps are rejected — we never mint a pre-expired
        # token (frontend would surface it as immediately broken).
        expires = payload.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires <= datetime.now(UTC):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="expires_at debe ser una fecha futura.",
            )
    else:
        expires = None

    row, raw_token = mint_share(
        db,
        report=report,
        version=version,
        audience=report.audience,
        requested_by=current.user,
        expires_at=expires,
        password=payload.password,
    )
    db.commit()
    db.refresh(row)
    return MintReportShareResponse(
        share=_read_share(row),
        token=raw_token,
        url=_share_consume_url(raw_token),
    )


@router.get(
    "/{report_id}/shares",
    response_model=ReportShareList,
    summary="List share links for a report (no tokens)",
)
def get_report_shares(
    report_id: str,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> ReportShareList:
    """List shares scoped to the report.

    Both active and revoked rows surface — the UI shows revoked
    ones grayed out so the sender can see "I shut that one down".
    Tokens / hashes are never in the response.
    """
    try:
        report, _ = get_report(
            db, actor=_actor_from(current, db), report_id=report_id
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    rows = list(
        db.scalars(
            select(ReportShare)
            .where(ReportShare.report_id == report.id)
            .order_by(ReportShare.created_at.desc())
        )
    )
    return ReportShareList(items=[_read_share(r) for r in rows])


@router.delete(
    "/shares/{share_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a share link",
)
def delete_report_share(
    share_id: str,
    db: DbSession,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> Response:
    """Revoke a share. Idempotent — re-revoking is also 204.

    Cross-tenant share ids return 404 because the parent report's
    permission gate fails — no enumeration of share ids across
    organisations.
    """
    share = db.get(ReportShare, share_id)
    if share is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Enlace compartido no encontrado.")
    try:
        get_report(db, actor=_actor_from(current, db), report_id=share.report_id)
    except ReportNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Enlace compartido no encontrado."
        ) from exc
    revoke_share(db, share=share)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
