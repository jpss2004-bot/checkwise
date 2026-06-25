"""Tests for the internal feedback endpoint.

Covers the contract that ``apps/web/lib/api/feedback.ts`` relies on:

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

import json
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
from app.models import FeedbackReport, Membership, Organization, User, entities  # noqa: F401
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
                role="operations_admin",
                status="active",
            )
        )
        db.commit()
        return issue_access_token(
            user_id=user.id, email=user.email, roles=["operations_admin"], orgs=[org.id]
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
    assert body["ok"] is True
    assert body["delivered"] is False
    # report_id is the persisted FeedbackReport row id (UUID v4 string).
    assert isinstance(body["report_id"], str) and len(body["report_id"]) == 36


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
    body = resp.json()
    assert body["ok"] is True
    assert body["delivered"] is False
    assert isinstance(body["report_id"], str) and len(body["report_id"]) == 36


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
    body = resp.json()
    assert body["ok"] is True
    assert body["delivered"] is False
    assert isinstance(body["report_id"], str) and len(body["report_id"]) == 36


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
    body = resp.json()
    assert body["ok"] is True
    assert body["delivered"] is False
    assert isinstance(body["report_id"], str) and len(body["report_id"]) == 36


# ─── Persistence ────────────────────────────────────────────────


def test_authenticated_submission_persists_row_with_user_identity(
    api_client: TestClient, db_factory: Any
) -> None:
    token = _seed_user_and_token(db_factory)
    resp = api_client.post("/api/v1/feedback", data=_form(), headers=_auth(token))
    assert resp.status_code == 202
    report_id = resp.json()["report_id"]

    db = db_factory()
    try:
        row = db.get(FeedbackReport, report_id)
        assert row is not None
        assert row.kind == "bug"
        assert row.source == "authenticated"
        assert row.is_public is False
        assert row.user_email == "qa@legalshelf.mx"
        assert row.user_full_name == "QA Tester"
        assert row.user_roles == "operations_admin"
        assert row.contact_email is None
        assert row.ip_hash is None
        assert row.status == "new"
        # No SLACK_BOT_TOKEN in the test env → BackgroundTask is not
        # scheduled and the endpoint marks delivery as 'skipped' so the
        # admin queue doesn't show 'pending' forever.
        assert row.slack_delivery_status == "skipped"
        assert row.slack_message_ts is None
    finally:
        db.close()


def test_public_submission_persists_row_with_ip_hash_and_no_user(
    api_client: TestClient, db_factory: Any
) -> None:
    resp = api_client.post(
        "/api/v1/feedback/public",
        data=_public_form(contact_email="visitor@example.com"),
        headers={"x-forwarded-for": "198.51.100.7"},
    )
    assert resp.status_code == 202
    report_id = resp.json()["report_id"]

    db = db_factory()
    try:
        row = db.get(FeedbackReport, report_id)
        assert row is not None
        assert row.source == "public"
        assert row.is_public is True
        assert row.user_id is None
        assert row.user_email is None
        assert row.user_roles is None
        assert row.contact_email == "visitor@example.com"
        # ip_hash is the peppered SHA-256 prefix; we don't pin the
        # exact value (it depends on AUTH_JWT_SECRET) but it must
        # exist and have the expected width.
        assert isinstance(row.ip_hash, str) and len(row.ip_hash) == 16
        assert row.slack_delivery_status == "skipped"
    finally:
        db.close()


def test_authenticated_submission_with_screenshot_stores_key_and_size(
    api_client: TestClient, db_factory: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    # Point the local storage backend at a temp dir so we can assert
    # the screenshot bytes hit disk.
    monkeypatch.setattr(
        feedback_service.settings, "LOCAL_STORAGE_PATH", str(tmp_path)
    )
    token = _seed_user_and_token(db_factory)
    resp = api_client.post(
        "/api/v1/feedback",
        data=_form(),
        files={"screenshot": ("page.png", TINY_PNG, "image/png")},
        headers=_auth(token),
    )
    assert resp.status_code == 202
    report_id = resp.json()["report_id"]

    db = db_factory()
    try:
        row = db.get(FeedbackReport, report_id)
        assert row is not None
        assert row.screenshot_storage_key == f"feedback/{report_id}/screenshot.png"
        assert row.screenshot_size_bytes == len(TINY_PNG)
        # And the bytes actually exist on disk under the temp root.
        stored = tmp_path / row.screenshot_storage_key
        assert stored.read_bytes() == TINY_PNG
    finally:
        db.close()


# ─── Admin triage endpoints ─────────────────────────────────────


def _seed_admin_token(db_factory: Any) -> str:
    """Insert an internal_admin user and return a Bearer JWT."""
    from app.constants.roles import MembershipRole
    from app.services.auth import issue_access_token

    with db_factory() as db:
        org = Organization(name="LegalShelf-Admin", kind="internal", status="active")
        db.add(org)
        db.flush()
        user = User(
            email="ops@legalshelf.mx",
            password_hash=hash_password("AdminFeedback!2026"),
            full_name="Ops Admin",
            status="active",
        )
        db.add(user)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org.id,
                role=MembershipRole.OPERATIONS_ADMIN.value,
                status="active",
            )
        )
        db.commit()
        token = issue_access_token(
            user_id=user.id,
            email=user.email,
            roles=[MembershipRole.OPERATIONS_ADMIN.value],
            orgs=[org.id],
        )
    return token


def _seed_feedback_rows(
    db_factory: Any,
    *,
    count: int = 3,
    kind: str = "bug",
    source: str = "authenticated",
    status_value: str = "new",
) -> list[str]:
    from app.models.entities import new_id, utc_now

    ids: list[str] = []
    with db_factory() as db:
        for i in range(count):
            rid = new_id()
            ids.append(rid)
            db.add(
                FeedbackReport(
                    id=rid,
                    kind=kind,
                    description=f"Seeded report {i}",
                    source=source,
                    is_public=source == "public",
                    path=f"/seeded/{i}",
                    user_email="seed@checkwise.test"
                    if source == "authenticated"
                    else None,
                    contact_email=None,
                    ip_hash="deadbeefdeadbeef" if source == "public" else None,
                    slack_delivery_status="skipped",
                    status=status_value,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            )
        db.commit()
    return ids


def test_admin_list_feedback_requires_auth(api_client: TestClient) -> None:
    resp = api_client.get("/api/v1/admin/feedback-reports")
    assert resp.status_code == 401


def test_admin_list_feedback_returns_rows_newest_first(
    api_client: TestClient, db_factory: Any
) -> None:
    token = _seed_admin_token(db_factory)
    _seed_feedback_rows(db_factory, count=3)
    resp = api_client.get(
        "/api/v1/admin/feedback-reports", headers=_auth(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert len(body["items"]) == 3
    # All seeded rows are kind=bug, source=authenticated.
    assert all(item["kind"] == "bug" for item in body["items"])
    assert all(item["source"] == "authenticated" for item in body["items"])


def test_admin_list_feedback_filters_by_kind_source_and_status(
    api_client: TestClient, db_factory: Any
) -> None:
    token = _seed_admin_token(db_factory)
    _seed_feedback_rows(db_factory, count=2, kind="bug", source="authenticated")
    _seed_feedback_rows(db_factory, count=1, kind="improvement", source="public")
    _seed_feedback_rows(
        db_factory, count=1, kind="bug", source="public", status_value="resolved"
    )

    # kind=improvement → 1
    r = api_client.get(
        "/api/v1/admin/feedback-reports?kind=improvement", headers=_auth(token)
    )
    assert r.status_code == 200
    assert r.json()["total"] == 1

    # source=public → 2 (improvement + resolved-bug)
    r = api_client.get(
        "/api/v1/admin/feedback-reports?source=public", headers=_auth(token)
    )
    assert r.status_code == 200
    assert r.json()["total"] == 2

    # status=resolved → 1
    r = api_client.get(
        "/api/v1/admin/feedback-reports?status=resolved", headers=_auth(token)
    )
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_admin_list_feedback_pagination(
    api_client: TestClient, db_factory: Any
) -> None:
    token = _seed_admin_token(db_factory)
    _seed_feedback_rows(db_factory, count=5)
    resp = api_client.get(
        "/api/v1/admin/feedback-reports?limit=2&offset=2", headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 2
    assert len(body["items"]) == 2


def test_admin_get_feedback_detail(
    api_client: TestClient, db_factory: Any
) -> None:
    token = _seed_admin_token(db_factory)
    ids = _seed_feedback_rows(db_factory, count=1)
    resp = api_client.get(
        f"/api/v1/admin/feedback-reports/{ids[0]}", headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == ids[0]
    # No storage key → no presigned URL.
    assert body["screenshot_url"] is None


def test_admin_get_feedback_404_for_missing_id(
    api_client: TestClient, db_factory: Any
) -> None:
    token = _seed_admin_token(db_factory)
    resp = api_client.get(
        "/api/v1/admin/feedback-reports/nope", headers=_auth(token)
    )
    assert resp.status_code == 404


def test_admin_patch_feedback_status_stamps_triage_and_writes_audit(
    api_client: TestClient, db_factory: Any
) -> None:
    from sqlalchemy import select

    from app.models import AuditLog

    token = _seed_admin_token(db_factory)
    ids = _seed_feedback_rows(db_factory, count=1)
    target = ids[0]

    resp = api_client.patch(
        f"/api/v1/admin/feedback-reports/{target}",
        json={"status": "triaged", "resolution_note": "Reproduced in staging"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "triaged"
    assert body["resolution_note"] == "Reproduced in staging"
    assert body["triaged_by_user_id"] is not None
    assert body["triaged_at"] is not None

    with db_factory() as db:
        audit_rows = list(
            db.scalars(
                select(AuditLog).where(
                    AuditLog.action == "admin.feedback_report.status_changed"
                )
            )
        )
        assert len(audit_rows) == 1
        assert audit_rows[0].entity_id == target
        assert audit_rows[0].before["status"] == "new"
        assert audit_rows[0].after["status"] == "triaged"


def test_admin_patch_feedback_status_rejects_invalid_value(
    api_client: TestClient, db_factory: Any
) -> None:
    token = _seed_admin_token(db_factory)
    ids = _seed_feedback_rows(db_factory, count=1)
    resp = api_client.patch(
        f"/api/v1/admin/feedback-reports/{ids[0]}",
        json={"status": "exploded"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_admin_patch_feedback_status_404_for_missing_id(
    api_client: TestClient, db_factory: Any
) -> None:
    token = _seed_admin_token(db_factory)
    resp = api_client.patch(
        "/api/v1/admin/feedback-reports/nope",
        json={"status": "resolved"},
        headers=_auth(token),
    )
    assert resp.status_code == 404


def test_admin_feedback_endpoints_reject_non_admin_token(
    api_client: TestClient, db_factory: Any
) -> None:
    """A user without the internal_admin role gets 403."""
    from app.services.auth import issue_access_token

    with db_factory() as db:
        user = User(
            email="vendor@example.com",
            password_hash=hash_password("vendor-pwd-123"),
            full_name="Vendor Demo",
            status="active",
        )
        db.add(user)
        db.commit()
        token = issue_access_token(
            user_id=user.id, email=user.email, roles=[], orgs=[]
        )

    resp = api_client.get(
        "/api/v1/admin/feedback-reports", headers=_auth(token)
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# CW-RATE-003 / CW-SLACK-001 — shared throttle + Slack escaping regressions
# ---------------------------------------------------------------------------


def test_public_record_and_check_rate_none_bypasses() -> None:
    """The unknown-IP bypass survives the shared-limiter swap."""
    for _ in range(10):
        assert feedback_service.record_and_check_public_rate(None) is True


def test_auth_and_public_limiters_are_segregated() -> None:
    """CW-RATE-003 — exhausting the authenticated bucket must not deplete
    the separate public bucket (two limiter instances)."""
    feedback_service._reset_rate_limiter_for_tests()  # noqa: SLF001
    for _ in range(_RATE := feedback_service._RATE_MAX_PER_WINDOW):  # noqa: SLF001
        assert feedback_service.record_and_check_rate("user-1") is True
    # Authenticated bucket now full…
    assert feedback_service.record_and_check_rate("user-1") is False
    # …but the public bucket is untouched.
    assert feedback_service.record_and_check_public_rate("ip-hash-abc") is True


def test_feedback_fallback_text_escapes_channel_mention() -> None:
    out = feedback_service._fallback_text(  # noqa: SLF001
        {"type": "bug", "is_public": True, "contact_email": "<!channel>", "path": "<!here>"}
    )
    assert "<!channel>" not in out
    assert "<!here>" not in out


def test_feedback_blocks_escape_path_viewport_and_link() -> None:
    blocks = feedback_service._format_blocks(  # noqa: SLF001
        {
            "type": "bug",
            "is_public": False,
            "description": "d",
            "user_email": "<!channel>@e.com",
            "user_roles": ["<!channel>"],
            "path": "/x`<!channel>`",
            "viewport": "<!here>",
            "url": "https://evil.com|<!channel>",
            "user_agent": "ua",
        }
    )
    out = json.dumps(blocks)
    assert "<!channel>" not in out
    assert "<!here>" not in out
    # The unsafe link target degraded to escaped plain text, not a live link.
    assert "<https://evil.com|" not in out
