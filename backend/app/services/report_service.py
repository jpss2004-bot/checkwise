"""Reports service layer.

CRUD operations for the Report and ReportVersion entities, with tenant
+ audience guards. Pure SQLAlchemy here — no FastAPI dependencies.
The API layer in ``app/api/v1/reports.py`` is responsible for
translating service errors into HTTP responses.

Phase 3.1 ships:
- create_report
- list_reports
- get_report
- patch_report
- create_version
- list_versions
- get_version

Phase 3.3+ adds AI-generated versions, snapshots, conversations.

All read paths enforce:
- Internal staff (``internal_admin`` or ``reviewer``) can see anything.
- Everyone else can only see reports whose ``organization_id`` is in
  their token's ``organization_ids``.

Write paths additionally require:
- The user must hold a membership in the report's owning org (or be
  internal staff).

The audience field is enforced in two places: at write time the
CHECK constraint + this service validate that non-``internal_only``
reports carry a client_id or vendor_id; at the API layer audience-
based redaction will kick in starting Phase 3.3 when we render report
content. Phase 3.1 stops short of redaction because no real data is
rendered yet — we're only shipping the entity layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants.reports import (
    ReportAudience,
    ReportStatus,
    ReportVersionOrigin,
)
from app.constants.roles import MembershipRole
from app.models.entities import (
    Membership,
    Report,
    ReportVersion,
    new_id,
    utc_now,
)

# ─── Exceptions ─────────────────────────────────────────────────


class ReportServiceError(Exception):
    """Base class for service-layer failures.

    The API layer converts each subclass to a specific HTTP code.
    Keep the exceptions narrow — generic errors become 500s.
    """


class ReportNotFoundError(ReportServiceError):
    """The requested report does not exist or is not visible to the caller."""


class ReportVersionNotFoundError(ReportServiceError):
    """The requested version does not exist for this report."""


class ReportPermissionError(ReportServiceError):
    """The caller lacks the membership required for this action."""


class ReportScopeError(ReportServiceError):
    """Audience says client/vendor scope required but neither was provided."""


# ─── Caller context ─────────────────────────────────────────────


@dataclass(frozen=True)
class ReportActor:
    """Tenant-scoping context derived from the authenticated user.

    Built once per request in the API layer and passed verbatim through
    the service. Keeping it separate from CurrentUser means service
    functions can be unit-tested without an HTTP fixture.
    """

    user_id: str
    organization_ids: tuple[str, ...]
    roles: tuple[str, ...]

    @property
    def is_internal(self) -> bool:
        """True for internal staff: internal_admin OR reviewer.

        Internal staff cross-organization access matches the existing
        admin/reviewer endpoints.
        """
        return (
            MembershipRole.INTERNAL_ADMIN in self.roles
            or MembershipRole.REVIEWER in self.roles
        )


# ─── Helpers ────────────────────────────────────────────────────


def _validate_scope(audience: str, client_id: str | None, vendor_id: str | None) -> None:
    """Mirror of the DB CHECK constraint, but with nicer error copy."""
    if audience == ReportAudience.INTERNAL_ONLY:
        return
    if not client_id and not vendor_id:
        raise ReportScopeError(
            f"Audience '{audience}' requires at least client_id or vendor_id."
        )


def _user_can_write_in_org(
    db: Session, user_id: str, organization_id: str
) -> bool:
    """Any active membership in the org grants write."""
    stmt = (
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
            Membership.status == "active",
        )
    )
    return db.scalar(stmt) > 0


def _pick_owning_org(actor: ReportActor) -> str:
    """Pick the actor's single org id for new-report creation.

    If the actor has multiple orgs and the API didn't disambiguate,
    fail — we don't pick one arbitrarily because that's a tenant-
    isolation footgun. Internal staff with the internal org should
    be picking explicitly via the API.
    """
    if not actor.organization_ids:
        raise ReportPermissionError("User has no organization memberships.")
    if len(actor.organization_ids) > 1:
        raise ReportPermissionError(
            "User belongs to multiple organizations; specify organization_id."
        )
    return actor.organization_ids[0]


# ─── Reports ─────────────────────────────────────────────────────


def create_report(
    db: Session,
    *,
    actor: ReportActor,
    title: str,
    description: str | None,
    audience: ReportAudience,
    organization_id: str | None,
    client_id: str | None,
    vendor_id: str | None,
    initial_content_json: dict | None,
) -> tuple[Report, ReportVersion]:
    """Create a report + an initial v1 version in one transaction.

    Always seeds a v1 version so the editor never has to special-case
    "empty report has no version yet". The seed content_json is either
    the caller-supplied initial_content_json or a minimal empty canvas.
    """

    owning_org = organization_id or _pick_owning_org(actor)
    # Internal staff may target any org; everyone else must hold a
    # membership in the target org.
    if not actor.is_internal and owning_org not in actor.organization_ids:
        raise ReportPermissionError(
            "User does not belong to the target organization."
        )

    _validate_scope(audience.value, client_id, vendor_id)

    now = utc_now()
    content = initial_content_json or {"schema_version": 1, "blocks": [], "global": {}}

    report = Report(
        id=new_id(),
        organization_id=owning_org,
        client_id=client_id,
        vendor_id=vendor_id,
        title=title.strip(),
        description=description,
        audience=audience.value,
        status=ReportStatus.DRAFT.value,
        created_by_user_id=actor.user_id,
        created_at=now,
        updated_at=now,
    )

    version = ReportVersion(
        id=new_id(),
        report_id=report.id,
        version_number=1,
        parent_version_id=None,
        label="v1",
        content_json=content,
        plan_json=None,
        generated_by=ReportVersionOrigin.USER.value,
        source_snapshot_id=None,
        llm_metadata=None,
        created_by_user_id=actor.user_id,
        created_at=now,
    )

    report.current_version_id = version.id

    db.add(report)
    db.add(version)
    db.commit()
    db.refresh(report)
    db.refresh(version)
    return report, version


def list_reports(
    db: Session,
    *,
    actor: ReportActor,
    organization_id: str | None = None,
    status: ReportStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Report], int]:
    """List reports visible to the actor.

    Internal staff see everything; everyone else is scoped to their
    organization_ids. Optional ``organization_id`` filter narrows
    further (and is enforced against the actor's memberships).
    """
    stmt = select(Report)

    if not actor.is_internal:
        if not actor.organization_ids:
            return [], 0
        stmt = stmt.where(Report.organization_id.in_(actor.organization_ids))

    if organization_id:
        if not actor.is_internal and organization_id not in actor.organization_ids:
            raise ReportPermissionError(
                "User does not belong to the requested organization."
            )
        stmt = stmt.where(Report.organization_id == organization_id)

    if status:
        stmt = stmt.where(Report.status == status.value)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0

    rows = list(
        db.scalars(
            stmt.order_by(Report.updated_at.desc()).limit(limit).offset(offset)
        )
    )
    return rows, total


def get_report(
    db: Session, *, actor: ReportActor, report_id: str
) -> tuple[Report, ReportVersion | None]:
    """Fetch report + its current version. 404 if not visible."""
    report = db.get(Report, report_id)
    if report is None:
        raise ReportNotFoundError(f"Report {report_id} not found.")

    if not actor.is_internal and report.organization_id not in actor.organization_ids:
        # Indistinguishable from not-found by design (no enumeration).
        raise ReportNotFoundError(f"Report {report_id} not found.")

    current = (
        db.get(ReportVersion, report.current_version_id)
        if report.current_version_id
        else None
    )
    return report, current


def patch_report(
    db: Session,
    *,
    actor: ReportActor,
    report_id: str,
    title: str | None = None,
    description: str | None = None,
    audience: ReportAudience | None = None,
    status: ReportStatus | None = None,
    client_id: str | None = None,
    vendor_id: str | None = None,
) -> Report:
    """Partial update. Re-validates scope when audience changes."""
    report, _ = get_report(db, actor=actor, report_id=report_id)

    if not actor.is_internal and not _user_can_write_in_org(
        db, actor.user_id, report.organization_id
    ):
        raise ReportPermissionError(
            "User cannot write reports in this organization."
        )

    if title is not None:
        report.title = title.strip()
    if description is not None:
        report.description = description
    if audience is not None:
        report.audience = audience.value
    if status is not None:
        report.status = status.value
    if client_id is not None:
        report.client_id = client_id or None
    if vendor_id is not None:
        report.vendor_id = vendor_id or None

    # Re-validate the scope rule against the final shape.
    _validate_scope(report.audience, report.client_id, report.vendor_id)

    report.updated_at = utc_now()
    db.commit()
    db.refresh(report)
    return report


# ─── Versions ────────────────────────────────────────────────────


def create_version(
    db: Session,
    *,
    actor: ReportActor,
    report_id: str,
    content_json: dict,
    label: str | None = None,
    plan_json: dict | None = None,
    generated_by: ReportVersionOrigin = ReportVersionOrigin.USER,
    parent_version_id: str | None = None,
    source_snapshot_id: str | None = None,
    llm_metadata: dict | None = None,
) -> ReportVersion:
    """Manual save: append a new version, advance current_version_id."""
    report, _ = get_report(db, actor=actor, report_id=report_id)

    if not actor.is_internal and not _user_can_write_in_org(
        db, actor.user_id, report.organization_id
    ):
        raise ReportPermissionError(
            "User cannot write reports in this organization."
        )

    next_n = (
        db.scalar(
            select(func.max(ReportVersion.version_number)).where(
                ReportVersion.report_id == report_id
            )
        )
        or 0
    ) + 1

    now = utc_now()
    version = ReportVersion(
        id=new_id(),
        report_id=report_id,
        version_number=next_n,
        parent_version_id=parent_version_id,
        label=label,
        content_json=content_json,
        plan_json=plan_json,
        generated_by=generated_by.value,
        source_snapshot_id=source_snapshot_id,
        llm_metadata=llm_metadata,
        created_by_user_id=actor.user_id,
        created_at=now,
    )
    report.current_version_id = version.id
    report.updated_at = now

    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def list_versions(
    db: Session, *, actor: ReportActor, report_id: str
) -> list[ReportVersion]:
    """Versions of a report in descending order."""
    _ = get_report(db, actor=actor, report_id=report_id)  # 404 if not visible
    return list(
        db.scalars(
            select(ReportVersion)
            .where(ReportVersion.report_id == report_id)
            .order_by(ReportVersion.version_number.desc())
        )
    )


def get_version(
    db: Session, *, actor: ReportActor, report_id: str, version_number: int
) -> ReportVersion:
    _, _ = get_report(db, actor=actor, report_id=report_id)  # visibility check
    version = db.scalar(
        select(ReportVersion).where(
            ReportVersion.report_id == report_id,
            ReportVersion.version_number == version_number,
        )
    )
    if version is None:
        raise ReportVersionNotFoundError(
            f"Version {version_number} not found for report {report_id}."
        )
    return version
