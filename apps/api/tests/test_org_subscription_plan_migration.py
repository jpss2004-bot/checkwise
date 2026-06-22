"""Migration 0056 — subscription plan + provider cap on client orgs.

Validates the exact backfill SQL against an in-memory SQLite schema (the
same verbatim-SQL discipline as ``test_client_multi_user_migration``), and
that the model-declared columns exist under ``Base.metadata.create_all`` —
the schema every endpoint-test fixture runs.
"""

from __future__ import annotations

import importlib.util
import pathlib

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0056_org_subscription_plan.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m0056", _MIGRATION_PATH)
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
                    plan TEXT,
                    provider_limit INTEGER,
                    demo_expires_at TEXT
                )"""
            )
        )
    return engine


def _org(conn, org_id: str, kind: str) -> None:
    conn.execute(
        text("INSERT INTO organizations (id, kind) VALUES (:i, :k)"),
        {"i": org_id, "k": kind},
    )


def test_backfill_tags_client_orgs_legacy_only():
    migration = _load_migration()
    engine = _make_schema()
    with engine.begin() as conn:
        _org(conn, "org-a", "client")
        _org(conn, "org-b", "client")
        _org(conn, "org-i", "internal")
        _org(conn, "org-v", "vendor")

    with engine.begin() as conn:
        conn.execute(text(migration._BACKFILL_PLAN_SQL))

    with engine.begin() as conn:
        rows = {
            r[0]: r[1]
            for r in conn.execute(text("SELECT id, plan FROM organizations"))
        }
    assert rows == {
        "org-a": "legacy",
        "org-b": "legacy",
        "org-i": None,
        "org-v": None,
    }


def test_backfill_leaves_provider_limit_null():
    """Grandfathered clients must stay UNCAPPED (provider_limit NULL)."""
    migration = _load_migration()
    engine = _make_schema()
    with engine.begin() as conn:
        _org(conn, "org-a", "client")
    with engine.begin() as conn:
        conn.execute(text(migration._BACKFILL_PLAN_SQL))
    with engine.begin() as conn:
        val = conn.execute(
            text("SELECT provider_limit FROM organizations WHERE id = 'org-a'")
        ).scalar()
    assert val is None


def test_model_metadata_has_plan_columns():
    from app.db.base import Base
    from app.models.entities import Organization  # noqa: F401 — register mapper

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("organizations")}
    assert {"plan", "provider_limit", "demo_expires_at"} <= cols


def test_plan_values_match_plan_enum():
    """The migration's hardcoded CHECK values must match the live Plan enum,
    or a future tier would pass tests then be rejected by the Postgres CHECK
    at deploy time (mirrors migration 0036's enum-match discipline)."""
    from app.constants.plans import Plan

    migration = _load_migration()
    assert set(migration._PLAN_VALUES) == {p.value for p in Plan}
