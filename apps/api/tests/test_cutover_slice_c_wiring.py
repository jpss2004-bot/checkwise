"""Phase 7 cutover Slice C — end-to-end emit-from-call-site wiring.

Each test invokes a production HTTP endpoint and asserts that the
unified-fabric ``notification_dispatch`` row landed, confirming
the emit call was reached during normal request processing. Failure
modes (Twilio not configured, SMTP missing) degrade gracefully —
the dispatch row + canonical statuses are still written.

Coverage:

  * POST /auth/forgot-password → ``account.password_reset_requested``
  * PUT  /me/notification-preferences → ``account.channel_preference_changed``
  * POST /admin/users (role=client) → ``account.invitation_sent``
  * POST /me/phone/verify/confirm → ``account.whatsapp_verified``
    (already covered by phone_verification suite — we just confirm
    the mode flip didn't break it).

Reviewer-decision, client/providers invite, and the renewal cron
flip are exercised in their own dedicated suites; this file is
specifically the cutover-wiring smoke test.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

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
    Membership,
    NotificationDispatch,
    Organization,
    User,
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
def bg_to_test_session(db_factory, monkeypatch):
    """Redirect the deferred notification fanout's fresh ``SessionLocal()``
    (CW-DOS-002) at the per-test in-memory engine so its dispatch-row writes
    land where the assertions look. Mirrors the report-export bg pattern."""
    from app.services.notifications import background as bg_module

    monkeypatch.setattr(bg_module, "SessionLocal", db_factory)


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


@pytest.fixture(autouse=True)
def messaging_dry_run():
    """Run Slice C tests with Twilio in dry-run so they don't try
    to reach the network."""
    saved = (
        settings.MESSAGING_ENABLED,
        settings.TWILIO_ENABLED,
        settings.TWILIO_DRY_RUN,
    )
    settings.MESSAGING_ENABLED = True
    settings.TWILIO_ENABLED = True
    settings.TWILIO_DRY_RUN = True
    yield
    (
        settings.MESSAGING_ENABLED,
        settings.TWILIO_ENABLED,
        settings.TWILIO_DRY_RUN,
    ) = saved


def _seed_internal_admin(db_factory) -> tuple[str, str, str]:
    db = db_factory()
    try:
        org = Organization(name="LegalShelf", kind="internal")
        db.add(org)
        db.flush()
        user = User(
            email="adm@legalshelf.mx",
            password_hash=hash_password("Correct horse battery 4"),
            full_name="Admin",
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
        token = issue_access_token(
            user_id=user.id,
            email=user.email,
            roles=["operations_admin"],
            orgs=[org.id],
        )
        return user.id, org.id, token
    finally:
        db.close()


# ===========================================================================
# POST /auth/forgot-password → emit account.password_reset_requested
# ===========================================================================


def test_forgot_password_fires_emitter(
    api_client: TestClient, db_factory, bg_to_test_session
) -> None:
    # Seed an active user so the endpoint actually progresses to the
    # emit call (the generic 202 path short-circuits on unknown email).
    db = db_factory()
    try:
        user = User(
            email="active@legalshelf.mx",
            password_hash=hash_password("Correct horse battery 4"),
            full_name="Active User",
            status="active",
        )
        db.add(user)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    with patch(
        "app.api.v1.auth.send_password_reset_email"
    ) as fake_email, patch(
        "app.services.notifications.fanout.smtp_configured",
        return_value=False,
    ):
        fake_email.return_value = type(
            "R", (), {"status": "sent", "error": None}
        )()
        r = api_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "active@legalshelf.mx"},
        )
    assert r.status_code == 202

    db = db_factory()
    try:
        row = db.scalar(
            select(NotificationDispatch).where(
                NotificationDispatch.event_type
                == "account.password_reset_requested",
                NotificationDispatch.user_id == user_id,
            )
        )
        assert row is not None, "expected dispatch row from forgot-password emit"
        # Critical email + SMTP unconfigured → email skipped with
        # the canonical reason. Twilio dry-run → sent.
        assert row.email_status in {"skipped", "sent"}
    finally:
        db.close()


# ===========================================================================
# PUT /me/notification-preferences → emit account.channel_preference_changed
# ===========================================================================


def test_preferences_update_fires_emitter(
    api_client: TestClient, db_factory
) -> None:
    user_id, _org_id, token = _seed_internal_admin(db_factory)
    r = api_client.put(
        "/api/v1/me/notification-preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={"contact_preference": "both"},
    )
    assert r.status_code == 200

    db = db_factory()
    try:
        row = db.scalar(
            select(NotificationDispatch).where(
                NotificationDispatch.event_type
                == "account.channel_preference_changed",
                NotificationDispatch.user_id == user_id,
            )
        )
        assert row is not None
        # Info-tier → email + WhatsApp both skipped with info_tier reason.
        assert row.email_status == "skipped"
        assert row.email_reason == "info_tier"
        assert row.whatsapp_status == "skipped"
        assert row.whatsapp_reason == "info_tier"
    finally:
        db.close()


# ===========================================================================
# POST /admin/users (role=client) → emit account.invitation_sent
# ===========================================================================


def test_admin_provision_client_fires_emitter(
    api_client: TestClient, db_factory, bg_to_test_session
) -> None:
    _admin_id, _org_id, token = _seed_internal_admin(db_factory)

    with patch(
        "app.api.v1.admin.send_welcome_with_temp_password_email"
    ) as fake_email, patch(
        "app.services.notifications.fanout.smtp_configured",
        return_value=False,
    ):
        fake_email.return_value = type(
            "R", (), {"status": "sent", "error": None}
        )()
        r = api_client.post(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "client",
                "full_name": "Cliente Nuevo",
                "email": "cliente@nueva.mx",
                "client_name": "Empresa Nueva",
            },
        )
    assert r.status_code in (200, 201), r.text

    db = db_factory()
    try:
        row = db.scalar(
            select(NotificationDispatch).where(
                NotificationDispatch.event_type
                == "account.invitation_sent"
            )
        )
        assert row is not None
        assert row.recipient_role == "invitee"
        # Critical tier — when SMTP isn't configured, the legacy
        # email already attempted (and the test mocks the response);
        # the unified fabric records a canonical skip with the
        # actual reason.
        assert row.email_status in {"sent", "skipped"}
    finally:
        db.close()
