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
    role: str = "operations_admin",
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
        user_id="u1", email="x@y.mx", roles=["operations_admin"], orgs=["o1"]
    )
    claims = decode_access_token(token)
    assert claims.user_id == "u1"
    assert claims.email == "x@y.mx"
    assert claims.roles == ("operations_admin",)
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
    assert payload["roles"] == ["operations_admin"]
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
    assert payload["roles"] == ["operations_admin"]
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


_AdminDep = Annotated[CurrentUser, Depends(require_role("operations_admin"))]
_ReviewerDep = Annotated[CurrentUser, Depends(require_role("platform_admin"))]
_OrgAdminDep = Annotated[CurrentUser, Depends(require_org_role("operations_admin"))]


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


# ---------------------------------------------------------------------------
# Audit findings 1, 2, 3 — auth hardening (2026-05-26 follow-up)
# ---------------------------------------------------------------------------


def test_login_persists_last_login_at(
    api_client: TestClient, db_factory
) -> None:
    """Audit finding #1 — the login handler used to ``db.flush()`` the
    ``last_login_at`` update without committing. ``get_db`` closes the
    session without an implicit commit, so the column silently rolled
    back to NULL. This test pins the explicit commit by re-reading the
    User row in a fresh session AFTER login and asserting the column
    is populated."""
    _seed_user(db_factory, email="lastlogin@legalshelf.mx")

    response = api_client.post(
        "/api/v1/auth/login",
        json={
            "email": "lastlogin@legalshelf.mx",
            "password": "Correct horse battery 4",
        },
    )
    assert response.status_code == 200, response.text

    db = db_factory()
    try:
        row = db.execute(
            select(User).where(User.email == "lastlogin@legalshelf.mx")
        ).scalar_one()
        # The bug would leave this as None forever despite the in-memory
        # update succeeding within the request.
        assert row.last_login_at is not None
    finally:
        db.close()


def test_set_password_rejects_weak_passwords(
    api_client: TestClient, db_factory
) -> None:
    """Audit finding #2 — the backend used to validate only
    ``min_length=12``; a caller bypassing the UI could land a password
    the official rules would have rejected (e.g., all-lowercase with
    no digit). The new validator mirrors the frontend ``PASSWORD_RULES``
    so every entry path enforces the same contract."""
    _, _, password = _seed_user(db_factory)
    token = _login(api_client, "ada@legalshelf.mx", password)

    weak_cases = [
        # 12 chars but lowercase-only (no uppercase, no digit)
        "aaaaaaaaaaaa",
        # 12 chars but uppercase + digit, no lowercase
        "AAAAAAAAAA11",
        # No digit
        "Aaaaaaaaaaaa",
        # No uppercase
        "aaaaaaaaaaa1",
    ]
    for pw in weak_cases:
        response = api_client.post(
            "/api/v1/auth/set-password",
            json={"new_password": pw},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422, (
            f"weak password '{pw}' should be rejected with 422"
        )


def test_reset_password_rejects_weak_passwords(
    api_client: TestClient, db_factory
) -> None:
    """Audit finding #2 (mirror of the set-password test) — same
    validator must guard the reset-password endpoint. Without it, a
    user with a fresh reset link could bypass the frontend rules via
    curl and persist a 12-char-all-lowercase password."""
    user_id, _, _ = _seed_user(db_factory, email="weak-reset@legalshelf.mx")
    raw_token = "weak-reset-token-for-test-1234567890"
    db = db_factory()
    try:
        db.add(
            PasswordResetToken(
                user_id=user_id,
                email="weak-reset@legalshelf.mx",
                token_hash=hash_password_reset_token(raw_token),
                expires_at=utc_now() + timedelta(minutes=30),
                delivery_status="sent",
            )
        )
        db.commit()
    finally:
        db.close()
    response = api_client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "aaaaaaaaaaaa"},
    )
    assert response.status_code == 422


def test_generate_temp_password_satisfies_password_rules() -> None:
    """Audit finding #3 — the temp-password generator used to be a
    pure random draw against the curated alphabet, which had a ~11%
    chance of producing a 14-char password with no digit. After the
    fix, every draw is guaranteed to contain at least one uppercase,
    one lowercase, and one digit so the recipient can flow through
    /activate using the same rules the UI enforces.

    Run the generator 200 times and assert every output satisfies
    the full rule set + is the requested length.
    """
    from app.services.auth import generate_temp_password

    for _ in range(200):
        pw = generate_temp_password()
        assert len(pw) == 14
        assert any(c.isupper() for c in pw), pw
        assert any(c.islower() for c in pw), pw
        assert any(c.isdigit() for c in pw), pw


def test_generate_temp_password_rejects_lengths_under_minimum() -> None:
    """The frontend rule set requires 12 chars. The generator MUST
    refuse to produce anything shorter — a caller asking for a 10-char
    temp password would silently land a value the recipient could not
    use to change their password through the official UI."""
    from app.services.auth import generate_temp_password

    with pytest.raises(ValueError):
        generate_temp_password(length=8)


# ---------------------------------------------------------------------------
# Audit-finding #5 — token-preview endpoint
# ---------------------------------------------------------------------------


def test_reset_password_preview_returns_email_for_valid_token(
    api_client: TestClient, db_factory
) -> None:
    """Audit finding #5 — ``GET /auth/reset-password/preview?token=...``
    returns the email the token was issued to. Lets /reset-password
    render "Cambiando contraseña de X" so the user can verify the
    target account before typing a new password (key when the same
    machine has multiple CheckWise accounts)."""
    user_id, _, _ = _seed_user(
        db_factory, email="preview-ok@legalshelf.mx"
    )
    raw_token = "preview-ok-token-1234567890ab"
    db = db_factory()
    try:
        db.add(
            PasswordResetToken(
                user_id=user_id,
                email="preview-ok@legalshelf.mx",
                token_hash=hash_password_reset_token(raw_token),
                expires_at=utc_now() + timedelta(minutes=30),
                delivery_status="sent",
            )
        )
        db.commit()
    finally:
        db.close()
    response = api_client.get(
        f"/api/v1/auth/reset-password/preview?token={raw_token}"
    )
    assert response.status_code == 200, response.text
    assert response.json()["email"] == "preview-ok@legalshelf.mx"


def test_reset_password_preview_rejects_unknown_token(
    api_client: TestClient,
) -> None:
    """Unknown tokens 400 with the same generic copy the POST handler
    uses — no oracle that distinguishes "never existed" from "used"
    from "expired"."""
    response = api_client.get(
        "/api/v1/auth/reset-password/preview?token=does-not-exist-anywhere"
    )
    assert response.status_code == 400
    assert "válido" in response.json()["detail"]


def test_reset_password_preview_rejects_used_token(
    api_client: TestClient, db_factory
) -> None:
    """A consumed token must not leak its associated email — the
    preview path mirrors the POST guard against ``used_at``."""
    user_id, _, _ = _seed_user(
        db_factory, email="preview-used@legalshelf.mx"
    )
    raw_token = "preview-used-token-1234567890"
    db = db_factory()
    try:
        db.add(
            PasswordResetToken(
                user_id=user_id,
                email="preview-used@legalshelf.mx",
                token_hash=hash_password_reset_token(raw_token),
                expires_at=utc_now() + timedelta(minutes=30),
                used_at=utc_now() - timedelta(minutes=5),
                delivery_status="sent",
            )
        )
        db.commit()
    finally:
        db.close()
    response = api_client.get(
        f"/api/v1/auth/reset-password/preview?token={raw_token}"
    )
    assert response.status_code == 400


def test_reset_password_preview_rejects_expired_token(
    api_client: TestClient, db_factory
) -> None:
    user_id, _, _ = _seed_user(
        db_factory, email="preview-expired@legalshelf.mx"
    )
    raw_token = "preview-expired-token-12345678"
    db = db_factory()
    try:
        db.add(
            PasswordResetToken(
                user_id=user_id,
                email="preview-expired@legalshelf.mx",
                token_hash=hash_password_reset_token(raw_token),
                expires_at=utc_now() - timedelta(minutes=1),
                delivery_status="sent",
            )
        )
        db.commit()
    finally:
        db.close()
    response = api_client.get(
        f"/api/v1/auth/reset-password/preview?token={raw_token}"
    )
    assert response.status_code == 400
    assert "venció" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Audit-finding #10 — password-history reuse prevention
# ---------------------------------------------------------------------------


def test_set_password_rejects_reuse_of_current_password(
    api_client: TestClient, db_factory
) -> None:
    """Audit finding #10 — the user cannot ``set-password`` to the
    same password they already have. The history check includes the
    current hash so this works even before any prior change has
    populated the password_history table."""
    _, _, password = _seed_user(db_factory, email="reuse-current@legalshelf.mx")
    token = _login(api_client, "reuse-current@legalshelf.mx", password)

    response = api_client.post(
        "/api/v1/auth/set-password",
        json={"new_password": password},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    assert "reutilizar" in response.json()["detail"]


def test_set_password_rejects_reuse_of_recent_password(
    api_client: TestClient, db_factory
) -> None:
    """The reuse check covers the rolling history, not just the
    current hash. Set password A → set password B → trying to set
    back to A within the depth window must 422."""
    from app.services.auth import PASSWORD_HISTORY_DEPTH

    _, _, original = _seed_user(
        db_factory, email="reuse-recent@legalshelf.mx"
    )
    token = _login(api_client, "reuse-recent@legalshelf.mx", original)

    # Rotate the password ``PASSWORD_HISTORY_DEPTH`` times so the
    # original lands inside the retained window but not at the top.
    intermediate = [f"Rotated{i}Password!{2026 + i}" for i in range(
        PASSWORD_HISTORY_DEPTH
    )]
    for pw in intermediate:
        response = api_client.post(
            "/api/v1/auth/set-password",
            json={"new_password": pw},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text
        # Re-login with the new password to refresh the token (each
        # change clears must_change_password but the existing JWT
        # stays valid; we log in fresh here to keep the test linear).
        token = _login(
            api_client, "reuse-recent@legalshelf.mx", pw
        )

    # Now try the original — within the retained depth, must reject.
    response = api_client.post(
        "/api/v1/auth/set-password",
        json={"new_password": original},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_password_history_trims_to_configured_depth(
    api_client: TestClient, db_factory
) -> None:
    """The history table must not grow unbounded. After more than
    ``PASSWORD_HISTORY_DEPTH`` changes, the oldest rows are pruned
    so the lookup stays cheap."""
    from app.models import PasswordHistory
    from app.services.auth import PASSWORD_HISTORY_DEPTH

    user_id, _, password = _seed_user(
        db_factory, email="trim-history@legalshelf.mx"
    )
    token = _login(api_client, "trim-history@legalshelf.mx", password)

    for i in range(PASSWORD_HISTORY_DEPTH + 3):
        pw = f"Rotation{i}Password!{2026 + i}"
        response = api_client.post(
            "/api/v1/auth/set-password",
            json={"new_password": pw},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text
        token = _login(api_client, "trim-history@legalshelf.mx", pw)

    db = db_factory()
    try:
        retained = list(
            db.scalars(
                select(PasswordHistory).where(PasswordHistory.user_id == user_id)
            )
        )
        # The depth is the rolling cap; the implementation may keep
        # exactly depth or depth+1 rows depending on whether the
        # latest insert counts toward the cap. Assert the strict
        # ceiling so a future drift gets caught.
        assert len(retained) <= PASSWORD_HISTORY_DEPTH
    finally:
        db.close()


def test_reset_password_rejects_reuse(
    api_client: TestClient, db_factory
) -> None:
    """The history check also runs on the /reset-password path —
    not just the authenticated /set-password flow. A user who
    requests a fresh reset link cannot set their password back to
    what it used to be either."""
    user_id, _, password = _seed_user(
        db_factory, email="reuse-reset@legalshelf.mx"
    )
    raw_token = "reuse-reset-token-for-test-12345"
    db = db_factory()
    try:
        db.add(
            PasswordResetToken(
                user_id=user_id,
                email="reuse-reset@legalshelf.mx",
                token_hash=hash_password_reset_token(raw_token),
                expires_at=utc_now() + timedelta(minutes=30),
                delivery_status="sent",
            )
        )
        db.commit()
    finally:
        db.close()

    response = api_client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": password},
    )
    assert response.status_code == 422
    assert "reutilizar" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Hardening pass (2026-05-26) — set-password audit coverage
# ---------------------------------------------------------------------------


def test_set_password_writes_audit_event(
    api_client: TestClient, db_factory
) -> None:
    """The /set-password endpoint backs the /activate forced-first-
    login flow. Without an audit row, the most material action on an
    account (initial password set + must-change-password clear) would
    leave no forensic trace. The /reset-password endpoint already
    writes ``auth.password_reset_completed``; this test pins the
    parallel ``auth.password_changed`` row for the set-password path."""
    from app.models import AuditLog

    user_id, _, password = _seed_user(
        db_factory, email="audit-set-pw@legalshelf.mx"
    )
    token = _login(api_client, "audit-set-pw@legalshelf.mx", password)
    response = api_client.post(
        "/api/v1/auth/set-password",
        json={"new_password": "BrandNewPassword!2026"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text

    db = db_factory()
    try:
        row = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "auth.password_changed")
            .where(AuditLog.entity_id == user_id)
        )
        assert row is not None
        after = row.after or {}
        assert after.get("email") == "audit-set-pw@legalshelf.mx"
        assert after.get("source") == "set_password"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Account lockout (platform rework follow-up) — threshold = 5 by default
# ---------------------------------------------------------------------------


def _attempt_login(api_client: TestClient, email: str, password: str):
    """Returns the raw login response — distinct from the module's earlier
    ``_login`` helper, which returns just the token string."""
    return api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )


def test_account_locks_after_threshold_failed_logins(
    api_client: TestClient, db_factory
) -> None:
    # Enumeration-safety change (2026-06-21): the lockout is still enforced
    # in the DB (locked_until is set, and even the correct password is
    # refused during the cooldown), but login now returns the SAME generic
    # 401 "Credenciales inválidas." for locked accounts as for unknown /
    # bad-password ones — a distinct 429 lockout message was a 401-vs-429
    # account-enumeration oracle (only an existing active account can lock).
    # So we assert the lock is invisible at the HTTP layer (all 401) and
    # verify the lock is real by checking locked_until in the DB.
    user_id, _org, _pw = _seed_user(db_factory, password="Correct horse battery 4")
    # Four bad attempts stay generic 401…
    for _ in range(4):
        r = _attempt_login(api_client, "ada@legalshelf.mx", "nope")
        assert r.status_code == 401, r.text
    # …the fifth trips the lock — still a generic 401, no 429 / "bloqueada".
    fifth = _attempt_login(api_client, "ada@legalshelf.mx", "nope")
    assert fifth.status_code == 401
    assert "bloqueada" not in fifth.json()["detail"].lower()
    # The lock is real even though it isn't surfaced: locked_until is set.
    db = db_factory()
    try:
        assert db.get(User, user_id).locked_until is not None
    finally:
        db.close()
    # Even the CORRECT password is refused during the cooldown — and the
    # refusal is the same generic 401 (no lockout oracle).
    correct = _attempt_login(
        api_client, "ada@legalshelf.mx", "Correct horse battery 4"
    )
    assert correct.status_code == 401


def test_expired_lock_allows_login(api_client: TestClient, db_factory) -> None:
    user_id, _org, pw = _seed_user(db_factory)
    db = db_factory()
    try:
        u = db.get(User, user_id)
        u.locked_until = utc_now() - timedelta(minutes=1)  # already elapsed
        u.failed_login_count = 0
        db.commit()
    finally:
        db.close()
    r = _attempt_login(api_client, "ada@legalshelf.mx", pw)
    assert r.status_code == 200, r.text


def test_successful_login_resets_failed_count(
    api_client: TestClient, db_factory
) -> None:
    user_id, _org, pw = _seed_user(db_factory)
    for _ in range(2):
        assert (
            _attempt_login(api_client, "ada@legalshelf.mx", "nope").status_code
            == 401
        )
    assert _attempt_login(api_client, "ada@legalshelf.mx", pw).status_code == 200
    db = db_factory()
    try:
        assert db.get(User, user_id).failed_login_count == 0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# FIX 3 — cross-IP per-email login rate cap (anti-spray)
# ---------------------------------------------------------------------------


def test_login_cross_ip_per_email_cap_trips(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spraying ONE account from many (spoofed) source IPs must eventually
    trip the cross-IP per-email bucket, even though no single (ip,email)
    pair exceeds its tighter cap. Calls the limiter helper directly with
    fake requests carrying rotating rightmost XFF hops so we exercise the
    bucket logic without bcrypt / DB work."""
    from fastapi import HTTPException

    from app.api.v1.auth import _enforce_login_rate_limit
    from app.core.config import settings as cfg
    from app.core.rate_limit import login_limiter

    login_limiter.reset()
    limit = cfg.AUTH_LOGIN_RATE_LIMIT_PER_MINUTE  # default 10
    email_cap = limit * 5  # cross-IP per-email cap

    def _req_with_ip(ip: str):
        class _Req:
            headers = {"x-forwarded-for": ip}
            client = None

        return _Req()

    # Each request uses a DISTINCT rightmost IP (so the per-(ip,email) and
    # per-IP buckets never fill) but the SAME email — only the per-email
    # bucket accumulates. The (email_cap+1)-th request trips.
    for i in range(email_cap):
        _enforce_login_rate_limit(
            _req_with_ip(f"203.0.113.{i}"), "spray@legalshelf.mx"
        )
    with pytest.raises(HTTPException) as exc:
        _enforce_login_rate_limit(
            _req_with_ip(f"203.0.113.{email_cap}"), "spray@legalshelf.mx"
        )
    assert exc.value.status_code == 429
    login_limiter.reset()


# ---------------------------------------------------------------------------
# FE-SEC-1 — httpOnly session-cookie foundation
# ---------------------------------------------------------------------------


def test_login_sets_session_cookie(api_client: TestClient, db_factory) -> None:
    """Login deposits the JWT in the httpOnly session cookie (carrying the
    same token the body returns) so the frontend can move off localStorage."""
    _, _, password = _seed_user(db_factory)
    resp = api_client.post(
        "/api/v1/auth/login",
        json={"email": "ada@legalshelf.mx", "password": password},
    )
    assert resp.status_code == 200, resp.text
    assert settings.AUTH_SESSION_COOKIE_NAME in resp.cookies
    assert (
        resp.cookies[settings.AUTH_SESSION_COOKIE_NAME]
        == resp.json()["access_token"]
    )


def test_me_authenticates_via_cookie_without_header(
    api_client: TestClient, db_factory
) -> None:
    """get_current_user falls back to the session cookie when no
    Authorization header is present (the frontend-cutover path)."""
    _, _, password = _seed_user(db_factory)
    login = api_client.post(
        "/api/v1/auth/login",
        json={"email": "ada@legalshelf.mx", "password": password},
    )
    assert login.status_code == 200
    # TestClient persists the Set-Cookie; deliberately send NO header.
    resp = api_client.get("/api/v1/auth/me")
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["email"] == "ada@legalshelf.mx"


def test_logout_clears_session_cookie(api_client: TestClient, db_factory) -> None:
    """Logout returns 204 and emits a deletion Set-Cookie for the session."""
    _, _, password = _seed_user(db_factory)
    api_client.post(
        "/api/v1/auth/login",
        json={"email": "ada@legalshelf.mx", "password": password},
    )
    out = api_client.post("/api/v1/auth/logout")
    assert out.status_code == 204
    set_cookie = " ".join(out.headers.get_list("set-cookie")).lower()
    assert settings.AUTH_SESSION_COOKIE_NAME in set_cookie
    assert "max-age=0" in set_cookie or 'session=""' in set_cookie
