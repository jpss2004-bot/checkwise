"""Phase B3 — portal freeze gate.

``_assert_workspace_active`` (applied on every portal auth path in
``current_portal_workspace``) blocks a provider whose workspace is frozen OR
whose client organization is frozen/expired, and passes a legacy orphan-client
workspace (no Organization) through unchanged.
"""

from __future__ import annotations

import itertools

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.portal import _assert_workspace_active
from app.db.base import Base
from app.models import Client, Organization, ProviderWorkspace, Vendor

_seq = itertools.count(1)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()


def _workspace(db, *, org_status="active", org_plan="standard", ws_status="active",
               with_org=True):
    seq = next(_seq)
    client = Client(name=f"Cliente {seq}")
    db.add(client)
    db.flush()
    if with_org:
        db.add(Organization(
            name=f"Cliente {seq}", kind="client", client_id=client.id,
            plan=org_plan, status=org_status,
        ))
    vendor = Vendor(
        client_id=client.id, name="Proveedor", rfc=f"WS{seq:09d}",
        persona_type="moral", status="active",
    )
    db.add(vendor)
    db.flush()
    ws = ProviderWorkspace(
        client_id=client.id, vendor_id=vendor.id, persona_type="moral",
        access_token=f"tok-{seq}", status=ws_status,
    )
    db.add(ws)
    db.flush()
    return ws


def test_active_workspace_and_org_passes(session):
    ws = _workspace(session)
    assert _assert_workspace_active(session, ws) is ws


def test_frozen_workspace_blocked(session):
    ws = _workspace(session, ws_status="frozen")
    with pytest.raises(HTTPException) as exc:
        _assert_workspace_active(session, ws)
    assert exc.value.status_code == 403
    assert "espacio" in exc.value.detail


def test_frozen_org_blocks_workspace(session):
    ws = _workspace(session, org_status="frozen")
    with pytest.raises(HTTPException) as exc:
        _assert_workspace_active(session, ws)
    assert exc.value.status_code == 403
    assert "organización" in exc.value.detail


def test_expired_demo_org_blocks_workspace(session):
    from datetime import timedelta

    from app.core.time import utc_now

    ws = _workspace(session, org_plan="demo", org_status="active")
    org = session.query(Organization).filter_by(client_id=ws.client_id).first()
    org.demo_expires_at = utc_now() - timedelta(days=1)
    session.flush()
    with pytest.raises(HTTPException) as exc:
        _assert_workspace_active(session, ws)
    assert exc.value.status_code == 403


def test_orphan_client_workspace_passes(session):
    # Legacy client with NO Organization → treated as not-frozen.
    ws = _workspace(session, with_org=False)
    assert _assert_workspace_active(session, ws) is ws
