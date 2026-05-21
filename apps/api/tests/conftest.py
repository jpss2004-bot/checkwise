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


@pytest.fixture(autouse=True)
def _reset_auth_rate_limiters() -> None:
    """Drop in-memory rate-limit buckets between tests.

    The auth rate limiter is a process-global. Without a reset, a long
    test module can accumulate enough hits to trip the per-IP bucket and
    flip otherwise-deterministic tests into 429. The reset is cheap and
    keeps each test fully isolated from the others.
    """
    from app.core.rate_limit import forgot_password_limiter, login_limiter

    login_limiter.reset()
    forgot_password_limiter.reset()
