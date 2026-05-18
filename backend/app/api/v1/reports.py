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
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
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
from app.db.session import get_db
from app.models.entities import Report, ReportVersion
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
from app.services.reports.executor import execute_plan
from app.services.reports.llm import LLMError, get_llm_client
from app.services.reports.planner import plan_report
from app.services.reports.templates import get_preset, presets_for_roles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])
DbSession = Annotated[Session, Depends(get_db)]


# ─── Helpers ─────────────────────────────────────────────────────


def _actor_from(current: CurrentUser, db: Session | None = None) -> ReportActor:
    """Build a tenant-scoping ReportActor from the request principal.

    For role-less users, P1 adds a workspace lookup: if the caller
    owns a ``ProviderWorkspace`` (the provider portal binding), pick
    up its ``vendor_id`` / ``client_id`` and inject them into the
    actor. If an ``Organization`` exists with the same ``client_id``,
    the actor also gains that org in ``organization_ids`` so
    ``create_report``'s owning-org resolution still works.

    ``db`` is optional for back-compat — callers that don't need the
    workspace branch (e.g. lightweight reads in the AI pipeline that
    already have the actor pre-built) can omit it.
    """
    workspace_vendor_id: str | None = None
    workspace_client_id: str | None = None
    org_ids: list[str] = list(current.organization_ids)

    if db is not None and not current.roles:
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

    return ReportActor(
        user_id=current.user.id,
        organization_ids=tuple(org_ids),
        roles=tuple(current.roles),
        workspace_vendor_id=workspace_vendor_id,
        workspace_client_id=workspace_client_id,
    )


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
    if (
        preset.audience == ReportAudience.CLIENT_FACING
        and client_id is None
        and not vendor_id
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

    try:
        report, version = create_report(
            db,
            actor=actor,
            title=preset.title,
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
