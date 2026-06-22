"""Multi-user step 2 — owner-managed seats under ``/client/users``.

Covers the 3-seat model end to end: listing with seat counters,
owner-only mutation guards, the seat cap, disable/reactivate lockout
semantics, removal + seat reuse (including same-email reinstatement),
owner-issued password resets, internal_admin support access,
cross-tenant isolation, and the audit trail every action writes.
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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


_seq = itertools.count(1)
_PASSWORD = "ClientUsers!2026"


def _seed_client_with_owner(
    db_factory, *, name: str = "Cliente Demo", seat_limit: int | None = 3
) -> dict:
    """Client + org(kind=client) + primary-owner user, as the
    provisioning flow creates them post-0037."""
    seq = next(_seq)
    email = f"owner-{seq}@checkwise.example"
    db = db_factory()
    try:
        client = Client(name=name)
        db.add(client)
        db.flush()
        org = Organization(
            name=name, kind="client", client_id=client.id, seat_limit=seat_limit
        )
        db.add(org)
        db.flush()
        owner = User(
            email=email,
            password_hash=hash_password(_PASSWORD),
            full_name=f"Owner {seq}",
            status="active",
        )
        db.add(owner)
        db.flush()
        db.add(
            Membership(
                user_id=owner.id,
                organization_id=org.id,
                role="client_admin",
                is_primary=True,
                status="active",
            )
        )
        db.commit()
        return {
            "client_id": client.id,
            "org_id": org.id,
            "owner_id": owner.id,
            "owner_email": email,
        }
    finally:
        db.close()


def _seed_secondary(db_factory, org_id: str) -> dict:
    """A seated (non-primary) member with a usable password — i.e. a
    secondary who already completed first login."""
    seq = next(_seq)
    email = f"secondary-{seq}@checkwise.example"
    db = db_factory()
    try:
        user = User(
            email=email,
            password_hash=hash_password(_PASSWORD),
            full_name=f"Secondary {seq}",
            status="active",
        )
        db.add(user)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org_id,
                role="client_admin",
                is_primary=False,
                status="active",
            )
        )
        db.commit()
        return {"user_id": user.id, "email": email}
    finally:
        db.close()


def _seed_internal_admin(db_factory) -> dict:
    seq = next(_seq)
    email = f"staff-{seq}@checkwise.example"
    db = db_factory()
    try:
        user = User(
            email=email,
            password_hash=hash_password(_PASSWORD),
            full_name=f"Staff {seq}",
            status="active",
        )
        db.add(user)
        db.flush()
        org = Organization(name=f"Internal {seq}", kind="internal")
        db.add(org)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org.id,
                role="internal_admin",
                status="active",
            )
        )
        db.commit()
        return {"user_id": user.id, "email": email}
    finally:
        db.close()


def _login(api_client: TestClient, email: str, password: str = _PASSWORD) -> str:
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create(
    api_client: TestClient,
    token: str,
    *,
    email: str,
    full_name: str = "Empleado Demo",
    client_id: str | None = None,
    role: str | None = None,
):
    params = {"client_id": client_id} if client_id else {}
    body: dict = {"full_name": full_name, "email": email}
    if role is not None:
        body["role"] = role
    return api_client.post(
        "/api/v1/client/users",
        json=body,
        params=params,
        headers=_h(token),
    )


# ---------------------------------------------------------------------------
# Listing + seat counters
# ---------------------------------------------------------------------------


def test_owner_lists_users_with_seat_counters(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    token = _login(api_client, ctx["owner_email"])

    resp = api_client.get("/api/v1/client/users", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["seat_limit"] == 3
    assert body["seats_used"] == 1
    assert body["seats_available"] == 2
    assert body["can_manage"] is True
    assert len(body["users"]) == 1
    assert body["users"][0]["is_primary"] is True
    assert body["users"][0]["email"] == ctx["owner_email"]


def test_null_seat_limit_falls_back_to_three(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory, seat_limit=None)
    token = _login(api_client, ctx["owner_email"])
    body = api_client.get("/api/v1/client/users", headers=_h(token)).json()
    assert body["seat_limit"] == 3


# ---------------------------------------------------------------------------
# Create + seat cap
# ---------------------------------------------------------------------------


def test_owner_creates_secondary_who_can_log_in(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    token = _login(api_client, ctx["owner_email"])

    resp = _create(api_client, token, email="empleado@checkwise.example")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["seats_used"] == 2
    assert body["reinstated"] is False
    temp = body["temp_password"]

    # The fresh secondary can authenticate with the temp password and
    # is parked behind the must_change_password gate.
    login = api_client.post(
        "/api/v1/auth/login",
        json={"email": "empleado@checkwise.example", "password": temp},
    )
    assert login.status_code == 200, login.text
    gated = api_client.get(
        "/api/v1/client/users", headers=_h(login.json()["access_token"])
    )
    assert gated.status_code == 403  # must change password first

    # Both users appear in the owner's list.
    listed = api_client.get("/api/v1/client/users", headers=_h(token)).json()
    assert listed["seats_used"] == 2
    pending = [u for u in listed["users"] if not u["is_primary"]]
    assert pending[0]["pending_first_login"] is True


def test_seat_cap_blocks_a_fourth_user(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    token = _login(api_client, ctx["owner_email"])

    assert _create(api_client, token, email="a@checkwise.example").status_code == 201
    assert _create(api_client, token, email="b@checkwise.example").status_code == 201
    third = _create(api_client, token, email="c@checkwise.example")
    assert third.status_code == 409
    assert "máximo" in third.json()["detail"]


def test_duplicate_email_conflicts(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    token = _login(api_client, ctx["owner_email"])
    resp = _create(api_client, token, email=ctx["owner_email"])
    assert resp.status_code == 409


def test_email_of_another_tenants_user_conflicts(db_factory, api_client):
    ctx_a = _seed_client_with_owner(db_factory)
    ctx_b = _seed_client_with_owner(db_factory)
    token_a = _login(api_client, ctx_a["owner_email"])
    # Owner A tries to seat owner B's email — global uniqueness wins.
    resp = _create(api_client, token_a, email=ctx_b["owner_email"])
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Owner-only guards
# ---------------------------------------------------------------------------


def test_secondary_cannot_manage_seats(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    sec = _seed_secondary(db_factory, ctx["org_id"])
    token = _login(api_client, sec["email"])

    listed = api_client.get("/api/v1/client/users", headers=_h(token))
    assert listed.status_code == 200
    assert listed.json()["can_manage"] is False

    create = _create(api_client, token, email="x@checkwise.example")
    assert create.status_code == 403

    remove = api_client.delete(
        f"/api/v1/client/users/{ctx['owner_id']}", headers=_h(token)
    )
    assert remove.status_code == 403


def test_primary_cannot_be_targeted(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    token = _login(api_client, ctx["owner_email"])

    for resp in (
        api_client.patch(
            f"/api/v1/client/users/{ctx['owner_id']}",
            json={"status": "disabled"},
            headers=_h(token),
        ),
        api_client.delete(
            f"/api/v1/client/users/{ctx['owner_id']}", headers=_h(token)
        ),
        api_client.post(
            f"/api/v1/client/users/{ctx['owner_id']}/reset-password",
            headers=_h(token),
        ),
    ):
        assert resp.status_code == 409, resp.text


def test_cross_tenant_access_is_blocked(db_factory, api_client):
    ctx_a = _seed_client_with_owner(db_factory)
    ctx_b = _seed_client_with_owner(db_factory)
    sec_b = _seed_secondary(db_factory, ctx_b["org_id"])
    token_a = _login(api_client, ctx_a["owner_email"])

    # Explicitly requesting the other tenant 404s at scope resolution — the
    # response is identical whether the foreign client exists or not, so it
    # cannot be used as a cross-tenant existence oracle (`_resolve_client_id`).
    listed = api_client.get(
        "/api/v1/client/users",
        params={"client_id": ctx_b["client_id"]},
        headers=_h(token_a),
    )
    assert listed.status_code == 404

    # Targeting another tenant's user inside one's own scope 404s.
    removed = api_client.delete(
        f"/api/v1/client/users/{sec_b['user_id']}", headers=_h(token_a)
    )
    assert removed.status_code == 404


# ---------------------------------------------------------------------------
# Disable / reactivate / remove
# ---------------------------------------------------------------------------


def test_disable_locks_out_and_reactivate_restores(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    sec = _seed_secondary(db_factory, ctx["org_id"])
    owner_token = _login(api_client, sec["email"])  # prove login works first
    owner_token = _login(api_client, ctx["owner_email"])

    resp = api_client.patch(
        f"/api/v1/client/users/{sec['user_id']}",
        json={"status": "disabled"},
        headers=_h(owner_token),
    )
    assert resp.status_code == 200
    # Seat stays occupied while disabled.
    assert resp.json()["seats_used"] == 2

    login = api_client.post(
        "/api/v1/auth/login",
        json={"email": sec["email"], "password": _PASSWORD},
    )
    assert login.status_code != 200

    resp = api_client.patch(
        f"/api/v1/client/users/{sec['user_id']}",
        json={"status": "active"},
        headers=_h(owner_token),
    )
    assert resp.status_code == 200
    assert _login(api_client, sec["email"])  # logs in again


def test_disable_revokes_inflight_session(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    sec = _seed_secondary(db_factory, ctx["org_id"])
    sec_token = _login(api_client, sec["email"])
    owner_token = _login(api_client, ctx["owner_email"])

    assert (
        api_client.get("/api/v1/client/users", headers=_h(sec_token)).status_code
        == 200
    )
    api_client.patch(
        f"/api/v1/client/users/{sec['user_id']}",
        json={"status": "disabled"},
        headers=_h(owner_token),
    )
    # The still-unexpired JWT dies on the next request.
    assert (
        api_client.get("/api/v1/client/users", headers=_h(sec_token)).status_code
        == 401
    )


def test_remove_frees_seat_and_same_email_reinstates(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    sec = _seed_secondary(db_factory, ctx["org_id"])
    sec_token = _login(api_client, sec["email"])
    owner_token = _login(api_client, ctx["owner_email"])

    resp = api_client.delete(
        f"/api/v1/client/users/{sec['user_id']}", headers=_h(owner_token)
    )
    assert resp.status_code == 200
    assert resp.json()["seats_used"] == 1

    # Removed user loses access immediately (membership gone, user disabled).
    assert (
        api_client.get("/api/v1/client/users", headers=_h(sec_token)).status_code
        == 401
    )

    # Re-inviting the same email reinstates the seat with fresh creds.
    resp = _create(api_client, owner_token, email=sec["email"])
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["reinstated"] is True
    assert body["user_id"] == sec["user_id"]
    login = api_client.post(
        "/api/v1/auth/login",
        json={"email": sec["email"], "password": body["temp_password"]},
    )
    assert login.status_code == 200


# ---------------------------------------------------------------------------
# Owner-issued password reset
# ---------------------------------------------------------------------------


def test_reset_password_rotates_credentials(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    sec = _seed_secondary(db_factory, ctx["org_id"])
    owner_token = _login(api_client, ctx["owner_email"])

    resp = api_client.post(
        f"/api/v1/client/users/{sec['user_id']}/reset-password",
        headers=_h(owner_token),
    )
    assert resp.status_code == 200, resp.text
    temp = resp.json()["temp_password"]

    old = api_client.post(
        "/api/v1/auth/login",
        json={"email": sec["email"], "password": _PASSWORD},
    )
    assert old.status_code != 200
    fresh = api_client.post(
        "/api/v1/auth/login", json={"email": sec["email"], "password": temp}
    )
    assert fresh.status_code == 200
    assert fresh.json()["user"]["must_change_password"] is True


def test_reset_password_requires_active_user(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    sec = _seed_secondary(db_factory, ctx["org_id"])
    owner_token = _login(api_client, ctx["owner_email"])
    api_client.patch(
        f"/api/v1/client/users/{sec['user_id']}",
        json={"status": "disabled"},
        headers=_h(owner_token),
    )
    resp = api_client.post(
        f"/api/v1/client/users/{sec['user_id']}/reset-password",
        headers=_h(owner_token),
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Internal admin support access
# ---------------------------------------------------------------------------


def test_internal_admin_manages_any_tenant_via_client_id(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    staff = _seed_internal_admin(db_factory)
    token = _login(api_client, staff["email"])

    listed = api_client.get(
        "/api/v1/client/users",
        params={"client_id": ctx["client_id"]},
        headers=_h(token),
    )
    assert listed.status_code == 200
    assert listed.json()["can_manage"] is True

    resp = _create(
        api_client,
        token,
        email="soporte-alta@checkwise.example",
        client_id=ctx["client_id"],
    )
    assert resp.status_code == 201, resp.text


def test_internal_admin_cross_tenant_access_is_audited(db_factory, api_client):
    """Break-glass: an internal_admin reaching a tenant they do NOT belong
    to leaves a forensic ``client.cross_tenant_access`` row, deduplicated to
    one per (actor, client) inside the window."""
    ctx = _seed_client_with_owner(db_factory)
    staff = _seed_internal_admin(db_factory)
    token = _login(api_client, staff["email"])

    # Two cross-tenant reads in the same window…
    for _ in range(2):
        resp = api_client.get(
            "/api/v1/client/users",
            params={"client_id": ctx["client_id"]},
            headers=_h(token),
        )
        assert resp.status_code == 200, resp.text

    db = db_factory()
    try:
        rows = list(
            db.scalars(
                select(AuditLog).where(
                    AuditLog.action == "client.cross_tenant_access",
                    AuditLog.entity_id == ctx["client_id"],
                )
            )
        )
    finally:
        db.close()
    # …collapse to a single row, attributed to the staff member.
    assert len(rows) == 1, rows
    assert rows[0].actor_id == staff["user_id"]
    assert rows[0].actor_type == "internal_admin"
    assert rows[0].entity_type == "client"


def test_owner_access_is_not_flagged_as_cross_tenant(db_factory, api_client):
    """A client_admin viewing their OWN tenant is not break-glass access —
    no ``client.cross_tenant_access`` row is written."""
    ctx = _seed_client_with_owner(db_factory)
    owner_token = _login(api_client, ctx["owner_email"])

    resp = api_client.get("/api/v1/client/users", headers=_h(owner_token))
    assert resp.status_code == 200, resp.text

    db = db_factory()
    try:
        flagged = list(
            db.scalars(
                select(AuditLog).where(
                    AuditLog.action == "client.cross_tenant_access"
                )
            )
        )
    finally:
        db.close()
    assert flagged == []


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


def test_lifecycle_actions_write_attributed_audit_rows(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    owner_token = _login(api_client, ctx["owner_email"])

    created = _create(api_client, owner_token, email="bitacora@checkwise.example")
    assert created.status_code == 201
    target_id = created.json()["user_id"]
    api_client.patch(
        f"/api/v1/client/users/{target_id}",
        json={"status": "disabled"},
        headers=_h(owner_token),
    )
    api_client.patch(
        f"/api/v1/client/users/{target_id}",
        json={"status": "active"},
        headers=_h(owner_token),
    )
    api_client.post(
        f"/api/v1/client/users/{target_id}/reset-password",
        headers=_h(owner_token),
    )
    api_client.delete(
        f"/api/v1/client/users/{target_id}", headers=_h(owner_token)
    )

    db = db_factory()
    try:
        rows = list(
            db.scalars(
                select(AuditLog).where(AuditLog.entity_id == target_id)
            )
        )
    finally:
        db.close()
    lifecycle = [r for r in rows if r.action.startswith("client.user_")]
    actions = {r.action for r in lifecycle}
    assert {
        "client.user_created",
        "client.user_disabled",
        "client.user_reactivated",
        "client.user_password_reset",
        "client.user_removed",
    } <= actions
    # Every lifecycle action is attributed to the specific owner, not
    # the org. (The notification fabric writes its own system-actor
    # rows for the same entity — those are out of scope here.)
    assert all(r.actor_id == ctx["owner_id"] for r in lifecycle)
    assert all(r.actor_type == "client_admin" for r in lifecycle)


def test_client_user_audit_captures_request_ip(db_factory, api_client):
    """Phase 6 — client_users mutations now stamp the originating IP /
    user-agent onto the audit row (previously NULL)."""
    ctx = _seed_client_with_owner(db_factory)
    token = _login(api_client, ctx["owner_email"])

    resp = _create(api_client, token, email="audit-ip@checkwise.example")
    assert resp.status_code == 201, resp.text

    db = db_factory()
    try:
        row = db.scalars(
            select(AuditLog)
            .where(AuditLog.action == "client.user_created")
            .order_by(AuditLog.created_at.desc())
        ).first()
        assert row is not None
        # TestClient populates request.client.host, so the IP is non-null
        # and the user-agent header is recorded.
        assert row.ip_address
        assert row.user_agent
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Phase 4 — seat tiers (Approver vs Viewer)
# ---------------------------------------------------------------------------


def _roles_by_email(api_client, token) -> dict:
    body = api_client.get("/api/v1/client/users", headers=_h(token)).json()
    return {u["email"]: u["role"] for u in body["users"]}


def test_new_seat_defaults_to_viewer(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    owner_token = _login(api_client, ctx["owner_email"])

    created = _create(api_client, owner_token, email="seat@checkwise.example")
    assert created.status_code == 201, created.text
    # Owner is the Approver; the new seat defaults to the least-privilege Viewer.
    roles = _roles_by_email(api_client, owner_token)
    assert roles[ctx["owner_email"]] == "client_admin"
    assert roles["seat@checkwise.example"] == "client_viewer"


def test_owner_can_create_approver_seat(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    owner_token = _login(api_client, ctx["owner_email"])

    created = _create(
        api_client,
        owner_token,
        email="appr@checkwise.example",
        role="client_admin",
    )
    assert created.status_code == 201, created.text
    assert _roles_by_email(api_client, owner_token)["appr@checkwise.example"] == (
        "client_admin"
    )


def test_owner_promotes_and_demotes_seat(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    owner_token = _login(api_client, ctx["owner_email"])
    created = _create(api_client, owner_token, email="promo@checkwise.example")
    user_id = created.json()["user_id"]

    promote = api_client.patch(
        f"/api/v1/client/users/{user_id}/role",
        json={"role": "client_admin"},
        headers=_h(owner_token),
    )
    assert promote.status_code == 200, promote.text
    assert promote.json()["role"] == "client_admin"
    assert _roles_by_email(api_client, owner_token)[
        "promo@checkwise.example"
    ] == "client_admin"

    demote = api_client.patch(
        f"/api/v1/client/users/{user_id}/role",
        json={"role": "client_viewer"},
        headers=_h(owner_token),
    )
    assert demote.status_code == 200
    assert _roles_by_email(api_client, owner_token)[
        "promo@checkwise.example"
    ] == "client_viewer"

    db = db_factory()
    try:
        actions = set(
            db.scalars(
                select(AuditLog.action).where(AuditLog.entity_id == user_id)
            )
        )
    finally:
        db.close()
    assert "client.user_role_changed" in actions


def test_cannot_change_primary_owner_role(db_factory, api_client):
    ctx = _seed_client_with_owner(db_factory)
    owner_token = _login(api_client, ctx["owner_email"])

    resp = api_client.patch(
        f"/api/v1/client/users/{ctx['owner_id']}/role",
        json={"role": "client_viewer"},
        headers=_h(owner_token),
    )
    assert resp.status_code == 409, resp.text


def test_secondary_cannot_change_roles(db_factory, api_client):
    """Tier changes are owner-only (same _require_can_manage gate)."""
    ctx = _seed_client_with_owner(db_factory)
    owner_token = _login(api_client, ctx["owner_email"])
    target = _create(api_client, owner_token, email="t@checkwise.example")
    target_id = target.json()["user_id"]
    sec = _seed_secondary(db_factory, ctx["org_id"])
    sec_token = _login(api_client, sec["email"])

    resp = api_client.patch(
        f"/api/v1/client/users/{target_id}/role",
        json={"role": "client_admin"},
        headers=_h(sec_token),
    )
    assert resp.status_code == 403, resp.text
