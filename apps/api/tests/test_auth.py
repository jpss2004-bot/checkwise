from __future__ import annotations

import time
from collections.abc import Generator
from datetime import timedelta
from types import SimpleNamespace
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.auth import (
    CurrentUser,
    require_org_role,
    require_role,
)
from app.api.v1.router import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Membership,
    Organization,
    PasswordResetToken,
    User,
    entities,  # noqa: F401
)
from app.models.entities import utc_now
from app.services.auth import (
    decode_access_token,
    hash_password,
    hash_password_reset_token,
    issue_access_token,
    verify_password,
)


@pytest.fixture
def db_factory(tmp_path):
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


def _seed_user(
    db_factory,
    *,
    email: str = "ada@legalshelf.mx",
    password: str = "Correct horse battery 4",
    full_name: str = "Ada Legal",
    org_name: str = "LegalShelf",
    org_kind: str = "internal",
    role: str = "internal_admin",
    status: str = "active",
) -> tuple[str, str, str]:
    """Inserts an Organization + User + Membership. Returns
    ``(user_id, organization_id, password)``."""
    db = db_factory()
    try:
        org = Organization(name=org_name, kind=org_kind)
        db.add(org)
        db.flush()
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            status=status,
        )
        db.add(user)
        db.flush()
        membership = Membership(
            user_id=user.id, organization_id=org.id, role=role, status="active"
        )
        db.add(membership)
        db.commit()
        return user.id, org.id, password
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Unit tests for the auth service (hashing + JWT)
# ---------------------------------------------------------------------------


def test_hash_and_verify_password_roundtrip() -> None:
    h1 = hash_password("hunter2")
    h2 = hash_password("hunter2")
    assert h1 != h2  # different salts
    assert verify_password("hunter2", h1)
    assert verify_password("hunter2", h2)
    assert not verify_password("hunter3", h1)
    assert not verify_password("", h1)
    assert not verify_password("hunter2", None)
    assert not verify_password("hunter2", "not-a-real-hash")


def test_issue_and_decode_token_carries_roles_and_orgs() -> None:
    token = issue_access_token(
        user_id="u1", email="x@y.mx", roles=["internal_admin"], orgs=["o1"]
    )
    claims = decode_access_token(token)
    assert claims.user_id == "u1"
    assert claims.email == "x@y.mx"
    assert claims.roles == ("internal_admin",)
    assert claims.orgs == ("o1",)
    assert claims.expires_at > claims.issued_at


def test_decode_expired_token_raises() -> None:
    from app.services.auth import TokenError

    long_ago = int(time.time()) - settings.AUTH_JWT_EXPIRES_MINUTES * 60 - 60
    token = issue_access_token(
        user_id="u1", email="x@y.mx", roles=[], orgs=[], now=long_ago
    )
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_decode_garbage_token_raises() -> None:
    from app.services.auth import TokenError

    with pytest.raises(TokenError):
        decode_access_token("not.a.jwt")
    with pytest.raises(TokenError):
        decode_access_token("")


# ---------------------------------------------------------------------------
# /auth/login
# ---------------------------------------------------------------------------


def test_login_happy_path(api_client: TestClient, db_factory) -> None:
    _seed_user(db_factory)
    response = api_client.post(
        "/api/v1/auth/login",
        json={"email": "ada@legalshelf.mx", "password": "Correct horse battery 4"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["access_token"]
    assert payload["token_type"] == "Bearer"
    assert payload["user"]["email"] == "ada@legalshelf.mx"
    assert payload["roles"] == ["internal_admin"]
    assert len(payload["organization_ids"]) == 1


def test_login_email_is_case_insensitive(api_client: TestClient, db_factory) -> None:
    _seed_user(db_factory)
    response = api_client.post(
        "/api/v1/auth/login",
        json={"email": "ADA@LegalShelf.MX", "password": "Correct horse battery 4"},
    )
    assert response.status_code == 200


def test_login_wrong_password_returns_401(api_client: TestClient, db_factory) -> None:
    _seed_user(db_factory)
    response = api_client.post(
        "/api/v1/auth/login",
        json={"email": "ada@legalshelf.mx", "password": "wrong"},
    )
    assert response.status_code == 401


def test_login_unknown_email_returns_401_with_generic_detail(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@legalshelf.mx", "password": "anything"},
    )
    assert response.status_code == 401
    # Must not reveal whether the user exists. Localized after the
    # 2026-05-25 M2 Spanish-error-normalization pass; the
    # indistinguishability contract is preserved — the same Spanish
    # message returns for unknown-email and bad-password.
    assert response.json()["detail"] == "Credenciales inválidas."


def test_login_disabled_user_returns_401(api_client: TestClient, db_factory) -> None:
    _seed_user(db_factory, email="disabled@x.mx", status="disabled")
    response = api_client.post(
        "/api/v1/auth/login",
        json={"email": "disabled@x.mx", "password": "Correct horse battery 4"},
    )
    assert response.status_code == 401


def test_login_invalid_email_format_returns_422(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/auth/login", json={"email": "no-at-sign", "password": "x"}
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /auth/me
# ---------------------------------------------------------------------------


def _login(api_client: TestClient, email: str, password: str) -> str:
    response = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_me_returns_current_user(api_client: TestClient, db_factory) -> None:
    _, org_id, password = _seed_user(db_factory)
    token = _login(api_client, "ada@legalshelf.mx", password)
    response = api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["user"]["email"] == "ada@legalshelf.mx"
    assert payload["roles"] == ["internal_admin"]
    assert payload["organization_ids"] == [org_id]


def test_me_missing_header_returns_401(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_invalid_token_returns_401(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer garbage"}
    )
    assert response.status_code == 401


def test_me_non_bearer_scheme_returns_401(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Basic abc"}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# RBAC dependencies — exercised through a tiny ad-hoc FastAPI app so the
# guards are tested in isolation from any production endpoint.
# ---------------------------------------------------------------------------


_AdminDep = Annotated[CurrentUser, Depends(require_role("internal_admin"))]
_ReviewerDep = Annotated[CurrentUser, Depends(require_role("reviewer"))]
_OrgAdminDep = Annotated[CurrentUser, Depends(require_org_role("internal_admin"))]


def _build_rbac_app(db_factory) -> TestClient:
    test_app = FastAPI()
    test_app.include_router(api_router, prefix="/api/v1")

    def override_get_db() -> Generator[Session, None, None]:
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    @test_app.get("/protected/admin")
    def _admin_only(current: _AdminDep) -> dict:
        return {"ok": True, "user_id": current.user.id}

    @test_app.get("/protected/reviewer")
    def _reviewer_only(current: _ReviewerDep) -> dict:
        return {"ok": True, "user_id": current.user.id}

    @test_app.get("/protected/orgs/{organization_id}/admin")
    def _org_admin(organization_id: str, current: _OrgAdminDep) -> dict:  # noqa: ARG001
        return {"ok": True, "user_id": current.user.id}

    test_app.dependency_overrides[get_db] = override_get_db
    return TestClient(test_app)


def test_require_role_passes_when_role_present(db_factory) -> None:
    client = _build_rbac_app(db_factory)
    _, _, password = _seed_user(db_factory)
    token = _login(client, "ada@legalshelf.mx", password)
    response = client.get(
        "/protected/admin", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text


def test_require_role_denies_when_role_missing(db_factory) -> None:
    client = _build_rbac_app(db_factory)
    _, _, password = _seed_user(db_factory)
    token = _login(client, "ada@legalshelf.mx", password)
    response = client.get(
        "/protected/reviewer", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


def test_require_org_role_passes_for_member(db_factory) -> None:
    client = _build_rbac_app(db_factory)
    _, org_id, password = _seed_user(db_factory)
    token = _login(client, "ada@legalshelf.mx", password)
    response = client.get(
        f"/protected/orgs/{org_id}/admin",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_require_org_role_denies_for_non_member(db_factory) -> None:
    client = _build_rbac_app(db_factory)
    _, _, password = _seed_user(db_factory)
    token = _login(client, "ada@legalshelf.mx", password)
    response = client.get(
        "/protected/orgs/some-other-org-id/admin",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_require_org_role_denies_when_membership_revoked(db_factory) -> None:
    """A token issued while the user had the role is rejected if the
    DB-side membership got revoked (status != active) before the token's
    natural expiry."""
    client = _build_rbac_app(db_factory)
    user_id, org_id, password = _seed_user(db_factory)
    token = _login(client, "ada@legalshelf.mx", password)

    # Revoke the membership after login.
    db = db_factory()
    try:
        membership = db.execute(
            __import__("sqlalchemy").select(Membership).where(
                Membership.user_id == user_id, Membership.organization_id == org_id
            )
        ).scalar_one()
        membership.status = "revoked"
        db.commit()
    finally:
        db.close()

    response = client.get(
        f"/protected/orgs/{org_id}/admin",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# must_change_password gate + /auth/set-password (CheckWise 1.8)
# ---------------------------------------------------------------------------


def test_login_response_includes_must_change_password_flag(
    api_client: TestClient, db_factory
) -> None:
    """When a user is seeded with must_change_password=True, the login
    response must surface that flag so the frontend can route to /activate."""
    db = db_factory()
    try:
        org = Organization(name="Demo Provider Org", kind="vendor")
        db.add(org)
        db.flush()
        user = User(
            email="prov-flag@checkwise.test",
            password_hash=hash_password("CheckWiseTest!2026"),
            full_name="Provider Flag",
            status="active",
            must_change_password=True,
        )
        db.add(user)
        db.flush()
        db.add(
            Membership(
                user_id=user.id, organization_id=org.id, role="provider", status="active"
            )
        )
        db.commit()
    finally:
        db.close()

    response = api_client.post(
        "/api/v1/auth/login",
        json={"email": "prov-flag@checkwise.test", "password": "CheckWiseTest!2026"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["must_change_password"] is True
    assert payload["user"]["must_change_password"] is True


def test_set_password_clears_must_change_flag_and_lets_user_log_in_again(
    api_client: TestClient, db_factory
) -> None:
    """After /auth/set-password, must_change_password is False and the
    new password authenticates."""
    db = db_factory()
    try:
        org = Organization(name="Demo Provider Org 2", kind="vendor")
        db.add(org)
        db.flush()
        user = User(
            email="prov-set@checkwise.test",
            password_hash=hash_password("temp-pass-12chars!"),
            full_name="Provider Set",
            status="active",
            must_change_password=True,
        )
        db.add(user)
        db.flush()
        db.add(
            Membership(
                user_id=user.id, organization_id=org.id, role="provider", status="active"
            )
        )
        db.commit()
    finally:
        db.close()

    token = _login(api_client, "prov-set@checkwise.test", "temp-pass-12chars!")
    new_password = "NewLongerPassword!2026"
    set_resp = api_client.post(
        "/api/v1/auth/set-password",
        json={"new_password": new_password},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert set_resp.status_code == 200, set_resp.text
    assert set_resp.json()["must_change_password"] is False

    # Old password no longer works.
    bad = api_client.post(
        "/api/v1/auth/login",
        json={"email": "prov-set@checkwise.test", "password": "temp-pass-12chars!"},
    )
    assert bad.status_code == 401

    # New password works and the flag stays clear.
    fresh = api_client.post(
        "/api/v1/auth/login",
        json={"email": "prov-set@checkwise.test", "password": new_password},
    )
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["must_change_password"] is False


def test_set_password_requires_authentication(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/auth/set-password",
        json={"new_password": "AnyLongerPassword!2026"},
    )
    assert response.status_code == 401


def test_set_password_rejects_short_password(
    api_client: TestClient, db_factory
) -> None:
    _, _, password = _seed_user(db_factory)
    token = _login(api_client, "ada@legalshelf.mx", password)
    response = api_client.post(
        "/api/v1/auth/set-password",
        json={"new_password": "tooshort"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Forgot password + reset link flow
# ---------------------------------------------------------------------------


def test_forgot_password_creates_token_and_sends_generic_response(
    api_client: TestClient, db_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, _, _ = _seed_user(db_factory, email="reset@legalshelf.mx")
    sent: list[dict[str, str]] = []

    def fake_send_password_reset_email(*, to_email: str, reset_url: str):
        sent.append({"to_email": to_email, "reset_url": reset_url})
        return SimpleNamespace(status="sent", error=None)

    monkeypatch.setattr(
        "app.api.v1.auth.send_password_reset_email", fake_send_password_reset_email
    )

    response = api_client.post(
        "/api/v1/auth/forgot-password", json={"email": "RESET@LegalShelf.MX"}
    )
    assert response.status_code == 202, response.text
    assert "Si el correo existe" in response.json()["message"]
    assert sent and sent[0]["to_email"] == "reset@legalshelf.mx"
    assert "/reset-password?token=" in sent[0]["reset_url"]

    db = db_factory()
    try:
        token = db.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
        ).scalar_one()
        assert token.email == "reset@legalshelf.mx"
        assert token.token_hash not in sent[0]["reset_url"]
        assert token.delivery_status == "sent"
        assert token.used_at is None
    finally:
        db.close()


def test_forgot_password_unknown_email_is_generic_and_creates_no_token(
    api_client: TestClient, db_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[dict[str, str]] = []

    def fake_send_password_reset_email(*, to_email: str, reset_url: str):
        sent.append({"to_email": to_email, "reset_url": reset_url})
        return SimpleNamespace(status="sent", error=None)

    monkeypatch.setattr(
        "app.api.v1.auth.send_password_reset_email", fake_send_password_reset_email
    )

    response = api_client.post(
        "/api/v1/auth/forgot-password", json={"email": "ghost@legalshelf.mx"}
    )
    assert response.status_code == 202, response.text
    assert "Si el correo existe" in response.json()["message"]
    assert sent == []

    db = db_factory()
    try:
        total = db.scalar(select(__import__("sqlalchemy").func.count(PasswordResetToken.id)))
        assert total == 0
    finally:
        db.close()


def test_reset_password_updates_password_and_consumes_token(
    api_client: TestClient, db_factory
) -> None:
    user_id, _, old_password = _seed_user(
        db_factory,
        email="consume@legalshelf.mx",
        password="OldPassword!2026",
        status="active",
    )
    raw_token = "reset-token-for-test-1234567890"
    db = db_factory()
    try:
        token = PasswordResetToken(
            user_id=user_id,
            email="consume@legalshelf.mx",
            token_hash=hash_password_reset_token(raw_token),
            expires_at=utc_now() + timedelta(minutes=30),
            delivery_status="sent",
        )
        db.add(token)
        db.commit()
    finally:
        db.close()

    new_password = "NewPassword!2026"
    response = api_client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": new_password},
    )
    assert response.status_code == 200, response.text

    old_login = api_client.post(
        "/api/v1/auth/login",
        json={"email": "consume@legalshelf.mx", "password": old_password},
    )
    assert old_login.status_code == 401
    new_login = api_client.post(
        "/api/v1/auth/login",
        json={"email": "consume@legalshelf.mx", "password": new_password},
    )
    assert new_login.status_code == 200, new_login.text

    reuse = api_client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "AnotherPassword!2026"},
    )
    assert reuse.status_code == 400

    db = db_factory()
    try:
        token = db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == hash_password_reset_token(raw_token)
            )
        ).scalar_one()
        assert token.used_at is not None
    finally:
        db.close()


def test_reset_password_rejects_expired_token(
    api_client: TestClient, db_factory
) -> None:
    user_id, _, _ = _seed_user(db_factory, email="expired@legalshelf.mx")
    raw_token = "expired-reset-token-for-test-123456"
    db = db_factory()
    try:
        db.add(
            PasswordResetToken(
                user_id=user_id,
                email="expired@legalshelf.mx",
                token_hash=hash_password_reset_token(raw_token),
                expires_at=utc_now() - timedelta(minutes=1),
                delivery_status="sent",
            )
        )
        db.commit()
    finally:
        db.close()

    response = api_client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "NewPassword!2026"},
    )
    assert response.status_code == 400
    assert "venció" in response.json()["detail"]
