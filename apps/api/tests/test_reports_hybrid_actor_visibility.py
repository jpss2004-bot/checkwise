"""BL-002 regression: hybrid-actor visibility in list_reports / get_report.

A "hybrid" actor is a user who simultaneously
  (a) holds a Membership in some Organization (e.g. CLIENT_ADMIN), AND
  (b) owns an active ProviderWorkspace whose vendor lives in a DIFFERENT
      organization.

The seed scenario that exposed this in production is cliente.demo,
who was set as ``owner_user_id`` on three portfolio ProviderWorkspaces
while ALSO carrying a CLIENT_ADMIN Membership in the demo Org. Before
this commit the read filter was an else-if: ``if is_workspace_owner:
stmt.where(vendor_id=...) else: stmt.where(organization_id IN ...)``.
The workspace branch silently shadowed the org branch, so every
client_facing report in cliente.demo's own org disappeared from their
listing — visible only after the seed was patched to revoke workspace
ownership (commit ``41c50a0``). The code-level guard was still missing.

The fix changes the predicate to a UNION (``OR`` of the two clauses)
in ``list_reports`` and mirrors that with a parallel OR check in
``get_report``. ``can_write_report`` already had union semantics; this
aligns the read paths with the existing write rule.

Tests are written at the service layer (no HTTP) because the bug is in
the SQL predicate, not the API surface. The full HTTP regression
matrix already lives in ``test_reports.py``; this module asserts the
specific union-vs-shadowing contract.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.roles import MembershipRole
from app.db.base import Base
from app.models import (
    Client,
    Organization,
    Report,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.services.report_service import (
    ReportActor,
    ReportNotFoundError,
    get_report,
    list_reports,
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


def _seed_hybrid_world(db: Session) -> dict[str, str]:
    """Set up the cliente.demo-shaped scenario.

    Three reports, all ``client_facing`` (so the CLIENT_ADMIN audience
    filter doesn't mask the BL-002 effect we're trying to test):
      - org_report     → matches the hybrid actor only via Org A membership.
      - workspace_report → matches the hybrid actor only via Vendor B workspace.
      - other_report   → cross-tenant control; must remain invisible.
    """
    client_a = Client(name="Cliente A")
    client_b = Client(name="Cliente B")
    client_c = Client(name="Cliente C")
    db.add_all([client_a, client_b, client_c])
    db.flush()

    org_a = Organization(name="Org A", kind="client", client_id=client_a.id)
    org_b = Organization(name="Org B", kind="client", client_id=client_b.id)
    org_c = Organization(name="Org C", kind="client", client_id=client_c.id)
    db.add_all([org_a, org_b, org_c])
    db.flush()

    vendor_b = Vendor(client_id=client_b.id, name="Vendor B", rfc="VDRB000101BB0")
    db.add(vendor_b)
    db.flush()

    org_report = Report(
        title="Org A client_facing report",
        audience="client_facing",
        status="draft",
        organization_id=org_a.id,
        client_id=client_a.id,
        vendor_id=None,
        created_by_user_id="seed-internal",
    )
    workspace_report = Report(
        title="Vendor B client_facing report",
        audience="client_facing",
        status="draft",
        organization_id=org_b.id,
        client_id=client_b.id,
        vendor_id=vendor_b.id,
        created_by_user_id="seed-internal",
    )
    other_report = Report(
        title="Org C client_facing report",
        audience="client_facing",
        status="draft",
        organization_id=org_c.id,
        client_id=client_c.id,
        vendor_id=None,
        created_by_user_id="seed-internal",
    )
    db.add_all([org_report, workspace_report, other_report])
    db.commit()

    return {
        "org_a_id": org_a.id,
        "vendor_b_id": vendor_b.id,
        "org_report_id": org_report.id,
        "workspace_report_id": workspace_report.id,
        "other_report_id": other_report.id,
    }


def _hybrid_actor(ids: dict[str, str]) -> ReportActor:
    return ReportActor(
        user_id="cliente-demo",
        organization_ids=(ids["org_a_id"],),
        roles=(MembershipRole.CLIENT_ADMIN,),
        workspace_vendor_id=ids["vendor_b_id"],
        workspace_client_id=None,
    )


# ─── list_reports ────────────────────────────────────────────────


def test_hybrid_actor_lists_both_org_and_workspace_reports(db: Session) -> None:
    """Union semantics: hybrid actor sees reports reachable by EITHER path."""
    ids = _seed_hybrid_world(db)
    actor = _hybrid_actor(ids)

    rows, total = list_reports(db, actor=actor)
    ids_returned = {r.id for r in rows}

    assert total == 2
    assert ids["org_report_id"] in ids_returned
    assert ids["workspace_report_id"] in ids_returned
    assert ids["other_report_id"] not in ids_returned


def test_hybrid_actor_with_no_visibility_returns_empty(db: Session) -> None:
    """Defence-in-depth: no org memberships AND no workspace → empty list,
    not a default-allow. The previous shape returned ``[], 0`` only on
    the org-branch; the union must preserve that for fully scopeless
    actors."""
    _seed_hybrid_world(db)
    actor = ReportActor(
        user_id="orphan-user",
        organization_ids=(),
        roles=(MembershipRole.CLIENT_ADMIN,),
        workspace_vendor_id=None,
        workspace_client_id=None,
    )

    rows, total = list_reports(db, actor=actor)

    assert total == 0
    assert rows == []


# ─── get_report ──────────────────────────────────────────────────


def test_hybrid_actor_can_get_org_report_via_org_branch(db: Session) -> None:
    """The bug surfaced as a 404 here: the else-if hid the org-membership
    check whenever ``is_workspace_owner`` was True, so a hybrid actor
    got 404 on reports they could legitimately read through their org."""
    ids = _seed_hybrid_world(db)
    actor = _hybrid_actor(ids)

    report, _ = get_report(db, actor=actor, report_id=ids["org_report_id"])
    assert report.id == ids["org_report_id"]


def test_hybrid_actor_can_get_workspace_report_via_workspace_branch(
    db: Session,
) -> None:
    """Sanity check: the workspace branch still works for hybrid actors."""
    ids = _seed_hybrid_world(db)
    actor = _hybrid_actor(ids)

    report, _ = get_report(
        db, actor=actor, report_id=ids["workspace_report_id"]
    )
    assert report.id == ids["workspace_report_id"]


def test_hybrid_actor_404s_on_cross_tenant_report(db: Session) -> None:
    """Cross-tenant access still 404s — the union must not widen scope
    beyond the actor's actual memberships + workspace."""
    ids = _seed_hybrid_world(db)
    actor = _hybrid_actor(ids)

    with pytest.raises(ReportNotFoundError):
        get_report(db, actor=actor, report_id=ids["other_report_id"])
