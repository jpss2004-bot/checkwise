"""Wise copilot — analytics endpoint coverage.

Verifies the ``POST /api/v1/portal/workspaces/{id}/wise/events``
endpoint introduced in Phase 1 of the Wise copilot rollout:

* Accepts a known ``event_type`` and persists a row.
* Rejects unknown event types with a 400.
* Enforces the same tenant guard as every other portal endpoint —
  user B cannot record events against user A's workspace.

The fixture reuses the same in-memory SQLite + JWT-mint setup the
dashboard test file uses; we copy the minimal version here so the
file is self-contained.
"""

from __future__ import annotations

import itertools
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Client,
    ProviderWorkspace,
    User,
    Vendor,
    WiseEvent,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password, issue_access_token

_user_seq = itertools.count(start=1)


@pytest.fixture
def api_client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    previous = settings.LOCAL_STORAGE_PATH
    settings.LOCAL_STORAGE_PATH = str(tmp_path / "storage")

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.app.state.testing_session = testing_session  # type: ignore[attr-defined]
    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        settings.LOCAL_STORAGE_PATH = previous


def _setup_workspace(
    api_client: TestClient,
    *,
    vendor_name: str = "Servicios Wise SA",
    vendor_rfc: str = "WIS260512AB1",
    client_name: str = "Cliente Wise Demo",
    fresh_client: TestClient | None = None,
) -> dict:
    target_client = fresh_client or api_client
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        seq = next(_user_seq)
        user = User(
            email=f"wise-{seq}@checkwise.test",
            password_hash=hash_password("CheckWiseTest!2026"),
            full_name=vendor_name,
            status="active",
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        client_row = db.query(Client).filter_by(name=client_name).first()
        if client_row is None:
            client_row = Client(name=client_name)
            db.add(client_row)
            db.flush()
        vendor = Vendor(
            client_id=client_row.id,
            name=vendor_name,
            rfc=vendor_rfc.upper(),
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        workspace = ProviderWorkspace(
            client_id=client_row.id,
            vendor_id=vendor.id,
            owner_user_id=user.id,
            persona_type="moral",
            display_name=vendor_name,
            access_token="placeholder",
        )
        db.add(workspace)
        db.commit()
        ws_id, user_id, user_email = workspace.id, user.id, user.email
    finally:
        db.close()

    token = issue_access_token(user_id=user_id, email=user_email, roles=[], orgs=[])
    target_client.cookies.clear()
    enter = target_client.post(
        "/api/v1/portal/enter",
        json={"workspace_id": ws_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert enter.status_code == 200, enter.text
    return {"workspace_id": ws_id, "bearer": token, "user_id": user_id}


def test_wise_event_persists_known_event_type(api_client: TestClient) -> None:
    ws = _setup_workspace(api_client)
    response = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/wise/events",
        json={
            "event_type": "wise.opened",
            "payload": {"trigger": "fab"},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["event_type"] == "wise.opened"
    assert body["id"]
    # Parse the ISO timestamp to confirm it's well-formed.
    from datetime import datetime

    datetime.fromisoformat(body["occurred_at"])

    # Row persisted with the expected workspace + user + payload.
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        row = db.scalar(select(WiseEvent).where(WiseEvent.id == body["id"]))
        assert row is not None
        assert row.workspace_id == ws["workspace_id"]
        assert row.user_id == ws["user_id"]
        assert row.event_type == "wise.opened"
        assert row.payload == {"trigger": "fab"}
    finally:
        db.close()


def test_wise_event_rejects_unknown_event_type(api_client: TestClient) -> None:
    ws = _setup_workspace(api_client)
    response = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/wise/events",
        json={"event_type": "wise.totally_made_up", "payload": None},
    )
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "Unknown event_type" in detail


def test_wise_event_rejects_foreign_workspace(api_client: TestClient) -> None:
    """User B cannot record events against user A's workspace."""
    ws_a = _setup_workspace(api_client)
    fresh = TestClient(api_client.app)
    fresh.app.state.testing_session = api_client.app.state.testing_session  # type: ignore[attr-defined]
    ws_b = _setup_workspace(
        api_client,
        vendor_name="Otro Wise SA",
        vendor_rfc="OTH260512AB1",
        fresh_client=fresh,
    )

    cross = fresh.post(
        f"/api/v1/portal/workspaces/{ws_a['workspace_id']}/wise/events",
        json={"event_type": "wise.opened", "payload": None},
        headers={"Authorization": f"Bearer {ws_b['bearer']}"},
    )
    assert cross.status_code == 403


def test_wise_event_accepts_all_known_event_types(api_client: TestClient) -> None:
    """The five Phase-1 event types should all round-trip cleanly."""
    ws = _setup_workspace(api_client)
    expected = {
        "wise.first_render",
        "wise.opened",
        "wise.collapsed",
        "wise.suggestion_clicked",
        "wise.suggestion_dismissed",
    }
    for event_type in expected:
        response = api_client.post(
            f"/api/v1/portal/workspaces/{ws['workspace_id']}/wise/events",
            json={"event_type": event_type, "payload": None},
        )
        assert response.status_code == 201, response.text
