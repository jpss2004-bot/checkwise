"""Phase B2 — org-status login gate.

A frozen/expired client is blocked from data/mutating routes (403 trial_expired)
but MUST always be able to log out, read /auth/me, and read /client/plan (the
upgrade surface). Internal staff are never trial-gated. The gate re-evaluates
per request off the DB.
"""

from __future__ import annotations

import itertools
from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.time import utc_now
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Client, Membership, Organization, User, entities  # noqa: F401
from app.services.auth import hash_password

_PASSWORD = "LoginGate!2026"
_seq = itertools.count(1)

# A real authenticated client route NOT in the frozen allow-list.
_GATED_ROUTE = "/api/v1/client/users"


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


def _seed_client_owner(db_factory, *, plan="standard", status="active",
                       demo_expires_at=None) -> str:
    seq = next(_seq)
    email = f"owner-{seq}@checkwise.example"
    db = db_factory()
    try:
        client = Client(name=f"Cliente {seq}")
        db.add(client)
        db.flush()
        org = Organization(
            name=f"Cliente {seq}", kind="client", client_id=client.id,
            seat_limit=3, plan=plan, status=status, demo_expires_at=demo_expires_at,
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
        return email
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


def _login(api_client, email):
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------


def test_frozen_client_blocked_on_data_route(db_factory, api_client):
    token = _login(api_client, _seed_client_owner(db_factory, status="frozen"))
    resp = api_client.get(_GATED_ROUTE, headers=_h(token))
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "trial_expired"


def test_frozen_client_can_still_logout(db_factory, api_client):
    token = _login(api_client, _seed_client_owner(db_factory, status="frozen"))
    resp = api_client.post("/api/v1/auth/logout", headers=_h(token))
    assert resp.status_code != 403, resp.text  # logout is never gated


def test_frozen_client_can_read_me_and_plan(db_factory, api_client):
    token = _login(api_client, _seed_client_owner(db_factory, status="frozen"))
    assert api_client.get("/api/v1/auth/me", headers=_h(token)).status_code == 200
    assert api_client.get("/api/v1/client/plan", headers=_h(token)).status_code == 200


def test_expired_demo_blocked(db_factory, api_client):
    past = utc_now() - timedelta(days=1)
    token = _login(api_client, _seed_client_owner(
        db_factory, plan="demo", demo_expires_at=past))
    resp = api_client.get(_GATED_ROUTE, headers=_h(token))
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "trial_expired"


def test_demo_within_deadline_not_blocked(db_factory, api_client):
    future = utc_now() + timedelta(days=3)
    token = _login(api_client, _seed_client_owner(
        db_factory, plan="demo", demo_expires_at=future))
    assert api_client.get(_GATED_ROUTE, headers=_h(token)).status_code == 200


def test_paid_client_not_blocked(db_factory, api_client):
    token = _login(api_client, _seed_client_owner(db_factory, plan="standard"))
    assert api_client.get(_GATED_ROUTE, headers=_h(token)).status_code == 200


def test_internal_admin_never_gated(db_factory, api_client):
    token = _login(api_client, _seed_internal_admin(db_factory))
    # An internal route works; the trial gate never applies to staff.
    assert api_client.get("/api/v1/admin/clients", headers=_h(token)).status_code == 200


def test_gate_reevaluates_per_request(db_factory, api_client):
    """Freezing takes effect immediately, no re-login (gate reads the DB)."""
    email = _seed_client_owner(db_factory, plan="standard")
    token = _login(api_client, email)
    assert api_client.get(_GATED_ROUTE, headers=_h(token)).status_code == 200
    # Freeze the org out-of-band; the SAME token is now blocked.
    db = db_factory()
    try:
        org = db.query(Organization).filter(Organization.kind == "client").first()
        org.status = "frozen"
        db.commit()
    finally:
        db.close()
    assert api_client.get(_GATED_ROUTE, headers=_h(token)).status_code == 403
