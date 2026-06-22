"""Phase D — provider-agnostic billing seam."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.plans import Plan
from app.db.base import Base
from app.models import Client, Organization
from app.services import billing
from app.services.subscription import plan_for_org


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


def _org(db, *, plan="demo"):
    client = Client(name="Acme")
    db.add(client)
    db.flush()
    org = Organization(name="Acme", kind="client", client_id=client.id, plan=plan)
    db.add(org)
    db.flush()
    return org


def test_get_or_create_is_idempotent(session):
    org = _org(session)
    a = billing.get_or_create_billing_account(session, org)
    assert a.provider == "manual"
    assert a.status == "none"
    b = billing.get_or_create_billing_account(session, org)
    assert b.id == a.id


def test_apply_billing_state_updates_account(session):
    org = _org(session)
    acct = billing.apply_billing_state(
        session, org, provider="stripe", status_value="active",
        customer_id="cus_1", subscription_id="sub_1",
    )
    assert acct.provider == "stripe"
    assert acct.status == "active"
    assert acct.customer_id == "cus_1"
    assert acct.subscription_id == "sub_1"


def test_apply_billing_state_moves_plan_and_clears_demo(session):
    org = _org(session, plan="demo")
    org.demo_expires_at = None  # (set_plan would clear it anyway)
    billing.apply_billing_state(session, org, status_value="active", plan=Plan.STANDARD)
    assert plan_for_org(org) is Plan.STANDARD
    assert org.demo_expires_at is None


def test_apply_billing_state_validates(session):
    org = _org(session)
    with pytest.raises(HTTPException):
        billing.apply_billing_state(session, org, provider="paypal")
    with pytest.raises(HTTPException):
        billing.apply_billing_state(session, org, status_value="weird")


def test_stripe_provider_is_stubbed(session):
    org = _org(session)
    provider = billing.get_billing_provider("stripe")
    with pytest.raises(NotImplementedError):
        provider.start_checkout(session, org, plan=Plan.STANDARD)


def test_manual_provider_has_no_checkout(session):
    org = _org(session)
    provider = billing.get_billing_provider("manual")
    with pytest.raises(HTTPException):
        provider.start_checkout(session, org, plan=Plan.STANDARD)


def test_unknown_provider_400(session):
    with pytest.raises(HTTPException):
        billing.get_billing_provider("nope")
