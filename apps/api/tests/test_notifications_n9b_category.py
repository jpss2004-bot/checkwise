"""Phase 7 / Slice N9b — category column + bell-badge math.

Tests pin:

  * ``derive_category`` maps every legacy ``notification_type``
    prefix the codebase uses today to a Phase 7 category;
  * ``add_client_notification`` / ``add_provider_notification``
    populate ``category`` at insert time without the caller
    threading it through;
  * the ``client_notifications`` GET response carries ``category``
    on every item and exposes ``unread_actionable_count`` alongside
    the existing ``unread_count``;
  * ``unread_actionable_count`` counts ONLY ``red`` + ``yellow``
    unread rows — info-tier unreads never inflate the bell.
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
from app.models import (
    Client,
    ClientNotification,
    Membership,
    Organization,
    ProviderNotification,
    ProviderWorkspace,
    User,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password, issue_access_token
from app.services.client_notifications import add_client_notification
from app.services.notifications.categorize import derive_category
from app.services.provider_notifications import add_provider_notification

# ===========================================================================
# derive_category — pure function
# ===========================================================================


@pytest.mark.parametrize(
    "notification_type,expected",
    [
        ("renewal_due_soon", "renewal"),
        ("renewal_overdue", "renewal"),
        ("renewal.threshold.t-0", "renewal"),
        ("reporting.window.opened", "reporting"),
        ("reporting.due.t-7", "reporting"),
        ("document_approve", "verification"),
        ("document_reject", "verification"),
        ("submission.approved", "verification"),
        ("submission.received", "verification"),
        ("provider_uploaded", "verification"),
        ("metadata_ready", "verification"),
        ("account.welcome", "account"),
        ("account.invitation_sent", "account"),
        ("admin.cron_health", "admin"),
        ("admin.workspace_at_risk", "admin"),
        ("support.ticket_opened", "admin"),
        ("absolutely_unknown", "other"),
        ("", "other"),
    ],
)
def test_derive_category(notification_type: str, expected: str) -> None:
    assert derive_category(notification_type) == expected


# ===========================================================================
# Insert-time category population
# ===========================================================================


@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_add_client_notification_sets_category(db_factory) -> None:
    db = db_factory()
    try:
        client = Client(name="Cliente Cat")
        db.add(client)
        db.flush()
        add_client_notification(
            db,
            client_id=client.id,
            notification_type="renewal_due_soon",
            severity="yellow",
            title="x",
            body="y",
        )
        add_client_notification(
            db,
            client_id=client.id,
            notification_type="document_approve",
            severity="green",
            title="x",
            body="y",
        )
        db.commit()
        rows = (
            db.query(ClientNotification)
            .order_by(ClientNotification.notification_type)
            .all()
        )
        cats = {r.notification_type: r.category for r in rows}
    finally:
        db.close()
    assert cats == {
        "document_approve": "verification",
        "renewal_due_soon": "renewal",
    }


def test_add_provider_notification_sets_category(db_factory) -> None:
    db = db_factory()
    try:
        client = Client(name="Cliente Cat P")
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id, name="V", rfc="VND260101AB1", persona_type="moral"
        )
        db.add(vendor)
        db.flush()
        ws = ProviderWorkspace(
            client_id=client.id,
            vendor_id=vendor.id,
            persona_type="moral",
            display_name="V",
            access_token="tk",
        )
        db.add(ws)
        db.flush()
        add_provider_notification(
            db,
            workspace_id=ws.id,
            notification_type="document_reject",
            severity="red",
            title="x",
            body="y",
        )
        add_provider_notification(
            db,
            workspace_id=ws.id,
            notification_type="renewal_overdue",
            severity="red",
            title="x",
            body="y",
        )
        db.commit()
        cats = {
            r.notification_type: r.category
            for r in db.query(ProviderNotification).all()
        }
    finally:
        db.close()
    assert cats == {
        "document_reject": "verification",
        "renewal_overdue": "renewal",
    }


# ===========================================================================
# API: client GET /notifications carries category + actionable count
# ===========================================================================


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


def _seed_client_admin(db_factory) -> tuple[str, str]:
    """Return ``(client_id, bearer_token)`` for an active client_admin."""
    db = db_factory()
    try:
        client = Client(name="Cliente N9b")
        db.add(client)
        db.flush()
        org = Organization(name="Cliente N9b", kind="client", client_id=client.id)
        db.add(org)
        db.flush()
        user = User(
            email="admin@n9b.mx",
            password_hash=hash_password("Correct horse battery 4"),
            full_name="Admin N9b",
            status="active",
        )
        db.add(user)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org.id,
                role="client_admin",
                status="active",
            )
        )
        db.commit()
        token = issue_access_token(
            user_id=user.id,
            email=user.email,
            roles=["client_admin"],
            orgs=[org.id],
        )
        return client.id, token
    finally:
        db.close()


def _seed_rows(db_factory, *, client_id: str) -> None:
    """One row per severity, all unread."""
    db = db_factory()
    try:
        for nt, sev in [
            ("renewal_overdue", "red"),
            ("renewal_due_soon", "yellow"),
            ("document_approve", "green"),
            ("provider_uploaded", "info"),
        ]:
            add_client_notification(
                db,
                client_id=client_id,
                notification_type=nt,
                severity=sev,
                title=nt,
                body=nt,
            )
        db.commit()
    finally:
        db.close()


def test_list_response_carries_category_per_item(
    api_client: TestClient, db_factory
) -> None:
    client_id, token = _seed_client_admin(db_factory)
    _seed_rows(db_factory, client_id=client_id)
    r = api_client.get(
        "/api/v1/client/notifications",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    by_type = {item["notification_type"]: item["category"] for item in body["items"]}
    assert by_type == {
        "renewal_overdue": "renewal",
        "renewal_due_soon": "renewal",
        "document_approve": "verification",
        "provider_uploaded": "verification",
    }


def test_actionable_count_excludes_info_and_green(
    api_client: TestClient, db_factory
) -> None:
    """Bell math: only red+yellow unread inflate the actionable count."""
    client_id, token = _seed_client_admin(db_factory)
    _seed_rows(db_factory, client_id=client_id)

    list_r = api_client.get(
        "/api/v1/client/notifications",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_r.json()["unread_count"] == 4
    assert list_r.json()["unread_actionable_count"] == 2  # red + yellow only

    summary_r = api_client.get(
        "/api/v1/client/notifications/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert summary_r.status_code == 200
    assert summary_r.json()["unread_count"] == 4
    assert summary_r.json()["unread_actionable_count"] == 2


def test_read_all_zeros_both_counters(
    api_client: TestClient, db_factory
) -> None:
    client_id, token = _seed_client_admin(db_factory)
    _seed_rows(db_factory, client_id=client_id)
    r = api_client.post(
        "/api/v1/client/notifications/read-all",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["unread_count"] == 0
    assert body["unread_actionable_count"] == 0
