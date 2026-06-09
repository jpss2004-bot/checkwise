"""Migration 0036 — status CHECK constraints.

Validates the predicate the migration ships and guards the point-in-time
status list against enum drift. The migration's prod ALTER uses
``NOT VALID`` (Postgres); here we assert the same ``status IN (...)``
predicate accepts every valid status and rejects an out-of-enum one by
building a minimal SQLite table with the CHECK inline.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from app.constants.statuses import DocumentStatus

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0036_status_check_constraints.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m0036", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_check_list_matches_document_status_enum():
    migration = _load_migration()
    assert set(migration._STATUSES) == {s.value for s in DocumentStatus}, (
        "0036's CHECK list drifted from DocumentStatus — a status was "
        "added/removed; ship a new migration that updates the constraint."
    )


def test_status_check_predicate_accepts_valid_rejects_invalid():
    migration = _load_migration()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                f"CREATE TABLE t (id TEXT PRIMARY KEY, status TEXT "
                f"CHECK (status IN ({migration._in_list()})))"
            )
        )
    # Every enum value is accepted.
    with engine.begin() as conn:
        for i, s in enumerate(DocumentStatus):
            conn.execute(
                text("INSERT INTO t (id, status) VALUES (:i, :s)"),
                {"i": str(i), "s": s.value},
            )
    # An out-of-enum value is rejected.
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO t (id, status) VALUES ('bad', :s)"),
                {"s": "no_es_un_estado"},
            )
