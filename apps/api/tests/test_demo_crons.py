"""Phase B4 — demo cron core logic (freeze sweep + cron-skip filter)."""

from __future__ import annotations

import itertools
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.time import utc_now
from app.db.base import Base
from app.models import Client, Organization
from app.services.subscription import blocked_client_ids, freeze_expired_demos

_seq = itertools.count(1)


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


def _org(db, *, plan="demo", status="active", demo_expires_at=None):
    seq = next(_seq)
    client = Client(name=f"C{seq}")
    db.add(client)
    db.flush()
    org = Organization(
        name=f"C{seq}", kind="client", client_id=client.id, plan=plan,
        status=status, demo_expires_at=demo_expires_at,
    )
    db.add(org)
    db.flush()
    return org


def test_freeze_expired_demos(session):
    past = utc_now() - timedelta(days=1)
    future = utc_now() + timedelta(days=2)
    expired = _org(session, demo_expires_at=past)
    fresh = _org(session, demo_expires_at=future)
    no_deadline = _org(session, demo_expires_at=None)
    paid = _org(session, plan="standard", demo_expires_at=past)

    frozen = freeze_expired_demos(session)

    assert {o.id for o in frozen} == {expired.id}
    assert expired.status == "frozen"
    assert fresh.status == "active"
    assert no_deadline.status == "active"
    assert paid.status == "active"  # a stray deadline on a paid plan is ignored


def test_freeze_is_idempotent(session):
    past = utc_now() - timedelta(days=1)
    _org(session, demo_expires_at=past)
    assert len(freeze_expired_demos(session)) == 1
    # Re-run: the already-frozen org is no longer matched.
    assert freeze_expired_demos(session) == []


def test_blocked_client_ids(session):
    active = _org(session, plan="standard", status="active")
    frozen = _org(session, plan="demo", status="frozen")
    expired_demo = _org(
        session, plan="demo", status="active",
        demo_expires_at=utc_now() - timedelta(days=1),
    )
    blocked = blocked_client_ids(session)
    assert frozen.client_id in blocked
    assert expired_demo.client_id in blocked
    assert active.client_id not in blocked
