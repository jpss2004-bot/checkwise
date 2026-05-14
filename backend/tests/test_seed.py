"""Tests for the catalog seed helper (Patch 2 of the Reconciliation series).

These tests do NOT go through Alembic; they call :func:`seed_catalog`
directly against a SQLite-in-memory session built with
``Base.metadata.create_all``. This isolates the seed logic from the
migration runner and verifies idempotency + correctness in isolation.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.seed import seed_catalog
from app.models import Institution, Requirement, RequirementVersion, entities  # noqa: F401


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_seed_inserts_all_institutions(session: Session) -> None:
    result = seed_catalog(session)
    assert result.institutions_inserted >= 5  # sat, imss, infonavit, stps_repse, interno_cliente
    codes = set(session.scalars(select(Institution.code)).all())
    for expected in {"sat", "imss", "infonavit", "stps_repse", "interno_cliente"}:
        assert expected in codes


def test_seed_inserts_known_onboarding_codes(session: Session) -> None:
    seed_catalog(session)
    codes = set(session.scalars(select(Requirement.code)).all())
    # Persona moral
    assert "ONB-CORP-M-001" in codes
    assert "ONB-CORP-M-002" in codes
    # Persona física
    assert "ONB-CORP-F-001" in codes
    assert "ONB-CORP-F-002" in codes
    # Shared
    assert "ONB-CONT-001" in codes
    assert "ONB-REPSE-001" in codes
    assert "ONB-PATR-001" in codes


def test_seed_inserts_recurring_codes_for_2026(session: Session) -> None:
    seed_catalog(session, years=(2026,))
    codes = set(session.scalars(select(Requirement.code)).all())
    # Sample REC codes across all four frequencies.
    sample_codes = [c for c in codes if c.startswith("REC-")]
    assert any(c.startswith("REC-IMSS-2026-") for c in sample_codes)
    assert any(c.startswith("REC-INFONAVIT-2026-") for c in sample_codes)
    assert any(c.startswith("REC-SAT-2026-") for c in sample_codes)
    assert any(c.startswith("REC-ACUSES-2026-") for c in sample_codes)
    # Annual code is well-known.
    assert "REC-SAT-2026-04-acuse-anual" in codes


def test_seed_creates_matching_version_1_for_every_requirement(session: Session) -> None:
    seed_catalog(session)
    req_count = len(session.scalars(select(Requirement.id)).all())
    version_count = len(
        session.scalars(
            select(RequirementVersion.id).where(RequirementVersion.version == 1)
        ).all()
    )
    assert version_count == req_count
    assert req_count > 0


def test_seed_is_idempotent(session: Session) -> None:
    first = seed_catalog(session)
    second = seed_catalog(session)
    assert first.institutions_inserted > 0
    assert first.requirements_inserted > 0
    assert first.requirement_versions_inserted > 0
    # Re-run inserts nothing.
    assert second.institutions_inserted == 0
    assert second.requirements_inserted == 0
    assert second.requirement_versions_inserted == 0


def test_seed_preserves_existing_institution_rows(session: Session) -> None:
    # Pre-existing institution should not be duplicated by the seed.
    session.add(Institution(code="sat", name="SAT (legacy)"))
    session.flush()
    result = seed_catalog(session)
    # sat is already there; seed must NOT insert a duplicate.
    sats = session.scalars(select(Institution).where(Institution.code == "sat")).all()
    assert len(sats) == 1
    # And the other institutions must still come in.
    assert result.institutions_inserted >= 4


def test_seed_does_not_alter_legacy_requirements(session: Session) -> None:
    """If a legacy free-text Requirement already exists for a non-canonical code,
    the seed must leave it alone."""
    # Create a legacy institution row.
    inst = Institution(code="sat", name="SAT")
    session.add(inst)
    session.flush()
    legacy = Requirement(
        code="REQ-SAT-MENSUAL-OPINION-CUMPLIMIENTO-SAT-POSITIV",
        name="Opinión de cumplimiento SAT positiva",
        institution_id=inst.id,
        load_type="mensual",
        frequency="mensual",
        risk_level="alto",
        current_version=1,
    )
    session.add(legacy)
    session.flush()
    legacy_id = legacy.id

    seed_catalog(session)

    still_there = session.scalar(select(Requirement).where(Requirement.id == legacy_id))
    assert still_there is not None
    assert still_there.code == legacy.code
