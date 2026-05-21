"""Regression tests for the persona_type CHECK constraint + migration.

Pairs with:
- ``backend/alembic/versions/0013_canonicalize_persona_type.py``
  (runtime migration that canonicalizes existing rows + adds the
  CHECK to both tables on production Postgres).
- ``app.models.entities._PERSONA_TYPE_CHECK`` (the same constraint
  declared on the SQLAlchemy ``__table_args__`` so SQLite test
  fixtures get the same enforcement as production).
- ``app.core.compliance_catalog.normalize_persona_type`` (the
  runtime safety net that maps any legacy value the DB still
  carries — e.g. on a replica that's behind on migrations — to a
  canonical token).

The Jay Luna bug was a Mapped[str] column with no value constraint
accepting full-label variants like ``"persona_moral"`` that the
catalog filter then refused to match. The runtime normalizer landed
in commit f28ae44 to unblock the calendar at read time; this test
file pins the durable schema-level guard that makes new bad rows
impossible.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Client, ProviderWorkspace, Vendor, entities  # noqa: F401


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Maker = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Maker()
    try:
        yield session
    finally:
        session.close()


def _seed_client(db: Session) -> Client:
    client = Client(name="Test Client")
    db.add(client)
    db.flush()
    return client


# ---------------------------------------------------------------------------
# Canonical values pass.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("persona_type", ["moral", "fisica"])
def test_vendor_accepts_canonical_persona_type(
    db: Session, persona_type: str
) -> None:
    client = _seed_client(db)
    vendor = Vendor(
        client_id=client.id,
        name=f"Vendor {persona_type}",
        rfc=f"VND07041{persona_type[0]}AB1".upper(),
        persona_type=persona_type,
    )
    db.add(vendor)
    db.commit()
    assert vendor.persona_type == persona_type


@pytest.mark.parametrize("persona_type", ["moral", "fisica"])
def test_workspace_accepts_canonical_persona_type(
    db: Session, persona_type: str
) -> None:
    client = _seed_client(db)
    vendor = Vendor(
        client_id=client.id,
        name="V1",
        rfc=f"VND07041{persona_type[0]}AB1".upper(),
        persona_type="moral",  # vendor canonical regardless
    )
    db.add(vendor)
    db.flush()
    workspace = ProviderWorkspace(
        client_id=client.id,
        vendor_id=vendor.id,
        persona_type=persona_type,
        display_name="Workspace",
        access_token=f"token-{persona_type}",
    )
    db.add(workspace)
    db.commit()
    assert workspace.persona_type == persona_type


# ---------------------------------------------------------------------------
# Non-canonical values are rejected by the CHECK constraint.
# ---------------------------------------------------------------------------


_BAD_VARIANTS = [
    "persona_moral",
    "persona_fisica",
    "persona moral",
    "persona física",
    "MORAL",
    "Fisica",
    "FISICA",
    "PM",
    "pf",
    "  moral  ",  # whitespace — normalizer strips, DB does not
    "",  # empty string
    "not_a_real_value",
]


@pytest.mark.parametrize("bad_value", _BAD_VARIANTS)
def test_workspace_rejects_non_canonical_persona_type(
    db: Session, bad_value: str
) -> None:
    """The CHECK constraint on provider_workspaces.persona_type must
    reject every non-canonical variant. The runtime
    ``normalize_persona_type`` helper still maps these at read time
    on legacy data, but new writes have to be canonical."""
    client = _seed_client(db)
    vendor = Vendor(
        client_id=client.id,
        name="V",
        rfc="VND070412AB1",
        persona_type="moral",
    )
    db.add(vendor)
    db.flush()
    workspace = ProviderWorkspace(
        client_id=client.id,
        vendor_id=vendor.id,
        persona_type=bad_value,
        display_name="Workspace",
        access_token=f"token-{bad_value or 'empty'}",
    )
    db.add(workspace)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


@pytest.mark.parametrize("bad_value", _BAD_VARIANTS)
def test_vendor_rejects_non_canonical_persona_type(
    db: Session, bad_value: str
) -> None:
    client = _seed_client(db)
    vendor = Vendor(
        client_id=client.id,
        name="V",
        rfc="VND070412AB1",
        persona_type=bad_value,
    )
    db.add(vendor)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_vendor_accepts_null_persona_type(db: Session) -> None:
    """``vendors.persona_type`` is nullable. CHECK constraints in
    SQL pass UNKNOWN/NULL by default, so a NULL value is allowed
    even with the IN-list constraint applied. The
    ``provider_workspaces.persona_type`` column is NOT NULL so this
    case doesn't apply there."""
    client = _seed_client(db)
    vendor = Vendor(
        client_id=client.id,
        name="V",
        rfc="VND070412AB1",
        persona_type=None,
    )
    db.add(vendor)
    db.commit()
    assert vendor.persona_type is None


# ---------------------------------------------------------------------------
# Migration parity — the canonicalization SQL must match the runtime
# normalizer's mapping. If these ever diverge, the read-time fallback
# and the migration's canonicalization will disagree on the same
# input, producing subtle drift between staging and prod databases.
# ---------------------------------------------------------------------------


def test_migration_aliases_match_runtime_normalizer() -> None:
    """The migration declares ``_MORAL_ALIASES`` / ``_FISICA_ALIASES``
    as the lookup key set. The runtime normalizer uses
    ``_PERSONA_TYPE_ALIASES`` — a flat dict from key → canonical
    token. Pin that every key in the runtime dict appears in exactly
    one of the migration's tuples, and vice versa."""
    from app.core.compliance_catalog import _PERSONA_TYPE_ALIASES

    # Inline the migration's tuples so the test doesn't depend on
    # importing alembic at runtime.
    migration_moral = {
        "moral",
        "persona_moral",
        "persona moral",
        "pm",
    }
    migration_fisica = {
        "fisica",
        "física",
        "persona_fisica",
        "persona_física",
        "persona fisica",
        "persona física",
        "pf",
    }

    runtime_moral = {k for k, v in _PERSONA_TYPE_ALIASES.items() if v == "moral"}
    runtime_fisica = {k for k, v in _PERSONA_TYPE_ALIASES.items() if v == "fisica"}

    assert runtime_moral == migration_moral, (
        "compliance_catalog._PERSONA_TYPE_ALIASES['→moral'] drifted from "
        "migration 0013 _MORAL_ALIASES. Update both in lockstep."
    )
    assert runtime_fisica == migration_fisica, (
        "compliance_catalog._PERSONA_TYPE_ALIASES['→fisica'] drifted from "
        "migration 0013 _FISICA_ALIASES. Update both in lockstep."
    )
