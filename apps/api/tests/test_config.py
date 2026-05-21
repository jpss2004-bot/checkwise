"""Config tests — focused on the URL normalization used to make Neon /
Render / Supabase paste-in URLs work without manual rewriting."""

from __future__ import annotations

import pytest

from app.core.config import _normalize_pg_url


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Drivers managed providers hand out
        (
            "postgresql://user:pw@ep-xx.us-east-1.aws.neon.tech/checkwise",
            "postgresql+psycopg://user:pw@ep-xx.us-east-1.aws.neon.tech/checkwise",
        ),
        # Heroku-style legacy scheme — psycopg 3 + SQLAlchemy reject this.
        (
            "postgres://user:pw@host/db",
            "postgresql+psycopg://user:pw@host/db",
        ),
        # Already-normalized URL is a no-op.
        (
            "postgresql+psycopg://user:pw@host:5432/db",
            "postgresql+psycopg://user:pw@host:5432/db",
        ),
        # Query string preserved (Neon pooled connections add ?sslmode=require).
        (
            "postgresql://user:pw@host/db?sslmode=require",
            "postgresql+psycopg://user:pw@host/db?sslmode=require",
        ),
        # Empty input is a no-op so the property can be called safely.
        ("", ""),
    ],
)
def test_normalize_pg_url(raw: str, expected: str) -> None:
    assert _normalize_pg_url(raw) == expected


def test_alembic_url_prefers_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(
        cfg.settings, "DATABASE_URL", "postgresql://pooled@host/db"
    )
    monkeypatch.setattr(
        cfg.settings, "DIRECT_DATABASE_URL", "postgresql://direct@host/db"
    )
    assert cfg.settings.alembic_url == "postgresql+psycopg://direct@host/db"


def test_alembic_url_falls_back_to_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(cfg.settings, "DATABASE_URL", "postgresql://only@host/db")
    monkeypatch.setattr(cfg.settings, "DIRECT_DATABASE_URL", "")
    assert cfg.settings.alembic_url == "postgresql+psycopg://only@host/db"
