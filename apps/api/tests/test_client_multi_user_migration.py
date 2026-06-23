"""Migration 0037 — multi-user client orgs (primary backfill + seat cap).

Validates the *exact* SQL the migration ships (``_BACKFILL_PRIMARY_SQL``,
``_PRIMARY_INDEX_SQL``, ``_SEAT_BACKFILL_SQL``) against an in-memory
SQLite schema holding just the columns the migration touches — the same
verbatim-SQL discipline as ``test_unique_active_slot_migration``.

Covers:
* the backfill promotes exactly one primary per client org — the oldest
  active ``client_admin`` membership — and leaves internal/vendor orgs,
  inactive memberships and non-client_admin roles untouched;
* the partial unique index rejects a second *active* primary in the same
  org, while allowing primaries across different orgs, multiple
  non-primary members, and a successor primary after the old one is
  deactivated (predicate exempts ``status != 'active'``);
* the seat backfill sets 3 on ``kind='client'`` orgs only.

A second test class exercises the model-declared twin index through
``Base.metadata.create_all`` so the SQLite fixtures used by endpoint
tests are proven to enforce the same invariant as prod Postgres.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0037_client_multi_user.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m0037", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _make_schema():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """CREATE TABLE organizations(
                    id TEXT PRIMARY KEY,
                    kind TEXT,
                    seat_limit INTEGER
                )"""
            )
        )
        conn.execute(
            text(
                """CREATE TABLE memberships(
                    id TEXT PRIMARY KEY,
                    organization_id TEXT,
                    role TEXT,
                    status TEXT,
                    is_primary BOOLEAN NOT NULL DEFAULT 0,
                    created_at TEXT
                )"""
            )
        )
    return engine


def _org(conn, org_id: str, kind: str) -> None:
    conn.execute(
        text("INSERT INTO organizations (id, kind) VALUES (:i, :k)"),
        {"i": org_id, "k": kind},
    )


def _member(conn, member_id: str, org_id: str, *, role="client_admin",
            status="active", is_primary=False, created_at="2026-01-01") -> None:
    conn.execute(
        text(
            "INSERT INTO memberships "
            "(id, organization_id, role, status, is_primary, created_at) "
            "VALUES (:i, :o, :r, :s, :p, :c)"
        ),
        {"i": member_id, "o": org_id, "r": role, "s": status,
         "p": is_primary, "c": created_at},
    )


def _primaries(conn) -> list[str]:
    rows = conn.execute(
        text("SELECT id FROM memberships WHERE is_primary ORDER BY id")
    )
    return [r[0] for r in rows]


def test_backfill_promotes_oldest_active_client_admin_per_org():
    migration = _load_migration()
    engine = _make_schema()
    with engine.begin() as conn:
        # Client org with two active admins (hand-seeded edge case):
        # only the oldest becomes primary.
        _org(conn, "org-a", "client")
        _member(conn, "a-new", "org-a", created_at="2026-02-01")
        _member(conn, "a-old", "org-a", created_at="2026-01-01")
        # Inactive membership predates both — must be skipped.
        _member(conn, "a-gone", "org-a", status="removed",
                created_at="2025-12-01")
        # Standard 1:1 client org.
        _org(conn, "org-b", "client")
        _member(conn, "b-only", "org-b")
        # Internal org — untouched even though the role string matches
        # nothing; also guard a stray client_admin row on it.
        _org(conn, "org-i", "internal")
        _member(conn, "i-admin", "org-i", role="operations_admin")
        _member(conn, "i-stray", "org-i", role="client_admin")

    with engine.begin() as conn:
        conn.execute(text(migration._BACKFILL_PRIMARY_SQL))

    with engine.begin() as conn:
        assert _primaries(conn) == ["a-old", "b-only"]


def test_seat_backfill_caps_client_orgs_only():
    migration = _load_migration()
    engine = _make_schema()
    with engine.begin() as conn:
        _org(conn, "org-a", "client")
        _org(conn, "org-i", "internal")
        _org(conn, "org-v", "vendor")

    with engine.begin() as conn:
        conn.execute(text(migration._SEAT_BACKFILL_SQL))

    with engine.begin() as conn:
        rows = {
            r[0]: r[1]
            for r in conn.execute(
                text("SELECT id, seat_limit FROM organizations")
            )
        }
        assert rows == {"org-a": 3, "org-i": None, "org-v": None}


def test_primary_index_allows_one_active_primary_per_org():
    migration = _load_migration()
    engine = _make_schema()
    with engine.begin() as conn:
        _org(conn, "org-a", "client")
        _org(conn, "org-b", "client")
        _member(conn, "a-1", "org-a", is_primary=True)
        conn.execute(text(migration._PRIMARY_INDEX_SQL))

    # Allowed: non-primary members in the same org, a primary in a
    # different org, and a successor primary once the old one is no
    # longer active (predicate exempts status != 'active').
    with engine.begin() as conn:
        _member(conn, "a-2", "org-a")
        _member(conn, "a-3", "org-a")
        _member(conn, "b-1", "org-b", is_primary=True)
        conn.execute(
            text("UPDATE memberships SET status = 'removed' WHERE id = 'a-1'")
        )
        _member(conn, "a-4", "org-a", is_primary=True)

    # Rejected: a second active primary in an occupied org.
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            _member(conn, "a-dup", "org-a", is_primary=True)


def test_model_metadata_enforces_primary_invariant():
    """The model-declared twin index (sqlite_where) must enforce the
    same invariant under ``Base.metadata.create_all`` — that is what
    every endpoint-test fixture runs."""
    from app.db.base import Base
    from app.models.entities import Membership, Organization, User

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        org = Organization(name="Acme", kind="client", seat_limit=3)
        owner = User(email="owner@acme.mx", full_name="Owner")
        second = User(email="second@acme.mx", full_name="Second")
        session.add_all([org, owner, second])
        session.flush()
        session.add(
            Membership(
                user_id=owner.id,
                organization_id=org.id,
                role="client_admin",
                is_primary=True,
            )
        )
        session.commit()

        session.add(
            Membership(
                user_id=second.id,
                organization_id=org.id,
                role="client_admin",
                is_primary=True,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # Same user as a plain (non-primary) second seat is fine.
        session.add(
            Membership(
                user_id=second.id,
                organization_id=org.id,
                role="client_admin",
            )
        )
        session.commit()
