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
