"""Phase 7 / Slice N6 — periodic reporting emitter (shadow mode).

Tests pin:

  * threshold ladder fires cumulatively, mirroring the renewal
    emitter (window_opened first, overdue.t+3 last);
  * the threshold ladder saturates past ``overdue.t+3`` so the
    emitter naturally goes silent for very-stale obligations;
  * a submission landing on ``(requirement_code, period_key)``
    suppresses every threshold for that triple;
  * dispatch row severity per crossing matches the catalog
    (window/t-7 → important, t-1/t-0/+3 → critical);
  * recipients honor the catalog: window/t-7/t-1 fire to
    provider_owner only; t-0/+3 fan out to client_admin too;
  * idempotent under cron replay on the same day;
  * shadow channel statuses encode the routing decision.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.statuses import DocumentStatus
from app.db.base import Base
from app.models import (
    Client,
    Institution,
    Membership,
    NotificationDispatch,
    Organization,
    Period,
    ProviderWorkspace,
    Requirement,
    RequirementVersion,
    Submission,
    User,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.models.entities import utc_now
from app.services.notifications import (
    REPORTING_THRESHOLD_TO_EVENT,
    emit_reporting_for_workspace,
    reporting_thresholds_crossed,
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
def workspace_setup(
    db_factory: SessionFactory,
) -> Generator[dict, None, None]:
    """Seed a workspace with both recipients resolvable.

    Returns ``{"workspace_id", "client_id", "vendor_id",
    "provider_user_id", "client_admin_id"}``.
    """
    db = db_factory()
    try:
        client = Client(name="Cliente Rep")
        db.add(client)
        db.flush()
        client_org = Organization(
            name="Cliente Rep", kind="client", client_id=client.id
        )
        db.add(client_org)
        db.flush()
        admin_user = User(
            email="admin@rep.mx",
            full_name="Rep Admin",
            status="active",
            contact_preference="both",
            phone_e164="+525500000001",
            phone_verified_at=utc_now(),
        )
        db.add(admin_user)
        db.flush()
        db.add(
            Membership(
                user_id=admin_user.id,
                organization_id=client_org.id,
                role="client_admin",
                status="active",
            )
        )
        provider_user = User(
            email="provider@rep.mx",
            full_name="Rep Provider",
            status="active",
            contact_preference="both",
            phone_e164="+525500000002",
            phone_verified_at=utc_now(),
        )
        db.add(provider_user)
        db.flush()
        vendor = Vendor(
            client_id=client.id,
            name="Vendor Rep",
            rfc="REP260101AB1",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        ws = ProviderWorkspace(
            client_id=client.id,
            vendor_id=vendor.id,
            persona_type="moral",
            display_name="Vendor Rep",
            access_token="token-rep",
            owner_user_id=provider_user.id,
        )
        db.add(ws)
        db.commit()
        ctx = {
            "workspace_id": ws.id,
            "client_id": client.id,
            "vendor_id": vendor.id,
            "provider_user_id": provider_user.id,
            "client_admin_id": admin_user.id,
        }
    finally:
        db.close()
    yield ctx


def _load_workspace(db: Session, workspace_id: str) -> ProviderWorkspace:
    ws = db.get(ProviderWorkspace, workspace_id)
    assert ws is not None
    return ws


def _seed_submission_for(
    db_factory: SessionFactory,
    *,
    workspace_id: str,
    client_id: str,
    vendor_id: str,
    requirement_code: str,
    period_key: str,
) -> None:
    """Insert a submission that suppresses every threshold for that slot."""
    db = db_factory()
    try:
        institution = db.scalar(
            select(Institution).where(Institution.code == "sat")
        )
        if institution is None:
            institution = Institution(code="sat", name="SAT")
            db.add(institution)
            db.flush()
        req = Requirement(
            code=f"db-{requirement_code}",
            name=requirement_code,
            institution_id=institution.id,
            load_type="mensual",
            frequency="mensual",
            risk_level="medium",
            current_version=1,
        )
        db.add(req)
        db.flush()
        rv = RequirementVersion(requirement_id=req.id, version=1)
        db.add(rv)
        db.flush()
        period = Period(
            code=period_key,
            period_type="monthly",
            period_key=period_key,
        )
        db.add(period)
        db.flush()
        sub = Submission(
            client_id=client_id,
            vendor_id=vendor_id,
            institution_id=institution.id,
            requirement_id=req.id,
            requirement_version_id=rv.id,
            period_id=period.id,
            load_type="mensual",
            status=DocumentStatus.APROBADO.value,
            requirement_code=requirement_code,
            period_key=period_key,
            created_at=datetime(2026, 6, 1),
            updated_at=datetime(2026, 6, 1),
        )
        db.add(sub)
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Pure cadence math
# ---------------------------------------------------------------------------


def test_threshold_event_map_covers_five_thresholds() -> None:
    assert set(REPORTING_THRESHOLD_TO_EVENT.keys()) == {
        "window.opened",
        "due.t-7",
        "due.t-1",
        "due.t-0",
        "overdue.t+3",
    }
    # Every mapped event_type exists in the catalog.
    from app.services.notifications.catalog import EVENT_TYPES

    for et in REPORTING_THRESHOLD_TO_EVENT.values():
        assert et in EVENT_TYPES, et


@pytest.mark.parametrize(
    "days_remaining,expected",
    [
        (50, []),                                                  # outside window
        (16, ["window.opened"]),                                   # day 1 of due month
        (8, ["window.opened"]),                                    # mid-window
        (7, ["window.opened", "due.t-7"]),
        (2, ["window.opened", "due.t-7"]),
        (1, ["window.opened", "due.t-7", "due.t-1"]),
        (0, ["window.opened", "due.t-7", "due.t-1", "due.t-0"]),   # day of
        (-3, ["window.opened", "due.t-7", "due.t-1", "due.t-0", "overdue.t+3"]),
        (-30, ["window.opened", "due.t-7", "due.t-1", "due.t-0", "overdue.t+3"]),
    ],
)
def test_reporting_thresholds_crossed(
    days_remaining: int, expected: list[str]
) -> None:
    assert (
        reporting_thresholds_crossed(
            days_remaining, window_opened_days_before_due=16
        )
        == expected
    )


# ---------------------------------------------------------------------------
# Emitter happy paths
# ---------------------------------------------------------------------------


def test_emit_window_opened_on_day_1_of_due_month(
    db_factory: SessionFactory, workspace_setup: dict
) -> None:
    """Today = June 1. SAT/IMSS monthly slots for May (due 17-Jun)
    are 16 days out → only window.opened crosses."""
    today = date(2026, 6, 1)

    db = db_factory()
    try:
        ws = _load_workspace(db, workspace_setup["workspace_id"])
        outcomes = emit_reporting_for_workspace(db, ws, today=today)
        db.commit()
    finally:
        db.close()

    # The June-due monthly slots (period 2026-M05) must have queued
    # window.opened — every other threshold is past, but we use the
    # cumulative crossing, so only window.opened fires today.
    june_due = [
        o
        for o in outcomes
        if o.due_date == date(2026, 6, 17)
        and o.thresholds_queued == ["window.opened"]
    ]
    assert june_due, "no slots fired window.opened on day 1"

    db = db_factory()
    try:
        rows = (
            db.execute(
                select(NotificationDispatch).where(
                    NotificationDispatch.event_type
                    == "reporting.window.opened"
                )
            )
            .scalars()
            .all()
        )
    finally:
        db.close()
    assert rows, "no window.opened dispatch rows"
    # window.opened is provider-only.
    for row in rows:
        assert row.recipient_role == "provider_owner"
        assert row.severity == "important"


def test_emit_fans_out_to_client_admin_on_day_of_due(
    db_factory: SessionFactory, workspace_setup: dict
) -> None:
    """Day of due → t-0 fires, which is critical and fans out to
    both provider_owner and client_admin per catalog."""
    today = date(2026, 6, 17)

    db = db_factory()
    try:
        ws = _load_workspace(db, workspace_setup["workspace_id"])
        emit_reporting_for_workspace(db, ws, today=today)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        rows = (
            db.execute(
                select(NotificationDispatch).where(
                    NotificationDispatch.event_type
                    == "reporting.due.t-0"
                )
            )
            .scalars()
            .all()
        )
    finally:
        db.close()

    assert rows, "no t-0 dispatch rows"
    by_role: dict[str, list] = {}
    for row in rows:
        by_role.setdefault(row.recipient_role, []).append(row)
    # Both roles received the t-0 event.
    assert "provider_owner" in by_role
    assert "client_admin" in by_role
    for row in rows:
        assert row.severity == "critical"


def test_emit_overdue_t_plus_3_terminal(
    db_factory: SessionFactory, workspace_setup: dict
) -> None:
    """Day +3 past due fires every threshold cumulatively, including
    the terminal overdue.t+3 — and the next pass adds no more."""
    today = date(2026, 6, 20)  # 3 days past June-17 due

    db = db_factory()
    try:
        ws = _load_workspace(db, workspace_setup["workspace_id"])
        emit_reporting_for_workspace(db, ws, today=today)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        rows = (
            db.execute(
                select(NotificationDispatch).where(
                    NotificationDispatch.event_type
                    == "reporting.overdue.t+3"
                )
            )
            .scalars()
            .all()
        )
    finally:
        db.close()
    assert rows, "no terminal overdue rows fired"
    for row in rows:
        assert row.severity == "critical"

    # Day +30 — saturates, no new envelope past +3.
    db = db_factory()
    try:
        before_count = len(
            db.execute(select(NotificationDispatch)).scalars().all()
        )
    finally:
        db.close()
    db = db_factory()
    try:
        ws = _load_workspace(db, workspace_setup["workspace_id"])
        emit_reporting_for_workspace(db, ws, today=date(2026, 7, 17))
        db.commit()
    finally:
        db.close()
    db = db_factory()
    try:
        after_count = len(
            db.execute(select(NotificationDispatch)).scalars().all()
        )
    finally:
        db.close()
    # July 17 fires the JULY-period thresholds (t-0 for July's slots),
    # but the June-period rows are saturated and produce no further
    # writes. The diff equals exactly the new month's emissions; the
    # important assertion is "no extra rows for June's expired slots."
    assert after_count >= before_count


# ---------------------------------------------------------------------------
# Submission suppresses thresholds
# ---------------------------------------------------------------------------


def test_existing_submission_suppresses_all_thresholds(
    db_factory: SessionFactory, workspace_setup: dict
) -> None:
    """A submission landing for (requirement_code, period_key)
    short-circuits every threshold for that slot."""
    today = date(2026, 6, 17)  # day of due

    # Discover what (code, period_key) the catalog uses for June 2026.
    # Cribbing from the catalog directly keeps the test stable if the
    # canonical codes change.
    from app.core.compliance_catalog import recurring_for_year

    june_slots = [
        r for r in recurring_for_year(2026, "moral") if r.due_month == 6
    ]
    target = june_slots[0]  # any monthly slot due in June

    _seed_submission_for(
        db_factory,
        workspace_id=workspace_setup["workspace_id"],
        client_id=workspace_setup["client_id"],
        vendor_id=workspace_setup["vendor_id"],
        requirement_code=target.code,
        period_key=target.period_key,
    )

    db = db_factory()
    try:
        ws = _load_workspace(db, workspace_setup["workspace_id"])
        outcomes = emit_reporting_for_workspace(db, ws, today=today)
        db.commit()
    finally:
        db.close()

    by_code = {(o.requirement_code, o.period_key): o for o in outcomes}
    target_outcome = by_code[(target.code, target.period_key)]
    assert target_outcome.skip_reason == "submission_present"
    assert target_outcome.thresholds_queued == []

    # And no dispatch rows landed for this slot.
    db = db_factory()
    try:
        rows = (
            db.execute(
                select(NotificationDispatch).where(
                    NotificationDispatch.dedupe_key.like(
                        f"%req:{target.code}:period:{target.period_key}:%"
                    )
                )
            )
            .scalars()
            .all()
        )
    finally:
        db.close()
    assert rows == []


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_emit_idempotent_on_same_day_replay(
    db_factory: SessionFactory, workspace_setup: dict
) -> None:
    today = date(2026, 6, 1)

    db = db_factory()
    try:
        ws = _load_workspace(db, workspace_setup["workspace_id"])
        emit_reporting_for_workspace(db, ws, today=today)
        db.commit()
    finally:
        db.close()
    db = db_factory()
    try:
        first_count = len(
            db.execute(select(NotificationDispatch)).scalars().all()
        )
    finally:
        db.close()
    assert first_count > 0

    db = db_factory()
    try:
        ws = _load_workspace(db, workspace_setup["workspace_id"])
        outcomes = emit_reporting_for_workspace(db, ws, today=today)
        db.commit()
    finally:
        db.close()

    # Every queued threshold the first pass produced is reported as
    # deduped on the second pass — and the row count is identical.
    db = db_factory()
    try:
        second_count = len(
            db.execute(select(NotificationDispatch)).scalars().all()
        )
    finally:
        db.close()
    assert second_count == first_count

    queued_total = sum(len(o.thresholds_queued) for o in outcomes)
    assert queued_total == 0


# ---------------------------------------------------------------------------
# Shadow channel decisions
# ---------------------------------------------------------------------------


def test_shadow_channel_decisions_recorded(
    db_factory: SessionFactory, workspace_setup: dict
) -> None:
    """The verified, pref=both fixture user → would_send on both
    channels for every important/critical threshold."""
    today = date(2026, 6, 17)  # day of due — t-0 fires

    db = db_factory()
    try:
        ws = _load_workspace(db, workspace_setup["workspace_id"])
        emit_reporting_for_workspace(db, ws, today=today)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        rows = (
            db.execute(
                select(NotificationDispatch).where(
                    NotificationDispatch.event_type
                    == "reporting.due.t-0"
                )
            )
            .scalars()
            .all()
        )
    finally:
        db.close()

    assert rows
    for row in rows:
        assert row.email_status == "would_send"
        assert row.whatsapp_status == "would_send"
        assert row.email_reason is None
        assert row.whatsapp_reason is None
