"""`_vendors_in_scope` cross-portfolio branch (P1-04).

The two internal admin presets ("Cola diaria de revisión", "Proveedores de
alto riesgo") carry no client/vendor anchor. Before P1-04 the scope resolver
returned ``[]`` for that case, so the vendor_risk_matrix rendered empty and the
reports looked decorative. The fix lets an ``internal_only`` unscoped report
aggregate over EVERY active vendor across all clients — the "all reachable
clients" rollup internal staff already see on the admin dashboard.

The safety property these tests pin: the cross-portfolio fan-out is gated to
``internal_only``. A ``client_facing`` / ``vendor_facing`` report with no
anchor must still return ``[]`` (never leak sibling tenants), and an explicit
``client_id`` must still narrow to that client.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.reports import ReportAudience
from app.db.base import Base
from app.models import Client, Vendor, entities  # noqa: F401
from app.services.reports.blocks.data_fetchers import _vendors_in_scope
from app.services.reports.context import ReportScope


@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _seed_two_clients_three_vendors(db_factory) -> dict[str, str]:
    """Two clients; client A has two active vendors, client B has one active
    vendor plus one archived vendor. Returns the ids by label."""
    db = db_factory()
    try:
        ca = Client(name="Client A")
        cb = Client(name="Client B")
        db.add_all([ca, cb])
        db.flush()
        va = Vendor(client_id=ca.id, name="Vendor A1", rfc="AAA010101AAA", persona_type="moral")
        vb = Vendor(client_id=ca.id, name="Vendor A2", rfc="AAA020202AAA", persona_type="moral")
        vc = Vendor(client_id=cb.id, name="Vendor B1", rfc="BBB010101BBB", persona_type="moral")
        vd = Vendor(
            client_id=cb.id,
            name="Vendor B2 (archived)",
            rfc="BBB020202BBB",
            persona_type="moral",
            status="archived",
        )
        db.add_all([va, vb, vc, vd])
        db.commit()
        return {
            "client_a": ca.id,
            "client_b": cb.id,
            "va": va.id,
            "vb": vb.id,
            "vc": vc.id,
            "vd_archived": vd.id,
        }
    finally:
        db.close()


def _scope(audience: ReportAudience, *, client_id=None, vendor_id=None) -> ReportScope:
    return ReportScope(
        organization_id="org",
        audience=audience,
        client_id=client_id,
        vendor_id=vendor_id,
    )


def test_internal_only_unscoped_aggregates_all_active_vendors(db_factory) -> None:
    ids = _seed_two_clients_three_vendors(db_factory)
    db = db_factory()
    try:
        vendors = _vendors_in_scope(db, _scope(ReportAudience.INTERNAL_ONLY))
    finally:
        db.close()
    got = {v.id for v in vendors}
    # All three active vendors across BOTH clients — the cross-portfolio rollup.
    assert got == {ids["va"], ids["vb"], ids["vc"]}
    # The archived vendor is excluded.
    assert ids["vd_archived"] not in got


def test_client_facing_unscoped_returns_empty_no_leak(db_factory) -> None:
    """The security guard: an external-audience report with no anchor must
    never fan out across tenants."""
    _seed_two_clients_three_vendors(db_factory)
    db = db_factory()
    try:
        cf = _vendors_in_scope(db, _scope(ReportAudience.CLIENT_FACING))
        vf = _vendors_in_scope(db, _scope(ReportAudience.VENDOR_FACING))
    finally:
        db.close()
    assert cf == []
    assert vf == []


def test_internal_only_with_client_id_still_narrows(db_factory) -> None:
    """Regression: an explicit client_id keeps narrowing even for internal
    audience — the cross-portfolio branch only fires when no anchor is set."""
    ids = _seed_two_clients_three_vendors(db_factory)
    db = db_factory()
    try:
        vendors = _vendors_in_scope(
            db, _scope(ReportAudience.INTERNAL_ONLY, client_id=ids["client_a"])
        )
    finally:
        db.close()
    got = {v.id for v in vendors}
    assert got == {ids["va"], ids["vb"]}
