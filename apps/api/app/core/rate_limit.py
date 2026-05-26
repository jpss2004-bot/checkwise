"""In-memory sliding-window rate limiter.

Used by the auth router (login, forgot-password). Conservative defaults
trade a small UX cost for protection against credential stuffing and
reset-link enumeration / mail-bombing.

Scaling note (audit P4-13 — 2026-05-25): the limiter is process-local.
Each worker keeps its own counters, so the effective per-cluster cap
scales with worker count — a multi-worker deploy is more permissive
than the configured values imply. Acceptable on Render's single-
worker starter tier; before horizontal scale, swap this for Redis
(or another shared store) so the limit is enforced across workers.
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    """Sliding-window counter keyed by an opaque bucket string."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, *, limit: int, window_seconds: float) -> bool:
        """Record a request for ``key`` and return True if it is within budget.

        ``limit`` is the maximum number of events allowed inside the
        most recent ``window_seconds``-second window. Returns False when
        the budget is exhausted; the caller should translate to HTTP 429.
        """
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
        """Test hook: drop one bucket or all of them."""
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)


# Module-level shared instances. Limiters are segregated so the
# buckets don't cross-deplete (a login attempt should not consume a
# share-unlock budget, etc.).
login_limiter = SlidingWindowRateLimiter()
forgot_password_limiter = SlidingWindowRateLimiter()
# M3 (2026-05-25) — brute-force protection on the public share-link
# password unlock endpoint. Buckets keyed by (ip, token_hash) so a
# single attacker can't grind through one share's password by
# rotating tokens, AND a single token's attempts get capped across
# any IPs that contribute. The consume + info endpoints share this
# limiter to defend against token enumeration too.
share_unlock_limiter = SlidingWindowRateLimiter()
# M3 (2026-05-25) — per-user cap on LLM-backed reports endpoints
# (generate / plan / refresh-data / conversation / explain /
# regenerate) + the provider portal's wise/ask copilot. Without
# this, a runaway client or curious operator can drive Anthropic
# costs unbounded. Per-user buckets so one heavy user can't
# starve another tenant.
ai_heavy_limiter = SlidingWindowRateLimiter()
# Phase 7 / Slice N8 — cap on phone-verification OTP issuance.
# Buckets keyed by ``user_id`` so a single user cannot brute-force
# the WhatsApp send pipeline (each issuance is a paid Meta API
# call). Defaults configured at the call site in ``app.api.v1.me``.
phone_verify_limiter = SlidingWindowRateLimiter()


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

    Trusts the first hop of ``X-Forwarded-For`` because Render terminates
    TLS in front of uvicorn. Falls back to ``X-Real-IP`` then to the
    direct socket peer. Never authoritative for authorization — bucket
    keys only.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
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
