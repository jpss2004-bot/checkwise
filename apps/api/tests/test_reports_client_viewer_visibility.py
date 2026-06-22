"""Phase 4 Viewer split: client_viewer report visibility + read-only guard.

The executive report service predates the Approver/Viewer seat split
(``app/constants/roles.py``). Its ``visible_audiences`` / ``writable_
audiences`` helpers only recognised ``client_admin`` among client seats,
so a ``client_viewer`` (the read + export "Viewer" tier) fell through to
the default-deny ``return ()`` branch — neither able to *read* nor
*generate* any report, even though the Viewer reads and exports
everything else in the client portal (audit packages, metadata).

These tests pin the fix and, just as importantly, its boundary:

  READ  — a client_viewer sees the same ``client_facing`` audience a
          client_admin sees (and only that audience).
  WRITE — a client_viewer stays read-only. Crucially, granting read
          must NOT leak into write: ``can_write_report`` resolves write
          through ``_user_can_write_in_org``, which used to grant write
          to *any* active membership. A Viewer holds an active
          Membership, so without the role exclusion the read grant would
          have silently handed them PATCH / save-version access.

Written at the service layer (no HTTP) because the bug and the fix live
in the audience matrix + the membership write helper, not the API
surface. The reports router only carries an ``authenticated_jwt`` gate
and delegates all role scoping to this service, so the manifest entries
are unchanged by this fix.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.reports import ReportAudience, ReportStatus
from app.constants.roles import MembershipRole
from app.db.base import Base
from app.models import (
    Client,
    Membership,
    Organization,
    Report,
    User,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.services.report_service import (
    ReportActor,
    ReportNotFoundError,
    ReportPermissionError,
    can_write_report,
    create_report,
    create_version,
    get_report,
    list_reports,
    patch_report,
    visible_audiences,
    writable_audiences,
)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed_world(db: Session, *, viewer_role: str = MembershipRole.CLIENT_VIEWER.value) -> dict[str, str]:
    """One client org with three reports spanning three audiences, plus a
    real active Membership for the seat under test.

    The membership is what makes the write-leak assertion meaningful:
    ``can_write_report`` only reaches ``_user_can_write_in_org`` when the
    actor actually belongs to the org, which is exactly the Viewer's
    situation.
    """
    client = Client(name="Cliente Viewer")
    db.add(client)
    db.flush()

    org = Organization(name="Org Viewer", kind="client", client_id=client.id)
    db.add(org)
    db.flush()

    vendor = Vendor(client_id=client.id, name="Vendor V", rfc="VDRV000101VV0")
    db.add(vendor)
    db.flush()

    user = User(email="viewer@checkwise.test", full_name="Vera Viewer")
    db.add(user)
    db.flush()

    db.add(
        Membership(
            user_id=user.id,
            organization_id=org.id,
            role=viewer_role,
            status="active",
        )
    )

    client_report = Report(
        title="client_facing report",
        audience=ReportAudience.CLIENT_FACING.value,
        status=ReportStatus.DRAFT.value,
        organization_id=org.id,
        client_id=client.id,
        vendor_id=None,
        created_by_user_id="seed-internal",
    )
    internal_report = Report(
        title="internal_only report",
        audience=ReportAudience.INTERNAL_ONLY.value,
        status=ReportStatus.DRAFT.value,
        organization_id=org.id,
        client_id=None,
        vendor_id=None,
        created_by_user_id="seed-internal",
    )
    vendor_report = Report(
        title="vendor_facing report",
        audience=ReportAudience.VENDOR_FACING.value,
        status=ReportStatus.DRAFT.value,
        organization_id=org.id,
        client_id=client.id,
        vendor_id=vendor.id,
        created_by_user_id="seed-internal",
    )
    db.add_all([client_report, internal_report, vendor_report])
    db.commit()

    return {
        "user_id": user.id,
        "org_id": org.id,
        "client_id": client.id,
        "client_report_id": client_report.id,
        "internal_report_id": internal_report.id,
        "vendor_report_id": vendor_report.id,
    }


def _viewer_actor(ids: dict[str, str]) -> ReportActor:
    return ReportActor(
        user_id=ids["user_id"],
        organization_ids=(ids["org_id"],),
        roles=(MembershipRole.CLIENT_VIEWER,),
    )


# ─── Audience matrix ─────────────────────────────────────────────


def test_viewer_visible_audiences_match_client_admin() -> None:
    """A Viewer reads exactly the client_facing audience — same as the
    Approver, and nothing internal/vendor."""
    actor = ReportActor(
        user_id="v", organization_ids=("org",), roles=(MembershipRole.CLIENT_VIEWER,)
    )
    admin = ReportActor(
        user_id="a", organization_ids=("org",), roles=(MembershipRole.CLIENT_ADMIN,)
    )
    assert visible_audiences(actor) == (ReportAudience.CLIENT_FACING,)
    assert visible_audiences(actor) == visible_audiences(admin)


def test_viewer_writable_audiences_empty() -> None:
    """Read-only contract: a Viewer can write into NO audience, unlike the
    Approver who can author client_facing reports."""
    actor = ReportActor(
        user_id="v", organization_ids=("org",), roles=(MembershipRole.CLIENT_VIEWER,)
    )
    admin = ReportActor(
        user_id="a", organization_ids=("org",), roles=(MembershipRole.CLIENT_ADMIN,)
    )
    assert writable_audiences(actor) == ()
    assert writable_audiences(admin) == (ReportAudience.CLIENT_FACING,)


# ─── READ: list / get ────────────────────────────────────────────


def test_viewer_lists_only_client_facing_reports(db: Session) -> None:
    ids = _seed_world(db)
    actor = _viewer_actor(ids)

    rows, total = list_reports(db, actor=actor)
    returned = {r.id for r in rows}

    assert total == 1
    assert ids["client_report_id"] in returned
    assert ids["internal_report_id"] not in returned
    assert ids["vendor_report_id"] not in returned


def test_viewer_can_get_client_facing_report(db: Session) -> None:
    """The regression headline: before the fix this 404'd because
    visible_audiences returned ()."""
    ids = _seed_world(db)
    actor = _viewer_actor(ids)

    report, _ = get_report(db, actor=actor, report_id=ids["client_report_id"])
    assert report.id == ids["client_report_id"]


def test_viewer_cannot_get_internal_only_report(db: Session) -> None:
    ids = _seed_world(db)
    actor = _viewer_actor(ids)

    with pytest.raises(ReportNotFoundError):
        get_report(db, actor=actor, report_id=ids["internal_report_id"])


def test_viewer_cannot_get_vendor_facing_report(db: Session) -> None:
    ids = _seed_world(db)
    actor = _viewer_actor(ids)

    with pytest.raises(ReportNotFoundError):
        get_report(db, actor=actor, report_id=ids["vendor_report_id"])


# ─── WRITE: stays read-only (no leak through can_write_report) ────


def test_viewer_can_write_report_is_false(db: Session) -> None:
    """The write-leak guard: an active client_viewer Membership must NOT
    satisfy ``_user_can_write_in_org``. Without the role exclusion the
    read grant above would have silently re-opened PATCH / save-version."""
    ids = _seed_world(db)
    actor = _viewer_actor(ids)
    report = db.get(Report, ids["client_report_id"])

    assert can_write_report(db, actor, report) is False


def test_viewer_cannot_create_report(db: Session) -> None:
    ids = _seed_world(db)
    actor = _viewer_actor(ids)

    with pytest.raises(ReportPermissionError):
        create_report(
            db,
            actor=actor,
            title="Nope",
            description=None,
            audience=ReportAudience.CLIENT_FACING,
            organization_id=ids["org_id"],
            client_id=ids["client_id"],
            vendor_id=None,
            initial_content_json=None,
        )


def test_viewer_cannot_patch_readable_report(db: Session) -> None:
    """A Viewer can now READ the client_facing report — but patching its
    title (a non-audience mutation that skips writable_audiences) must
    still be rejected via can_write_report."""
    ids = _seed_world(db)
    actor = _viewer_actor(ids)

    with pytest.raises(ReportPermissionError):
        patch_report(
            db, actor=actor, report_id=ids["client_report_id"], title="Renamed by viewer"
        )


def test_viewer_cannot_save_version(db: Session) -> None:
    ids = _seed_world(db)
    actor = _viewer_actor(ids)

    with pytest.raises(ReportPermissionError):
        create_version(
            db,
            actor=actor,
            report_id=ids["client_report_id"],
            content_json={"schema_version": 1, "blocks": [], "global": {}},
        )


# ─── Guard against over-tightening the write helper ──────────────


def test_client_admin_in_same_org_can_still_write(db: Session) -> None:
    """The role exclusion must only drop client_viewer rows — an Approver
    membership in the same org keeps full write access."""
    ids = _seed_world(db, viewer_role=MembershipRole.CLIENT_ADMIN.value)
    admin = ReportActor(
        user_id=ids["user_id"],
        organization_ids=(ids["org_id"],),
        roles=(MembershipRole.CLIENT_ADMIN,),
    )
    report = db.get(Report, ids["client_report_id"])

    assert can_write_report(db, admin, report) is True
