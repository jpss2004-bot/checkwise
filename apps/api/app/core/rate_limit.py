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


# Module-level shared instances. Two limiters so the buckets are
# segregated (a login attempt should not deplete reset budget).
login_limiter = SlidingWindowRateLimiter()
forgot_password_limiter = SlidingWindowRateLimiter()


def hash_identifier(value: str) -> str:
    """Stable short hash for an IP or email. Avoid putting plaintext in
    bucket keys so dumping the in-memory state for debugging does not
    expose user identifiers."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
