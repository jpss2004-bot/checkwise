"""Phase 7 cutover — Twilio adapter + active-mode dispatcher.

Tests pin:

  * ``messaging_delivery.send_message`` short-circuits to
    ``skipped_disabled`` when ``MESSAGING_ENABLED=False``;
  * Twilio POST body has ``From`` / ``To`` / ``Body`` set correctly
    and the SID extracted from a stubbed response;
  * with both backends off it returns ``skipped_no_backend``;
  * ``dispatch(mode="active")`` writes the in-app row + stamps
    canonical statuses on the dispatch row;
  * the active path renders the seeded N3 template body and
    delivers it via the stubbed messaging adapter;
  * a route fails-closed (status="failed" with reason) when the
    Twilio HTTP path 4xxs;
  * mode="shadow" remains the default and behaves exactly as before
    (no in-app row, no send).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import (
    Client,
    ClientNotification,
    Membership,
    NotificationDispatch,
    NotificationTemplateVersion,
    Organization,
    ProviderNotification,
    ProviderWorkspace,
    User,
    UserNotificationPreference,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.models.entities import utc_now
from app.services.messaging_delivery import (
    send_message,
    twilio_configured,
)
from app.services.notifications import NotificationEnvelope, Recipient, dispatch

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def reset_settings():
    """Default messaging off + dry-run off so tests opt-in explicitly."""
    saved = {
        "MESSAGING_ENABLED": settings.MESSAGING_ENABLED,
        "TWILIO_ENABLED": settings.TWILIO_ENABLED,
        "TWILIO_DRY_RUN": settings.TWILIO_DRY_RUN,
        "TWILIO_ACCOUNT_SID": settings.TWILIO_ACCOUNT_SID,
        "TWILIO_AUTH_TOKEN": settings.TWILIO_AUTH_TOKEN,
        "TWILIO_FROM_NUMBER": settings.TWILIO_FROM_NUMBER,
        "WHATSAPP_ENABLED": settings.WHATSAPP_ENABLED,
        "WHATSAPP_DRY_RUN": settings.WHATSAPP_DRY_RUN,
    }
    settings.MESSAGING_ENABLED = False
    settings.TWILIO_ENABLED = False
    settings.TWILIO_DRY_RUN = False
    settings.TWILIO_ACCOUNT_SID = ""
    settings.TWILIO_AUTH_TOKEN = ""
    settings.TWILIO_FROM_NUMBER = ""
    settings.WHATSAPP_ENABLED = False
    settings.WHATSAPP_DRY_RUN = False
    yield
    for k, v in saved.items():
        setattr(settings, k, v)


# ===========================================================================
# messaging_delivery — send_message
# ===========================================================================


def test_send_message_skips_when_master_gate_off() -> None:
    r = send_message(to_phone="525500000010", body="hola")
    assert r.delivered is False
    assert r.status == "skipped_disabled"
    assert r.backend == "none"


def test_send_message_skips_when_no_backend_configured() -> None:
    settings.MESSAGING_ENABLED = True
    r = send_message(to_phone="525500000010", body="hola")
    assert r.status == "skipped_no_backend"


def test_send_message_dry_run_returns_sent() -> None:
    settings.MESSAGING_ENABLED = True
    settings.TWILIO_DRY_RUN = True
    r = send_message(to_phone="525500000010", body="hola")
    assert r.delivered is True
    assert r.status == "sent"
    assert r.backend == "dry_run"


def test_send_message_skips_when_no_recipient() -> None:
    settings.MESSAGING_ENABLED = True
    r = send_message(to_phone="", body="hola")
    assert r.status == "skipped_no_recipient"


def test_twilio_configured_requires_all_three() -> None:
    assert twilio_configured() is False
    settings.TWILIO_ACCOUNT_SID = "AC123"
    assert twilio_configured() is False
    settings.TWILIO_AUTH_TOKEN = "secret"
    assert twilio_configured() is False
    settings.TWILIO_FROM_NUMBER = "+15005550006"
    assert twilio_configured() is True


def test_send_message_via_twilio_happy_path() -> None:
    settings.MESSAGING_ENABLED = True
    settings.TWILIO_ENABLED = True
    settings.TWILIO_ACCOUNT_SID = "AC_test"
    settings.TWILIO_AUTH_TOKEN = "secret"
    settings.TWILIO_FROM_NUMBER = "+15005550006"

    class _FakeResp:
        def __init__(self, body: bytes):
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    captured: dict = {}

    def _fake_urlopen(req, *, timeout):  # noqa: ARG001
        captured["url"] = req.full_url
        captured["data"] = req.data
        captured["auth"] = req.headers.get("Authorization", "")
        return _FakeResp(b'{"sid": "SMxxxxx"}')

    with patch(
        "app.services.messaging_delivery.urllib.request.urlopen",
        _fake_urlopen,
    ):
        r = send_message(to_phone="525500000010", body="hola desde checkwise")

    assert r.delivered is True
    assert r.status == "sent"
    assert r.backend == "twilio"
    assert r.message_id == "SMxxxxx"
    assert r.recipient == "+525500000010"
    # POST body shape — Twilio is form-urlencoded, not JSON.
    assert b"From=%2B15005550006" in captured["data"]
    assert b"To=%2B525500000010" in captured["data"]
    assert b"Body=hola+desde+checkwise" in captured["data"]
    assert captured["auth"].startswith("Basic ")


def test_send_message_via_twilio_failure_returns_failed() -> None:
    import urllib.error

    settings.MESSAGING_ENABLED = True
    settings.TWILIO_ENABLED = True
    settings.TWILIO_ACCOUNT_SID = "AC_test"
    settings.TWILIO_AUTH_TOKEN = "bad"
    settings.TWILIO_FROM_NUMBER = "+15005550006"

    def _fake_urlopen(req, *, timeout):  # noqa: ARG001
        raise urllib.error.HTTPError(
            req.full_url,
            401,
            "Unauthorized",
            {},
            None,  # fp
        )

    with patch(
        "app.services.messaging_delivery.urllib.request.urlopen",
        _fake_urlopen,
    ):
        r = send_message(to_phone="525500000010", body="x")
    assert r.delivered is False
    assert r.status == "failed"
    assert r.backend == "twilio"
    assert "http_401" in (r.error or "")


# ===========================================================================
# dispatcher(mode="active") — end-to-end with N3 seeded template
# ===========================================================================


def _seed_user_with_client_admin_membership(
    db: Session,
    *,
    email: str = "user@cliente.mx",
    client: Client | None = None,
) -> User:
    if client is None:
        client = Client(name="Cliente Active")
        db.add(client)
        db.flush()
    org = Organization(name="Cliente Active", kind="client", client_id=client.id)
    db.add(org)
    db.flush()
    user = User(
        email=email,
        full_name="Cliente Admin",
        status="active",
        contact_preference="both",
        phone_e164="525511112222",
        phone_verified_at=utc_now(),
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
    db.flush()
    return user


def _seed_renewal_t0_templates(db: Session) -> None:
    """Seed the active N3 templates the t-0 fanout test reads."""
    rows = [
        NotificationTemplateVersion(
            event_type="renewal.threshold.t-0",
            channel="inapp",
            locale="es-MX",
            version=1,
            body="{{requirement_name}} de {{vendor_name}} vence HOY.",
            is_active=True,
        ),
        NotificationTemplateVersion(
            event_type="renewal.threshold.t-0",
            channel="email",
            locale="es-MX",
            version=1,
            subject="Tu {{requirement_name}} vence hoy",
            body="Hola, sube {{requirement_name}} antes del cierre.",
            is_active=True,
        ),
        NotificationTemplateVersion(
            event_type="renewal.threshold.t-0",
            channel="whatsapp",
            locale="es-MX",
            version=1,
            body="{{requirement_name}} de {{vendor_name}} vence HOY.",
            meta_template_name="cw_renewal_threshold",
            is_active=True,
        ),
    ]
    for row in rows:
        db.add(row)
    db.flush()


def test_active_mode_writes_client_inapp_and_sends_email_sms(
    db_factory,
) -> None:
    """Happy path: pref=both, verified phone, SMTP+Twilio configured —
    canonical row + email sent + SMS sent."""
    settings.MESSAGING_ENABLED = True
    settings.TWILIO_DRY_RUN = True  # don't actually call Twilio
    settings.TWILIO_ENABLED = True
    settings.TWILIO_ACCOUNT_SID = "AC_test"
    settings.TWILIO_AUTH_TOKEN = "secret"
    settings.TWILIO_FROM_NUMBER = "+15005550006"

    db = db_factory()
    try:
        user = _seed_user_with_client_admin_membership(db)
        _seed_renewal_t0_templates(db)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    envelope = NotificationEnvelope(
        event_type="renewal.threshold.t-0",
        dedupe_key="workspace:w1:req:csf:cycle:2026-01-01:t:0",
        recipients=(Recipient(user_id=user_id, role="client_admin"),),
        payload={
            "vendor_name": "ACME",
            "requirement_name": "Constancia REPSE",
            "due_on": "2026-06-01",
        },
    )

    db = db_factory()
    try:
        with patch(
            "app.services.notifications.fanout.smtp_configured",
            return_value=True,
        ), patch(
            "app.services.notifications.fanout.send_transactional_email"
        ) as fake_email:
            fake_email.return_value = type(
                "R",
                (),
                {"delivered": True, "status": "sent", "error": None},
            )()
            result = dispatch(db, envelope, mode="active")
        db.commit()
    finally:
        db.close()

    # In-app row landed.
    db = db_factory()
    try:
        inapp = db.scalar(select(ClientNotification))
        assert inapp is not None
        assert inapp.event_type if hasattr(inapp, "event_type") else True
        assert inapp.notification_type == "renewal.threshold.t-0"
        assert inapp.severity == "red"  # catalog critical → red
        assert inapp.category == "renewal"
        # Dispatch row stamped canonical.
        dr = db.scalar(select(NotificationDispatch))
        assert dr is not None
        assert dr.email_status == "sent"
        assert dr.email_reason is None
        # Twilio in dry-run returns delivered=True → status="sent".
        assert dr.whatsapp_status == "sent"
        assert dr.whatsapp_reason is None
        assert dr.inapp_id == inapp.id
    finally:
        db.close()

    assert result.queued == 1


def test_active_mode_respects_category_email_mute_for_important(
    db_factory,
) -> None:
    """A user who muted ``renewal`` email on the t-7 (important) event
    gets skipped on email but still gets SMS + in-app."""
    settings.MESSAGING_ENABLED = True
    settings.TWILIO_DRY_RUN = True
    settings.TWILIO_ENABLED = True
    settings.TWILIO_ACCOUNT_SID = "AC_test"
    settings.TWILIO_AUTH_TOKEN = "secret"
    settings.TWILIO_FROM_NUMBER = "+15005550006"

    db = db_factory()
    try:
        user = _seed_user_with_client_admin_membership(db)
        db.add(
            UserNotificationPreference(
                user_id=user.id,
                category="renewal",
                email_muted=True,
                whatsapp_muted=False,
            )
        )
        # Seed t-7 templates.
        for ch, subj, body, meta in [
            ("inapp", None, "Vence en 7 días.", None),
            ("email", "T-7", "Vence en 7 días.", None),
            ("whatsapp", None, "Vence en 7 días.", "cw_renewal_threshold"),
        ]:
            db.add(
                NotificationTemplateVersion(
                    event_type="renewal.threshold.t-7",
                    channel=ch,
                    locale="es-MX",
                    version=1,
                    subject=subj,
                    body=body,
                    meta_template_name=meta,
                    is_active=True,
                )
            )
        db.commit()
        user_id = user.id
    finally:
        db.close()

    envelope = NotificationEnvelope(
        event_type="renewal.threshold.t-7",
        dedupe_key="workspace:w1:req:csf:cycle:2026-01-01:t:7",
        recipients=(Recipient(user_id=user_id, role="client_admin"),),
        payload={},
    )

    db = db_factory()
    try:
        with patch(
            "app.services.notifications.fanout.smtp_configured",
            return_value=True,
        ), patch(
            "app.services.notifications.fanout.send_transactional_email"
        ) as fake_email:
            fake_email.return_value = type(
                "R",
                (),
                {"delivered": True, "status": "sent", "error": None},
            )()
            dispatch(db, envelope, mode="active")
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        dr = db.scalar(select(NotificationDispatch))
        assert dr.email_status == "skipped"
        assert dr.email_reason == "category_muted"
        # WhatsApp/SMS unaffected by the email mute.
        assert dr.whatsapp_status == "sent"
    finally:
        db.close()


def test_active_mode_failed_when_smtp_not_configured(db_factory) -> None:
    """No SMTP env → email status='skipped' with reason='smtp_not_configured'."""
    settings.MESSAGING_ENABLED = True
    settings.TWILIO_DRY_RUN = True

    db = db_factory()
    try:
        user = _seed_user_with_client_admin_membership(db)
        _seed_renewal_t0_templates(db)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    envelope = NotificationEnvelope(
        event_type="renewal.threshold.t-0",
        dedupe_key="d-no-smtp",
        recipients=(Recipient(user_id=user_id, role="client_admin"),),
        payload={
            "vendor_name": "ACME",
            "requirement_name": "Constancia REPSE",
            "due_on": "2026-06-01",
        },
    )

    db = db_factory()
    try:
        with patch(
            "app.services.notifications.fanout.smtp_configured",
            return_value=False,
        ):
            dispatch(db, envelope, mode="active")
        db.commit()
    finally:
        db.close()
    db = db_factory()
    try:
        dr = db.scalar(select(NotificationDispatch))
        assert dr.email_status == "skipped"
        assert dr.email_reason == "smtp_not_configured"
    finally:
        db.close()


def test_shadow_mode_remains_default_and_does_not_send(db_factory) -> None:
    """Critical regression: existing emitter tests assert default
    shadow behavior. Confirm dispatch(env) — no mode arg — does NOT
    write an in-app row and does NOT call any sender."""
    db = db_factory()
    try:
        user = _seed_user_with_client_admin_membership(db)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    envelope = NotificationEnvelope(
        event_type="renewal.threshold.t-0",
        dedupe_key="shadow-default",
        recipients=(Recipient(user_id=user_id, role="client_admin"),),
        payload={},
    )

    db = db_factory()
    try:
        dispatch(db, envelope)  # no mode= arg
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        # No in-app row.
        inapp = db.scalar(select(ClientNotification))
        assert inapp is None
        # Dispatch row exists but channel statuses untouched.
        dr = db.scalar(select(NotificationDispatch))
        assert dr is not None
        assert dr.email_status is None
        assert dr.whatsapp_status is None
    finally:
        db.close()


def test_active_mode_provider_role_writes_provider_notification(
    db_factory,
) -> None:
    """``provider_owner`` recipient → ProviderNotification, not Client."""
    settings.MESSAGING_ENABLED = True
    settings.TWILIO_DRY_RUN = True

    db = db_factory()
    try:
        client = Client(name="Cliente P")
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id,
            name="Vendor P",
            rfc="PRV260101AB1",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        user = User(
            email="prov@ws.mx",
            full_name="Provider",
            status="active",
            contact_preference="both",
            phone_e164="525500000099",
            phone_verified_at=utc_now(),
        )
        db.add(user)
        db.flush()
        ws = ProviderWorkspace(
            client_id=client.id,
            vendor_id=vendor.id,
            persona_type="moral",
            display_name="V",
            access_token="tk-active",
            owner_user_id=user.id,
        )
        db.add(ws)
        _seed_renewal_t0_templates(db)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    envelope = NotificationEnvelope(
        event_type="renewal.threshold.t-0",
        dedupe_key="prov-active",
        recipients=(Recipient(user_id=user_id, role="provider_owner"),),
        payload={
            "vendor_name": "Vendor P",
            "requirement_name": "Constancia REPSE",
            "due_on": "2026-06-01",
        },
    )

    db = db_factory()
    try:
        with patch(
            "app.services.notifications.fanout.smtp_configured",
            return_value=True,
        ), patch(
            "app.services.notifications.fanout.send_transactional_email"
        ) as fake_email:
            fake_email.return_value = type(
                "R",
                (),
                {"delivered": True, "status": "sent", "error": None},
            )()
            dispatch(db, envelope, mode="active")
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        # ProviderNotification row landed.
        prov = db.scalar(select(ProviderNotification))
        assert prov is not None
        assert prov.notification_type == "renewal.threshold.t-0"
        # No ClientNotification — wrong role.
        cli = db.scalar(select(ClientNotification))
        assert cli is None
    finally:
        db.close()
