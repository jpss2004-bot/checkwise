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


# ---------------------------------------------------------------------------
# Audit P4-01 (2026-05-25) — AUTH_JWT_SECRET placeholder boot guard
# ---------------------------------------------------------------------------


def test_boot_guard_passes_in_local_with_placeholder() -> None:
    """The placeholder secret is fine in local — the validator's
    contract is "non-local must override" and local stays unblocked
    so dev workflows keep working without env files."""
    from app.core.config import Settings, _validate_boot_security

    s = Settings(
        CHECKWISE_ENV="local",
        AUTH_JWT_SECRET="checkwise-local-dev-secret-change-me-please-min-32-chars",
    )
    # No raise.
    _validate_boot_security(s)


def test_boot_guard_raises_on_placeholder_in_production() -> None:
    """The committed placeholder cannot reach a non-local deploy.
    Refusing to boot is correct here — silently shipping the public
    secret would let anyone mint admin JWTs."""
    from app.core.config import (
        InsecureBootError,
        Settings,
        _validate_boot_security,
    )

    s = Settings(
        CHECKWISE_ENV="production",
        AUTH_JWT_SECRET="checkwise-local-dev-secret-change-me-please-min-32-chars",
    )
    with pytest.raises(InsecureBootError):
        _validate_boot_security(s)


def test_boot_guard_raises_on_short_secret_in_production() -> None:
    """A non-placeholder but too-short secret (covers empty + weak) must
    also refuse to boot in production — the placeholder check only catches
    the exact committed string, so a blank or 1-char dashboard value would
    otherwise sign every JWT with a brute-forceable key (FIX 2)."""
    from app.core.config import (
        InsecureBootError,
        Settings,
        _validate_boot_security,
    )

    for weak in ("", "x", "short-secret"):
        s = Settings(CHECKWISE_ENV="production", AUTH_JWT_SECRET=weak)
        with pytest.raises(InsecureBootError):
            _validate_boot_security(s)


def test_boot_guard_passes_with_real_secret_in_production() -> None:
    """A secret that isn't the in-code placeholder is allowed even in
    production — the guard intentionally trips on the *known* leaked
    string only, not on every weak value."""
    from app.core.config import Settings, _validate_boot_security

    s = Settings(
        CHECKWISE_ENV="production",
        AUTH_JWT_SECRET="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
    )
    _validate_boot_security(s)


def test_boot_guard_warns_on_localhost_frontend_url_in_production(caplog) -> None:
    """A non-local deploy that still points FRONTEND_BASE_URL at
    localhost gets a loud warning so it shows up on first start —
    audit P2-05 (2026-05-25). Soft warning, not a fatal error, so a
    deploy intentionally running without outbound email still boots."""
    import logging

    from app.core.config import Settings, _validate_boot_security

    s = Settings(
        CHECKWISE_ENV="production",
        AUTH_JWT_SECRET="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
        FRONTEND_BASE_URL="http://localhost:3000",
    )
    with caplog.at_level(logging.WARNING, logger="checkwise.config"):
        _validate_boot_security(s)
    messages = [r.getMessage() for r in caplog.records]
    assert any("FRONTEND_BASE_URL" in m for m in messages)


def test_boot_guard_silent_on_production_frontend_url(caplog) -> None:
    """A real production URL must not trigger the warning."""
    import logging

    from app.core.config import Settings, _validate_boot_security

    s = Settings(
        CHECKWISE_ENV="production",
        AUTH_JWT_SECRET="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
        FRONTEND_BASE_URL="https://app.checkwise.mx",
    )
    with caplog.at_level(logging.WARNING, logger="checkwise.config"):
        _validate_boot_security(s)
    assert all("FRONTEND_BASE_URL" not in r.getMessage() for r in caplog.records)
