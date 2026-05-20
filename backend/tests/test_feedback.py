"""Tests for the internal feedback endpoint.

Covers the contract that ``frontend/lib/api/feedback.ts`` relies on:

* 401 without an Authorization header.
* 422 on a too-short description (after stripping whitespace) and on
  an invalid ``type`` value.
* 415 when the screenshot is not a real PNG (magic-byte check).
* 413 when the screenshot exceeds the 5 MB cap.
* 202 + ``{ok: true, delivered: false}`` happy path with no Slack
  configured (stub mode the local dev / first-deploy state ships in).
* 429 after the per-user rate limit (10/min) is exceeded.

DB fixture mirrors ``test_contact.py`` / ``test_auth.py``: in-memory
SQLite, schema synthesised from SQLAlchemy models. We never hit a
real Slack endpoint — the endpoint's stub-mode branch is what we
exercise here (``SLACK_BOT_TOKEN`` is unset by default in
``Settings``).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Membership, Organization, User, entities  # noqa: F401
from app.services import feedback_service
from app.services.auth import hash_password, issue_access_token

# A real PNG header (8-byte magic) followed by a tiny payload. Backend
# only inspects the first 8 bytes, so anything with this prefix passes
# the format check. Tests that need an "invalid" image swap the prefix.
PNG_HEADER = b"\x89PNG\r\n\x1a\n"
TINY_PNG = PNG_HEADER + b"tiny-png-body"
NOT_A_PNG = b"GIF89a-totally-not-a-png-payload"


@pytest.fixture
def db_factory() -> Any:
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
    feedback_service._reset_rate_limiter_for_tests()  # noqa: SLF001 — test hook
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        feedback_service._reset_rate_limiter_for_tests()  # noqa: SLF001


def _seed_user_and_token(db_factory) -> str:
    """Insert an active internal_admin and return its JWT."""
    db = db_factory()
    try:
        org = Organization(name="LegalShelf", kind="internal")
        db.add(org)
        db.flush()
        user = User(
            email="qa@legalshelf.mx",
            password_hash=hash_password("Correct horse battery 4"),
            full_name="QA Tester",
            status="active",
        )
        db.add(user)
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
        return issue_access_token(
            user_id=user.id, email=user.email, roles=["internal_admin"], orgs=[org.id]
        )
    finally:
        db.close()


def _form(**overrides: str) -> dict[str, str]:
    base = {
        "type": "bug",
        "description": "El botón Guardar se queda gris al subir un PDF grande.",
        "url": "http://localhost:3000/admin/reviewer/abc",
        "path": "/admin/reviewer/abc",
        "viewport": "1512x900",
        "user_agent": "pytest",
        "console_logs": "",
    }
    base.update(overrides)
    return base


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ─── Auth ────────────────────────────────────────────────────────


def test_missing_auth_returns_401(api_client: TestClient) -> None:
    resp = api_client.post("/api/v1/feedback", data=_form())
    assert resp.status_code == 401


# ─── Validation ──────────────────────────────────────────────────


def test_short_description_returns_422(api_client: TestClient, db_factory: Any) -> None:
    token = _seed_user_and_token(db_factory)
    resp = api_client.post(
        "/api/v1/feedback",
        data=_form(description="short"),
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_whitespace_only_description_returns_422(
    api_client: TestClient, db_factory: Any
) -> None:
    token = _seed_user_and_token(db_factory)
    # 12 spaces — clears Form(min_length=10) but should fail the
    # in-handler strip check.
    resp = api_client.post(
        "/api/v1/feedback",
        data=_form(description="            "),
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_bad_type_returns_422(api_client: TestClient, db_factory: Any) -> None:
    token = _seed_user_and_token(db_factory)
    resp = api_client.post(
        "/api/v1/feedback",
        data=_form(type="flame"),
        headers=_auth(token),
    )
    assert resp.status_code == 422


# ─── Screenshot validation ───────────────────────────────────────


def test_non_png_screenshot_returns_415(
    api_client: TestClient, db_factory: Any
) -> None:
    token = _seed_user_and_token(db_factory)
    resp = api_client.post(
        "/api/v1/feedback",
        data=_form(),
        files={"screenshot": ("not-a-png.png", NOT_A_PNG, "image/png")},
        headers=_auth(token),
    )
    assert resp.status_code == 415


def test_oversized_screenshot_returns_413(
    api_client: TestClient, db_factory: Any
) -> None:
    token = _seed_user_and_token(db_factory)
    # 5 MB + 1 byte, valid PNG magic so the size check is what fires.
    payload = PNG_HEADER + b"\x00" * (5 * 1024 * 1024 + 1 - len(PNG_HEADER))
    resp = api_client.post(
        "/api/v1/feedback",
        data=_form(),
        files={"screenshot": ("big.png", payload, "image/png")},
        headers=_auth(token),
    )
    assert resp.status_code == 413


# ─── Happy path ──────────────────────────────────────────────────


def test_valid_request_returns_202_stub_mode(
    api_client: TestClient, db_factory: Any
) -> None:
    token = _seed_user_and_token(db_factory)
    resp = api_client.post(
        "/api/v1/feedback",
        data=_form(),
        files={"screenshot": ("page.png", TINY_PNG, "image/png")},
        headers=_auth(token),
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body == {"ok": True, "delivered": False}


def test_valid_request_without_screenshot_returns_202(
    api_client: TestClient, db_factory: Any
) -> None:
    token = _seed_user_and_token(db_factory)
    resp = api_client.post(
        "/api/v1/feedback",
        data=_form(type="improvement"),
        headers=_auth(token),
    )
    assert resp.status_code == 202
    assert resp.json() == {"ok": True, "delivered": False}


# ─── Rate limit ──────────────────────────────────────────────────


def test_rate_limit_kicks_in_after_ten_reports(
    api_client: TestClient, db_factory: Any
) -> None:
    token = _seed_user_and_token(db_factory)
    for _ in range(10):
        resp = api_client.post(
            "/api/v1/feedback", data=_form(), headers=_auth(token)
        )
        assert resp.status_code == 202
    # 11th should be blocked.
    blocked = api_client.post(
        "/api/v1/feedback", data=_form(), headers=_auth(token)
    )
    assert blocked.status_code == 429


# ─── Public (unauthenticated) endpoint ───────────────────────────


def _public_form(**overrides: str) -> dict[str, str]:
    """Form payload for the public endpoint — same shape minus auth."""
    base = {
        "type": "improvement",
        "description": "Sería útil mostrar el RFC en la lista de proveedores.",
        "url": "https://checkwise.mx/",
        "path": "/",
        "viewport": "1440x900",
        "user_agent": "pytest-public",
        "console_logs": "",
        "contact_email": "",
    }
    base.update(overrides)
    return base


def test_public_happy_path_returns_202_no_auth_required(
    api_client: TestClient,
) -> None:
    # No Authorization header — the public route MUST accept it.
    resp = api_client.post("/api/v1/feedback/public", data=_public_form())
    assert resp.status_code == 202
    assert resp.json() == {"ok": True, "delivered": False}


def test_public_short_description_returns_422(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/v1/feedback/public", data=_public_form(description="short")
    )
    assert resp.status_code == 422


def test_public_whitespace_only_description_returns_422(
    api_client: TestClient,
) -> None:
    resp = api_client.post(
        "/api/v1/feedback/public",
        data=_public_form(description="            "),
    )
    assert resp.status_code == 422


def test_public_bad_type_returns_422(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/v1/feedback/public", data=_public_form(type="flame")
    )
    assert resp.status_code == 422


def test_public_non_png_screenshot_returns_415(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/v1/feedback/public",
        data=_public_form(),
        files={"screenshot": ("not-a-png.png", NOT_A_PNG, "image/png")},
    )
    assert resp.status_code == 415


def test_public_oversized_screenshot_returns_413(api_client: TestClient) -> None:
    payload = PNG_HEADER + b"\x00" * (5 * 1024 * 1024 + 1 - len(PNG_HEADER))
    resp = api_client.post(
        "/api/v1/feedback/public",
        data=_public_form(),
        files={"screenshot": ("big.png", payload, "image/png")},
    )
    assert resp.status_code == 413


def test_public_rate_limit_kicks_in_after_five_reports(
    api_client: TestClient,
) -> None:
    # Pin a stable client IP so the IP-hash bucket is shared across
    # the loop (TestClient defaults to 127.0.0.1, but be explicit so
    # the test is resistant to env changes).
    headers = {"x-forwarded-for": "203.0.113.42"}
    for _ in range(5):
        resp = api_client.post(
            "/api/v1/feedback/public", data=_public_form(), headers=headers
        )
        assert resp.status_code == 202
    blocked = api_client.post(
        "/api/v1/feedback/public", data=_public_form(), headers=headers
    )
    assert blocked.status_code == 429


def test_public_accepts_optional_contact_email(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/v1/feedback/public",
        data=_public_form(contact_email="visitor@example.com"),
    )
    assert resp.status_code == 202
    assert resp.json() == {"ok": True, "delivered": False}
