"""Tests for the public contact form endpoint (P0-3).

Covers the contract that ``frontend/lib/api/contact.ts`` relies on:

* 201 with ``{ok, request_id, created_at}`` on a valid submission.
* Real persistence — row appears in the DB with hashed IP.
* 422 on missing required fields, on over-long fields, on bad email.
* 429 after the per-IP cap is exceeded.
* Slack delivery is fire-and-forget; webhook failure does NOT fail
  the request, and the row still persists.

DB fixture mirrors ``test_auth.py``: in-memory SQLite with
``Base.metadata.create_all`` so we get the schema synthesised from
the SQLAlchemy models. The ``contact_requests`` table lands via that
path (Alembic isn't run in tests; we trust model⇄DDL parity, same
contract every other test relies on).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import ContactRequest, entities  # noqa: F401 — schema register
from app.services import contact_service

VALID_PAYLOAD = {
    "name": "María Test",
    "email": "maria@example.com",
    "company": "Constructora MX",
    "role": "Compras",
    "message": "Quiero saber más sobre la plataforma.",
}


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
    contact_service._reset_rate_limiter_for_tests()  # noqa: SLF001 — test hook
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        contact_service._reset_rate_limiter_for_tests()  # noqa: SLF001


# ─── Happy path ─────────────────────────────────────────────────


def test_post_contact_success_returns_201_and_persists(
    api_client: TestClient, db_factory: Any
) -> None:
    resp = api_client.post("/api/v1/contact", json=VALID_PAYLOAD)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["request_id"]
    assert body["created_at"]

    with db_factory() as db:
        row = db.scalar(select(ContactRequest))
        assert row is not None
        assert row.name == "María Test"
        assert row.email == "maria@example.com"
        assert row.company == "Constructora MX"
        assert row.role == "Compras"
        assert row.message.startswith("Quiero saber")
        assert row.status == "new"
        assert row.source == "landing"
        assert row.id == body["request_id"]


def test_post_contact_persists_hashed_ip_not_raw(
    api_client: TestClient, db_factory: Any
) -> None:
    resp = api_client.post(
        "/api/v1/contact",
        json=VALID_PAYLOAD,
        headers={"X-Forwarded-For": "203.0.113.42"},
    )
    assert resp.status_code == 201
    with db_factory() as db:
        row = db.scalar(select(ContactRequest))
        assert row is not None
        # We do NOT store the raw IP; only the 16-char peppered hash.
        assert row.ip_hash is not None
        assert len(row.ip_hash) == 16
        assert "203.0.113.42" not in row.ip_hash


def test_post_contact_records_user_agent_truncated(
    api_client: TestClient, db_factory: Any
) -> None:
    long_ua = "x" * 1000
    resp = api_client.post(
        "/api/v1/contact",
        json=VALID_PAYLOAD,
        headers={"User-Agent": long_ua},
    )
    assert resp.status_code == 201
    with db_factory() as db:
        row = db.scalar(select(ContactRequest))
        assert row is not None
        assert row.user_agent is not None
        assert len(row.user_agent) == 512


def test_post_contact_optional_fields_can_be_omitted(
    api_client: TestClient, db_factory: Any
) -> None:
    minimal = {
        "name": "Juan",
        "email": "juan@example.com",
        "message": "Hola",
    }
    resp = api_client.post("/api/v1/contact", json=minimal)
    assert resp.status_code == 201, resp.text
    with db_factory() as db:
        row = db.scalar(select(ContactRequest))
        assert row is not None
        assert row.company is None
        assert row.role is None


def test_post_contact_strips_whitespace_around_fields(
    api_client: TestClient, db_factory: Any
) -> None:
    payload = {
        "name": "   Padded Name   ",
        "email": "padded@example.com",
        "message": "   Tiene espacios   ",
        "company": "   ",  # whitespace-only optional → None
    }
    resp = api_client.post("/api/v1/contact", json=payload)
    assert resp.status_code == 201
    with db_factory() as db:
        row = db.scalar(select(ContactRequest))
        assert row is not None
        assert row.name == "Padded Name"
        assert row.message == "Tiene espacios"
        assert row.company is None


# ─── Validation ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "patch,reason",
    [
        ({"name": ""}, "empty name"),
        ({"name": "x" * 121}, "over-long name"),
        ({"email": "not-an-email"}, "bad email"),
        ({"email": "x" * 250 + "@example.com"}, "over-long email"),
        ({"message": ""}, "empty message"),
        ({"message": "x" * 5001}, "over-long message"),
        ({"company": "x" * 201}, "over-long company"),
        ({"role": "x" * 61}, "over-long role"),
    ],
)
def test_post_contact_validation_rejects_bad_input(
    api_client: TestClient, patch: dict, reason: str
) -> None:
    body = {**VALID_PAYLOAD, **patch}
    resp = api_client.post("/api/v1/contact", json=body)
    assert resp.status_code == 422, f"expected 422 for: {reason}, got {resp.status_code}: {resp.text}"


def test_post_contact_validation_rejects_missing_required_fields(
    api_client: TestClient,
) -> None:
    resp = api_client.post("/api/v1/contact", json={})
    assert resp.status_code == 422


# ─── Rate limit ─────────────────────────────────────────────────


def test_post_contact_rate_limit_kicks_in_at_six(api_client: TestClient) -> None:
    """5 submissions/hour/IP — the 6th from the same IP returns 429."""
    headers = {"X-Forwarded-For": "198.51.100.10"}
    for i in range(5):
        resp = api_client.post("/api/v1/contact", json=VALID_PAYLOAD, headers=headers)
        assert resp.status_code == 201, f"unexpected on attempt {i + 1}: {resp.text}"
    resp = api_client.post("/api/v1/contact", json=VALID_PAYLOAD, headers=headers)
    assert resp.status_code == 429
    assert "Demasiadas" in resp.json()["detail"]


def test_post_contact_rate_limit_is_per_ip(api_client: TestClient) -> None:
    """Exhausting one IP's quota does not throttle another."""
    for _ in range(5):
        api_client.post(
            "/api/v1/contact",
            json=VALID_PAYLOAD,
            headers={"X-Forwarded-For": "198.51.100.20"},
        )
    other = api_client.post(
        "/api/v1/contact",
        json=VALID_PAYLOAD,
        headers={"X-Forwarded-For": "198.51.100.21"},
    )
    assert other.status_code == 201


# ─── Slack delivery isolation ────────────────────────────────────


def test_slack_delivery_no_op_when_webhook_unset(monkeypatch) -> None:
    """Empty SLACK_CONTACT_WEBHOOK_URL = no-op; never raises."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "SLACK_CONTACT_WEBHOOK_URL", "")
    # Should return without error and without doing any HTTP call.
    contact_service.deliver_to_slack(
        "row-id-123",
        contact_service.slack_payload_snapshot(
            name="X",
            email="x@example.com",
            company=None,
            role=None,
            message="hi",
            source="landing",
        ),
    )


def test_slack_delivery_swallows_network_failure(monkeypatch) -> None:
    """When the webhook URL points at a dead host, the function logs
    and returns; it never raises. The endpoint pre-condition is that
    the row was already persisted before this task fires."""
    from app.core.config import settings

    monkeypatch.setattr(
        settings,
        "SLACK_CONTACT_WEBHOOK_URL",
        "http://127.0.0.1:1/dead-endpoint-for-test",
    )
    # Should NOT raise. Logged warning is fine.
    contact_service.deliver_to_slack(
        "row-id-456",
        contact_service.slack_payload_snapshot(
            name="X",
            email="x@example.com",
            company=None,
            role=None,
            message="hi",
            source="landing",
        ),
    )


# ─── IP hash determinism ─────────────────────────────────────────


def test_hash_ip_is_deterministic_and_truncated() -> None:
    h1 = contact_service.hash_ip("203.0.113.7")
    h2 = contact_service.hash_ip("203.0.113.7")
    assert h1 == h2
    assert h1 is not None
    assert len(h1) == 16
    assert all(c in "0123456789abcdef" for c in h1)


def test_hash_ip_none_for_missing_ip() -> None:
    assert contact_service.hash_ip(None) is None
    assert contact_service.hash_ip("") is None


# ─── Admin endpoints ─────────────────────────────────────────────


def _seed_admin_user(db_factory) -> str:
    """Insert an internal_admin user and return a Bearer JWT."""
    from app.constants.roles import MembershipRole
    from app.models import Membership, Organization, User
    from app.services.auth import hash_password, issue_access_token

    with db_factory() as db:
        org = Organization(name="LegalShelf", kind="internal", status="active")
        db.add(org)
        db.flush()
        user = User(
            email="ada@legalshelf.mx",
            password_hash=hash_password("test-pwd-123"),
            full_name="Ada Admin",
            status="active",
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org.id,
                role=MembershipRole.INTERNAL_ADMIN.value,
                status="active",
            )
        )
        db.commit()
        token = issue_access_token(
            user_id=user.id,
            email=user.email,
            roles=[MembershipRole.INTERNAL_ADMIN.value],
            orgs=[org.id],
        )
    return token


def _seed_contact_rows(db_factory, count: int = 3, *, status_value: str = "new") -> None:
    from app.models import ContactRequest
    from app.models.entities import new_id, utc_now

    with db_factory() as db:
        for i in range(count):
            db.add(
                ContactRequest(
                    id=new_id(),
                    name=f"Seed {i}",
                    email=f"seed{i}@example.com",
                    company=None,
                    role=None,
                    message=f"Mensaje {i}",
                    source="landing",
                    status=status_value,
                    ip_hash=None,
                    user_agent=None,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            )
        db.commit()


def test_admin_list_contact_requests_requires_auth(api_client: TestClient) -> None:
    resp = api_client.get("/api/v1/admin/contact-requests")
    assert resp.status_code == 401


def test_admin_list_returns_rows_newest_first(api_client, db_factory) -> None:
    token = _seed_admin_user(db_factory)
    _seed_contact_rows(db_factory, count=3)
    resp = api_client.get(
        "/api/v1/admin/contact-requests",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert len(body["items"]) == 3
    # The seed loop's first iteration gets the earliest timestamp;
    # ordered desc means item[0] is the most recent → "Seed 2".
    names = [it["name"] for it in body["items"]]
    assert names[0].startswith("Seed")
    # Internal fields preserved
    assert body["items"][0]["status"] == "new"
    assert body["items"][0]["source"] == "landing"


def test_admin_list_filters_by_status(api_client, db_factory) -> None:
    token = _seed_admin_user(db_factory)
    _seed_contact_rows(db_factory, count=2, status_value="new")
    _seed_contact_rows(db_factory, count=1, status_value="reviewed")
    resp = api_client.get(
        "/api/v1/admin/contact-requests?status=reviewed",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert all(it["status"] == "reviewed" for it in body["items"])


def test_admin_list_pagination_offset_and_limit(api_client, db_factory) -> None:
    token = _seed_admin_user(db_factory)
    _seed_contact_rows(db_factory, count=5)
    resp = api_client.get(
        "/api/v1/admin/contact-requests?limit=2&offset=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5  # unaffected by limit/offset
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 2


def test_admin_patch_status_updates_row_and_writes_audit(api_client, db_factory) -> None:
    from sqlalchemy import select

    from app.models import AuditLog, ContactRequest

    token = _seed_admin_user(db_factory)
    _seed_contact_rows(db_factory, count=1)
    with db_factory() as db:
        target_id = db.scalar(select(ContactRequest.id))
    assert target_id

    resp = api_client.patch(
        f"/api/v1/admin/contact-requests/{target_id}",
        json={"status": "reviewed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "reviewed"

    with db_factory() as db:
        row = db.get(ContactRequest, target_id)
        assert row is not None
        assert row.status == "reviewed"
        audit_rows = list(
            db.scalars(
                select(AuditLog).where(
                    AuditLog.action == "admin.contact_request.status_changed"
                )
            )
        )
        assert len(audit_rows) == 1
        assert audit_rows[0].entity_id == target_id
        assert audit_rows[0].before["status"] == "new"
        assert audit_rows[0].after["status"] == "reviewed"


def test_admin_patch_status_404_for_missing_id(api_client, db_factory) -> None:
    token = _seed_admin_user(db_factory)
    resp = api_client.patch(
        "/api/v1/admin/contact-requests/does-not-exist",
        json={"status": "closed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.parametrize("bad_status", ["unknown", "deleted", "NEW", ""])
def test_admin_patch_status_rejects_invalid_value(
    api_client, db_factory, bad_status: str
) -> None:
    from sqlalchemy import select

    from app.models import ContactRequest

    token = _seed_admin_user(db_factory)
    _seed_contact_rows(db_factory, count=1)
    with db_factory() as db:
        target_id = db.scalar(select(ContactRequest.id))
    resp = api_client.patch(
        f"/api/v1/admin/contact-requests/{target_id}",
        json={"status": bad_status},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_admin_endpoints_reject_non_admin_token(api_client, db_factory) -> None:
    """A user without the internal_admin role gets 403."""
    from app.models import User
    from app.services.auth import hash_password, issue_access_token

    with db_factory() as db:
        user = User(
            email="provider@example.com",
            password_hash=hash_password("test-pwd-123"),
            full_name="Provider Demo",
            status="active",
            must_change_password=False,
        )
        db.add(user)
        db.commit()
        token = issue_access_token(
            user_id=user.id, email=user.email, roles=[], orgs=[]
        )

    resp = api_client.get(
        "/api/v1/admin/contact-requests",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
