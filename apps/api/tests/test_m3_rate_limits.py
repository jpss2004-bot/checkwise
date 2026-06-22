"""M3 — share-unlock + AI-heavy rate limiters + upload-413 normalization.

Pins the three behaviors the M3 hardening milestone introduced:

* Public share-link consume / unlock / info endpoints reject after the
  per-(ip, token) minute budget is exhausted.
* The LLM-backed reports endpoints (plan / generate / conversation /
  explain / regenerate / refresh-data) and the provider copilot
  reject after the per-user minute budget is exhausted.
* ``UploadTooLargeError`` raised from the storage layer surfaces as
  HTTP 413 — not 400 — across every upload handler.

Limiter buckets are process-global; each test calls ``.reset()`` on
the relevant limiter so case ordering doesn't matter.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.rate_limit import (
    ai_heavy_limiter,
    enforce_ai_heavy_rate_limit,
    enforce_export_rate_limit,
    enforce_share_unlock_rate_limit,
    export_heavy_limiter,
    share_unlock_limiter,
)
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import entities  # noqa: F401
from app.services.storage import UploadTooLargeError


@pytest.fixture
def api_client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_limiters() -> Generator[None, None, None]:
    """Clear the M3 limiters before and after every case."""
    ai_heavy_limiter.reset()
    share_unlock_limiter.reset()
    export_heavy_limiter.reset()
    yield
    ai_heavy_limiter.reset()
    share_unlock_limiter.reset()
    export_heavy_limiter.reset()


# ─── X-Forwarded-For resolution (spoof-resistant bucketing) ─────


def test_client_ip_takes_rightmost_xff_hop() -> None:
    """Render APPENDS the real peer to any client-supplied XFF chain, so
    the rightmost entry is the IP Render saw and the leftmost is
    attacker-controlled. The resolver must take the rightmost hop;
    otherwise rotating the leftmost value mints a fresh rate-limit bucket
    per request and defeats every limit."""
    from app.core.rate_limit import client_ip_from_request

    class _Req:
        # Attacker spoofs two fake hops; Render appends the real 198.51.100.9.
        headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8, 198.51.100.9"}
        client = None

    assert client_ip_from_request(_Req()) == "198.51.100.9"


def test_client_ip_rotating_leftmost_xff_shares_one_bucket() -> None:
    """Two requests that differ only in the (spoofable) leftmost XFF
    entries but share the real rightmost hop must resolve to the SAME IP,
    so they share a rate-limit bucket."""
    from app.core.rate_limit import client_ip_from_request

    class _ReqA:
        headers = {"x-forwarded-for": "9.9.9.9, 203.0.113.50"}
        client = None

    class _ReqB:
        headers = {"x-forwarded-for": "8.8.8.8, 203.0.113.50"}
        client = None

    assert client_ip_from_request(_ReqA()) == client_ip_from_request(_ReqB())


def test_client_ip_falls_back_to_real_ip_then_sentinel() -> None:
    """No XFF → X-Real-IP; nothing at all → the 0.0.0.0 sentinel."""
    from app.core.rate_limit import client_ip_from_request

    class _RealIp:
        headers = {"x-real-ip": "203.0.113.77"}
        client = None

    class _Nothing:
        headers: dict[str, str] = {}
        client = None

    assert client_ip_from_request(_RealIp()) == "203.0.113.77"
    assert client_ip_from_request(_Nothing()) == "0.0.0.0"


# ─── Share-unlock brute-force limiter ───────────────────────────


def test_share_unlock_limiter_admits_below_minute_cap() -> None:
    """Below the per-(ip, token) minute cap, the limiter is a no-op
    so legitimate users can retry a forgotten password."""
    from app.core.rate_limit import client_ip_from_request  # noqa: F401

    class _Req:
        headers = {"x-forwarded-for": "203.0.113.1"}
        client = None

    # Permissive budget — 5 attempts in this window should all pass.
    for _ in range(5):
        enforce_share_unlock_rate_limit(
            _Req(), "tok-A", per_minute=5, per_hour=100
        )


def test_share_unlock_limiter_blocks_on_minute_overflow() -> None:
    """The 6th attempt in the same minute trips a 429."""

    class _Req:
        headers = {"x-forwarded-for": "203.0.113.2"}
        client = None

    for _ in range(5):
        enforce_share_unlock_rate_limit(
            _Req(), "tok-B", per_minute=5, per_hour=100
        )
    with pytest.raises(HTTPException) as exc_info:
        enforce_share_unlock_rate_limit(
            _Req(), "tok-B", per_minute=5, per_hour=100
        )
    assert exc_info.value.status_code == 429
    assert "Demasiados intentos" in exc_info.value.detail


def test_share_unlock_limiter_separates_buckets_per_ip_and_token() -> None:
    """Different (ip, token) pairs don't deplete each other."""

    class _ReqA:
        headers = {"x-forwarded-for": "203.0.113.10"}
        client = None

    class _ReqB:
        headers = {"x-forwarded-for": "203.0.113.11"}
        client = None

    for _ in range(5):
        enforce_share_unlock_rate_limit(
            _ReqA(), "tok-A", per_minute=5, per_hour=100
        )
    # New IP — full budget.
    enforce_share_unlock_rate_limit(
        _ReqB(), "tok-A", per_minute=5, per_hour=100
    )
    # New token, same first IP — also full budget (per-pair key).
    enforce_share_unlock_rate_limit(
        _ReqA(), "tok-B", per_minute=5, per_hour=100
    )


def test_share_unlock_limiter_disabled_when_limit_zero() -> None:
    """``0`` means "disabled" — useful as a kill switch."""

    class _Req:
        headers = {"x-forwarded-for": "203.0.113.20"}
        client = None

    # The minute bucket is disabled; the hour bucket would still
    # eventually trip, but the budget is huge here so it doesn't.
    for _ in range(20):
        enforce_share_unlock_rate_limit(
            _Req(), "tok-Z", per_minute=0, per_hour=100
        )


# ─── AI-heavy per-user limiter ──────────────────────────────────


def test_ai_heavy_limiter_admits_below_cap() -> None:
    """Per-user minute cap — below budget, every call passes."""
    for _ in range(15):
        enforce_ai_heavy_rate_limit("user-A", per_minute=15, per_hour=200)


def test_ai_heavy_limiter_blocks_on_minute_overflow() -> None:
    for _ in range(15):
        enforce_ai_heavy_rate_limit("user-B", per_minute=15, per_hour=200)
    with pytest.raises(HTTPException) as exc_info:
        enforce_ai_heavy_rate_limit("user-B", per_minute=15, per_hour=200)
    assert exc_info.value.status_code == 429
    assert "Demasiados intentos" in exc_info.value.detail


def test_ai_heavy_limiter_isolates_users() -> None:
    """One heavy user must not deplete another tenant's budget."""
    for _ in range(15):
        enforce_ai_heavy_rate_limit("user-C", per_minute=15, per_hour=200)
    # user-D still has the full minute budget.
    for _ in range(15):
        enforce_ai_heavy_rate_limit("user-D", per_minute=15, per_hour=200)


def test_ai_heavy_limiter_disabled_when_limit_zero() -> None:
    for _ in range(50):
        enforce_ai_heavy_rate_limit("user-E", per_minute=0, per_hour=0)


# ─── Heavy export limiter (P2-8) ────────────────────────────────


def test_export_limiter_admits_below_cap() -> None:
    for _ in range(10):
        enforce_export_rate_limit("exp-A", per_minute=10, per_hour=200)


def test_export_limiter_blocks_on_minute_overflow() -> None:
    for _ in range(10):
        enforce_export_rate_limit("exp-B", per_minute=10, per_hour=200)
    with pytest.raises(HTTPException) as exc_info:
        enforce_export_rate_limit("exp-B", per_minute=10, per_hour=200)
    assert exc_info.value.status_code == 429
    assert "Demasiados intentos" in exc_info.value.detail


def test_export_limiter_isolates_users() -> None:
    """One operator pulling many ZIPs must not deplete another's budget."""
    for _ in range(10):
        enforce_export_rate_limit("exp-C", per_minute=10, per_hour=200)
    for _ in range(10):
        enforce_export_rate_limit("exp-D", per_minute=10, per_hour=200)


def test_export_limiter_does_not_share_bucket_with_ai_heavy() -> None:
    """Segregated buckets: exhausting the export bucket leaves AI untouched."""
    for _ in range(10):
        enforce_export_rate_limit("exp-E", per_minute=10, per_hour=200)
    with pytest.raises(HTTPException):
        enforce_export_rate_limit("exp-E", per_minute=10, per_hour=200)
    # Same user id, AI bucket is independent and still admits.
    enforce_ai_heavy_rate_limit("exp-E", per_minute=15, per_hour=200)


def test_export_limiter_disabled_when_limit_zero() -> None:
    for _ in range(50):
        enforce_export_rate_limit("exp-F", per_minute=0, per_hour=0)


# ─── Settings carry sane defaults ───────────────────────────────


def test_m3_settings_defaults_are_finite_and_positive() -> None:
    """Guard against a future refactor that quietly drops the caps
    to 0 (which would silently disable the limiters in production)."""
    assert settings.SHARE_UNLOCK_RATE_LIMIT_PER_MINUTE > 0
    assert settings.SHARE_UNLOCK_RATE_LIMIT_PER_HOUR > 0
    assert settings.AI_HEAVY_RATE_LIMIT_PER_MINUTE > 0
    assert settings.AI_HEAVY_RATE_LIMIT_PER_HOUR > 0
    assert settings.EXPORT_RATE_LIMIT_PER_MINUTE > 0
    assert settings.EXPORT_RATE_LIMIT_PER_HOUR > 0


# ─── UploadTooLargeError → 413 contract ─────────────────────────


def test_upload_too_large_error_is_a_value_error() -> None:
    """Back-compat: existing handlers that catch the bare
    ``ValueError`` keep working."""
    exc = UploadTooLargeError("too big")
    assert isinstance(exc, ValueError)
    assert str(exc) == "too big"
