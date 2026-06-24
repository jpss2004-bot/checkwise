"""Phase 7 / Slice N2 — /api/v1/me/notification-preferences endpoint.

GET returns the full category matrix with defaults materialized
for any category the user has not overridden. PUT updates
``contact_preference`` and upserts category rows, keeping the
underlying table sparse (default-default rows are not persisted).
Auth required on both verbs.
"""

from __future__ import annotations

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
    Organization,
    User,
    UserNotificationPreference,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password, issue_access_token


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


def _seed_user(db_factory, *, email: str = "user@legalshelf.mx") -> tuple[str, str]:
    """Returns (user_id, bearer_token)."""
    db = db_factory()
    try:
        org = Organization(name="LegalShelf", kind="internal")
        db.add(org)
        db.flush()
        user = User(
            email=email,
            password_hash=hash_password("Correct horse battery 4"),
            full_name="Test User",
            status="active",
        )
        db.add(user)
        db.commit()
        token = issue_access_token(
            user_id=user.id, email=user.email, roles=["operations_admin"], orgs=[org.id]
        )
        return user.id, token
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/v1/me/notification-preferences
# ---------------------------------------------------------------------------


def test_get_requires_auth(api_client: TestClient) -> None:
    r = api_client.get("/api/v1/me/notification-preferences")
    assert r.status_code == 401


def test_get_returns_full_matrix_with_defaults_when_no_overrides(
    api_client: TestClient, db_factory
) -> None:
    _, token = _seed_user(db_factory)
    r = api_client.get(
        "/api/v1/me/notification-preferences",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["contact_preference"] == "email"  # User default
    assert body["phone_e164"] is None
    assert body["phone_verified"] is False
    assert body["whatsapp_opt_in_at"] is None
    cats = {row["category"]: row for row in body["categories"]}
    assert set(cats.keys()) == {
        "renewal",
        "reporting",
        "verification",
        "account",
        "admin",
    }
    for row in cats.values():
        assert row["email_muted"] is False
        assert row["whatsapp_muted"] is False


def test_get_returns_user_overrides(
    api_client: TestClient, db_factory
) -> None:
    user_id, token = _seed_user(db_factory)
    db = db_factory()
    try:
        db.add(
            UserNotificationPreference(
                user_id=user_id,
                category="reporting",
                email_muted=True,
                whatsapp_muted=False,
            )
        )
        db.commit()
    finally:
        db.close()

    r = api_client.get(
        "/api/v1/me/notification-preferences",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    cats = {row["category"]: row for row in r.json()["categories"]}
    assert cats["reporting"]["email_muted"] is True
    assert cats["reporting"]["whatsapp_muted"] is False
    # Other categories still report defaults.
    assert cats["renewal"]["email_muted"] is False


# ---------------------------------------------------------------------------
# PUT /api/v1/me/notification-preferences
# ---------------------------------------------------------------------------


def test_put_requires_auth(api_client: TestClient) -> None:
    r = api_client.put(
        "/api/v1/me/notification-preferences",
        json={"contact_preference": "both"},
    )
    assert r.status_code == 401


def test_put_updates_contact_preference(
    api_client: TestClient, db_factory
) -> None:
    _, token = _seed_user(db_factory)
    r = api_client.put(
        "/api/v1/me/notification-preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={"contact_preference": "both"},
    )
    assert r.status_code == 200
    assert r.json()["contact_preference"] == "both"


def test_put_rejects_invalid_contact_preference(
    api_client: TestClient, db_factory
) -> None:
    _, token = _seed_user(db_factory)
    r = api_client.put(
        "/api/v1/me/notification-preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={"contact_preference": "telegram"},
    )
    assert r.status_code == 422


def test_put_upserts_category_overrides(
    api_client: TestClient, db_factory
) -> None:
    user_id, token = _seed_user(db_factory)
    r = api_client.put(
        "/api/v1/me/notification-preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "categories": [
                {"category": "renewal", "email_muted": False, "whatsapp_muted": True},
                {"category": "reporting", "email_muted": True, "whatsapp_muted": True},
            ]
        },
    )
    assert r.status_code == 200
    cats = {row["category"]: row for row in r.json()["categories"]}
    assert cats["renewal"]["whatsapp_muted"] is True
    assert cats["reporting"]["email_muted"] is True
    assert cats["reporting"]["whatsapp_muted"] is True

    # Persisted in DB.
    db = db_factory()
    try:
        rows = (
            db.execute(
                select(UserNotificationPreference).where(
                    UserNotificationPreference.user_id == user_id
                )
            )
            .scalars()
            .all()
        )
        assert {row.category for row in rows} == {"renewal", "reporting"}
    finally:
        db.close()


def test_put_does_not_insert_default_rows(
    api_client: TestClient, db_factory
) -> None:
    """Sparse-table discipline: posting an all-false row when no
    override exists must not persist a useless row."""
    user_id, token = _seed_user(db_factory)
    r = api_client.put(
        "/api/v1/me/notification-preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "categories": [
                {"category": "renewal", "email_muted": False, "whatsapp_muted": False},
            ]
        },
    )
    assert r.status_code == 200

    db = db_factory()
    try:
        rows = (
            db.execute(
                select(UserNotificationPreference).where(
                    UserNotificationPreference.user_id == user_id
                )
            )
            .scalars()
            .all()
        )
        assert rows == []
    finally:
        db.close()


def test_put_writes_audit_event(api_client: TestClient, db_factory) -> None:
    user_id, token = _seed_user(db_factory)
    api_client.put(
        "/api/v1/me/notification-preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={"contact_preference": "whatsapp"},
    )
    db = db_factory()
    try:
        row = db.execute(
            select(AuditLog).where(
                AuditLog.action == "user.notification_preferences_updated",
                AuditLog.entity_id == user_id,
            )
        ).scalar_one()
        assert row.actor_type == "user"
        assert row.actor_id == user_id
        assert (row.before or {}).get("contact_preference") == "email"
        assert (row.after or {}).get("contact_preference") == "whatsapp"
    finally:
        db.close()
