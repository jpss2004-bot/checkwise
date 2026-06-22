"""Unit tests for ``app.services.subscription``.

Covers provider-limit resolution (override > tier default > legacy/NULL
uncapped), active-provider counting (archived excluded), and the capacity
guard (hard 409 for clients at the cap, internal_admin override).
"""

from __future__ import annotations

import itertools

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Client, Organization, Vendor
from app.services import subscription as sub

_rfc = itertools.count(1)


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


def _client_org(db, *, plan=None, provider_limit=None):
    client = Client(name="Acme")
    db.add(client)
    db.flush()
    org = Organization(
        name="Acme",
        kind="client",
        client_id=client.id,
        plan=plan,
        provider_limit=provider_limit,
    )
    db.add(org)
    db.flush()
    return client, org


def _add_vendor(db, client_id, *, status="active"):
    rfc = f"RFC{next(_rfc):09d}"  # 12 chars, unique per (client, rfc)
    v = Vendor(
        client_id=client_id, name="Proveedor", rfc=rfc,
        persona_type="moral", status=status,
    )
    db.add(v)
    db.flush()
    return v


def test_provider_limit_override_wins(session):
    _, org = _client_org(session, plan="demo", provider_limit=12)
    assert sub.provider_limit_for_org(org) == 12


def test_provider_limit_tier_defaults(session):
    for plan, expected in (("demo", 5), ("standard", 30), ("growth", 50)):
        _, org = _client_org(session, plan=plan)
        assert sub.provider_limit_for_org(org) == expected


def test_provider_limit_legacy_and_null_are_uncapped(session):
    _, legacy = _client_org(session, plan="legacy")
    _, missing = _client_org(session, plan=None)
    assert sub.provider_limit_for_org(legacy) is None
    assert sub.provider_limit_for_org(missing) is None


def test_active_count_excludes_archived(session):
    client, _ = _client_org(session, plan="demo")
    _add_vendor(session, client.id)
    _add_vendor(session, client.id)
    _add_vendor(session, client.id, status="inactive")
    assert sub.active_provider_count(session, client.id) == 2


def test_assert_capacity_blocks_client_at_cap(session):
    client, org = _client_org(session, plan="demo", provider_limit=2)
    _add_vendor(session, client.id)
    _add_vendor(session, client.id)
    with pytest.raises(HTTPException) as exc:
        sub.assert_provider_capacity(session, org, is_internal=False)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "provider_limit_reached"
    assert exc.value.detail["limit"] == 2
    assert "máximo" in exc.value.detail["message"]


def test_assert_capacity_internal_admin_override(session):
    client, org = _client_org(session, plan="demo", provider_limit=2)
    _add_vendor(session, client.id)
    _add_vendor(session, client.id)
    decision = sub.assert_provider_capacity(session, org, is_internal=True)
    assert decision.over_limit is True
    assert decision.allowed is True
    assert decision.used == 2 and decision.limit == 2


def test_assert_capacity_under_cap_ok(session):
    client, org = _client_org(session, plan="demo")  # default limit 5
    _add_vendor(session, client.id)
    decision = sub.assert_provider_capacity(session, org, is_internal=False)
    assert decision.used == 1 and decision.limit == 5
    assert decision.over_limit is False


def test_uncapped_never_blocks(session):
    client, org = _client_org(session, plan="legacy")
    for _ in range(40):
        _add_vendor(session, client.id)
    decision = sub.assert_provider_capacity(session, org, is_internal=False)
    assert decision.limit is None and decision.allowed is True
    assert decision.over_limit is False
