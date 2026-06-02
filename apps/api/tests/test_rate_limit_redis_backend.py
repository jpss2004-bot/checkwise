"""M4 (2026-06-02) — Redis-backed rate limiter contract tests.

The point of the swap is *behavioural equivalence*: every existing
caller (login, forgot-password, share-unlock, ai-heavy, phone-verify)
keeps working byte-for-byte when ``REDIS_URL`` is set, and the
cross-worker correctness gap that the in-memory backend has under
horizontal scaling disappears.

These tests therefore parametrize the same scenarios against both
backends. The Redis branch uses ``fakeredis`` so we don't need a live
Redis server during CI; ``fakeredis`` implements the ZSET + EVAL
operations the Lua sliding window needs (verified inside this file
via a smoke test that the script returns 1/0 as expected).

The build_rate_limiter() factory is also covered: empty REDIS_URL →
in-memory; non-empty → Redis.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import fakeredis
import pytest

from app.core import rate_limit
from app.core.rate_limit import (
    InMemoryRateLimiter,
    RedisRateLimiter,
    SlidingWindowRateLimiter,
    build_rate_limiter,
)


# ─── Backend fixtures ─────────────────────────────────────────────


def _make_in_memory() -> InMemoryRateLimiter:
    return InMemoryRateLimiter()


def _make_redis() -> RedisRateLimiter:
    return RedisRateLimiter(fakeredis.FakeRedis())


BackendFactory = Callable[[], object]
BACKENDS: list[tuple[str, BackendFactory]] = [
    ("in_memory", _make_in_memory),
    ("redis", _make_redis),
]


@pytest.fixture(params=BACKENDS, ids=[name for name, _ in BACKENDS])
def limiter(request: pytest.FixtureRequest) -> Iterator[object]:
    _, factory = request.param
    instance = factory()
    yield instance
    instance.reset()


# ─── Contract: budget enforcement ────────────────────────────────


def test_check_admits_until_limit_then_rejects(limiter) -> None:
    """Both backends honour the exact ``limit`` value."""
    for i in range(5):
        assert limiter.check("k", limit=5, window_seconds=60), (
            f"Call {i} should have been admitted"
        )
    assert limiter.check("k", limit=5, window_seconds=60) is False


def test_zero_limit_is_treated_as_disabled(limiter) -> None:
    """limit=0 means "disabled" → always-allow on both backends."""
    for _ in range(50):
        assert limiter.check("k", limit=0, window_seconds=60) is True


def test_buckets_are_keyed_independently(limiter) -> None:
    """Filling one key must not bleed into another."""
    for _ in range(3):
        assert limiter.check("a", limit=3, window_seconds=60)
    assert limiter.check("a", limit=3, window_seconds=60) is False
    # ``b`` is still fresh.
    assert limiter.check("b", limit=3, window_seconds=60)


def test_reset_specific_key_clears_only_that_bucket(limiter) -> None:
    for _ in range(3):
        limiter.check("a", limit=3, window_seconds=60)
    for _ in range(3):
        limiter.check("b", limit=3, window_seconds=60)
    assert limiter.check("a", limit=3, window_seconds=60) is False
    assert limiter.check("b", limit=3, window_seconds=60) is False

    limiter.reset("a")
    assert limiter.check("a", limit=3, window_seconds=60) is True
    # ``b`` is untouched.
    assert limiter.check("b", limit=3, window_seconds=60) is False


def test_reset_all_clears_every_bucket(limiter) -> None:
    for _ in range(3):
        limiter.check("a", limit=3, window_seconds=60)
        limiter.check("b", limit=3, window_seconds=60)
    assert limiter.check("a", limit=3, window_seconds=60) is False
    assert limiter.check("b", limit=3, window_seconds=60) is False

    limiter.reset()
    assert limiter.check("a", limit=3, window_seconds=60) is True
    assert limiter.check("b", limit=3, window_seconds=60) is True


def test_short_window_admits_burst_after_expiry(limiter) -> None:
    """An event older than ``window_seconds`` should not count.

    Uses a sub-second window so the test runs quickly. Both backends
    bound their notion of "now" to a real clock (monotonic / wall);
    the assertion sleeps just past the window.
    """
    import time

    assert limiter.check("k", limit=2, window_seconds=0.2)
    assert limiter.check("k", limit=2, window_seconds=0.2)
    assert limiter.check("k", limit=2, window_seconds=0.2) is False
    time.sleep(0.25)
    # Window has passed; the bucket should be fresh again.
    assert limiter.check("k", limit=2, window_seconds=0.2)


# ─── Redis-specific guarantees ───────────────────────────────────


def test_redis_keys_are_namespaced() -> None:
    """The KEY_PREFIX keeps the limiter from colliding with unrelated
    data on a shared Redis instance."""
    client = fakeredis.FakeRedis()
    rl = RedisRateLimiter(client)
    rl.check("hello", limit=5, window_seconds=60)
    keys = {k.decode() for k in client.keys("*")}
    assert keys == {"cwrl:hello"}


def test_redis_check_is_atomic_via_lua() -> None:
    """The Lua script returns the bool semantics we depend on. Smoke
    test that fakeredis correctly implements EVAL/ZADD/ZCARD/
    ZREMRANGEBYSCORE — if any of those break in a future fakeredis
    upgrade this test fires before the limiter does."""
    client = fakeredis.FakeRedis()
    rl = RedisRateLimiter(client)
    assert rl.check("k", limit=1, window_seconds=60) is True
    assert rl.check("k", limit=1, window_seconds=60) is False


def test_redis_unique_members_let_burst_share_a_millisecond() -> None:
    """Two checks in the same millisecond must not collide on the
    ZSET member — otherwise the second one silently overwrites and
    the bucket counter undercounts."""
    client = fakeredis.FakeRedis()
    rl = RedisRateLimiter(client)
    # Hammer a high-limit bucket; if members collided, ZCARD would
    # plateau at 1 and the limit would never trip even though we've
    # done 50 calls.
    for _ in range(50):
        assert rl.check("k", limit=100, window_seconds=60)
    assert client.zcard("cwrl:k") == 50


# ─── Factory ─────────────────────────────────────────────────────


def test_build_rate_limiter_picks_in_memory_when_redis_url_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rate_limit.settings, "REDIS_URL", "")
    instance = build_rate_limiter()
    assert isinstance(instance, InMemoryRateLimiter)


def test_build_rate_limiter_picks_redis_when_url_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rate_limit.settings, "REDIS_URL", "redis://localhost:6379/0"
    )
    monkeypatch.setattr(rate_limit.settings, "REDIS_RATE_LIMIT_TIMEOUT_MS", 250)
    instance = build_rate_limiter()
    assert isinstance(instance, RedisRateLimiter)


def test_build_rate_limiter_strips_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A REDIS_URL of "   " (whitespace only) reads as unset, not as
    a malformed connection string."""
    monkeypatch.setattr(rate_limit.settings, "REDIS_URL", "   ")
    instance = build_rate_limiter()
    assert isinstance(instance, InMemoryRateLimiter)


# ─── Backwards-compat alias ──────────────────────────────────────


def test_sliding_window_alias_points_at_in_memory() -> None:
    """The legacy name imported by ``test_m3_rate_limits.py`` and a
    couple of older call-sites must still resolve to the in-memory
    class."""
    assert SlidingWindowRateLimiter is InMemoryRateLimiter
