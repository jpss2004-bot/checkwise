"""Phase D — per-tenant entitlement overrides + the capability shim merge."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.time import utc_now
from app.db.base import Base
from app.models import Client, Organization
from app.services import entitlements as ent
from app.services.subscription import capabilities_for_org


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


def test_demo_default_gates_exports(session):
    caps = capabilities_for_org(session, _org(session))
    assert caps["export_audit_package"] is False
    assert caps["bulk_export"] is False
    assert caps["download_documents"] is True


def test_grant_overrides_tier_default(session):
    org = _org(session)
    ent.grant_entitlement(session, org.id, key="export_audit_package", enabled=True)
    caps = capabilities_for_org(session, org)
    assert caps["export_audit_package"] is True  # granted
    assert caps["bulk_export"] is False  # untouched


def test_revoke_reverts_to_default(session):
    org = _org(session)
    ent.grant_entitlement(session, org.id, key="bulk_export", enabled=True)
    assert capabilities_for_org(session, org)["bulk_export"] is True
    assert ent.revoke_entitlement(session, org.id, key="bulk_export") is True
    assert capabilities_for_org(session, org)["bulk_export"] is False


def test_expired_grant_is_ignored(session):
    org = _org(session)
    ent.grant_entitlement(
        session, org.id, key="bulk_export", enabled=True,
        expires_at=utc_now() - timedelta(days=1),
    )
    assert capabilities_for_org(session, org)["bulk_export"] is False


def test_entitlement_can_revoke_a_paid_capability(session):
    # A 'standard' org normally has bulk_export; an entitlement can turn it OFF.
    org = _org(session, plan="standard")
    assert capabilities_for_org(session, org)["bulk_export"] is True
    ent.grant_entitlement(session, org.id, key="bulk_export", enabled=False)
    assert capabilities_for_org(session, org)["bulk_export"] is False


def test_grant_invalid_key_400(session):
    org = _org(session)
    with pytest.raises(HTTPException) as exc:
        ent.grant_entitlement(session, org.id, key="nonsense", enabled=True)
    assert exc.value.status_code == 400


def test_grant_is_upsert(session):
    org = _org(session)
    ent.grant_entitlement(session, org.id, key="bulk_export", enabled=True)
    ent.grant_entitlement(session, org.id, key="bulk_export", enabled=False)
    rows = ent.list_entitlements(session, org.id)
    assert len(rows) == 1
    assert rows[0].enabled is False
