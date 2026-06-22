"""Sliding-window rate limiter with pluggable backing store.

Used by the auth router (login, forgot-password), the public share-
link consume / unlock endpoints, the LLM-backed reports + provider
copilot endpoints, and the phone-verification OTP issuer.
Conservative defaults trade a small UX cost for protection against
credential stuffing, reset-link enumeration / mail-bombing, share-
link brute-force, runaway LLM cost, and OTP-send abuse.

== Backend selection (M4 — 2026-06-02) ==

The original implementation kept counters in a per-process
``dict`` + ``deque`` — correct on Render's single-worker starter
tier, but silently broken on every additional worker because each
process kept its own buckets (audit P4-13 — 2026-05-25).

The module now exposes two implementations behind a common
``RateLimiterBackend`` protocol:

* :class:`InMemoryRateLimiter` — the original sliding window. Picks
  ``time.monotonic`` because the bucket is bound to one process.
* :class:`RedisRateLimiter` — a Lua-script sliding window stored in
  Redis. Atomic check-then-add (the script is evaluated server-side,
  no race between ``ZCARD`` and ``ZADD``). Cluster-wide.

:func:`build_rate_limiter` reads ``settings.REDIS_URL`` and returns
the right one. Module-level singletons are constructed via the
factory so every call-site keeps its existing import:
``from app.core.rate_limit import login_limiter``. The legacy
``SlidingWindowRateLimiter`` name is kept as an alias for the
existing tests and any third-party importers.
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Protocol

import redis
from fastapi import HTTPException, Request, status

from app.core.config import settings


class RateLimiterBackend(Protocol):
    """Minimal interface a rate-limit store must implement."""

    def check(self, key: str, *, limit: int, window_seconds: float) -> bool:
        """Record a request for ``key`` and return True if within budget."""

    def reset(self, key: str | None = None) -> None:
        """Drop one bucket or all of them. Test hook."""


# ---------------------------------------------------------------------------
# In-memory implementation (single-worker only).
# ---------------------------------------------------------------------------


class InMemoryRateLimiter:
    """Sliding-window counter keyed by an opaque bucket string.

    Correct on a single uvicorn worker. On a multi-worker deploy
    each process keeps its own counters, so the effective per-
    cluster cap scales with worker count. Provision Redis and set
    ``REDIS_URL`` before scaling horizontally.
    """

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, *, limit: int, window_seconds: float) -> bool:
        if limit <= 0:
            # 0 means "disabled" → always allow.
            return True
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)


# Backwards-compat alias — existing tests and a couple of call-sites
# still import this name.
SlidingWindowRateLimiter = InMemoryRateLimiter


# ---------------------------------------------------------------------------
# Redis implementation (shared across workers + hosts).
# ---------------------------------------------------------------------------


# Sliding-window Lua. Atomic check-then-add inside Redis: prunes
# entries older than ``now - window``, returns 0 if the bucket is
# full, otherwise adds the entry (with a unique member to avoid
# ZSET collisions inside the same millisecond) and returns 1. Sets
# the key's TTL to the window so abandoned buckets self-clean.
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count < limit then
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, math.ceil(window))
    return 1
end
return 0
"""


class RedisRateLimiter:
    """Sliding-window counter backed by Redis sorted sets.

    Fail-closed: if Redis is unreachable the ``check()`` call
    propagates a :class:`redis.RedisError`, which the FastAPI
    exception handler turns into a 500. Better to surface a Redis
    outage as alert-triggering 500s than to silently fall back to
    "always allow" and disable the limiter cluster-wide.

    Key namespace: every key is prefixed with ``cwrl:`` so a shared
    Redis instance hosting unrelated data can still be safely used.

    The Lua script is registered once per process via
    ``redis.register_script``; the client transparently retries
    with ``EVAL`` on ``NOSCRIPT`` if Redis flushes its script cache.
    """

    KEY_PREFIX = "cwrl:"

    def __init__(
        self,
        client: redis.Redis,
        *,
        member_counter_start: int = 0,
    ) -> None:
        self._client = client
        self._script = client.register_script(_SLIDING_WINDOW_LUA)
        # Monotonic per-instance counter that lets the Lua script add
        # multiple events in the same millisecond without collision.
        # Wraps via modulo — the value is opaque, only uniqueness in
        # the window matters.
        self._counter = member_counter_start
        self._counter_lock = Lock()

    def _next_member(self, now_ms: int) -> str:
        with self._counter_lock:
            self._counter = (self._counter + 1) % 1_000_000
            return f"{now_ms}:{self._counter}"

    def check(self, key: str, *, limit: int, window_seconds: float) -> bool:
        if limit <= 0:
            return True
        # Wall-clock seconds — shared backend means every worker must
        # use the same time source. The 60s / 3600s windows are loose
        # enough that any reasonable clock skew across workers
        # (NTP-synced) is well below the window precision.
        now = time.time()
        now_ms = int(now * 1000)
        member = self._next_member(now_ms)
        full_key = self.KEY_PREFIX + key
        result = self._script(
            keys=[full_key],
            args=[now, window_seconds, limit, member],
        )
        return bool(result)

    def reset(self, key: str | None = None) -> None:
        if key is None:
            # Drop every key in our namespace. SCAN+DEL because KEYS
            # on a large keyspace blocks the Redis main thread.
            cursor = 0
            while True:
                cursor, batch = self._client.scan(
                    cursor=cursor,
                    match=self.KEY_PREFIX + "*",
                    count=500,
                )
                if batch:
                    self._client.delete(*batch)
                if cursor == 0:
                    break
            return
        self._client.delete(self.KEY_PREFIX + key)


# ---------------------------------------------------------------------------
# Factory.
# ---------------------------------------------------------------------------


def build_rate_limiter() -> RateLimiterBackend:
    """Return the right backend for the current configuration.

    Empty ``REDIS_URL`` → in-memory (the default for local dev and
    Render's single-worker plan). Any non-empty value is passed
    through to ``redis.Redis.from_url`` and used to construct a
    shared backend. The connection is lazy — the client is created
    here but no socket opens until the first ``check()`` call.
    """
    url = (settings.REDIS_URL or "").strip()
    if not url:
        return InMemoryRateLimiter()
    timeout_s = settings.REDIS_RATE_LIMIT_TIMEOUT_MS / 1000.0
    client = redis.Redis.from_url(
        url,
        socket_timeout=timeout_s,
        socket_connect_timeout=timeout_s,
        decode_responses=False,
    )
    return RedisRateLimiter(client)


# ---------------------------------------------------------------------------
# Module-level singletons.
#
# Limiters are segregated so the buckets don't cross-deplete (a
# login attempt should not consume a share-unlock budget, etc.).
# When Redis is configured each singleton still gets its own
# instance — the Lua script's atomicity is per-key, not per-client,
# so a single client would be functionally equivalent but the
# per-purpose instances make the namespace explicit.
# ---------------------------------------------------------------------------


login_limiter = build_rate_limiter()
forgot_password_limiter = build_rate_limiter()
# M3 (2026-05-25) — brute-force protection on the public share-link
# password unlock endpoint. Buckets keyed by (ip, token_hash) so a
# single attacker can't grind through one share's password by
# rotating tokens, AND a single token's attempts get capped across
# any IPs that contribute. The consume + info endpoints share this
# limiter to defend against token enumeration too.
share_unlock_limiter = build_rate_limiter()
# M3 (2026-05-25) — per-user cap on LLM-backed reports endpoints
# (generate / plan / refresh-data / conversation / explain /
# regenerate) + the provider portal's wise/ask copilot. Without
# this, a runaway client or curious operator can drive Anthropic
# costs unbounded. Per-user buckets so one heavy user can't
# starve another tenant.
ai_heavy_limiter = build_rate_limiter()
# Phase 7 / Slice N8 — cap on phone-verification OTP issuance.
# Buckets keyed by ``user_id`` so a single user cannot brute-force
# the WhatsApp send pipeline (each issuance is a paid Meta API
# call). Defaults configured at the call site in ``app.api.v1.me``.
phone_verify_limiter = build_rate_limiter()
# Cap on heavy file-export endpoints: the client/provider audit-package and
# expediente ZIPs stream up to hundreds of files / hundreds of MB and render a
# Chromium-backed manifest PDF. Without this an authenticated operator can
# repeatedly trigger them as a resource-exhaustion lever (perf audit P2-8).
# Per-user buckets, segregated from ai_heavy so a ZIP burst can't starve Wise.
export_heavy_limiter = build_rate_limiter()


def hash_identifier(value: str) -> str:
    """Stable short hash for an IP or email. Avoid putting plaintext in
    bucket keys so dumping the in-memory state for debugging does not
    expose user identifiers."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Shared helpers — keep the auth-side wording in lockstep with M2.
# ---------------------------------------------------------------------------


_RATE_LIMITED_DETAIL = (
    "Demasiados intentos. Espera unos minutos antes de volver a intentar."
)


def client_ip_from_request(request: Request) -> str:
    """Best-effort client IP for rate-limit bucketing.

    Takes the RIGHTMOST ``X-Forwarded-For`` entry because Render
    terminates TLS in front of uvicorn and *appends* the real peer to
    any client-supplied chain — so the leftmost entry is attacker-
    controlled (rotating it would mint a fresh bucket per request and
    defeat every rate limit) while the rightmost is the IP Render saw.
    With Render's single trusted proxy in front, that last hop is the
    real client. Falls back to ``X-Real-IP`` then to the direct socket
    peer. Never authoritative for authorization — bucket keys only.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        last = xff.split(",")[-1].strip()
        if last:
            return last
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    if request.client and request.client.host:
        return request.client.host
    return "0.0.0.0"


def enforce_share_unlock_rate_limit(
    request: Request,
    token: str,
    *,
    per_minute: int,
    per_hour: int,
) -> None:
    """Throttle public share-link consume / unlock attempts.

    Two complementary buckets:

    * ``per_minute`` keyed by ``(ip, token_hash)`` so a legitimate
      user can retype a forgotten password a handful of times in a
      minute without locking themselves out, but a single attacker
      grinding one share's password is capped tight.
    * ``per_hour`` keyed by ``ip`` only so an attacker rotating
      across many tokens from one source still trips a slow brute-
      force cap.

    Raises HTTP 429 with the standard Spanish detail when either
    bucket is exhausted. Setting either limit to 0 disables that
    bucket.
    """
    ip = client_ip_from_request(request)
    ip_h = hash_identifier(ip)
    token_h = hash_identifier(token)
    ok_pair = share_unlock_limiter.check(
        f"share:ip-token:{ip_h}:{token_h}",
        limit=per_minute,
        window_seconds=60,
    )
    ok_ip = share_unlock_limiter.check(
        f"share:ip:{ip_h}",
        limit=per_hour,
        window_seconds=3600,
    )
    if not ok_pair or not ok_ip:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_RATE_LIMITED_DETAIL,
        )


def enforce_ai_heavy_rate_limit(
    user_id: str,
    *,
    per_minute: int,
    per_hour: int,
) -> None:
    """Throttle LLM-backed reports + copilot endpoints.

    Per-user buckets so one heavy operator doesn't starve another
    tenant. The minute bucket bounds burst cost (one runaway loop);
    the hour bucket bounds sustained cost (a scripted scrape).
    Raises HTTP 429 with the standard Spanish detail when either
    bucket is exhausted. Either limit at 0 disables that bucket.
    """
    user_h = hash_identifier(user_id)
    ok_minute = ai_heavy_limiter.check(
        f"ai:user-min:{user_h}",
        limit=per_minute,
        window_seconds=60,
    )
    ok_hour = ai_heavy_limiter.check(
        f"ai:user-hour:{user_h}",
        limit=per_hour,
        window_seconds=3600,
    )
    if not ok_minute or not ok_hour:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_RATE_LIMITED_DETAIL,
        )


def enforce_export_rate_limit(
    user_id: str,
    *,
    per_minute: int,
    per_hour: int,
) -> None:
    """Throttle heavy ZIP / manifest-PDF export endpoints.

    Per-user buckets so one operator repeatedly pulling large packages can't
    exhaust the worker pool for other tenants. The minute bucket bounds bursts;
    the hour bucket bounds a sustained scrape. Raises HTTP 429 with the standard
    Spanish detail when either bucket is exhausted. Either limit at 0 disables
    that bucket.
    """
    user_h = hash_identifier(user_id)
    ok_minute = export_heavy_limiter.check(
        f"export:user-min:{user_h}",
        limit=per_minute,
        window_seconds=60,
    )
    ok_hour = export_heavy_limiter.check(
        f"export:user-hour:{user_h}",
        limit=per_hour,
        window_seconds=3600,
    )
    if not ok_minute or not ok_hour:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_RATE_LIMITED_DETAIL,
        )
