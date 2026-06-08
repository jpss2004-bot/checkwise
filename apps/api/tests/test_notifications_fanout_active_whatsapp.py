"""Phase 7 reverse cutover — active-mode WhatsApp dispatch.

The fanout's ``_send_messaging_if_eligible`` ships an
``whatsapp_components=None`` payload by default — that's the SMS-first
cutover plan. When the operator flips
``WHATSAPP_NATIVE_TEMPLATES_ENABLED=true``, the fanout builds the
per-event Meta template ``components`` array using the builders in
:mod:`app.services.whatsapp_templates` and dispatches via the
WhatsApp Cloud API. These tests pin the new dispatch table, the
flag gate, and the audit-trail invariants the operator needs.

Coverage matrix:

    1. Flag OFF                       → components=None, Twilio path.
    2. Flag ON, renewal event         → cw_renewal_threshold built,
                                        Meta backend selected.
    3. Flag ON, decision event        → cw_reviewer_decision built,
                                        reviewer_name defaults to
                                        "Legal Shelf".
    4. Flag ON, unmapped event        → components=None, Twilio path
                                        (reporting + invitation
                                        events fall through).
    5. Meta template_not_found        → whatsapp_status=failed,
                                        NO Twilio fallback.
    6. Meta returns success           → whatsapp_status=sent.
    7. User without verified phone    → skipped/phone_not_verified,
                                        no send.
    8. Category muted (important)     → skipped/category_muted.
    9. Critical event with WA muted   → email still fires.
   10. Audit row written for Meta path only.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import (
    AuditLog,
    Client,
    Membership,
    NotificationDispatch,
    NotificationTemplateVersion,
    Organization,
    User,
    UserNotificationPreference,
    entities,  # noqa: F401 — register mappers
)
from app.models.entities import utc_now
from app.services.messaging_delivery import MessageDeliveryResult
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
def _reset_settings():
    saved = {
        "MESSAGING_ENABLED": settings.MESSAGING_ENABLED,
        "TWILIO_ENABLED": settings.TWILIO_ENABLED,
        "TWILIO_DRY_RUN": settings.TWILIO_DRY_RUN,
        "WHATSAPP_ENABLED": settings.WHATSAPP_ENABLED,
        "WHATSAPP_DRY_RUN": settings.WHATSAPP_DRY_RUN,
        "WHATSAPP_NATIVE_TEMPLATES_ENABLED": (
            settings.WHATSAPP_NATIVE_TEMPLATES_ENABLED
        ),
    }
    settings.MESSAGING_ENABLED = True
    settings.TWILIO_ENABLED = False
    settings.TWILIO_DRY_RUN = False
    settings.WHATSAPP_ENABLED = True
    settings.WHATSAPP_DRY_RUN = False
    settings.WHATSAPP_NATIVE_TEMPLATES_ENABLED = False
    yield
    for k, v in saved.items():
        setattr(settings, k, v)


def _seed_user(db, *, email: str = "u@cliente.mx") -> User:
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


def _seed_renewal_t0_templates(db) -> None:
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


def _seed_decision_templates(db) -> None:
    rows = [
        NotificationTemplateVersion(
            event_type="submission.approved",
            channel="inapp",
            locale="es-MX",
            version=1,
            body="{{vendor_name}}: {{requirement_name}} aprobado.",
            is_active=True,
        ),
        NotificationTemplateVersion(
            event_type="submission.approved",
            channel="email",
            locale="es-MX",
            version=1,
            subject="Documento aprobado",
            body="{{requirement_name}} aprobado.",
            is_active=True,
        ),
        NotificationTemplateVersion(
            event_type="submission.approved",
            channel="whatsapp",
            locale="es-MX",
            version=1,
            body="{{requirement_name}} aprobado.",
            meta_template_name="cw_reviewer_decision",
            is_active=True,
        ),
    ]
    for row in rows:
        db.add(row)
    db.flush()


def _renewal_envelope(user_id: str) -> NotificationEnvelope:
    return NotificationEnvelope(
        event_type="renewal.threshold.t-0",
        dedupe_key=f"renewal-{user_id}",
        recipients=(Recipient(user_id=user_id, role="client_admin"),),
        payload={
            "vendor_name": "ACME",
            "requirement_name": "Constancia REPSE",
            "due_on": "2026-06-01",
            "days_remaining": 0,
        },
    )


def _decision_envelope(user_id: str) -> NotificationEnvelope:
    return NotificationEnvelope(
        event_type="submission.approved",
        dedupe_key=f"decision-{user_id}",
        recipients=(Recipient(user_id=user_id, role="client_admin"),),
        payload={
            "vendor_name": "ACME",
            "requirement_name": "Declaración IVA",
        },
    )


def _stub_email(returns_sent: bool = True):
    """Stub the email leg so tests focus on the messaging leg only."""

    class _R:
        delivered = returns_sent
        status = "sent" if returns_sent else "failed"
        error = None

    return _R()


# ---------------------------------------------------------------------------
# 1. Flag OFF — components stays None, Twilio path engaged
# ---------------------------------------------------------------------------


def test_flag_off_passes_none_components_to_send_message(db_factory) -> None:
    settings.WHATSAPP_NATIVE_TEMPLATES_ENABLED = False

    db = db_factory()
    try:
        user = _seed_user(db)
        _seed_renewal_t0_templates(db)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    captured: dict = {}

    def _fake_send_message(**kwargs):
        captured.update(kwargs)
        return MessageDeliveryResult(
            delivered=True, status="sent", backend="twilio"
        )

    db = db_factory()
    try:
        with patch(
            "app.services.notifications.fanout.smtp_configured",
            return_value=True,
        ), patch(
            "app.services.notifications.fanout.send_transactional_email",
            return_value=_stub_email(),
        ), patch(
            "app.services.notifications.fanout.send_message",
            side_effect=_fake_send_message,
        ):
            dispatch(db, _renewal_envelope(user_id), mode="active")
        db.commit()
    finally:
        db.close()

    assert captured["whatsapp_components"] is None
    # Template name still surfaces — it's the rendered row's
    # meta_template_name even on the SMS path, useful for logging.
    assert captured["whatsapp_template_name"] == "cw_renewal_threshold"


# ---------------------------------------------------------------------------
# 2. Flag ON, renewal event — cw_renewal_threshold components built
# ---------------------------------------------------------------------------


def test_flag_on_renewal_builds_native_components(db_factory) -> None:
    settings.WHATSAPP_NATIVE_TEMPLATES_ENABLED = True

    db = db_factory()
    try:
        user = _seed_user(db)
        _seed_renewal_t0_templates(db)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    captured: dict = {}

    def _fake_send_message(**kwargs):
        captured.update(kwargs)
        return MessageDeliveryResult(
            delivered=True,
            status="sent",
            backend="whatsapp",
            message_id="wamid.test123",
        )

    db = db_factory()
    try:
        with patch(
            "app.services.notifications.fanout.smtp_configured",
            return_value=True,
        ), patch(
            "app.services.notifications.fanout.send_transactional_email",
            return_value=_stub_email(),
        ), patch(
            "app.services.notifications.fanout.send_message",
            side_effect=_fake_send_message,
        ):
            dispatch(db, _renewal_envelope(user_id), mode="active")
        db.commit()
    finally:
        db.close()

    assert captured["whatsapp_template_name"] == "cw_renewal_threshold"
    components = captured["whatsapp_components"]
    assert components is not None
    assert len(components) == 1
    body = components[0]
    assert body["type"] == "body"
    params = [p["text"] for p in body["parameters"]]
    # {{1}} vendor, {{2}} requirement, {{3}} due date, {{4}} severity hint
    assert params[0] == "ACME"
    assert params[1] == "Constancia REPSE"
    assert params[2] == "01/06/2026"
    # t-0 is catalog "critical" → severity label "Vencido" with vence hoy hint
    assert "Vencido" in params[3] and "hoy" in params[3]


# ---------------------------------------------------------------------------
# 3. Flag ON, decision event — cw_reviewer_decision built with default reviewer
# ---------------------------------------------------------------------------


def test_flag_on_decision_builds_with_default_reviewer(db_factory) -> None:
    settings.WHATSAPP_NATIVE_TEMPLATES_ENABLED = True

    db = db_factory()
    try:
        user = _seed_user(db)
        _seed_decision_templates(db)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    captured: dict = {}

    def _fake_send_message(**kwargs):
        captured.update(kwargs)
        return MessageDeliveryResult(
            delivered=True, status="sent", backend="whatsapp"
        )

    db = db_factory()
    try:
        with patch(
            "app.services.notifications.fanout.smtp_configured",
            return_value=True,
        ), patch(
            "app.services.notifications.fanout.send_transactional_email",
            return_value=_stub_email(),
        ), patch(
            "app.services.notifications.fanout.send_message",
            side_effect=_fake_send_message,
        ):
            dispatch(db, _decision_envelope(user_id), mode="active")
        db.commit()
    finally:
        db.close()

    assert captured["whatsapp_template_name"] == "cw_reviewer_decision"
    params = [p["text"] for p in captured["whatsapp_components"][0]["parameters"]]
    # {{1}} vendor, {{2}} requirement, {{3}} action, {{4}} reviewer
    assert params[0] == "ACME"
    assert params[1] == "Declaración IVA"
    assert params[2] == "Aprobado"
    assert params[3] == "Legal Shelf"  # default per kickoff decision


# ---------------------------------------------------------------------------
# 4. Flag ON, unmapped event (reporting) — components=None, SMS fallthrough
# ---------------------------------------------------------------------------


def test_flag_on_unmapped_event_falls_through_to_sms(db_factory) -> None:
    settings.WHATSAPP_NATIVE_TEMPLATES_ENABLED = True

    db = db_factory()
    try:
        user = _seed_user(db)
        # Reporting events have NO native builder today; the fanout
        # must leave components=None so messaging_delivery routes to
        # the Twilio SMS path. Catalog allows client_admin on the
        # ``reporting.due.t-0`` critical event, which keeps the test
        # focused on the dispatch table without provider-workspace
        # plumbing.
        for ch, subj, body, meta in [
            ("inapp", None, "Reporte vence", None),
            ("email", "Reporte", "Reporte vence", None),
            ("whatsapp", None, "Reporte vence", "cw_reporting_window"),
        ]:
            db.add(
                NotificationTemplateVersion(
                    event_type="reporting.due.t-0",
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

    captured: dict = {}

    def _fake_send_message(**kwargs):
        captured.update(kwargs)
        return MessageDeliveryResult(
            delivered=True, status="sent", backend="twilio"
        )

    envelope = NotificationEnvelope(
        event_type="reporting.due.t-0",
        dedupe_key=f"reporting-cli-{user_id}",
        recipients=(Recipient(user_id=user_id, role="client_admin"),),
        payload={
            "vendor_name": "ACME",
            "requirement_name": "IMSS SUA",
            "period_label": "junio 2026",
            "due_on": "2026-06-17",
            "days_remaining": 0,
        },
    )

    db = db_factory()
    try:
        with patch(
            "app.services.notifications.fanout.smtp_configured",
            return_value=True,
        ), patch(
            "app.services.notifications.fanout.send_transactional_email",
            return_value=_stub_email(),
        ), patch(
            "app.services.notifications.fanout.send_message",
            side_effect=_fake_send_message,
        ):
            dispatch(db, envelope, mode="active")
        db.commit()
    finally:
        db.close()

    # Unmapped event → components remains None; messaging_delivery
    # routes to Twilio per its WhatsApp gate (requires non-None).
    assert captured["whatsapp_components"] is None


# ---------------------------------------------------------------------------
# 5. Meta returns failure — dispatch row stamped failed; no Twilio fallback
# ---------------------------------------------------------------------------


def test_meta_failure_stamps_failed_with_no_fallback(db_factory) -> None:
    settings.WHATSAPP_NATIVE_TEMPLATES_ENABLED = True

    db = db_factory()
    try:
        user = _seed_user(db)
        _seed_renewal_t0_templates(db)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    call_count = {"n": 0}

    def _fake_send_message(**kwargs):
        call_count["n"] += 1
        # Meta path returned a template_not_found error. We expect
        # the fanout to stamp ``failed`` and NOT retry via Twilio.
        return MessageDeliveryResult(
            delivered=False,
            status="failed",
            backend="whatsapp",
            error='http_400: {"error":{"code":132001,"message":"Template name does not exist in this language"}}',
        )

    db = db_factory()
    try:
        with patch(
            "app.services.notifications.fanout.smtp_configured",
            return_value=True,
        ), patch(
            "app.services.notifications.fanout.send_transactional_email",
            return_value=_stub_email(),
        ), patch(
            "app.services.notifications.fanout.send_message",
            side_effect=_fake_send_message,
        ):
            dispatch(db, _renewal_envelope(user_id), mode="active")
        db.commit()
    finally:
        db.close()

    # Exactly one outbound attempt — no fallback retry.
    assert call_count["n"] == 1

    db = db_factory()
    try:
        dr = db.scalar(select(NotificationDispatch))
        assert dr.whatsapp_status == "failed"
        assert "132001" in (dr.whatsapp_reason or "")
        # Email leg still fired for the critical event.
        assert dr.email_status == "sent"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 6. Meta success — dispatch row stamped sent
# ---------------------------------------------------------------------------


def test_meta_success_stamps_sent(db_factory) -> None:
    settings.WHATSAPP_NATIVE_TEMPLATES_ENABLED = True

    db = db_factory()
    try:
        user = _seed_user(db)
        _seed_renewal_t0_templates(db)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    def _fake_send_message(**kwargs):
        return MessageDeliveryResult(
            delivered=True,
            status="sent",
            backend="whatsapp",
            message_id="wamid.OK",
        )

    db = db_factory()
    try:
        with patch(
            "app.services.notifications.fanout.smtp_configured",
            return_value=True,
        ), patch(
            "app.services.notifications.fanout.send_transactional_email",
            return_value=_stub_email(),
        ), patch(
            "app.services.notifications.fanout.send_message",
            side_effect=_fake_send_message,
        ):
            dispatch(db, _renewal_envelope(user_id), mode="active")
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        dr = db.scalar(select(NotificationDispatch))
        assert dr.whatsapp_status == "sent"
        assert dr.whatsapp_reason is None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 7. User without verified phone — skipped/phone_not_verified, no send
# ---------------------------------------------------------------------------


def test_unverified_phone_skips_messaging(db_factory) -> None:
    settings.WHATSAPP_NATIVE_TEMPLATES_ENABLED = True

    db = db_factory()
    try:
        client = Client(name="Cliente NP")
        db.add(client)
        db.flush()
        org = Organization(name="Cliente NP", kind="client", client_id=client.id)
        db.add(org)
        db.flush()
        user = User(
            email="np@cliente.mx",
            full_name="No Phone",
            status="active",
            contact_preference="both",
            phone_e164=None,
            phone_verified_at=None,
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
        _seed_renewal_t0_templates(db)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    called = {"n": 0}

    def _fake_send_message(**kwargs):
        called["n"] += 1
        return MessageDeliveryResult(
            delivered=True, status="sent", backend="whatsapp"
        )

    db = db_factory()
    try:
        with patch(
            "app.services.notifications.fanout.smtp_configured",
            return_value=True,
        ), patch(
            "app.services.notifications.fanout.send_transactional_email",
            return_value=_stub_email(),
        ), patch(
            "app.services.notifications.fanout.send_message",
            side_effect=_fake_send_message,
        ):
            dispatch(db, _renewal_envelope(user_id), mode="active")
        db.commit()
    finally:
        db.close()

    # Routing returns whatsapp=False (phone_not_verified) before we
    # get to the send leg.
    assert called["n"] == 0

    db = db_factory()
    try:
        dr = db.scalar(select(NotificationDispatch))
        assert dr.whatsapp_status == "skipped"
        assert dr.whatsapp_reason == "phone_not_verified"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 8. Category muted on important event — skipped/category_muted
# ---------------------------------------------------------------------------


def test_category_muted_skips_whatsapp(db_factory) -> None:
    settings.WHATSAPP_NATIVE_TEMPLATES_ENABLED = True

    db = db_factory()
    try:
        user = _seed_user(db)
        db.add(
            UserNotificationPreference(
                user_id=user.id,
                category="renewal",
                email_muted=False,
                whatsapp_muted=True,
            )
        )
        # t-7 is the "important" tier event (yellow) and is mutable
        # via category preference.
        for ch, subj, body, meta in [
            ("inapp", None, "Vence en 7 días.", None),
            ("email", "T-7", "Vence en 7 días.", None),
            (
                "whatsapp",
                None,
                "Vence en 7 días.",
                "cw_renewal_threshold",
            ),
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

    called = {"n": 0}

    def _fake_send_message(**kwargs):
        called["n"] += 1
        return MessageDeliveryResult(
            delivered=True, status="sent", backend="whatsapp"
        )

    envelope = NotificationEnvelope(
        event_type="renewal.threshold.t-7",
        dedupe_key=f"renewal-t7-{user_id}",
        recipients=(Recipient(user_id=user_id, role="client_admin"),),
        payload={
            "vendor_name": "ACME",
            "requirement_name": "Constancia REPSE",
            "due_on": "2026-06-08",
            "days_remaining": 7,
        },
    )
    db = db_factory()
    try:
        with patch(
            "app.services.notifications.fanout.smtp_configured",
            return_value=True,
        ), patch(
            "app.services.notifications.fanout.send_transactional_email",
            return_value=_stub_email(),
        ), patch(
            "app.services.notifications.fanout.send_message",
            side_effect=_fake_send_message,
        ):
            dispatch(db, envelope, mode="active")
        db.commit()
    finally:
        db.close()

    assert called["n"] == 0
    db = db_factory()
    try:
        dr = db.scalar(select(NotificationDispatch))
        assert dr.whatsapp_status == "skipped"
        assert dr.whatsapp_reason == "category_muted"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 9. Critical event with WhatsApp muted — email still fires (regression)
# ---------------------------------------------------------------------------


def test_critical_event_emails_even_when_whatsapp_muted(db_factory) -> None:
    settings.WHATSAPP_NATIVE_TEMPLATES_ENABLED = True

    db = db_factory()
    try:
        user = _seed_user(db)
        db.add(
            UserNotificationPreference(
                user_id=user.id,
                category="renewal",
                email_muted=True,  # also muted — must be ignored for critical
                whatsapp_muted=True,
            )
        )
        _seed_renewal_t0_templates(db)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    email_called = {"n": 0}
    wa_called = {"n": 0}

    def _fake_email(**kwargs):
        email_called["n"] += 1
        return _stub_email()

    def _fake_send_message(**kwargs):
        wa_called["n"] += 1
        return MessageDeliveryResult(
            delivered=True, status="sent", backend="whatsapp"
        )

    db = db_factory()
    try:
        with patch(
            "app.services.notifications.fanout.smtp_configured",
            return_value=True,
        ), patch(
            "app.services.notifications.fanout.send_transactional_email",
            side_effect=_fake_email,
        ), patch(
            "app.services.notifications.fanout.send_message",
            side_effect=_fake_send_message,
        ):
            dispatch(db, _renewal_envelope(user_id), mode="active")
        db.commit()
    finally:
        db.close()

    # Email mandatory for critical events — unmuteable rule.
    assert email_called["n"] == 1
    # WhatsApp mute respected even at critical tier.
    assert wa_called["n"] == 0

    db = db_factory()
    try:
        dr = db.scalar(select(NotificationDispatch))
        assert dr.email_status == "sent"
        assert dr.whatsapp_status == "skipped"
        assert dr.whatsapp_reason == "category_muted"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 10. Audit row written only for Meta-backend attempts
# ---------------------------------------------------------------------------


def test_meta_send_writes_audit_log_row(db_factory) -> None:
    settings.WHATSAPP_NATIVE_TEMPLATES_ENABLED = True

    db = db_factory()
    try:
        user = _seed_user(db)
        _seed_renewal_t0_templates(db)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    def _fake_send_message(**kwargs):
        return MessageDeliveryResult(
            delivered=True,
            status="sent",
            backend="whatsapp",
            message_id="wamid.AUDIT",
        )

    db = db_factory()
    try:
        with patch(
            "app.services.notifications.fanout.smtp_configured",
            return_value=True,
        ), patch(
            "app.services.notifications.fanout.send_transactional_email",
            return_value=_stub_email(),
        ), patch(
            "app.services.notifications.fanout.send_message",
            side_effect=_fake_send_message,
        ):
            dispatch(db, _renewal_envelope(user_id), mode="active")
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        row = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "notification.whatsapp_dispatched"
            )
        )
        assert row is not None
        assert row.entity_type == "user"
        assert row.entity_id == user_id
        meta = row.event_metadata or {}
        assert meta["event_type"] == "renewal.threshold.t-0"
        assert meta["template_name"] == "cw_renewal_threshold"
        assert meta["status"] == "sent"
        assert meta["message_id"] == "wamid.AUDIT"
        # PII safety: only the last four digits land in audit metadata.
        assert meta["phone_last4"] == "2222"
        assert "525511112222" not in str(meta)
    finally:
        db.close()


def test_twilio_backend_does_not_write_whatsapp_audit_row(db_factory) -> None:
    """When components=None and Twilio handles the send, the audit
    row scoped to ``notification.whatsapp_dispatched`` must NOT be
    written — that signal is reserved for Meta health monitoring."""
    settings.WHATSAPP_NATIVE_TEMPLATES_ENABLED = False  # Twilio path

    db = db_factory()
    try:
        user = _seed_user(db)
        _seed_renewal_t0_templates(db)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    def _fake_send_message(**kwargs):
        return MessageDeliveryResult(
            delivered=True, status="sent", backend="twilio"
        )

    db = db_factory()
    try:
        with patch(
            "app.services.notifications.fanout.smtp_configured",
            return_value=True,
        ), patch(
            "app.services.notifications.fanout.send_transactional_email",
            return_value=_stub_email(),
        ), patch(
            "app.services.notifications.fanout.send_message",
            side_effect=_fake_send_message,
        ):
            dispatch(db, _renewal_envelope(user_id), mode="active")
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        row = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "notification.whatsapp_dispatched"
            )
        )
        assert row is None
    finally:
        db.close()
