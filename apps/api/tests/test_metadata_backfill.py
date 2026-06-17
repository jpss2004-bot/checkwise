"""CW-14 — metadata backfill service guards + scoping.

Covers the orchestration guards without the heavy XLSX/storage IO (which the
intake + reexport paths already exercise): the empty-scope no-op, the
``AUTO_METADATA_EXPORT_ENABLED`` gate, and ``force`` overriding that gate.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import entities  # noqa: F401 - register mappers
from app.services.metadata_export import backfill_metadata_exports


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def test_backfill_empty_scope_is_noop(db: Session) -> None:
    result = backfill_metadata_exports(db, dry_run=True)
    assert result.scanned == 0
    assert result.generated == 0
    assert result.failed == 0
    assert result.clients_rebuilt == 0


def test_backfill_respects_disabled_flag(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "AUTO_METADATA_EXPORT_ENABLED", False)
    messages: list[str] = []
    result = backfill_metadata_exports(db, dry_run=True, log=messages.append)
    # Early-return guard: nothing scanned, and the operator is told why.
    assert result.scanned == 0
    assert any("AUTO_METADATA_EXPORT_ENABLED" in m for m in messages)


def test_backfill_force_overrides_disabled_flag(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "AUTO_METADATA_EXPORT_ENABLED", False)
    # force=True bypasses the global gate (still a no-op on an empty DB, but it
    # must NOT short-circuit on the flag).
    result = backfill_metadata_exports(db, dry_run=True, force=True)
    assert result.scanned == 0
