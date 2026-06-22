"""Phase B — org status + demo-lifecycle helpers.

Covers the single ``is_org_blocked`` predicate (the truth table shared by the
B2 login gate and B3 portal gate) plus ``start_demo`` / ``set_plan`` /
``set_org_status`` mutations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.plans import DEMO_DURATION_DAYS, Plan
from app.core.time import utc_now
from app.db.base import Base
from app.models import Client, Organization
from app.services import subscription as sub


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()


def _org(db, *, plan="standard", status="active", demo_expires_at=None,
         provider_limit=None):
    client = Client(name="Acme")
    db.add(client)
    db.flush()
    org = Organization(
        name="Acme", kind="client", client_id=client.id, plan=plan,
        status=status, demo_expires_at=demo_expires_at, provider_limit=provider_limit,
    )
    db.add(org)
    db.flush()
    return org


# --- is_org_blocked truth table ------------------------------------------


def test_active_paid_not_blocked(session):
    assert sub.is_org_blocked(_org(session, plan="standard")) is False


def test_frozen_status_blocked(session):
    assert sub.is_org_blocked(_org(session, status="frozen")) is True


def test_expired_status_blocked(session):
    assert sub.is_org_blocked(_org(session, status="expired")) is True


def test_demo_past_deadline_blocked(session):
    past = utc_now() - timedelta(days=1)
    assert sub.is_org_blocked(_org(session, plan="demo", demo_expires_at=past)) is True


def test_demo_future_deadline_not_blocked(session):
    future = utc_now() + timedelta(days=3)
    assert sub.is_org_blocked(
        _org(session, plan="demo", demo_expires_at=future)
    ) is False


def test_demo_null_deadline_not_blocked(session):
    assert sub.is_org_blocked(
        _org(session, plan="demo", demo_expires_at=None)
    ) is False


def test_paid_with_stray_past_deadline_not_blocked(session):
    # A leftover deadline on a paid plan must never block (set_plan clears it).
    past = utc_now() - timedelta(days=1)
    assert sub.is_org_blocked(
        _org(session, plan="standard", demo_expires_at=past)
    ) is False


def test_naive_deadline_treated_as_utc(session):
    # SQLite can hand back a naive datetime; the comparison must not raise.
    past_naive = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    assert sub.is_org_blocked(
        _org(session, plan="demo", demo_expires_at=past_naive)
    ) is True


# --- start_demo / set_plan / set_org_status ------------------------------


def test_start_demo_sets_fields(session):
    org = _org(session, plan="legacy", provider_limit=99, status="frozen")
    sub.start_demo(session, org)
    assert org.plan == "demo"
    assert org.provider_limit is None  # demo tier default (5) applies
    assert org.status == "active"
    assert org.demo_expires_at is not None
    delta = sub._as_utc(org.demo_expires_at) - utc_now()
    assert timedelta(days=DEMO_DURATION_DAYS - 1) < delta <= timedelta(
        days=DEMO_DURATION_DAYS
    )


def test_set_plan_clears_demo_deadline(session):
    org = _org(session, plan="demo", demo_expires_at=utc_now() + timedelta(days=5))
    sub.set_plan(session, org, plan=Plan.STANDARD)
    assert org.plan == "standard"
    assert org.demo_expires_at is None


def test_set_plan_keeps_provider_limit_override(session):
    org = _org(session, plan="demo", provider_limit=12)
    sub.set_plan(session, org, plan=Plan.GROWTH)
    assert org.provider_limit == 12  # negotiated override survives an upgrade


def test_set_org_status_validates(session):
    org = _org(session)
    sub.set_org_status(session, org, status="frozen")
    assert org.status == "frozen"
    with pytest.raises(HTTPException) as exc:
        sub.set_org_status(session, org, status="bogus")
    assert exc.value.status_code == 400
