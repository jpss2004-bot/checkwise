"""Phase B4 — purge_org: irreversible hard-delete of a demo tenant.

Verifies the cascade deletes the tenant's data + storage blobs, anonymizes its
users, and never touches a user still active in another org.
"""

from __future__ import annotations

import itertools

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    Client,
    Document,
    Membership,
    Organization,
    ProviderWorkspace,
    Submission,
    User,
    Vendor,
)
from app.services.org_purge import purge_org

_seq = itertools.count(1)


class FakeStorage:
    def __init__(self):
        self.deleted: list[str] = []

    def delete(self, key: str) -> None:
        self.deleted.append(key)


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


def _seed_demo_tenant(db, *, status="frozen"):
    seq = next(_seq)
    client = Client(name=f"Demo {seq}")
    db.add(client)
    db.flush()
    org = Organization(
        name=f"Demo {seq}", kind="client", client_id=client.id,
        plan="demo", status=status,
    )
    db.add(org)
    db.flush()
    member = User(email=f"owner-{seq}@x.test", password_hash="h",
                  full_name="Owner", status="active")
    provider_user = User(email=f"prov-{seq}@x.test", password_hash="h",
                         full_name="Prov", status="active")
    db.add_all([member, provider_user])
    db.flush()
    db.add(Membership(user_id=member.id, organization_id=org.id,
                      role="client_admin", is_primary=True, status="active"))
    vendor = Vendor(client_id=client.id, name="V", rfc=f"PRG{seq:09d}",
                    persona_type="moral", status="active")
    db.add(vendor)
    db.flush()
    ws = ProviderWorkspace(client_id=client.id, vendor_id=vendor.id,
                           owner_user_id=provider_user.id, persona_type="moral",
                           access_token=f"tok-{seq}", status="active")
    db.add(ws)
    db.flush()
    sub = Submission(client_id=client.id, vendor_id=vendor.id, period_id="p",
                     institution_id="i", requirement_id="r", load_type="manual")
    db.add(sub)
    db.flush()
    doc = Document(submission_id=sub.id, storage_key=f"blob/{seq}.pdf",
                   original_filename="f.pdf", size_bytes=1, sha256="abc")
    db.add(doc)
    db.commit()
    return {
        "org": org, "org_id": org.id, "client_id": client.id, "vendor_id": vendor.id,
        "ws_id": ws.id, "member_id": member.id, "provider_id": provider_user.id,
        "doc_key": f"blob/{seq}.pdf",
    }


def test_purge_deletes_tenant_and_anonymizes_users(session):
    ctx = _seed_demo_tenant(session)
    storage = FakeStorage()
    result = purge_org(session, ctx["org"], storage=storage)
    session.commit()

    assert ctx["doc_key"] in storage.deleted
    assert session.get(Organization, ctx["org_id"]) is None
    assert session.get(Client, ctx["client_id"]) is None
    assert session.get(Vendor, ctx["vendor_id"]) is None
    assert session.get(ProviderWorkspace, ctx["ws_id"]) is None

    member = session.get(User, ctx["member_id"])
    provider = session.get(User, ctx["provider_id"])
    for u in (member, provider):
        assert u.status == "disabled"
        assert u.deleted_at is not None
        assert u.email.startswith("purged-")
        assert u.password_hash == ""
    assert result.counts.get("Vendor") == 1
    assert result.counts.get("storage_blobs") == 1


def test_purge_keeps_multi_org_user(session):
    ctx = _seed_demo_tenant(session)
    # Give the member a second active membership in another (untouched) org.
    other = Organization(name="Other", kind="client", plan="standard")
    session.add(other)
    session.flush()
    session.add(Membership(user_id=ctx["member_id"], organization_id=other.id,
                           role="client_admin", status="active"))
    session.commit()

    purge_org(session, ctx["org"], storage=FakeStorage())
    session.commit()

    member = session.get(User, ctx["member_id"])
    assert member.status == "active"  # still active elsewhere → NOT anonymized
    assert not member.email.startswith("purged-")
