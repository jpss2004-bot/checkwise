"""Session-wide pytest configuration.

Forces the deterministic mock LLM for the entire test session. Without
this, tests that assume a fixture-shaped plan/streaming response fail
when the developer happens to have a real ``ANTHROPIC_API_KEY`` set
in their shell or ``apps/api/.env`` — because the factory then builds
the real Anthropic client and tries to call the network.

Set at module import time (before any test or app import) so the
Settings cache picks the mock branch.
"""

from __future__ import annotations

import os

import pytest

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["CHECKWISE_LLM_BACKEND"] = "mock"

# Async intake (§1.5) runs the validation pipeline in a FastAPI
# BackgroundTask that opens its own ``SessionLocal`` — which binds to the
# configured engine, NOT the per-test in-memory SQLite each ``api_client``
# fixture builds. Force the synchronous in-request path for the suite so
# finalize writes land in the test session; the dedicated async-path tests
# flip ``settings.INTAKE_ASYNC_FINALIZE`` back on (and patch SessionLocal)
# to exercise the background function directly.
os.environ["INTAKE_ASYNC_FINALIZE"] = "false"


@pytest.fixture(autouse=True)
def _reset_auth_rate_limiters() -> None:
    """Drop in-memory rate-limit buckets between tests.

    The auth rate limiter is a process-global. Without a reset, a long
    test module can accumulate enough hits to trip the per-IP bucket and
    flip otherwise-deterministic tests into 429. The reset is cheap and
    keeps each test fully isolated from the others.
    """
    from app.core.rate_limit import (
        forgot_password_limiter,
        login_limiter,
        phone_verify_limiter,
    )

    login_limiter.reset()
    forgot_password_limiter.reset()
    phone_verify_limiter.reset()
