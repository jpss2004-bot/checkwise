"""Phase 7 / Slice N7 — account + admin emitters (shadow mode).

Tests pin:

  * each account event fires with the correct catalog role (invitee
    for invitation_sent, user for the other four);
  * critical account events (invitation_sent, password_reset_requested)
    have email always-firing per routing.decide();
  * info account events (channel_preference_changed, whatsapp_verified)
    are in-app only — no email, no WhatsApp;
  * password_reset is NOT WhatsApp-eligible at the catalog level
    (Meta credential-recovery policy);
  * admin events fan out to every active internal_admin;
  * admin events never WhatsApp regardless of user preference;
  * dedupe keys carry the right discriminator (token id for
    invitations / resets, change_id for prefs, ticket_id for
    tickets, date for cron / risk);
  * replays land as ``deduped`` without writing extra rows.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    Membership,
    NotificationDispatch,
    Organization,
    User,
    entities,  # noqa: F401 — register mappers
)
from app.models.entities import utc_now
from app.services.notifications import (
    emit_channel_preference_changed,
    emit_cron_health,
    emit_invitation_sent,
    emit_password_reset_requested,
    emit_support_ticket_opened,
    emit_welcome,
    emit_whatsapp_verified,
    emit_workspace_at_risk,
)

SessionFactory = Callable[[], Session]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_factory() -> SessionFactory:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def basic_user(db_factory: SessionFactory) -> Generator[str, None, None]:
    """Seed a single User with verified phone + pref=both."""
    db = db_factory()
    try:
        user = User(
            email="jose@legalshelf.mx",
            full_name="Jose Pablo",
            status="active",
            contact_preference="both",
            phone_e164="+525500000010",
            phone_verified_at=utc_now(),
        )
        db.add(user)
        db.commit()
        uid = user.id
    finally:
        db.close()
    yield uid


def _seed_internal_admins(
    db_factory: SessionFactory, *, count: int = 2
) -> list[str]:
    """Seed ``count`` active internal_admin Users + return their ids."""
    db = db_factory()
    try:
        org = Organization(name="LegalShelf", kind="internal")
        db.add(org)
        db.flush()
        ids: list[str] = []
        for n in range(count):
            user = User(
                email=f"admin{n}@legalshelf.mx",
                full_name=f"Admin {n}",
                status="active",
                contact_preference="both",
                phone_e164=f"+5255000{n:05d}",
                phone_verified_at=utc_now(),
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
            ids.append(user.id)
        db.commit()
        return ids
    finally:
        db.close()


# ===========================================================================
# Account events
# ===========================================================================


def test_invitation_sent_role_is_invitee_and_email_fires(
    db_factory: SessionFactory, basic_user: str
) -> None:
    db = db_factory()
    try:
        user = db.get(User, basic_user)
        result = emit_invitation_sent(
            db,
            user=user,
            invitation_token_id="tok-abc",
            invitation_url="https://app.checkwise.mx/activate?t=tok-abc",
        )
        db.commit()
    finally:
        db.close()

    assert result is not None
    assert {o.role for o in result.outcomes} == {"invitee"}

    db = db_factory()
    try:
        row = db.scalar(select(NotificationDispatch))
    finally:
        db.close()
    assert row is not None
    assert row.event_type == "account.invitation_sent"
    assert row.severity == "critical"
    assert row.recipient_role == "invitee"
    # Critical → email always fires.
    assert row.email_status == "would_send"
    # invitation_sent IS WhatsApp-eligible per catalog → fires for
    # verified user with pref=both.
    assert row.whatsapp_status == "would_send"


def test_invitation_dedupe_includes_token(
    db_factory: SessionFactory, basic_user: str
) -> None:
    """Re-issuing under a different token id produces a fresh envelope."""
    db = db_factory()
    try:
        user = db.get(User, basic_user)
        emit_invitation_sent(
            db, user=user, invitation_token_id="tok-1", invitation_url="x"
        )
        emit_invitation_sent(
            db, user=user, invitation_token_id="tok-2", invitation_url="y"
        )
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        rows = db.execute(select(NotificationDispatch)).scalars().all()
    finally:
        db.close()
    assert len(rows) == 2


def test_welcome_dedupes_per_user(
    db_factory: SessionFactory, basic_user: str
) -> None:
    """Calling welcome twice never sends two welcomes."""
    db = db_factory()
    try:
        user = db.get(User, basic_user)
        first = emit_welcome(db, user=user)
        db.commit()
    finally:
        db.close()
    db = db_factory()
    try:
        user = db.get(User, basic_user)
        second = emit_welcome(db, user=user)
        db.commit()
    finally:
        db.close()

    assert first.queued == 1
    assert second.queued == 0
    assert second.deduped == 1

    db = db_factory()
    try:
        rows = db.execute(select(NotificationDispatch)).scalars().all()
    finally:
        db.close()
    assert len(rows) == 1
    assert rows[0].event_type == "account.welcome"
    assert rows[0].severity == "important"


def test_password_reset_is_critical_and_not_whatsapp(
    db_factory: SessionFactory, basic_user: str
) -> None:
    db = db_factory()
    try:
        user = db.get(User, basic_user)
        emit_password_reset_requested(
            db,
            user=user,
            reset_token_id="rt-1",
            reset_url="https://app.checkwise.mx/reset?t=rt-1",
        )
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        row = db.scalar(select(NotificationDispatch))
    finally:
        db.close()
    assert row is not None
    assert row.severity == "critical"
    # Critical email always fires.
    assert row.email_status == "would_send"
    # Catalog marks this NOT WhatsApp-eligible → would_skip.
    assert row.whatsapp_status == "would_skip"
    assert row.whatsapp_reason == "event_not_eligible"


def test_password_reset_distinct_per_token(
    db_factory: SessionFactory, basic_user: str
) -> None:
    db = db_factory()
    try:
        user = db.get(User, basic_user)
        emit_password_reset_requested(
            db, user=user, reset_token_id="t1", reset_url="x"
        )
        emit_password_reset_requested(
            db, user=user, reset_token_id="t2", reset_url="y"
        )
        db.commit()
    finally:
        db.close()
    db = db_factory()
    try:
        rows = db.execute(select(NotificationDispatch)).scalars().all()
    finally:
        db.close()
    assert len(rows) == 2


def test_channel_preference_changed_is_info_only(
    db_factory: SessionFactory, basic_user: str
) -> None:
    """The confirmation echo never sends email or WhatsApp."""
    db = db_factory()
    try:
        user = db.get(User, basic_user)
        emit_channel_preference_changed(
            db, user=user, change_id="2026-05-26T12:00:00Z"
        )
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        row = db.scalar(select(NotificationDispatch))
    finally:
        db.close()
    assert row is not None
    assert row.severity == "info"
    assert row.email_status == "would_skip"
    assert row.email_reason == "info_tier"
    assert row.whatsapp_status == "would_skip"
    assert row.whatsapp_reason == "info_tier"


def test_whatsapp_verified_is_info_only(
    db_factory: SessionFactory, basic_user: str
) -> None:
    db = db_factory()
    try:
        user = db.get(User, basic_user)
        emit_whatsapp_verified(db, user=user)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        row = db.scalar(select(NotificationDispatch))
    finally:
        db.close()
    assert row is not None
    assert row.event_type == "account.whatsapp_verified"
    assert row.severity == "info"
    assert row.email_status == "would_skip"
    assert row.whatsapp_status == "would_skip"


# ===========================================================================
# Admin events
# ===========================================================================


def test_support_ticket_fans_out_to_every_internal_admin(
    db_factory: SessionFactory,
) -> None:
    admin_ids = _seed_internal_admins(db_factory, count=2)
    db = db_factory()
    try:
        result = emit_support_ticket_opened(
            db,
            ticket_id="tkt-123",
            summary="No puedo subir el comprobante",
            category="provider_portal",
            actor_email="proveedor@vendedor.mx",
        )
        db.commit()
    finally:
        db.close()

    assert result is not None
    assert result.queued == 2

    db = db_factory()
    try:
        rows = db.execute(select(NotificationDispatch)).scalars().all()
    finally:
        db.close()
    assert len(rows) == 2
    assert {r.user_id for r in rows} == set(admin_ids)
    for row in rows:
        assert row.recipient_role == "internal_admin"
        assert row.severity == "important"
        # Admin events are never WhatsApp-eligible per catalog.
        assert row.whatsapp_status == "would_skip"
        assert row.whatsapp_reason == "event_not_eligible"


def test_support_ticket_dedupe_per_ticket(
    db_factory: SessionFactory,
) -> None:
    _seed_internal_admins(db_factory, count=2)
    db = db_factory()
    try:
        emit_support_ticket_opened(
            db, ticket_id="tkt-1", summary="x", category="general"
        )
        emit_support_ticket_opened(
            db, ticket_id="tkt-1", summary="x", category="general"
        )
        db.commit()
    finally:
        db.close()
    db = db_factory()
    try:
        rows = db.execute(select(NotificationDispatch)).scalars().all()
    finally:
        db.close()
    # 2 admins × 1 ticket = 2 rows; second call dedupes both.
    assert len(rows) == 2


def test_workspace_at_risk_dedupes_per_day(
    db_factory: SessionFactory,
) -> None:
    _seed_internal_admins(db_factory, count=1)
    db = db_factory()
    try:
        emit_workspace_at_risk(
            db,
            workspace_id="ws-1",
            workspace_label="Vendor ACME",
            red_count=5,
            on_date=date(2026, 6, 1),
        )
        # Same day re-emit → deduped.
        second = emit_workspace_at_risk(
            db,
            workspace_id="ws-1",
            workspace_label="Vendor ACME",
            red_count=7,
            on_date=date(2026, 6, 1),
        )
        # Next day → fresh envelope.
        third = emit_workspace_at_risk(
            db,
            workspace_id="ws-1",
            workspace_label="Vendor ACME",
            red_count=7,
            on_date=date(2026, 6, 2),
        )
        db.commit()
    finally:
        db.close()

    assert second is not None and second.queued == 0 and second.deduped == 1
    assert third is not None and third.queued == 1

    db = db_factory()
    try:
        rows = db.execute(select(NotificationDispatch)).scalars().all()
    finally:
        db.close()
    assert len(rows) == 2  # one per day, one admin


def test_cron_health_is_info_only(db_factory: SessionFactory) -> None:
    _seed_internal_admins(db_factory, count=1)
    db = db_factory()
    try:
        emit_cron_health(
            db,
            cron_name="checkwise-renewal-cron",
            on_date=date(2026, 6, 1),
            dispatched_count=42,
            error_count=0,
            duration_seconds=12.4,
        )
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        row = db.scalar(select(NotificationDispatch))
    finally:
        db.close()
    assert row is not None
    assert row.event_type == "admin.cron_health"
    assert row.severity == "info"
    assert row.email_status == "would_skip"
    assert row.email_reason == "info_tier"


def test_admin_emit_returns_none_when_no_admins(
    db_factory: SessionFactory,
) -> None:
    """Empty admin set is a setup bug; emit returns None gracefully."""
    db = db_factory()
    try:
        result = emit_support_ticket_opened(
            db, ticket_id="t", summary="x", category="y"
        )
    finally:
        db.close()
    assert result is None
