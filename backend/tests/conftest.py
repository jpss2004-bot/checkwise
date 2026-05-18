"""Session-wide pytest configuration.

Forces the deterministic mock LLM for the entire test session. Without
this, tests that assume a fixture-shaped plan/streaming response fail
when the developer happens to have a real ``ANTHROPIC_API_KEY`` set
in their shell or ``backend/.env`` — because the factory then builds
the real Anthropic client and tries to call the network.

Set at module import time (before any test or app import) so the
Settings cache picks the mock branch.
"""

from __future__ import annotations

import os

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["CHECKWISE_LLM_BACKEND"] = "mock"
