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
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.auth import CurrentUser, get_current_user
from app.constants.reports import ReportAudience, ReportStatus
from app.db.session import get_db
from app.models.entities import Report, ReportVersion
from app.schemas.reports import (
    PlannedBlockResponse,
    PlanReportRequest,
    PlanReportResponse,
    ReportCreate,
    ReportList,
    ReportPatch,
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
from app.services.reports.executor import execute_plan
from app.services.reports.llm import LLMError, get_llm_client
from app.services.reports.planner import plan_report

router = APIRouter(prefix="/reports", tags=["reports"])
DbSession = Annotated[Session, Depends(get_db)]


# ─── Helpers ─────────────────────────────────────────────────────


def _actor_from(current: CurrentUser) -> ReportActor:
    return ReportActor(
        user_id=current.user.id,
        organization_ids=tuple(current.organization_ids),
        roles=tuple(current.roles),
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
            actor=_actor_from(current),
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
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReportList:
    try:
        rows, total = list_reports(
            db,
            actor=_actor_from(current),
            organization_id=organization_id,
            status=report_status,
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
        report, version = get_report(db, actor=_actor_from(current), report_id=report_id)
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
            actor=_actor_from(current),
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
    _, version = get_report(db, actor=_actor_from(current), report_id=report.id)
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
            actor=_actor_from(current),
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
        rows = list_versions(db, actor=_actor_from(current), report_id=report_id)
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
            actor=_actor_from(current),
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
    actor = _actor_from(current)

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
    actor = _actor_from(current)

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
