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

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.auth import CurrentUser, get_current_user
from app.constants.reports import ReportStatus
from app.db.session import get_db
from app.models.entities import Report, ReportVersion
from app.schemas.reports import (
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
