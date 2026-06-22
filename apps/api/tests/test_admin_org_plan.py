"""Phase B — admin demo provisioning + plan-management endpoints.

POST /admin/organizations/{id}/start-demo and PATCH /admin/organizations/{id}:
start-demo stamps a 14-day deadline; plan changes clear it; status='frozen' is
rejected (cron's job); reactivation works; non-admins are 403; audited.
"""

from __future__ import annotations

import itertools
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    AuditLog,
    Client,
    Membership,
    Organization,
    User,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password

_PASSWORD = "AdminOrgPlan!2026"
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


def _seed_client_org(db_factory, *, plan="legacy", status="active") -> str:
    seq = next(_seq)
    db = db_factory()
    try:
        client = Client(name=f"Cliente {seq}")
        db.add(client)
        db.flush()
        org = Organization(
            name=f"Cliente {seq}", kind="client", client_id=client.id,
            seat_limit=3, plan=plan, status=status,
        )
        db.add(org)
        db.commit()
        return org.id
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
            role="internal_admin", status="active",
        ))
        db.commit()
        return email
    finally:
        db.close()


def _seed_client_admin(db_factory, org_id: str) -> str:
    seq = next(_seq)
    email = f"owner-{seq}@checkwise.example"
    db = db_factory()
    try:
        user = User(
            email=email, password_hash=hash_password(_PASSWORD),
            full_name=f"Owner {seq}", status="active",
        )
        db.add(user)
        db.flush()
        db.add(Membership(
            user_id=user.id, organization_id=org_id,
            role="client_admin", is_primary=True, status="active",
        ))
        db.commit()
        return email
    finally:
        db.close()


def _login(api_client: TestClient, email: str) -> str:
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------


def test_start_demo(db_factory, api_client):
    org_id = _seed_client_org(db_factory, plan="legacy")
    token = _login(api_client, _seed_internal_admin(db_factory))
    resp = api_client.post(
        f"/api/v1/admin/organizations/{org_id}/start-demo", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["plan"] == "demo"
    assert body["demo_expires_at"] is not None
    assert body["status"] == "active"
    assert body["capabilities"]["export_audit_package"] is False  # demo gates it
    db = db_factory()
    try:
        row = db.scalars(
            select(AuditLog).where(AuditLog.action == "admin.org.demo_started")
        ).first()
        assert row is not None
    finally:
        db.close()


def test_patch_upgrade_clears_demo_deadline(db_factory, api_client):
    org_id = _seed_client_org(db_factory)
    token = _login(api_client, _seed_internal_admin(db_factory))
    api_client.post(
        f"/api/v1/admin/organizations/{org_id}/start-demo", headers=_h(token)
    )
    resp = api_client.patch(
        f"/api/v1/admin/organizations/{org_id}",
        json={"plan": "standard"}, headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["plan"] == "standard"
    assert body["demo_expires_at"] is None  # cleared on plan change


def test_patch_sets_provider_limit_override(db_factory, api_client):
    org_id = _seed_client_org(db_factory, plan="standard")
    token = _login(api_client, _seed_internal_admin(db_factory))
    resp = api_client.patch(
        f"/api/v1/admin/organizations/{org_id}",
        json={"provider_limit": 7}, headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["provider_limit"] == 7


def test_patch_rejects_manual_freeze(db_factory, api_client):
    org_id = _seed_client_org(db_factory)
    token = _login(api_client, _seed_internal_admin(db_factory))
    resp = api_client.patch(
        f"/api/v1/admin/organizations/{org_id}",
        json={"status": "frozen"}, headers=_h(token),
    )
    assert resp.status_code == 400, resp.text


def test_patch_reactivates_frozen_org(db_factory, api_client):
    org_id = _seed_client_org(db_factory, plan="demo", status="frozen")
    token = _login(api_client, _seed_internal_admin(db_factory))
    resp = api_client.patch(
        f"/api/v1/admin/organizations/{org_id}",
        json={"status": "active"}, headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"


def test_patch_invalid_plan_400(db_factory, api_client):
    org_id = _seed_client_org(db_factory)
    token = _login(api_client, _seed_internal_admin(db_factory))
    resp = api_client.patch(
        f"/api/v1/admin/organizations/{org_id}",
        json={"plan": "platinum"}, headers=_h(token),
    )
    assert resp.status_code == 400, resp.text


def test_non_admin_forbidden(db_factory, api_client):
    org_id = _seed_client_org(db_factory)
    token = _login(api_client, _seed_client_admin(db_factory, org_id))
    resp = api_client.post(
        f"/api/v1/admin/organizations/{org_id}/start-demo", headers=_h(token)
    )
    assert resp.status_code == 403, resp.text


def test_start_demo_unknown_org_404(db_factory, api_client):
    token = _login(api_client, _seed_internal_admin(db_factory))
    resp = api_client.post(
        "/api/v1/admin/organizations/nope/start-demo", headers=_h(token)
    )
    assert resp.status_code == 404, resp.text
