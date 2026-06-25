"""Phase D — admin entitlement + billing endpoints, incl. the end-to-end
reflection in GET /client/plan (the capability shim merge)."""

from __future__ import annotations

import itertools
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Client,
    Membership,
    Organization,
    User,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password

_PASSWORD = "Entitle!2026"
_seq = itertools.count(1)


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


def _seed_demo_client(db_factory) -> dict:
    seq = next(_seq)
    email = f"owner-{seq}@checkwise.example"
    db = db_factory()
    try:
        client = Client(name=f"Cliente {seq}")
        db.add(client)
        db.flush()
        org = Organization(
            name=f"Cliente {seq}", kind="client", client_id=client.id,
            seat_limit=3, plan="demo", status="active",
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
        db.commit()
        return {"org_id": org.id, "owner_email": email}
    finally:
        db.close()


def _seed_internal_admin(db_factory) -> str:
    seq = next(_seq)
    email = f"staff-{seq}@checkwise.example"
    db = db_factory()
    try:
        user = User(
            email=email, password_hash=hash_password(_PASSWORD),
            full_name=f"Staff {seq}", status="active",
        )
        db.add(user)
        db.flush()
        org = Organization(name=f"Internal {seq}", kind="internal")
        db.add(org)
        db.flush()
        db.add(Membership(
            user_id=user.id, organization_id=org.id,
            role="operations_admin", status="active",
        ))
        db.commit()
        return email
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


def test_entitlement_grant_reflects_in_client_plan(db_factory, api_client):
    ctx = _seed_demo_client(db_factory)
    staff = _login(api_client, _seed_internal_admin(db_factory))
    owner = _login(api_client, ctx["owner_email"])
    org_id = ctx["org_id"]

    # Demo gates the audit package by default.
    caps0 = api_client.get("/api/v1/client/plan", headers=_h(owner)).json()[
        "capabilities"
    ]
    assert caps0["export_audit_package"] is False

    # Grant it for this tenant.
    g = api_client.put(
        f"/api/v1/admin/organizations/{org_id}/entitlements/export_audit_package",
        json={"enabled": True}, headers=_h(staff),
    )
    assert g.status_code == 200, g.text

    # Reflected in the client's effective capabilities.
    caps1 = api_client.get("/api/v1/client/plan", headers=_h(owner)).json()[
        "capabilities"
    ]
    assert caps1["export_audit_package"] is True
    assert caps1["bulk_export"] is False  # other gates untouched

    # Listed for the admin.
    listed = api_client.get(
        f"/api/v1/admin/organizations/{org_id}/entitlements", headers=_h(staff)
    ).json()
    assert any(
        e["key"] == "export_audit_package" and e["enabled"] for e in listed
    )

    # Revoke → reverts to the tier default.
    d = api_client.delete(
        f"/api/v1/admin/organizations/{org_id}/entitlements/export_audit_package",
        headers=_h(staff),
    )
    assert d.status_code == 200 and d.json()["removed"] is True
    caps2 = api_client.get("/api/v1/client/plan", headers=_h(owner)).json()[
        "capabilities"
    ]
    assert caps2["export_audit_package"] is False


def test_grant_invalid_key_400(db_factory, api_client):
    ctx = _seed_demo_client(db_factory)
    staff = _login(api_client, _seed_internal_admin(db_factory))
    r = api_client.put(
        f"/api/v1/admin/organizations/{ctx['org_id']}/entitlements/bogus",
        json={"enabled": True}, headers=_h(staff),
    )
    assert r.status_code == 400, r.text


def test_non_admin_cannot_grant(db_factory, api_client):
    ctx = _seed_demo_client(db_factory)
    owner = _login(api_client, ctx["owner_email"])
    r = api_client.put(
        f"/api/v1/admin/organizations/{ctx['org_id']}/entitlements/bulk_export",
        json={"enabled": True}, headers=_h(owner),
    )
    assert r.status_code == 403, r.text


def test_billing_read_update_and_plan_move(db_factory, api_client):
    ctx = _seed_demo_client(db_factory)
    staff = _login(api_client, _seed_internal_admin(db_factory))
    org_id = ctx["org_id"]

    g = api_client.get(
        f"/api/v1/admin/organizations/{org_id}/billing", headers=_h(staff)
    ).json()
    assert g["provider"] == "manual" and g["status"] == "none"

    p = api_client.patch(
        f"/api/v1/admin/organizations/{org_id}/billing",
        json={"provider": "stripe", "status": "active", "plan": "standard"},
        headers=_h(staff),
    )
    assert p.status_code == 200, p.text
    assert p.json()["provider"] == "stripe"
    assert p.json()["status"] == "active"

    # The optional plan move took effect.
    owner = _login(api_client, ctx["owner_email"])
    assert (
        api_client.get("/api/v1/client/plan", headers=_h(owner)).json()["plan"]
        == "standard"
    )


def test_billing_invalid_provider_400(db_factory, api_client):
    ctx = _seed_demo_client(db_factory)
    staff = _login(api_client, _seed_internal_admin(db_factory))
    r = api_client.patch(
        f"/api/v1/admin/organizations/{ctx['org_id']}/billing",
        json={"provider": "paypal"}, headers=_h(staff),
    )
    assert r.status_code == 400, r.text
