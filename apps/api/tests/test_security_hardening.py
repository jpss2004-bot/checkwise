"""Security-hardening tests (2026-05-21 remediation pass).

Covers:
  * Legacy ``POST /api/v1/submissions`` is anonymous only in local.
  * ``/api/v1/metadata-dry-run/pdf`` is anonymous only in local, and
    enforces an upload-size cap before reading the full body.
  * Portal cookie-authenticated mutations require an allowed Origin.
  * Bearer-token portal mutations bypass the Origin check.
  * Login rate limiter returns 429 once the budget is exhausted.
  * Forgot-password rate limiter returns 429.
  * API docs are disabled when ``CHECKWISE_ENV != "local"``.

All tests run in-process with TestClient. The settings cache is
mutated via ``monkeypatch.setattr`` for the duration of the test.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app, create_app
from app.models import (
    Client,
    Membership,
    Organization,
    ProviderWorkspace,
    User,
    Vendor,
    entities,  # noqa: F401
)
from app.services.auth import hash_password, issue_access_token
from app.services.portal_session import issue_portal_session_token


def _pdf_bytes() -> bytes:
    buf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture
def api_client(tmp_path) -> Generator[tuple[TestClient, sessionmaker], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    previous_storage_path = settings.LOCAL_STORAGE_PATH
    settings.LOCAL_STORAGE_PATH = str(tmp_path / "storage")

    def override_get_db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), factory
    finally:
        app.dependency_overrides.clear()
        settings.LOCAL_STORAGE_PATH = previous_storage_path


# ---------------------------------------------------------------------------
# Legacy submissions endpoint
# ---------------------------------------------------------------------------


def test_legacy_submissions_anonymous_allowed_in_local(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/api/v1/submissions",
        data={
            "client_name": "ACME",
            "vendor_name": "Proveedor",
            "vendor_rfc": "AAA010101AAA",
            "period_code": "2025-01",
            "load_type": "monthly",
            "institution_code": "imss",
            "requirement_name": "Comprobante",
        },
        files={"file": ("e.pdf", _pdf_bytes(), "application/pdf")},
    )
    # In local without auth we expect the handler to run (response is
    # 202 on success, or 422 on catalog validation — but never 401/403).
    assert response.status_code not in (401, 403), response.text


def test_legacy_submissions_anonymous_blocked_in_production(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = api_client
    monkeypatch.setattr(settings, "CHECKWISE_ENV", "production")
    response = client.post(
        "/api/v1/submissions",
        data={
            "client_name": "ACME",
            "vendor_name": "Proveedor",
            "vendor_rfc": "AAA010101AAA",
            "period_code": "2025-01",
            "load_type": "monthly",
            "institution_code": "imss",
            "requirement_name": "Comprobante",
        },
        files={"file": ("e.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 401, response.text


def test_legacy_submissions_internal_admin_allowed_in_production(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, factory = api_client
    monkeypatch.setattr(settings, "CHECKWISE_ENV", "production")
    db = factory()
    try:
        org = Organization(name="LegalShelf", kind="internal")
        db.add(org)
        db.flush()
        user = User(
            email="admin@legalshelf.mx",
            password_hash=hash_password("ignored password 12345"),
            full_name="Admin",
            status="active",
        )
        db.add(user)
        db.flush()
        membership = Membership(
            user_id=user.id,
            organization_id=org.id,
            role="operations_admin",
            status="active",
        )
        db.add(membership)
        db.commit()
        token = issue_access_token(
            user_id=user.id,
            email=user.email,
            roles=["operations_admin"],
            orgs=[org.id],
        )
    finally:
        db.close()

    response = client.post(
        "/api/v1/submissions",
        data={
            "client_name": "ACME",
            "vendor_name": "Proveedor",
            "vendor_rfc": "AAA010101AAA",
            "period_code": "2025-01",
            "load_type": "monthly",
            "institution_code": "imss",
            "requirement_name": "Comprobante",
        },
        files={"file": ("e.pdf", _pdf_bytes(), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Auth gate passes — handler runs; status comes from the handler.
    assert response.status_code not in (401, 403), response.text


# ---------------------------------------------------------------------------
# Metadata dry-run endpoint
# ---------------------------------------------------------------------------


def test_metadata_dry_run_blocked_in_production(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = api_client
    monkeypatch.setattr(settings, "CHECKWISE_ENV", "production")
    response = client.post(
        "/api/v1/metadata-dry-run/pdf",
        data={"document_type_code": "acuse_sisub"},
        files={"file": ("e.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 401, response.text


def test_metadata_dry_run_rejects_oversize_upload(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = api_client
    # Drop the cap so we don't have to ship a 15MB payload through the
    # test client just to trip the guard.
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_BYTES", 16)
    response = client.post(
        "/api/v1/metadata-dry-run/pdf",
        data={
            "document_type_code": "acuse_sisub",
            "context_json": json.dumps({}),
        },
        files={"file": ("e.pdf", b"A" * 2048, "application/pdf")},
    )
    assert response.status_code == 413, response.text


# ---------------------------------------------------------------------------
# Portal CSRF
# ---------------------------------------------------------------------------


def _seed_workspace(factory: sessionmaker) -> tuple[ProviderWorkspace, User]:
    db = factory()
    try:
        client_row = Client(name="ACME")
        vendor_row = Vendor(client=client_row, name="Proveedor", rfc="AAA010101AAA")
        user = User(
            email="proveedor@example.com",
            password_hash=hash_password("ignored-password-12345"),
            full_name="Proveedor",
            status="active",
        )
        db.add_all([client_row, vendor_row, user])
        db.flush()
        workspace = ProviderWorkspace(
            client_id=client_row.id,
            vendor_id=vendor_row.id,
            owner_user_id=user.id,
            persona_type="moral",
            filial_name=None,
            access_token="initial-access-token-not-used",
        )
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        db.refresh(user)
        return workspace, user
    finally:
        db.close()


def _mint_portal_cookie(workspace: ProviderWorkspace) -> str:
    token, _ = issue_portal_session_token(
        workspace_id=workspace.id, access_token=workspace.access_token
    )
    return token


def test_portal_post_requires_allowed_origin_in_production(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, factory = api_client
    monkeypatch.setattr(settings, "CHECKWISE_ENV", "production")
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://app.checkwise.mx")
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://app.checkwise.mx")

    workspace, _ = _seed_workspace(factory)
    cookie = _mint_portal_cookie(workspace)

    rejected = client.post(
        "/api/v1/portal/logout",
        cookies={settings.PORTAL_SESSION_COOKIE_NAME: cookie},
        headers={"Origin": "https://evil.example.com"},
    )
    assert rejected.status_code == 403, rejected.text


def test_portal_post_accepts_allowed_origin_in_production(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, factory = api_client
    monkeypatch.setattr(settings, "CHECKWISE_ENV", "production")
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://app.checkwise.mx")
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://app.checkwise.mx")

    workspace, _ = _seed_workspace(factory)
    cookie = _mint_portal_cookie(workspace)

    ok = client.post(
        "/api/v1/portal/logout",
        cookies={settings.PORTAL_SESSION_COOKIE_NAME: cookie},
        headers={"Origin": "https://app.checkwise.mx"},
    )
    assert ok.status_code == 204, ok.text


def test_portal_post_missing_origin_rejected_in_production(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, factory = api_client
    monkeypatch.setattr(settings, "CHECKWISE_ENV", "production")
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://app.checkwise.mx")
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://app.checkwise.mx")

    workspace, _ = _seed_workspace(factory)
    cookie = _mint_portal_cookie(workspace)

    rejected = client.post(
        "/api/v1/portal/logout",
        cookies={settings.PORTAL_SESSION_COOKIE_NAME: cookie},
    )
    assert rejected.status_code == 403, rejected.text


def test_portal_post_bearer_path_bypasses_origin_check(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bearer-token requests do not rely on the portal cookie and must
    not be blocked by the CSRF guard, even with an unknown Origin."""
    client, factory = api_client
    monkeypatch.setattr(settings, "CHECKWISE_ENV", "production")
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://app.checkwise.mx")
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://app.checkwise.mx")

    workspace, user = _seed_workspace(factory)
    token = issue_access_token(
        user_id=user.id, email=user.email, roles=[], orgs=[]
    )

    # No cookie attached → CSRF guard skips; bearer auth carries the
    # request the rest of the way. /portal/logout doesn't read auth,
    # so it returns 204 regardless — what matters is that we are NOT
    # 403'd by the CSRF guard.
    response = client.post(
        "/api/v1/portal/logout",
        headers={
            "Authorization": f"Bearer {token}",
            "Origin": "https://some-mobile-app.example",
        },
    )
    assert response.status_code == 204, response.text


def test_portal_get_not_affected_by_csrf_guard(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Safe methods are no-ops for the CSRF guard."""
    client, factory = api_client
    monkeypatch.setattr(settings, "CHECKWISE_ENV", "production")
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://app.checkwise.mx")
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://app.checkwise.mx")

    workspace, _ = _seed_workspace(factory)
    cookie = _mint_portal_cookie(workspace)

    # GET /portal/me with an unknown Origin must not 403 from CSRF.
    response = client.get(
        "/api/v1/portal/me",
        cookies={settings.PORTAL_SESSION_COOKIE_NAME: cookie},
        headers={"Origin": "https://evil.example.com"},
    )
    assert response.status_code != 403, response.text


# ---------------------------------------------------------------------------
# Auth rate limiting
# ---------------------------------------------------------------------------


def test_login_rate_limit_returns_429(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = api_client
    monkeypatch.setattr(settings, "AUTH_LOGIN_RATE_LIMIT_PER_MINUTE", 2)

    # First two failures eat the budget; the third trips the limiter.
    for _ in range(2):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@legalshelf.mx", "password": "wrong-password"},
        )
        assert resp.status_code == 401
    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@legalshelf.mx", "password": "wrong-password"},
    )
    assert blocked.status_code == 429, blocked.text


def test_forgot_password_rate_limit_returns_429(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = api_client
    monkeypatch.setattr(settings, "AUTH_FORGOT_PASSWORD_RATE_LIMIT_PER_HOUR", 1)

    first = client.post(
        "/api/v1/auth/forgot-password", json={"email": "target@legalshelf.mx"}
    )
    assert first.status_code == 202
    blocked = client.post(
        "/api/v1/auth/forgot-password", json={"email": "target@legalshelf.mx"}
    )
    assert blocked.status_code == 429, blocked.text


# ---------------------------------------------------------------------------
# App boot contract
# ---------------------------------------------------------------------------


def test_create_app_registers_portal_bootstrap_routes() -> None:
    route_app = create_app()
    route_pairs = {
        (method, getattr(route, "path", ""))
        for route in route_app.routes
        for method in (getattr(route, "methods", None) or set())
    }
    assert ("POST", "/api/v1/portal/enter") in route_pairs
    assert ("GET", "/api/v1/portal/me") in route_pairs

    response = TestClient(route_app).post("/api/v1/portal/enter", json={})
    assert response.status_code != 404, response.text


# ---------------------------------------------------------------------------
# API docs gating
# ---------------------------------------------------------------------------


def test_api_docs_disabled_outside_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CHECKWISE_ENV", "production")
    monkeypatch.setattr(settings, "ENABLE_API_DOCS", "")

    prod_app = create_app()
    assert prod_app.docs_url is None
    assert prod_app.redoc_url is None
    assert prod_app.openapi_url is None


def test_api_docs_force_enabled_via_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CHECKWISE_ENV", "production")
    monkeypatch.setattr(settings, "ENABLE_API_DOCS", "true")

    prod_app = create_app()
    assert prod_app.docs_url == "/docs"
    assert prod_app.openapi_url == "/openapi.json"


def test_api_docs_enabled_by_default_in_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CHECKWISE_ENV", "local")
    monkeypatch.setattr(settings, "ENABLE_API_DOCS", "")
    local_app = create_app()
    assert local_app.docs_url == "/docs"
