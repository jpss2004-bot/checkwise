"""Phase 7 / Slice N3 — versioned notification templates.

Behavior pinned at N3:

  * the seed migration lands the v1 rows for renewal + reviewer
    decisions with ``is_active=true``;
  * ``render()`` returns ``None`` when no active row exists;
  * ``render()`` performs ``{{var}}`` substitution and surfaces
    missing payload keys via :class:`MissingTemplateVariable`;
  * the admin API auto-increments the version number per
    ``(event_type, channel, locale)`` key, atomically demotes the
    prior active row when ``set_active=true``, validates
    channel-specific fields, and emits audit rows.
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
    Membership,
    NotificationTemplateVersion,
    Organization,
    User,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password, issue_access_token
from app.services.notifications import (
    MissingTemplateVariable,
    render,
)


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
def db(db_factory) -> Generator[Session, None, None]:
    session = db_factory()
    try:
        yield session
    finally:
        session.close()


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


def _seed_admin(db_factory) -> tuple[str, str]:
    db = db_factory()
    try:
        org = Organization(name="LegalShelf", kind="internal")
        db.add(org)
        db.flush()
        user = User(
            email="admin@legalshelf.mx",
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
        return user.id, issue_access_token(
            user_id=user.id,
            email=user.email,
            roles=["operations_admin"],
            orgs=[org.id],
        )
    finally:
        db.close()


def _seed_non_admin(db_factory) -> tuple[str, str]:
    db = db_factory()
    try:
        org = Organization(name="Client Co", kind="client")
        db.add(org)
        db.flush()
        user = User(
            email="user@cliente.mx",
            password_hash=hash_password("Correct horse battery 4"),
            full_name="User",
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
        return user.id, issue_access_token(
            user_id=user.id,
            email=user.email,
            roles=["client_admin"],
            orgs=[org.id],
        )
    finally:
        db.close()


def _seed_template(
    db: Session,
    *,
    event_type: str,
    channel: str,
    body: str,
    subject: str | None = None,
    meta_template_name: str | None = None,
    is_active: bool = True,
    version: int = 1,
    locale: str = "es-MX",
) -> NotificationTemplateVersion:
    row = NotificationTemplateVersion(
        event_type=event_type,
        channel=channel,
        locale=locale,
        version=version,
        subject=subject,
        body=body,
        meta_template_name=meta_template_name,
        is_active=is_active,
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# render() — pure lookup + substitution
# ---------------------------------------------------------------------------


def test_render_returns_none_when_no_active_row(db: Session) -> None:
    out = render(
        db,
        event_type="renewal.threshold.t-7",
        channel="email",
        payload={},
    )
    assert out is None


def test_render_substitutes_payload_into_body(db: Session) -> None:
    _seed_template(
        db,
        event_type="renewal.threshold.t-7",
        channel="inapp",
        body="{{requirement_name}} de {{vendor_name}} vence pronto.",
    )
    out = render(
        db,
        event_type="renewal.threshold.t-7",
        channel="inapp",
        payload={"requirement_name": "CSF", "vendor_name": "ACME"},
    )
    assert out is not None
    assert out.body == "CSF de ACME vence pronto."
    assert out.subject is None
    assert out.version == 1


def test_render_substitutes_subject_for_email(db: Session) -> None:
    _seed_template(
        db,
        event_type="renewal.threshold.t-0",
        channel="email",
        subject="Tu {{requirement_name}} vence hoy",
        body="Sube {{requirement_name}} antes del cierre.",
    )
    out = render(
        db,
        event_type="renewal.threshold.t-0",
        channel="email",
        payload={"requirement_name": "CSF"},
    )
    assert out is not None
    assert out.subject == "Tu CSF vence hoy"
    assert out.body == "Sube CSF antes del cierre."


def test_render_raises_on_missing_payload_key(db: Session) -> None:
    _seed_template(
        db,
        event_type="submission.rejected",
        channel="inapp",
        body="Tu {{requirement_name}} fue rechazado: {{reason}}.",
    )
    with pytest.raises(MissingTemplateVariable, match="reason"):
        render(
            db,
            event_type="submission.rejected",
            channel="inapp",
            payload={"requirement_name": "CSF"},
        )


def test_render_ignores_extra_payload_keys(db: Session) -> None:
    _seed_template(
        db,
        event_type="submission.approved",
        channel="inapp",
        body="Tu {{requirement_name}} fue aprobado.",
    )
    out = render(
        db,
        event_type="submission.approved",
        channel="inapp",
        payload={
            "requirement_name": "CSF",
            "vendor_name": "ACME",
            "owner_email": "secret@example.com",
        },
    )
    assert out is not None
    assert out.body == "Tu CSF fue aprobado."


def test_render_skips_inactive_versions(db: Session) -> None:
    _seed_template(
        db,
        event_type="renewal.threshold.t-0",
        channel="inapp",
        body="v1 body",
        version=1,
        is_active=False,
    )
    _seed_template(
        db,
        event_type="renewal.threshold.t-0",
        channel="inapp",
        body="v2 body",
        version=2,
        is_active=True,
    )
    out = render(
        db,
        event_type="renewal.threshold.t-0",
        channel="inapp",
        payload={},
    )
    assert out is not None
    assert out.body == "v2 body"
    assert out.version == 2


def test_render_returns_meta_template_name_for_whatsapp(db: Session) -> None:
    _seed_template(
        db,
        event_type="renewal.threshold.t-0",
        channel="whatsapp",
        body="vence hoy",
        meta_template_name="cw_renewal_threshold",
    )
    out = render(
        db,
        event_type="renewal.threshold.t-0",
        channel="whatsapp",
        payload={},
    )
    assert out is not None
    assert out.meta_template_name == "cw_renewal_threshold"


# ---------------------------------------------------------------------------
# Admin API — list / get
# ---------------------------------------------------------------------------


def test_list_templates_requires_internal_admin(
    api_client: TestClient, db_factory
) -> None:
    r_anon = api_client.get("/api/v1/admin/notification-templates")
    assert r_anon.status_code == 401

    _, non_admin_token = _seed_non_admin(db_factory)
    r_client = api_client.get(
        "/api/v1/admin/notification-templates",
        headers={"Authorization": f"Bearer {non_admin_token}"},
    )
    assert r_client.status_code == 403


def test_list_templates_returns_rows_filtered(
    api_client: TestClient, db_factory
) -> None:
    _, token = _seed_admin(db_factory)
    db = db_factory()
    try:
        _seed_template(
            db,
            event_type="renewal.threshold.t-7",
            channel="email",
            subject="s",
            body="b",
            is_active=True,
        )
        _seed_template(
            db,
            event_type="renewal.threshold.t-7",
            channel="inapp",
            body="i",
            is_active=True,
        )
        db.commit()
    finally:
        db.close()

    r = api_client.get(
        "/api/v1/admin/notification-templates?channel=email",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["channel"] == "email"


# ---------------------------------------------------------------------------
# Admin API — create
# ---------------------------------------------------------------------------


def test_create_rejects_unknown_event_type(
    api_client: TestClient, db_factory
) -> None:
    _, token = _seed_admin(db_factory)
    r = api_client.post(
        "/api/v1/admin/notification-templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "event_type": "made.up.event",
            "channel": "inapp",
            "body": "hola",
        },
    )
    assert r.status_code == 422
    assert "catálogo" in r.json()["detail"]


def test_create_rejects_email_without_subject(
    api_client: TestClient, db_factory
) -> None:
    _, token = _seed_admin(db_factory)
    r = api_client.post(
        "/api/v1/admin/notification-templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "event_type": "renewal.threshold.t-0",
            "channel": "email",
            "body": "hola",
        },
    )
    assert r.status_code == 422


def test_create_rejects_whatsapp_without_meta_name(
    api_client: TestClient, db_factory
) -> None:
    _, token = _seed_admin(db_factory)
    r = api_client.post(
        "/api/v1/admin/notification-templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "event_type": "renewal.threshold.t-0",
            "channel": "whatsapp",
            "body": "hola",
        },
    )
    assert r.status_code == 422


def test_create_rejects_subject_on_non_email(
    api_client: TestClient, db_factory
) -> None:
    _, token = _seed_admin(db_factory)
    r = api_client.post(
        "/api/v1/admin/notification-templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "event_type": "renewal.threshold.t-0",
            "channel": "inapp",
            "subject": "should not be here",
            "body": "hola",
        },
    )
    assert r.status_code == 422


def test_create_assigns_next_version(
    api_client: TestClient, db_factory
) -> None:
    _, token = _seed_admin(db_factory)
    headers = {"Authorization": f"Bearer {token}"}

    r1 = api_client.post(
        "/api/v1/admin/notification-templates",
        headers=headers,
        json={
            "event_type": "renewal.threshold.t-0",
            "channel": "inapp",
            "body": "v1",
        },
    )
    assert r1.status_code == 201
    assert r1.json()["version"] == 1
    assert r1.json()["is_active"] is False

    r2 = api_client.post(
        "/api/v1/admin/notification-templates",
        headers=headers,
        json={
            "event_type": "renewal.threshold.t-0",
            "channel": "inapp",
            "body": "v2",
        },
    )
    assert r2.status_code == 201
    assert r2.json()["version"] == 2


def test_create_with_set_active_demotes_prior_active_atomically(
    api_client: TestClient, db_factory
) -> None:
    _, token = _seed_admin(db_factory)
    headers = {"Authorization": f"Bearer {token}"}

    # Seed v1 active.
    db = db_factory()
    try:
        v1 = _seed_template(
            db,
            event_type="renewal.threshold.t-0",
            channel="inapp",
            body="v1",
            version=1,
            is_active=True,
        )
        db.commit()
        v1_id = v1.id
    finally:
        db.close()

    r = api_client.post(
        "/api/v1/admin/notification-templates",
        headers=headers,
        json={
            "event_type": "renewal.threshold.t-0",
            "channel": "inapp",
            "body": "v2",
            "set_active": True,
        },
    )
    assert r.status_code == 201
    assert r.json()["version"] == 2
    assert r.json()["is_active"] is True

    db = db_factory()
    try:
        rows = (
            db.execute(
                select(NotificationTemplateVersion).where(
                    NotificationTemplateVersion.event_type
                    == "renewal.threshold.t-0",
                    NotificationTemplateVersion.channel == "inapp",
                )
            )
            .scalars()
            .all()
        )
        by_id = {row.id: row for row in rows}
        assert by_id[v1_id].is_active is False
        active = [r for r in rows if r.is_active]
        assert len(active) == 1
        assert active[0].version == 2
    finally:
        db.close()


def test_create_writes_audit_row(
    api_client: TestClient, db_factory
) -> None:
    admin_id, token = _seed_admin(db_factory)
    r = api_client.post(
        "/api/v1/admin/notification-templates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "event_type": "renewal.threshold.t-0",
            "channel": "inapp",
            "body": "v1",
        },
    )
    assert r.status_code == 201
    template_id = r.json()["id"]

    db = db_factory()
    try:
        row = db.execute(
            select(AuditLog).where(
                AuditLog.action == "admin.notification_template.created",
                AuditLog.entity_id == template_id,
            )
        ).scalar_one()
        assert row.actor_id == admin_id
        assert row.actor_type == "operations_admin"
        assert (row.after or {}).get("event_type") == "renewal.threshold.t-0"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Admin API — activate
# ---------------------------------------------------------------------------


def test_activate_demotes_prior_active(
    api_client: TestClient, db_factory
) -> None:
    _, token = _seed_admin(db_factory)
    db = db_factory()
    try:
        v1 = _seed_template(
            db,
            event_type="renewal.threshold.t-0",
            channel="inapp",
            body="v1",
            version=1,
            is_active=True,
        )
        v2 = _seed_template(
            db,
            event_type="renewal.threshold.t-0",
            channel="inapp",
            body="v2",
            version=2,
            is_active=False,
        )
        db.commit()
        v1_id, v2_id = v1.id, v2.id
    finally:
        db.close()

    r = api_client.post(
        f"/api/v1/admin/notification-templates/{v2_id}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is True

    db = db_factory()
    try:
        v1_after = db.get(NotificationTemplateVersion, v1_id)
        v2_after = db.get(NotificationTemplateVersion, v2_id)
        assert v1_after is not None and v1_after.is_active is False
        assert v2_after is not None and v2_after.is_active is True
    finally:
        db.close()


def test_activate_is_idempotent_on_already_active(
    api_client: TestClient, db_factory
) -> None:
    _, token = _seed_admin(db_factory)
    db = db_factory()
    try:
        v1 = _seed_template(
            db,
            event_type="renewal.threshold.t-0",
            channel="inapp",
            body="v1",
            version=1,
            is_active=True,
        )
        db.commit()
        v1_id = v1.id
    finally:
        db.close()

    r = api_client.post(
        f"/api/v1/admin/notification-templates/{v1_id}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is True

    # Idempotent → no audit row written.
    db = db_factory()
    try:
        rows = (
            db.execute(
                select(AuditLog).where(
                    AuditLog.action == "admin.notification_template.activated"
                )
            )
            .scalars()
            .all()
        )
        assert rows == []
    finally:
        db.close()


def test_activate_404_when_missing(
    api_client: TestClient, db_factory
) -> None:
    _, token = _seed_admin(db_factory)
    r = api_client.post(
        "/api/v1/admin/notification-templates/does-not-exist/activate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
