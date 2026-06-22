"""Phase B5 — plan capability enforcement on heavy export surfaces.

Demo plans cannot pull the audit package, expediente ZIP, or metadata XLSX;
paid + legacy tiers can; single-document previews stay open. Unit-tests the
``assert_capability`` predicate, then exercises the client-portal export gates.
"""

from __future__ import annotations

import itertools
from collections.abc import Generator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.plans import Capability
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Client, Membership, Organization, User, Vendor, entities  # noqa: F401
from app.services import subscription as sub
from app.services.auth import hash_password

_PASSWORD = "Capability!2026"
_seq = itertools.count(1)


# --- unit: assert_capability ---------------------------------------------


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


def _client_with_plan(db, plan):
    client = Client(name="Acme")
    db.add(client)
    db.flush()
    if plan is not None:
        db.add(Organization(name="Acme", kind="client", client_id=client.id, plan=plan))
        db.flush()
    return client


def test_demo_lacks_bulk_export(session):
    client = _client_with_plan(session, "demo")
    with pytest.raises(HTTPException) as exc:
        sub.assert_capability(session, client.id, Capability.BULK_EXPORT.value)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "plan_capability_required"


def test_demo_lacks_audit_package(session):
    client = _client_with_plan(session, "demo")
    with pytest.raises(HTTPException):
        sub.assert_capability(
            session, client.id, Capability.EXPORT_AUDIT_PACKAGE.value
        )


def test_standard_has_all_capabilities(session):
    client = _client_with_plan(session, "standard")
    sub.assert_capability(session, client.id, Capability.BULK_EXPORT.value)
    sub.assert_capability(session, client.id, Capability.EXPORT_AUDIT_PACKAGE.value)


def test_legacy_and_orphan_are_full(session):
    legacy = _client_with_plan(session, "legacy")
    orphan = _client_with_plan(session, None)  # no Organization → LEGACY
    sub.assert_capability(session, legacy.id, Capability.BULK_EXPORT.value)
    sub.assert_capability(session, orphan.id, Capability.BULK_EXPORT.value)


# --- endpoint gates -------------------------------------------------------


@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def api_client(db_factory) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed(db_factory, *, plan):
    seq = next(_seq)
    email = f"owner-{seq}@checkwise.example"
    db = db_factory()
    try:
        client = Client(name=f"Cliente {seq}")
        db.add(client)
        db.flush()
        org = Organization(
            name=f"Cliente {seq}", kind="client", client_id=client.id,
            seat_limit=3, plan=plan,
        )
        db.add(org)
        owner = User(
            email=email, password_hash=hash_password(_PASSWORD),
            full_name=f"Owner {seq}", status="active",
        )
        db.add(owner)
        db.flush()
        db.add(Membership(
            user_id=owner.id, organization_id=org.id,
            role="client_admin", is_primary=True, status="active",
        ))
        vendor = Vendor(
            client_id=client.id, name="Proveedor", rfc=f"CAP{seq:09d}",
            persona_type="moral", status="active",
        )
        db.add(vendor)
        db.commit()
        return {"client_id": client.id, "owner_email": email, "vendor_id": vendor.id}
    finally:
        db.close()


def _login(api_client, email):
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _is_capability_403(resp) -> bool:
    if resp.status_code != 403:
        return False
    detail = resp.json().get("detail")
    return isinstance(detail, dict) and detail.get("code") == "plan_capability_required"


def test_demo_blocked_on_metadata_master(db_factory, api_client):
    ctx = _seed(db_factory, plan="demo")
    token = _login(api_client, ctx["owner_email"])
    resp = api_client.get("/api/v1/client/metadata/download", headers=_h(token))
    assert _is_capability_403(resp), resp.text


def test_demo_blocked_on_vendor_metadata(db_factory, api_client):
    ctx = _seed(db_factory, plan="demo")
    token = _login(api_client, ctx["owner_email"])
    resp = api_client.get(
        f"/api/v1/client/vendors/{ctx['vendor_id']}/metadata/download",
        headers=_h(token),
    )
    assert _is_capability_403(resp), resp.text


def test_demo_blocked_on_expediente_zip(db_factory, api_client):
    ctx = _seed(db_factory, plan="demo")
    token = _login(api_client, ctx["owner_email"])
    resp = api_client.get(
        f"/api/v1/client/vendors/{ctx['vendor_id']}/expediente.zip",
        headers=_h(token),
    )
    assert _is_capability_403(resp), resp.text


def test_standard_not_blocked_on_metadata_master(db_factory, api_client):
    ctx = _seed(db_factory, plan="standard")
    token = _login(api_client, ctx["owner_email"])
    resp = api_client.get("/api/v1/client/metadata/download", headers=_h(token))
    # Not a capability block (likely 404 — no master file in tests).
    assert not _is_capability_403(resp), resp.text


def test_demo_can_still_preview_metadata(db_factory, api_client):
    ctx = _seed(db_factory, plan="demo")
    token = _login(api_client, ctx["owner_email"])
    resp = api_client.get("/api/v1/client/metadata", headers=_h(token))
    # The read-only preview stays open for demo plans.
    assert resp.status_code == 200, resp.text
