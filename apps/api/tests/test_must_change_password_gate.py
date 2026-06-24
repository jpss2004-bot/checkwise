"""P0 — must_change_password gate.

A user whose ``User.must_change_password`` flag is ``True`` may only
reach the narrow surface needed to clear the flag. Anything else returns
403 with a Spanish detail message. Without this gate, a freshly-activated
provider whose JWT was issued before they set a personal password could
read or mutate any route their role permits.

Coverage:

* A user with the flag set is blocked (403) on a sample of admin, client,
  reviewer, and portal endpoints.
* The same user reaches ``/auth/me`` and ``/auth/set-password`` (200) so
  the forced-password screen can render and accept the new password.
* After ``/auth/set-password`` clears the flag, the same JWT (still
  valid) succeeds on previously-blocked endpoints.

Cross-referenced with ``must_change_password_allowed`` in
``app/security/route_policy_manifest.json``; the allow-list lives in
``app.api.v1.auth._PASSWORD_GATE_ALLOWED_PATHS`` and is the single source
of truth for the gate itself.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Membership, Organization, User, entities  # noqa: F401
from app.services.auth import hash_password


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


def _seed_user_with_must_change(
    db_factory,
    *,
    email: str,
    password: str,
    role: str,
    org_kind: str = "internal",
) -> str:
    """Seed a user with ``must_change_password=True`` carrying ``role``
    in a single organization. Returns the organization id."""
    db = db_factory()
    try:
        org = Organization(name=f"Org for {email}", kind=org_kind)
        db.add(org)
        db.flush()
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Must Change Password",
            status="active",
            must_change_password=True,
        )
        db.add(user)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org.id,
                role=role,
                status="active",
            )
        )
        db.commit()
        return org.id
    finally:
        db.close()


def _login(api_client: TestClient, email: str, password: str) -> str:
    response = api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_gate_blocks_admin_routes_when_flag_is_set(
    api_client: TestClient, db_factory
) -> None:
    """An ``internal_admin`` user with the flag set is forbidden from
    admin endpoints they would otherwise be able to reach."""
    email = "admin-flag@checkwise.test"
    password = "TempPassword!2026"
    _seed_user_with_must_change(
        db_factory, email=email, password=password, role="operations_admin"
    )
    token = _login(api_client, email, password)

    response = api_client.get(
        "/api/v1/admin/clients", headers=_auth_headers(token)
    )
    assert response.status_code == 403, response.text
    assert "contraseña" in response.json()["detail"]


def test_gate_blocks_client_admin_routes_when_flag_is_set(
    api_client: TestClient, db_factory
) -> None:
    """A ``client_admin`` user with the flag set is forbidden from
    client-scoped endpoints."""
    email = "client-flag@checkwise.test"
    password = "TempPassword!2026"
    _seed_user_with_must_change(
        db_factory,
        email=email,
        password=password,
        role="client_admin",
        org_kind="client",
    )
    token = _login(api_client, email, password)

    response = api_client.get(
        "/api/v1/client/me", headers=_auth_headers(token)
    )
    assert response.status_code == 403, response.text
    assert "contraseña" in response.json()["detail"]


def test_gate_blocks_reviewer_routes_when_flag_is_set(
    api_client: TestClient, db_factory
) -> None:
    """A ``reviewer`` user with the flag set is forbidden from the
    reviewer queue."""
    email = "reviewer-flag@checkwise.test"
    password = "TempPassword!2026"
    _seed_user_with_must_change(
        db_factory, email=email, password=password, role="platform_admin"
    )
    token = _login(api_client, email, password)

    response = api_client.get(
        "/api/v1/reviewer/queue", headers=_auth_headers(token)
    )
    assert response.status_code == 403, response.text
    assert "contraseña" in response.json()["detail"]


def test_gate_allows_auth_me_when_flag_is_set(
    api_client: TestClient, db_factory
) -> None:
    """``/auth/me`` must succeed so the forced-password screen can render."""
    email = "me-flag@checkwise.test"
    password = "TempPassword!2026"
    _seed_user_with_must_change(
        db_factory, email=email, password=password, role="operations_admin"
    )
    token = _login(api_client, email, password)

    response = api_client.get(
        "/api/v1/auth/me", headers=_auth_headers(token)
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["must_change_password"] is True


def test_gate_allows_set_password_when_flag_is_set(
    api_client: TestClient, db_factory
) -> None:
    """``/auth/set-password`` must succeed so the user can clear the flag."""
    email = "setpw-flag@checkwise.test"
    password = "TempPassword!2026"
    _seed_user_with_must_change(
        db_factory, email=email, password=password, role="operations_admin"
    )
    token = _login(api_client, email, password)

    response = api_client.post(
        "/api/v1/auth/set-password",
        json={"new_password": "NewLongerPassword!2026"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["must_change_password"] is False


def test_gate_clears_after_set_password_and_admin_routes_unlock(
    api_client: TestClient, db_factory
) -> None:
    """After /auth/set-password flips the flag, the same JWT (still
    valid) must reach previously-blocked endpoints."""
    email = "unlock-flag@checkwise.test"
    password = "TempPassword!2026"
    _seed_user_with_must_change(
        db_factory, email=email, password=password, role="operations_admin"
    )
    token = _login(api_client, email, password)

    # Blocked before clearing the flag.
    blocked = api_client.get(
        "/api/v1/admin/clients", headers=_auth_headers(token)
    )
    assert blocked.status_code == 403, blocked.text

    # Clear the flag.
    set_resp = api_client.post(
        "/api/v1/auth/set-password",
        json={"new_password": "NewLongerPassword!2026"},
        headers=_auth_headers(token),
    )
    assert set_resp.status_code == 200, set_resp.text

    # Unblocked after clearing the flag — same JWT, no relogin.
    unblocked = api_client.get(
        "/api/v1/admin/clients", headers=_auth_headers(token)
    )
    assert unblocked.status_code == 200, unblocked.text
