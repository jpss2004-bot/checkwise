"""Process-global Anthropic concurrency ceiling + circuit breaker (A2).

The per-org daily caps (``spend_limiter``) bound *spend per tenant per day*.
They never see the constraint that actually hurts a single web/worker dyno:
how many 30–90 second Anthropic ``messages.create`` calls are in flight on
*this process* at once, and whether the upstream is already failing. Fifty
concurrent uploads each waiting 90s on the API will pin the threadpool and
pile load onto an API that may already be degraded.

This module adds two cheap, process-local guards around — and ONLY around —
the ``messages.create`` call:

* a **bounded semaphore** admitting at most
  ``ANTHROPIC_MAX_CONCURRENT_REQUESTS`` concurrent calls. A caller that cannot
  get a slot within ``ANTHROPIC_CONCURRENCY_ACQUIRE_TIMEOUT_SECONDS`` raises
  ``ConcurrencyExhaustedError`` (fast-fail) rather than queueing unboundedly.
* a **circuit breaker** that, after ``ANTHROPIC_BREAKER_FAILURE_THRESHOLD``
  CONSECUTIVE call failures, opens for ``ANTHROPIC_BREAKER_COOLDOWN_SECONDS``
  and raises ``BreakerOpenError`` for every call in that window WITHOUT
  touching Anthropic — so a broken/timing-out upstream is not hammered. When
  the cooldown elapses it half-opens as a *cooldown-only* breaker: it admits a
  bounded burst (up to the concurrency ceiling) of trial calls rather than a
  single probe, and the first trial failure immediately re-opens it.

Design properties (load-bearing):

* **Default OFF.** With ``ANTHROPIC_CONCURRENCY_BREAKER_ENABLED=False`` the
  guard is a pure pass-through: no semaphore, no breaker state, the wrapped
  call runs exactly as before. Existing behaviour is byte-for-byte unchanged
  until an operator opts in.
* **Fail-open / advisory only.** ``BreakerOpenError`` and
  ``ConcurrencyExhaustedError`` are ordinary exceptions; the provider catches
  them in its existing ``except`` and returns an ``AnalysisResult`` with a
  categorised ``error`` (``breaker_open`` / ``concurrency_exhausted``). Shadow
  analysis is advisory, so a fast-fail only records a diagnostic — the
  deterministic verdict and the user-visible status never change.
* **Per process.** State is module-global, so each worker process has its own
  ceiling/breaker. This is exactly the per-worker constraint we want to bound;
  there is deliberately no cross-process coordination.
* **Only real upstream failures count.** The breaker increments on an
  ``Exception`` raised by the WRAPPED call that the caller's ``is_failure``
  predicate classifies as an upstream-health signal (timeout, connection, 5xx,
  429). It does NOT count: a semaphore-acquire timeout or an already-open
  breaker (local backpressure, raised in ``__enter__`` so it never reaches the
  recorder); a deterministic client-side 4xx (bad request / auth / schema) —
  those are self-inflicted, so the predicate marks them NEUTRAL and a recurring
  400 can't open the breaker and mask itself; a non-``Exception``
  ``BaseException`` (cancellation / interpreter shutdown); or a successful call
  that later parses to ``malformed_response`` (the API DID respond → SUCCESS).
"""

from __future__ import annotations

import logging
import threading
import time

from app.core.config import settings

logger = logging.getLogger(__name__)


class BreakerOpenError(Exception):
    """Raised when the circuit breaker is open — the call was not attempted."""


class ConcurrencyExhaustedError(Exception):
    """Raised when no concurrency slot was free within the acquire timeout."""


class AnthropicConcurrencyBreaker:
    """Process-global semaphore + consecutive-failure circuit breaker.

    Thread-safe. All tunables are read from ``settings`` at call time so an
    operator (or a test via monkeypatch) can change them without reconstructing
    the singleton; call :meth:`reset` after changing the max-concurrency to
    rebuild the semaphore at the new size.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._semaphore: threading.BoundedSemaphore | None = None
        self._semaphore_size: int | None = None
        self._consecutive_failures = 0
        self._open_until = 0.0  # monotonic deadline; 0 = closed

    # -- test / ops hook ------------------------------------------------

    def reset(self) -> None:
        """Drop the semaphore and clear breaker state (tests / size change)."""
        with self._lock:
            self._semaphore = None
            self._semaphore_size = None
            self._consecutive_failures = 0
            self._open_until = 0.0

    # -- internal state -------------------------------------------------

    def _get_semaphore(self) -> threading.BoundedSemaphore:
        size = max(1, int(settings.ANTHROPIC_MAX_CONCURRENT_REQUESTS or 1))
        with self._lock:
            if self._semaphore is None or self._semaphore_size != size:
                self._semaphore = threading.BoundedSemaphore(size)
                self._semaphore_size = size
            return self._semaphore

    def _is_open(self) -> bool:
        with self._lock:
            if self._open_until <= 0.0:
                return False
            if time.monotonic() < self._open_until:
                return True
            # Cooldown elapsed → half-open. This is a cooldown-only breaker, not
            # a single-probe one: every caller arriving at/after the deadline is
            # admitted, so up to ANTHROPIC_MAX_CONCURRENT_REQUESTS trial calls
            # can fire at once (the semaphore still hard-caps true concurrency).
            # The consecutive-failure counter is deliberately NOT reset here, so
            # the FIRST trial failure immediately re-opens the breaker — the
            # degraded upstream sees a bounded burst, then is shut out again.
            self._open_until = 0.0
            return False

    def _record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._open_until = 0.0

    def _record_failure(self) -> None:
        threshold = max(1, int(settings.ANTHROPIC_BREAKER_FAILURE_THRESHOLD or 1))
        cooldown = float(settings.ANTHROPIC_BREAKER_COOLDOWN_SECONDS or 0.0)
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= threshold and cooldown > 0.0:
                self._open_until = time.monotonic() + cooldown
                logger.warning(
                    "Anthropic circuit breaker OPEN after %d consecutive "
                    "failures; cooling down %.0fs.",
                    self._consecutive_failures,
                    cooldown,
                )

    # -- the guard ------------------------------------------------------

    def guard(self, *, is_failure=None) -> _BreakerGuard:  # noqa: ANN001
        """Context manager wrapping ONE provider call. See module docstring.

        ``is_failure`` is an optional ``Callable[[BaseException], bool]`` the
        caller supplies to classify a wrapped-call exception: return ``True`` for
        an upstream-health signal that should move the breaker, ``False`` for a
        breaker-NEUTRAL error (counter untouched). Default ``None`` = count every
        ``Exception``. A non-``Exception`` ``BaseException`` (cancellation /
        interpreter shutdown) is ALWAYS neutral regardless of the predicate.
        """
        return _BreakerGuard(self, is_failure)


class _BreakerGuard:
    """Single-use context manager: admit, run, record outcome, release."""

    __slots__ = ("_breaker", "_acquired", "_active", "_is_failure")

    def __init__(
        self,
        breaker: AnthropicConcurrencyBreaker,
        is_failure=None,  # noqa: ANN001 — Callable[[BaseException], bool] | None
    ) -> None:
        self._breaker = breaker
        self._acquired: threading.BoundedSemaphore | None = None
        self._active = False
        self._is_failure = is_failure

    def __enter__(self) -> _BreakerGuard:
        # Snapshot the enable flag ONCE so admission (__enter__) and outcome
        # recording (__exit__) always agree, even under a mid-call toggle.
        self._active = bool(settings.ANTHROPIC_CONCURRENCY_BREAKER_ENABLED)
        if not self._active:
            return self  # pass-through; inactive guard

        breaker = self._breaker
        if breaker._is_open():
            raise BreakerOpenError("anthropic circuit breaker is open")

        semaphore = breaker._get_semaphore()
        timeout = float(settings.ANTHROPIC_CONCURRENCY_ACQUIRE_TIMEOUT_SECONDS or 0.0)
        if timeout > 0.0:
            acquired = semaphore.acquire(timeout=timeout)
        else:
            acquired = semaphore.acquire(blocking=False)
        if not acquired:
            raise ConcurrencyExhaustedError(
                "no anthropic concurrency slot free within "
                f"{timeout:.1f}s (max={breaker._semaphore_size})"
            )
        self._acquired = semaphore
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        # Release the slot first, then record the outcome. ``__exit__`` runs
        # only when ``__enter__`` completed, so BreakerOpen/ConcurrencyExhausted
        # (raised in ``__enter__``) never reach here — only None (success) or a
        # real exception from the wrapped ``messages.create`` does.
        if self._acquired is not None:
            self._acquired.release()
            self._acquired = None
        if not self._active:
            return False
        if exc_type is None:
            self._breaker._record_success()
        elif issubclass(exc_type, Exception) and (
            self._is_failure is None or self._is_failure(exc)
        ):
            # A genuine upstream-call Exception the predicate counts. A
            # non-Exception BaseException (cancellation/shutdown) or a
            # predicate-NEUTRAL error (e.g. a deterministic 4xx) leaves the
            # consecutive-failure counter untouched — neither success nor
            # failure — so a self-inflicted bad request can't open the breaker.
            self._breaker._record_failure()
        return False  # never suppress the wrapped exception


# Process-global singleton. Each worker process gets its own ceiling/breaker.
anthropic_concurrency_breaker = AnthropicConcurrencyBreaker()
