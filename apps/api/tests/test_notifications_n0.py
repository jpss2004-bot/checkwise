"""Phase 7 / Slices N0–N2 — catalog, envelope, dispatcher, idempotency, routing.

Behavior pinned at N0:

  * catalog completeness — every event group represented, no
    duplicate ``event_type``, invariants enforced at import time;
  * envelope construction rejects unknown events, empty
    recipients, empty dedupe keys, role mismatches, dup user_ids;
  * dispatcher writes exactly one ``audit_log`` row per recipient
    with the canonical metadata shape, and returns the matching
    :class:`DispatchResult`.

Behavior added at N1:

  * insert-first claim into ``notification_dispatch`` snapshots
    severity + payload at emit time;
  * a duplicate claim short-circuits with status ``deduped`` —
    no audit row, no row mutation;
  * a SAVEPOINT contains the IntegrityError so the outer
    transaction stays usable for the next recipient.

Behavior added at N2:

  * ``routing.decide()`` implements the §2 severity × preference
    × mute matrix as a pure function;
  * critical-tier email is unmuteable (preference + mute ignored);
  * info-tier never fires outbound channels;
  * WhatsApp requires event eligibility AND verified phone AND
    matching preference AND not category-muted.

Slices N3+ extend this file rather than replacing it; the
contracts asserted here become regressions for the rest of the
phase.
"""

from __future__ import annotations

from collections.abc import Callable, Generator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import AuditLog, NotificationDispatch, entities  # noqa: F401 — register mappers
from app.services.notifications import (
    CATALOG,
    EVENT_TYPES,
    SKIP_CATEGORY_MUTED,
    SKIP_EVENT_NOT_ELIGIBLE,
    SKIP_INFO_TIER,
    SKIP_PHONE_NOT_VERIFIED,
    SKIP_PREFERENCE_EXCLUDES,
    NotificationEnvelope,
    Recipient,
    claim,
    decide,
    dispatch,
    get_event,
)

SessionFactory = Callable[[], Session]


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
def db(db_factory: SessionFactory) -> Generator[Session, None, None]:
    session = db_factory()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_catalog_has_all_five_groups() -> None:
    """Smoke test — Plan §1 promises every group is wired."""
    categories = {row.category for row in CATALOG.values()}
    assert categories == {
        "renewal",
        "reporting",
        "verification",
        "account",
        "admin",
    }


def test_catalog_renewal_thresholds_complete() -> None:
    """The 8 renewal thresholds from the PDF must all be present."""
    renewal_events = {
        et for et in EVENT_TYPES if et.startswith("renewal.threshold.")
    }
    assert renewal_events == {
        "renewal.threshold.t-30",
        "renewal.threshold.t-14",
        "renewal.threshold.t-7",
        "renewal.threshold.t-0",
        "renewal.threshold.t+7",
        "renewal.threshold.t+14",
        "renewal.threshold.t+21",
        "renewal.threshold.t+28",
    }


def test_catalog_t_minus_30_and_14_are_info_only() -> None:
    """De-spam decision: 30d and 14d nudges live in the bell only."""
    assert get_event("renewal.threshold.t-30").severity == "info"
    assert get_event("renewal.threshold.t-14").severity == "info"
    assert get_event("renewal.threshold.t-30").whatsapp_eligible is False
    assert get_event("renewal.threshold.t-14").whatsapp_eligible is False


def test_catalog_critical_renewal_events_whatsapp_eligible() -> None:
    """Every red-tier renewal threshold has a WhatsApp template."""
    for et in (
        "renewal.threshold.t-0",
        "renewal.threshold.t+7",
        "renewal.threshold.t+14",
        "renewal.threshold.t+21",
        "renewal.threshold.t+28",
    ):
        row = get_event(et)
        assert row.severity == "critical"
        assert row.whatsapp_eligible is True


def test_catalog_info_tier_is_never_whatsapp_eligible() -> None:
    """Routing invariant — info events are in-app only by design."""
    for row in CATALOG.values():
        if row.severity == "info":
            assert row.whatsapp_eligible is False, (
                f"{row.event_type} is info-tier but whatsapp_eligible=True"
            )


def test_catalog_admin_group_is_never_whatsapp() -> None:
    """Internal staff are not paged on personal WhatsApp by the platform."""
    for row in CATALOG.values():
        if row.category == "admin":
            assert row.whatsapp_eligible is False


def test_catalog_every_row_has_recipients() -> None:
    for row in CATALOG.values():
        assert row.recipients, f"{row.event_type} has empty recipients"


def test_get_event_raises_keyerror_for_unknown_event() -> None:
    with pytest.raises(KeyError, match="Unknown notification event_type"):
        get_event("renewal.threshold.t-1")  # not in cadence


# ---------------------------------------------------------------------------
# Envelope construction
# ---------------------------------------------------------------------------


def test_envelope_accepts_valid_event_and_recipients() -> None:
    env = NotificationEnvelope(
        event_type="renewal.threshold.t-7",
        dedupe_key="workspace:w1:req:csf:cycle:2026-01-01:t:7",
        recipients=(
            Recipient(user_id="user-prov-1", role="provider_owner"),
            Recipient(user_id="user-client-1", role="client_admin"),
        ),
        payload={"vendor_name": "ACME", "due_on": "2026-06-01"},
    )
    assert env.definition.severity == "important"
    assert env.definition.category == "renewal"


def test_envelope_rejects_unknown_event_type() -> None:
    with pytest.raises(ValueError, match="Unknown notification event_type"):
        NotificationEnvelope(
            event_type="renewal.threshold.t-1",
            dedupe_key="x",
            recipients=(Recipient(user_id="u1", role="provider_owner"),),
        )


def test_envelope_rejects_empty_recipients() -> None:
    with pytest.raises(ValueError, match="no recipients"):
        NotificationEnvelope(
            event_type="renewal.threshold.t-7",
            dedupe_key="x",
            recipients=(),
        )


def test_envelope_rejects_empty_dedupe_key() -> None:
    with pytest.raises(ValueError, match="empty dedupe_key"):
        NotificationEnvelope(
            event_type="renewal.threshold.t-7",
            dedupe_key="",
            recipients=(Recipient(user_id="u1", role="provider_owner"),),
        )


def test_envelope_rejects_recipient_role_not_in_catalog() -> None:
    """Reporting events do not allow internal_admin recipients."""
    with pytest.raises(ValueError, match="not allowed for event"):
        NotificationEnvelope(
            event_type="reporting.window.opened",
            dedupe_key="x",
            recipients=(
                Recipient(user_id="u1", role="operations_admin"),
            ),
        )


def test_envelope_rejects_duplicate_user_id() -> None:
    """Same user listed twice = emitter bug; fail loud."""
    with pytest.raises(ValueError, match="more than once"):
        NotificationEnvelope(
            event_type="renewal.threshold.t-7",
            dedupe_key="x",
            recipients=(
                Recipient(user_id="u1", role="provider_owner"),
                Recipient(user_id="u1", role="client_admin"),
            ),
        )


# ---------------------------------------------------------------------------
# Dispatcher (N0 — audit-only skeleton)
# ---------------------------------------------------------------------------


def test_dispatch_writes_one_audit_row_per_recipient(db: Session) -> None:
    env = NotificationEnvelope(
        event_type="renewal.threshold.t-0",
        dedupe_key="workspace:w1:req:csf:cycle:2026-01-01:t:0",
        recipients=(
            Recipient(user_id="user-prov-1", role="provider_owner"),
            Recipient(user_id="user-client-1", role="client_admin"),
        ),
        payload={"vendor_name": "ACME"},
    )
    result = dispatch(db, env)
    db.flush()

    rows = db.execute(
        select(AuditLog).where(AuditLog.action == "notification.dispatch_attempted")
    ).scalars().all()
    assert len(rows) == 2
    assert {r.entity_id for r in rows} == {"user-prov-1", "user-client-1"}
    for row in rows:
        assert row.entity_type == "user"
        assert row.actor_type == "system"
        meta = row.event_metadata or {}
        assert meta["event_type"] == "renewal.threshold.t-0"
        assert meta["severity"] == "critical"
        assert meta["category"] == "renewal"
        assert meta["dedupe_key"] == env.dedupe_key
        assert meta["payload_keys"] == ["vendor_name"]
        assert meta["phase"] == "n1_idempotency"
        assert meta["recipient_role"] in {"provider_owner", "client_admin"}

    assert result.event_type == "renewal.threshold.t-0"
    assert result.queued == 2
    assert {o.role for o in result.outcomes} == {
        "provider_owner",
        "client_admin",
    }


def test_dispatch_does_not_commit(db: Session) -> None:
    """The caller owns the commit boundary — same discipline as
    ``renewal_dispatch``. A rollback after dispatch must remove the
    audit rows.
    """
    env = NotificationEnvelope(
        event_type="submission.received",
        dedupe_key="submission:s1:received",
        recipients=(Recipient(user_id="user-prov-1", role="provider_owner"),),
    )
    dispatch(db, env)
    db.flush()
    assert db.scalar(select(AuditLog).where(AuditLog.action == "notification.dispatch_attempted"))

    db.rollback()
    assert db.scalar(select(AuditLog).where(AuditLog.action == "notification.dispatch_attempted")) is None


def test_dispatch_payload_keys_never_include_values(db: Session) -> None:
    """At N0 we log payload key names only — no PII leaks into audit_log."""
    env = NotificationEnvelope(
        event_type="renewal.threshold.t-7",
        dedupe_key="workspace:w1:req:csf:cycle:2026-01-01:t:7",
        recipients=(Recipient(user_id="u1", role="provider_owner"),),
        payload={
            "vendor_name": "ACME",
            "owner_email": "secret@example.com",
            "phone": "+525500000000",
        },
    )
    dispatch(db, env)
    db.flush()

    row = db.execute(
        select(AuditLog).where(AuditLog.action == "notification.dispatch_attempted")
    ).scalar_one()
    meta = row.event_metadata or {}
    assert meta["payload_keys"] == ["owner_email", "phone", "vendor_name"]
    serialized = str(meta)
    assert "ACME" not in serialized
    assert "secret@example.com" not in serialized
    assert "+525500000000" not in serialized


# ---------------------------------------------------------------------------
# Idempotency (N1)
# ---------------------------------------------------------------------------


def test_claim_creates_row_with_severity_and_payload_snapshot(db: Session) -> None:
    row = claim(
        db,
        user_id="user-1",
        recipient_role="provider_owner",
        event_type="renewal.threshold.t-0",
        dedupe_key="workspace:w1:req:csf:cycle:2026-01-01:t:0",
        severity="critical",
        payload={"vendor_name": "ACME"},
    )
    db.flush()
    assert row is not None
    assert row.user_id == "user-1"
    assert row.recipient_role == "provider_owner"
    assert row.event_type == "renewal.threshold.t-0"
    assert row.severity == "critical"
    assert row.payload == {"vendor_name": "ACME"}
    assert row.email_status is None
    assert row.whatsapp_status is None
    assert row.inapp_id is None


def test_claim_returns_none_on_duplicate(db: Session) -> None:
    """The second claim on the same triple short-circuits silently."""
    first = claim(
        db,
        user_id="user-1",
        recipient_role="provider_owner",
        event_type="renewal.threshold.t-0",
        dedupe_key="workspace:w1:req:csf:cycle:2026-01-01:t:0",
        severity="critical",
        payload={},
    )
    assert first is not None

    second = claim(
        db,
        user_id="user-1",
        recipient_role="provider_owner",
        event_type="renewal.threshold.t-0",
        dedupe_key="workspace:w1:req:csf:cycle:2026-01-01:t:0",
        severity="critical",
        payload={},
    )
    assert second is None
    db.flush()
    rows = db.execute(select(NotificationDispatch)).scalars().all()
    assert len(rows) == 1


def test_claim_role_is_not_part_of_unique_key(db: Session) -> None:
    """Same user under a different role on the same event still dedupes.

    The dispatcher should not double-send because the emitter
    resolved the same principal under two different recipient
    roles — that is a bug in the emitter, not a fresh send.
    """
    first = claim(
        db,
        user_id="user-1",
        recipient_role="provider_owner",
        event_type="renewal.threshold.t-0",
        dedupe_key="dk",
        severity="critical",
    )
    assert first is not None

    second = claim(
        db,
        user_id="user-1",
        recipient_role="client_admin",
        event_type="renewal.threshold.t-0",
        dedupe_key="dk",
        severity="critical",
    )
    assert second is None


def test_dispatch_second_call_is_deduped_for_every_recipient(db: Session) -> None:
    env = NotificationEnvelope(
        event_type="renewal.threshold.t-0",
        dedupe_key="workspace:w1:req:csf:cycle:2026-01-01:t:0",
        recipients=(
            Recipient(user_id="user-prov-1", role="provider_owner"),
            Recipient(user_id="user-client-1", role="client_admin"),
        ),
        payload={"vendor_name": "ACME"},
    )

    first = dispatch(db, env)
    db.flush()
    assert first.queued == 2 and first.deduped == 0

    second = dispatch(db, env)
    db.flush()
    assert second.queued == 0 and second.deduped == 2

    dispatch_rows = db.execute(select(NotificationDispatch)).scalars().all()
    assert len(dispatch_rows) == 2

    audit_rows = db.execute(
        select(AuditLog).where(AuditLog.action == "notification.dispatch_attempted")
    ).scalars().all()
    assert len(audit_rows) == 2


def test_dispatch_partial_dedup_when_one_recipient_already_claimed(db: Session) -> None:
    """One recipient pre-claimed → only the new one is queued."""
    claim(
        db,
        user_id="user-prov-1",
        recipient_role="provider_owner",
        event_type="renewal.threshold.t-0",
        dedupe_key="dk",
        severity="critical",
    )
    db.flush()

    env = NotificationEnvelope(
        event_type="renewal.threshold.t-0",
        dedupe_key="dk",
        recipients=(
            Recipient(user_id="user-prov-1", role="provider_owner"),
            Recipient(user_id="user-client-1", role="client_admin"),
        ),
    )
    result = dispatch(db, env)
    db.flush()

    assert result.queued == 1
    assert result.deduped == 1
    by_user = {o.user_id: o.status for o in result.outcomes}
    assert by_user == {
        "user-prov-1": "deduped",
        "user-client-1": "queued",
    }

    audit_rows = db.execute(
        select(AuditLog).where(AuditLog.action == "notification.dispatch_attempted")
    ).scalars().all()
    # Only the newly-queued recipient gets an audit row; the deduped
    # recipient was a silent skip per the trazabilidad contract.
    assert len(audit_rows) == 1
    assert audit_rows[0].entity_id == "user-client-1"


def test_dispatch_dedupe_key_differentiates_cycles(db: Session) -> None:
    """A new cycle (different dedupe_key) re-claims the same recipient."""
    env_cycle_a = NotificationEnvelope(
        event_type="renewal.threshold.t-0",
        dedupe_key="workspace:w1:req:csf:cycle:2026-01-01:t:0",
        recipients=(Recipient(user_id="user-prov-1", role="provider_owner"),),
    )
    env_cycle_b = NotificationEnvelope(
        event_type="renewal.threshold.t-0",
        dedupe_key="workspace:w1:req:csf:cycle:2026-04-01:t:0",
        recipients=(Recipient(user_id="user-prov-1", role="provider_owner"),),
    )
    a = dispatch(db, env_cycle_a)
    b = dispatch(db, env_cycle_b)
    db.flush()
    assert a.queued == 1
    assert b.queued == 1
    assert db.execute(select(NotificationDispatch)).scalars().all().__len__() == 2


def test_dispatch_never_commits(db: Session) -> None:
    """Caller still owns the transaction boundary.

    The dispatcher must never call ``db.commit()`` on the caller's
    behalf — same discipline as ``renewal_dispatch``. We assert the
    contract by checking the session is still in-transaction after
    a successful dispatch; if the dispatcher had committed, the
    transaction would be closed.
    """
    env = NotificationEnvelope(
        event_type="renewal.threshold.t-0",
        dedupe_key="dk",
        recipients=(Recipient(user_id="user-prov-1", role="provider_owner"),),
    )
    dispatch(db, env)
    # ``in_transaction()`` returns True if there are pending changes
    # the caller still has to commit or roll back. The dispatcher
    # would have closed the transaction if it had committed.
    assert db.in_transaction()


# ---------------------------------------------------------------------------
# Routing matrix (N2)
# ---------------------------------------------------------------------------


_INFO_EVENT = get_event("renewal.threshold.t-30")  # info, renewal
_IMPORTANT_EVENT = get_event("renewal.threshold.t-7")  # important, renewal, WA-eligible
_CRITICAL_EVENT = get_event("renewal.threshold.t-0")  # critical, renewal, WA-eligible
_IMPORTANT_NOT_WA = get_event("account.welcome")  # important, account, NOT WA-eligible
_CRITICAL_NOT_WA = get_event("account.password_reset_requested")  # critical, account, NOT WA


def test_decide_info_tier_is_in_app_only() -> None:
    for pref in ("email", "whatsapp", "both"):
        d = decide(
            event=_INFO_EVENT,
            contact_preference=pref,  # type: ignore[arg-type]
            has_verified_phone=True,
            category_email_muted=False,
            category_whatsapp_muted=False,
        )
        assert d.in_app is True
        assert d.email is False
        assert d.email_skip_reason == SKIP_INFO_TIER
        assert d.whatsapp is False
        assert d.whatsapp_skip_reason == SKIP_INFO_TIER


def test_decide_critical_email_fires_regardless_of_preference() -> None:
    """The unmuteable critical-email rule — the entire compliance trail."""
    for pref in ("email", "whatsapp", "both"):
        d = decide(
            event=_CRITICAL_EVENT,
            contact_preference=pref,  # type: ignore[arg-type]
            has_verified_phone=True,
            category_email_muted=False,
            category_whatsapp_muted=False,
        )
        assert d.email is True, f"critical email should fire for pref={pref}"
        assert d.email_skip_reason is None


def test_decide_critical_email_fires_even_when_category_muted() -> None:
    """Even with the renewal category muted, critical email still fires."""
    d = decide(
        event=_CRITICAL_EVENT,
        contact_preference="both",
        has_verified_phone=True,
        category_email_muted=True,
        category_whatsapp_muted=False,
    )
    assert d.email is True
    assert d.email_skip_reason is None


def test_decide_important_email_respects_preference() -> None:
    d = decide(
        event=_IMPORTANT_EVENT,
        contact_preference="whatsapp",
        has_verified_phone=True,
        category_email_muted=False,
        category_whatsapp_muted=False,
    )
    assert d.email is False
    assert d.email_skip_reason == SKIP_PREFERENCE_EXCLUDES


def test_decide_important_email_respects_category_mute() -> None:
    d = decide(
        event=_IMPORTANT_EVENT,
        contact_preference="both",
        has_verified_phone=True,
        category_email_muted=True,
        category_whatsapp_muted=False,
    )
    assert d.email is False
    assert d.email_skip_reason == SKIP_CATEGORY_MUTED


def test_decide_important_email_fires_for_email_and_both() -> None:
    for pref in ("email", "both"):
        d = decide(
            event=_IMPORTANT_EVENT,
            contact_preference=pref,  # type: ignore[arg-type]
            has_verified_phone=False,
            category_email_muted=False,
            category_whatsapp_muted=False,
        )
        assert d.email is True
        assert d.email_skip_reason is None


def test_decide_whatsapp_skipped_when_event_not_eligible() -> None:
    """Admin events + ``account.welcome`` are catalog-marked
    ``whatsapp_eligible=False``. WhatsApp must never fire for them
    regardless of preference."""
    d = decide(
        event=_IMPORTANT_NOT_WA,
        contact_preference="both",
        has_verified_phone=True,
        category_email_muted=False,
        category_whatsapp_muted=False,
    )
    assert d.whatsapp is False
    assert d.whatsapp_skip_reason == SKIP_EVENT_NOT_ELIGIBLE


def test_decide_whatsapp_skipped_when_preference_is_email() -> None:
    d = decide(
        event=_CRITICAL_EVENT,
        contact_preference="email",
        has_verified_phone=True,
        category_email_muted=False,
        category_whatsapp_muted=False,
    )
    assert d.whatsapp is False
    assert d.whatsapp_skip_reason == SKIP_PREFERENCE_EXCLUDES


def test_decide_whatsapp_skipped_when_phone_not_verified() -> None:
    d = decide(
        event=_CRITICAL_EVENT,
        contact_preference="both",
        has_verified_phone=False,
        category_email_muted=False,
        category_whatsapp_muted=False,
    )
    assert d.whatsapp is False
    assert d.whatsapp_skip_reason == SKIP_PHONE_NOT_VERIFIED


def test_decide_whatsapp_can_be_muted_even_for_critical() -> None:
    """Meta requires opt-in, so WhatsApp mute applies to every tier."""
    d = decide(
        event=_CRITICAL_EVENT,
        contact_preference="both",
        has_verified_phone=True,
        category_email_muted=False,
        category_whatsapp_muted=True,
    )
    assert d.whatsapp is False
    assert d.whatsapp_skip_reason == SKIP_CATEGORY_MUTED
    # And email still fires — the critical-email rule is intact.
    assert d.email is True


def test_decide_full_house_critical_with_both_and_verified_fires_everything() -> None:
    d = decide(
        event=_CRITICAL_EVENT,
        contact_preference="both",
        has_verified_phone=True,
        category_email_muted=False,
        category_whatsapp_muted=False,
    )
    assert d.in_app is True
    assert d.email is True
    assert d.whatsapp is True
    assert d.any_outbound is True


def test_decide_critical_password_reset_does_not_whatsapp() -> None:
    """``account.password_reset_requested`` is critical but not WA-eligible
    — Meta does not allow OTP/password resets via this template
    surface at N2. Email must still fire."""
    d = decide(
        event=_CRITICAL_NOT_WA,
        contact_preference="both",
        has_verified_phone=True,
        category_email_muted=False,
        category_whatsapp_muted=False,
    )
    assert d.email is True
    assert d.whatsapp is False
    assert d.whatsapp_skip_reason == SKIP_EVENT_NOT_ELIGIBLE
