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

import json
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.constants.reports import (
    ReportAudience,
    ReportStatus,
    ReportVersionOrigin,
)
from app.constants.roles import STAFF_ROLES, MembershipRole
from app.core.config import settings
from app.models.entities import (
    Membership,
    Organization,
    Report,
    ReportVersion,
    Vendor,
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


class ReportContentTooLargeError(ReportServiceError):
    """content_json / plan_json exceeds the configured size, block-count,
    per-block-text, or nesting limits (CW-DOS-001). Mapped to HTTP 413."""


def _max_depth_within(obj: object, limit: int, _depth: int = 1) -> bool:
    """True if ``obj``'s nesting depth is within ``limit``. Bails as soon as
    the limit is exceeded so a maliciously deep payload can't blow Python's
    recursion limit before the check trips."""
    if _depth > limit:
        return False
    if isinstance(obj, dict):
        return all(_max_depth_within(v, limit, _depth + 1) for v in obj.values())
    if isinstance(obj, list):
        return all(_max_depth_within(v, limit, _depth + 1) for v in obj)
    return True


def _sum_str_len(obj: object) -> int:
    """Total length of all string leaves under ``obj``."""
    if isinstance(obj, str):
        return len(obj)
    if isinstance(obj, dict):
        return sum(_sum_str_len(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(_sum_str_len(v) for v in obj)
    return 0


def _validate_report_content(
    content_json: dict,
    *,
    plan_json: dict | None = None,
    llm_metadata: dict | None = None,
) -> None:
    """Reject over-budget report payloads BEFORE persistence (CW-DOS-001).

    Bounds the serialized size, block count, per-block text length, and
    nesting depth of ``content_json`` (the input the HTML/PDF renderer
    walks), plus a coarse byte cap on ``plan_json``/``llm_metadata``.
    Raises :class:`ReportContentTooLargeError` (→ HTTP 413) on any breach.
    """
    try:
        raw = json.dumps(content_json, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ReportContentTooLargeError("content_json is not JSON-serializable.") from exc
    if len(raw.encode("utf-8")) > settings.REPORT_CONTENT_MAX_BYTES:
        raise ReportContentTooLargeError("content_json exceeds the maximum size.")

    if not _max_depth_within(content_json, settings.REPORT_CONTENT_MAX_DEPTH):
        raise ReportContentTooLargeError("content_json is nested too deeply.")

    blocks = content_json.get("blocks") if isinstance(content_json, dict) else None
    if isinstance(blocks, list):
        if len(blocks) > settings.REPORT_CONTENT_MAX_BLOCKS:
            raise ReportContentTooLargeError("content_json has too many blocks.")
        for block in blocks:
            if _sum_str_len(block) > settings.REPORT_CONTENT_MAX_TEXT_PER_BLOCK:
                raise ReportContentTooLargeError(
                    "A report block exceeds the maximum text length."
                )

    for name, extra in (("plan_json", plan_json), ("llm_metadata", llm_metadata)):
        if extra is None:
            continue
        try:
            extra_raw = json.dumps(extra, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ReportContentTooLargeError(f"{name} is not JSON-serializable.") from exc
        if len(extra_raw.encode("utf-8")) > settings.REPORT_PLAN_MAX_BYTES:
            raise ReportContentTooLargeError(f"{name} exceeds the maximum size.")


# ─── Caller context ─────────────────────────────────────────────


@dataclass(frozen=True)
class ReportActor:
    """Tenant-scoping context derived from the authenticated user.

    Built once per request in the API layer and passed verbatim through
    the service. Keeping it separate from CurrentUser means service
    functions can be unit-tested without an HTTP fixture.

    ``workspace_vendor_id`` / ``workspace_client_id`` are populated for
    role-less providers who own a ``ProviderWorkspace``. They power the
    P1 vendor_facing visibility branch — see ``visible_audiences``.
    Internal staff and client_admins keep these as ``None`` (membership
    drives their scope instead).
    """

    user_id: str
    organization_ids: tuple[str, ...]
    roles: tuple[str, ...]
    workspace_vendor_id: str | None = None
    workspace_client_id: str | None = None

    @property
    def is_internal(self) -> bool:
        """True for CheckWise staff: the review team (platform_admin) or
        the superadmin (operations_admin).

        Staff cross-organization access matches the admin/review endpoints.
        """
        return bool(STAFF_ROLES & {str(r) for r in self.roles})

    @property
    def is_workspace_owner(self) -> bool:
        """True for any actor bound to an active ``ProviderWorkspace``.

        Used to gate the vendor_facing visibility branch. BL-001
        (2026-05-20) loosened this from the previous "roles-must-be-
        empty" rule because real-world provider seeds carry a
        ``provider`` Membership row, which silently locked them out of
        their own vendor-facing presets. A user actively browsing the
        provider portal owns a workspace, period — internal_admin
        status no longer overrides workspace ownership.

        Internal staff who also happen to own a provider workspace
        (rare) now see vendor_facing presets in addition to internal
        ones — acceptable because those presets target the workspace
        owner's own data anyway.
        """
        return self.workspace_vendor_id is not None


# ─── Audience visibility (R1.0) ─────────────────────────────────
#
# Role → audience matrix. Source of truth for who can read or write
# which audiences. UI hiding alone is never the protection — list /
# create / patch must intersect with these.
#
# Internal staff: all four audiences (they operate the platform).
# client_admin (Approver) + client_viewer (Viewer): client_facing only
#   (their own org). Read parity between the two client seats; the write
#   split lives in writable_audiences() / can_write_report().
# Anyone else (no recognised role): empty — default-deny.


def visible_audiences(actor: ReportActor) -> tuple[ReportAudience, ...]:
    """Audiences this actor is allowed to *read*."""
    if actor.is_internal:
        return (
            ReportAudience.INTERNAL_ONLY,
            ReportAudience.CLIENT_FACING,
            ReportAudience.VENDOR_FACING,
            ReportAudience.EXTERNAL_SIGNED,
        )
    # Both client seat tiers READ the client-facing surface: client_admin
    # (Approver) and client_viewer (Viewer, Phase 4). The Viewer is an
    # oversight/export seat — it reads the same reports the Approver sees
    # (it already pulls audit packages and metadata exports elsewhere) but
    # never authors them. The read/write split is enforced by leaving
    # client_viewer OUT of writable_audiences() and can_write_report();
    # granting read here keeps the Viewer from being silently locked out
    # of the report builder while staying read-only.
    if (
        MembershipRole.CLIENT_ADMIN in actor.roles
        or MembershipRole.CLIENT_VIEWER in actor.roles
    ):
        return (ReportAudience.CLIENT_FACING,)
    if actor.is_workspace_owner:
        # P1: role-less providers see only reports targeted at them.
        # list_reports() additionally restricts by Report.vendor_id ==
        # actor.workspace_vendor_id so cross-vendor reads return empty.
        return (ReportAudience.VENDOR_FACING,)
    return ()


def writable_audiences(actor: ReportActor) -> tuple[ReportAudience, ...]:
    """Audiences this actor is allowed to *create or patch into*.

    Diverges from ``visible_audiences`` on the Phase 4 Viewer split:
    ``client_viewer`` (Viewer) reads the client-facing surface but is
    deliberately ABSENT here, so it can never author a report or change a
    report's audience. Only the ``client_admin`` (Approver) tier writes
    among client seats. Do not add ``client_viewer`` to this branch — the
    read-only contract depends on it (and ``can_write_report`` below
    enforces the same exclusion for non-audience mutations).
    """
    if actor.is_internal:
        return (
            ReportAudience.INTERNAL_ONLY,
            ReportAudience.CLIENT_FACING,
            ReportAudience.VENDOR_FACING,
            ReportAudience.EXTERNAL_SIGNED,
        )
    if MembershipRole.CLIENT_ADMIN in actor.roles:
        return (ReportAudience.CLIENT_FACING,)
    if actor.is_workspace_owner:
        return (ReportAudience.VENDOR_FACING,)
    return ()


# ─── Helpers ────────────────────────────────────────────────────


def _validate_scope(audience: str, client_id: str | None, vendor_id: str | None) -> None:
    """Mirror of the DB CHECK constraint, but with nicer error copy."""
    if audience == ReportAudience.INTERNAL_ONLY:
        return
    if not client_id and not vendor_id:
        raise ReportScopeError(
            f"Audience '{audience}' requires at least client_id or vendor_id."
        )


def _allowed_client_ids_for_actor(db: Session, actor: ReportActor) -> set[str]:
    """The set of ``client_id`` values a non-internal actor may scope a
    report to: the Client bound to any of the actor's organizations, plus
    the Client of the actor's provider workspace (if any)."""
    allowed: set[str] = set()
    if actor.organization_ids:
        rows = db.scalars(
            select(Organization.client_id).where(
                Organization.id.in_(actor.organization_ids),
                Organization.client_id.is_not(None),
            )
        )
        allowed.update(cid for cid in rows if cid)
    if actor.workspace_client_id:
        allowed.add(actor.workspace_client_id)
    return allowed


def _enforce_report_tenant_scope(
    db: Session,
    actor: ReportActor,
    *,
    client_id: str | None,
    vendor_id: str | None,
) -> None:
    """Tenant-isolation guard for report create/patch (audit REPORT-1).

    ``create_report``/``patch_report`` previously trusted the
    body-supplied ``client_id``/``vendor_id`` verbatim — they only
    validated that the *owning org* belonged to the actor. A
    ``client_admin`` for tenant A could therefore author/patch a
    ``client_facing`` report whose ``client_id`` (or ``vendor_id``)
    pointed at tenant B and then generate it, pulling B's entire
    compliance portfolio (vendor names, RFCs, risk scores) into a report
    they own and can export/share.

    This enforces that any supplied ``client_id``/``vendor_id`` resolves
    to a Client the actor legitimately reaches. Internal staff keep
    cross-tenant authorship (that is part of the role). Falsy values
    (``None``/``""`` — meaning "unset"/"clear") are not checked.
    """
    if actor.is_internal:
        return
    if not client_id and not vendor_id:
        return
    allowed = _allowed_client_ids_for_actor(db, actor)
    if client_id and client_id not in allowed:
        raise ReportPermissionError(
            "No puedes crear o asignar reportes para otro cliente."
        )
    if vendor_id:
        vendor_client_id = db.scalar(
            select(Vendor.client_id).where(Vendor.id == vendor_id)
        )
        if vendor_client_id is None or vendor_client_id not in allowed:
            raise ReportPermissionError(
                "No puedes asignar reportes a un proveedor de otro cliente."
            )


def _user_can_write_in_org(
    db: Session, user_id: str, organization_id: str
) -> bool:
    """An active *write-capable* membership in the org grants write.

    Phase 4 split the client seat into Approver (``client_admin``) and
    read-only Viewer (``client_viewer``). A Viewer holds a real active
    Membership row, so the previous "any active membership" rule would
    have silently handed them report write access the moment
    ``visible_audiences`` started letting them read a report — turning a
    read grant into a write grant. Exclude ``client_viewer`` so the
    Viewer stays read-only. A user who (anomalously) holds BOTH a
    ``client_viewer`` and a ``client_admin`` row in the same org still
    writes via the Approver row, which this filter keeps.
    """
    stmt = (
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
            Membership.status == "active",
            Membership.role != MembershipRole.CLIENT_VIEWER.value,
        )
    )
    return db.scalar(stmt) > 0


def can_write_report(db: Session, actor: ReportActor, report: Report) -> bool:
    """Write gate for a specific report.

    Read paths use the dedicated ``is_workspace_owner`` branch in
    ``list_reports`` / ``get_report``; write paths historically only
    checked ``Membership``, which silently locks provider workspace
    owners out of refreshing or saving their own vendor_facing
    reports (providers never hold a Membership — their workspace IS
    the tenant). This helper unifies both rules:

    - internal staff always pass.
    - any active Membership in the report's organization passes.
    - workspace owners pass when the report targets THEIR vendor.

    Callers stay responsible for ``writable_audiences`` checks on
    audience transitions; this only governs "can the actor mutate
    this report at all".
    """
    if actor.is_internal:
        return True
    if _user_can_write_in_org(db, actor.user_id, report.organization_id):
        return True
    if actor.is_workspace_owner and report.vendor_id == actor.workspace_vendor_id:
        return True
    return False


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

    if audience not in writable_audiences(actor):
        raise ReportPermissionError(
            f"Role cannot create reports with audience '{audience.value}'."
        )

    _validate_scope(audience.value, client_id, vendor_id)
    _enforce_report_tenant_scope(db, actor, client_id=client_id, vendor_id=vendor_id)

    now = utc_now()
    content = initial_content_json or {"schema_version": 1, "blocks": [], "global": {}}
    # CW-DOS-001 — bound the seed content too (covers the create vector).
    _validate_report_content(content)

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
    audience: ReportAudience | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Report], int]:
    """List reports visible to the actor.

    Internal staff see everything; everyone else is scoped to their
    organization_ids. Optional ``organization_id`` filter narrows
    further (and is enforced against the actor's memberships).

    ``audience`` narrows to a single value when present. The
    visible_audiences() intersection still applies — a caller cannot
    bypass it by passing a forbidden audience; the list just returns
    empty in that case.
    """
    stmt = select(Report)

    if not actor.is_internal:
        # BL-002 (2026-06-02): the read filter is a UNION of vendor-
        # scope and org-scope, not an else-if. The earlier shape
        # (``if workspace_owner: ... else: ...``) silently shadowed
        # org memberships when a hybrid actor was also a workspace
        # owner — a real-world demo persona (cliente.demo was set as
        # ``owner_user_id`` on three portfolio ProviderWorkspaces)
        # lost visibility into their own org's reports. ``can_write_
        # report`` already evaluates with union semantics; aligning
        # the read side keeps the rules symmetric.
        visibility = []
        if actor.is_workspace_owner:
            visibility.append(Report.vendor_id == actor.workspace_vendor_id)
        if actor.organization_ids:
            visibility.append(
                Report.organization_id.in_(actor.organization_ids)
            )
        if not visibility:
            return [], 0
        stmt = stmt.where(or_(*visibility))

    if organization_id:
        if not actor.is_internal and organization_id not in actor.organization_ids:
            raise ReportPermissionError(
                "User does not belong to the requested organization."
            )
        stmt = stmt.where(Report.organization_id == organization_id)

    # Audience filter — UI hiding is not the protection. A client_admin
    # logged in with cross-tenant org membership still must not see
    # internal_only reports.
    allowed = visible_audiences(actor)
    if not allowed:
        return [], 0
    if audience is not None:
        # Intersect the requested audience with the visible set. If the
        # caller asks for one they cannot see, return empty rather than
        # raise — mirrors the not-found-shape semantics elsewhere.
        if audience not in allowed:
            return [], 0
        stmt = stmt.where(Report.audience == audience.value)
    else:
        stmt = stmt.where(Report.audience.in_([a.value for a in allowed]))

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

    if not actor.is_internal:
        # BL-002 mirror of the ``list_reports`` filter: a hybrid actor
        # with both workspace ownership AND org memberships is visible
        # via *either* path. The previous else-if shadowed the org
        # branch when ``is_workspace_owner`` was True, returning 404
        # for reports the user could legitimately read through their
        # org. 404 (not 403) on the failure path is intentional — no
        # id enumeration through error-code differentiation.
        visible_via_workspace = (
            actor.is_workspace_owner
            and report.vendor_id == actor.workspace_vendor_id
        )
        visible_via_org = report.organization_id in actor.organization_ids
        if not (visible_via_workspace or visible_via_org):
            raise ReportNotFoundError(f"Report {report_id} not found.")

    allowed = visible_audiences(actor)
    if report.audience not in {a.value for a in allowed}:
        # Same not-found surface — never reveal that the report exists
        # but the audience is forbidden.
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

    if not can_write_report(db, actor, report):
        raise ReportPermissionError(
            "User cannot write reports in this organization."
        )

    # L1 (2026-05-20): tenant-lock for workspace owners.
    #
    # ``can_write_report`` grants providers write access to any report
    # whose ``vendor_id`` matches their workspace. That's the right
    # rule for refreshing data and saving versions, but it leaves the
    # scope-mutation fields (``vendor_id`` / ``client_id`` /
    # ``audience``) unguarded — a workspace owner could PATCH their
    # own report's vendor_id to another vendor and corrupt the
    # report's tenancy metadata. The UI doesn't expose this, but the
    # API used to accept it. Internal staff still cross-mutate at
    # will (that's part of their role); client_admins are already
    # constrained by their Membership matrix at the audience check.
    if actor.is_workspace_owner and not actor.is_internal:
        if vendor_id is not None and vendor_id != actor.workspace_vendor_id:
            raise ReportPermissionError(
                "Workspace owners cannot reassign reports to a different vendor."
            )
        if (
            client_id is not None
            and actor.workspace_client_id is not None
            and client_id != actor.workspace_client_id
        ):
            raise ReportPermissionError(
                "Workspace owners cannot reassign reports to a different client."
            )
        if audience is not None and audience != ReportAudience.VENDOR_FACING:
            raise ReportPermissionError(
                "Workspace owners cannot change report audience."
            )

    # REPORT-1: a client_admin is not a workspace owner, so the L1 lock
    # above never fired for them — they could PATCH client_id/vendor_id
    # to another tenant. Enforce the tenant-scope guard for every
    # non-internal actor on the values actually being changed.
    _enforce_report_tenant_scope(db, actor, client_id=client_id, vendor_id=vendor_id)

    if title is not None:
        report.title = title.strip()
    if description is not None:
        report.description = description
    if audience is not None:
        if audience not in writable_audiences(actor):
            raise ReportPermissionError(
                f"Role cannot patch reports to audience '{audience.value}'."
            )
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

    if not can_write_report(db, actor, report):
        raise ReportPermissionError(
            "User cannot write reports in this organization."
        )

    # CW-DOS-001 — bound the payload before it is persisted and later
    # rendered. Runs after the permission check so 403 still precedes 413.
    _validate_report_content(
        content_json, plan_json=plan_json, llm_metadata=llm_metadata
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
