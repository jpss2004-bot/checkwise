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


def test_empty_int_env_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render lets you save an env var with an empty value. Pydantic 2.13
    refuses to parse ``''`` as an int, so the boot fails. The Settings
    class normalizes empty strings to the declared default for any
    non-``str`` field, which keeps a blank dashboard cell from crashing
    alembic + uvicorn."""
    from app.core.config import Settings

    monkeypatch.setenv("AUTH_LOGIN_RATE_LIMIT_PER_MINUTE", "")
    monkeypatch.setenv("AUTH_FORGOT_PASSWORD_RATE_LIMIT_PER_HOUR", "")
    monkeypatch.setenv("SMTP_PORT", "")
    monkeypatch.setenv("AUTH_BCRYPT_ROUNDS", "")

    s = Settings()

    assert s.AUTH_LOGIN_RATE_LIMIT_PER_MINUTE == 10
    assert s.AUTH_FORGOT_PASSWORD_RATE_LIMIT_PER_HOUR == 5
    assert s.SMTP_PORT == 587
    assert s.AUTH_BCRYPT_ROUNDS == 12


def test_empty_str_env_stays_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty ``str`` env vars are deliberately preserved as ``""``. A
    contributor setting ``CORS_ORIGINS=""`` in production means "no
    allowed origins" — that's a strict choice the platform should not
    silently override with the localhost default."""
    from app.core.config import Settings

    monkeypatch.setenv("CORS_ORIGINS", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    s = Settings()

    assert s.CORS_ORIGINS == ""
    assert s.cors_origins_list == []
    assert s.ANTHROPIC_API_KEY == ""
