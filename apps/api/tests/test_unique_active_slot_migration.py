"""Migration 0035 — de-dup backfill + slot-uniqueness index.

Validates the *exact* SQL the migration ships (``_DEDUP_SQL`` and the
unique-index definition from ``_CREATE_SQL``) against an in-memory
SQLite table holding just the columns the migration touches. The
migration's prod path uses ``CREATE INDEX CONCURRENTLY``; SQLite can't
do CONCURRENTLY, so the test strips that one keyword and asserts the
predicate + ``coalesce(period_key, '')`` expression behave identically.

Covers:
* the backfill chains pre-existing parallel-genesis rows so exactly one
  genesis (``supersedes_submission_id IS NULL``) remains per slot, oldest
  kept, newest still the lineage leaf (read-result-preserving);
* codeless legacy rows are left untouched and exempt from the index;
* onboarding (NULL period_key) duplicates collide via ``coalesce``;
* recurring same-period duplicates collide; different periods don't;
* superseding rows never count as a second genesis.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0035_unique_active_slot.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m0035", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _make_table():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """CREATE TABLE submissions(
                    id TEXT PRIMARY KEY,
                    client_id TEXT, vendor_id TEXT,
                    requirement_code TEXT, period_key TEXT,
                    supersedes_submission_id TEXT,
                    created_at TEXT
                )"""
            )
        )
    return engine


def _insert(conn, **row):
    cols = ", ".join(row)
    binds = ", ".join(f":{k}" for k in row)
    conn.execute(text(f"INSERT INTO submissions ({cols}) VALUES ({binds})"), row)


def _genesis(conn, slot_code: str) -> list[str]:
    rows = conn.execute(
        text(
            "SELECT id FROM submissions WHERE requirement_code = :c "
            "AND supersedes_submission_id IS NULL ORDER BY id"
        ),
        {"c": slot_code},
    )
    return [r[0] for r in rows]


def test_dedup_backfill_collapses_parallel_genesis():
    migration = _load_migration()
    engine = _make_table()
    with engine.begin() as conn:
        # Three parallel-genesis rows for one recurring slot...
        _insert(conn, id="a", client_id="C", vendor_id="V", requirement_code="REC-1",
                period_key="2026-01", supersedes_submission_id=None, created_at="2026-01-01")
        _insert(conn, id="b", client_id="C", vendor_id="V", requirement_code="REC-1",
                period_key="2026-01", supersedes_submission_id=None, created_at="2026-01-02")
        _insert(conn, id="c", client_id="C", vendor_id="V", requirement_code="REC-1",
                period_key="2026-01", supersedes_submission_id=None, created_at="2026-01-03")
        # ...two parallel onboarding genesis (NULL period)...
        _insert(conn, id="o1", client_id="C", vendor_id="V", requirement_code="ONB-1",
                period_key=None, supersedes_submission_id=None, created_at="2026-01-01")
        _insert(conn, id="o2", client_id="C", vendor_id="V", requirement_code="ONB-1",
                period_key=None, supersedes_submission_id=None, created_at="2026-01-02")
        # ...a single-genesis slot (must be untouched)...
        _insert(conn, id="s1", client_id="C", vendor_id="V", requirement_code="REC-2",
                period_key="2026-01", supersedes_submission_id=None, created_at="2026-01-01")
        # ...and a codeless legacy row (exempt, untouched).
        _insert(conn, id="z", client_id="C", vendor_id="V", requirement_code=None,
                period_key=None, supersedes_submission_id=None, created_at="2026-01-01")

    with engine.begin() as conn:
        conn.execute(text(migration._DEDUP_SQL))

    with engine.begin() as conn:
        # Exactly one genesis per duplicated slot — the oldest.
        assert _genesis(conn, "REC-1") == ["a"]
        assert _genesis(conn, "ONB-1") == ["o1"]
        # Newest stays the lineage leaf (nobody supersedes it).
        superseded = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT supersedes_submission_id FROM submissions "
                    "WHERE supersedes_submission_id IS NOT NULL"
                )
            )
        }
        rec1_ids = {"a", "b", "c"}
        rec1_leaves = rec1_ids - superseded
        assert rec1_leaves == {"c"}
        # Single-genesis + codeless rows untouched.
        assert _genesis(conn, "REC-2") == ["s1"]
        z_sup = conn.execute(
            text("SELECT supersedes_submission_id FROM submissions WHERE id='z'")
        ).scalar()
        assert z_sup is None


def _create_index(conn, migration):
    ddl = migration._CREATE_SQL.replace("CONCURRENTLY ", "")
    conn.execute(text(ddl))


def test_unique_index_rejects_duplicate_genesis_only():
    migration = _load_migration()
    engine = _make_table()
    with engine.begin() as conn:
        _insert(conn, id="a", client_id="C", vendor_id="V", requirement_code="REC-1",
                period_key="2026-01", supersedes_submission_id=None, created_at="1")
        _insert(conn, id="o1", client_id="C", vendor_id="V", requirement_code="ONB-1",
                period_key=None, supersedes_submission_id=None, created_at="1")
        _create_index(conn, migration)

    # Allowed: supersede, different period, codeless x2, different slot.
    with engine.begin() as conn:
        _insert(conn, id="a2", client_id="C", vendor_id="V", requirement_code="REC-1",
                period_key="2026-01", supersedes_submission_id="a", created_at="2")
        _insert(conn, id="a3", client_id="C", vendor_id="V", requirement_code="REC-1",
                period_key="2026-02", supersedes_submission_id=None, created_at="3")
        _insert(conn, id="z1", client_id="C", vendor_id="V", requirement_code=None,
                period_key=None, supersedes_submission_id=None, created_at="1")
        _insert(conn, id="z2", client_id="C", vendor_id="V", requirement_code=None,
                period_key=None, supersedes_submission_id=None, created_at="1")

    # Rejected: a second recurring genesis for the occupied (REC-1, 2026-01) slot.
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert(conn, id="dup", client_id="C", vendor_id="V", requirement_code="REC-1",
                    period_key="2026-01", supersedes_submission_id=None, created_at="9")

    # Rejected: a second onboarding genesis (NULL period collapses via coalesce).
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _insert(conn, id="odup", client_id="C", vendor_id="V", requirement_code="ONB-1",
                    period_key=None, supersedes_submission_id=None, created_at="9")
