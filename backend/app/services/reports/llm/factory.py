"""Factory that picks the right LLM client implementation.

Resolution rules (in order):

1. ``CHECKWISE_LLM_BACKEND=mock`` env → always mock. Useful for CI and
   for local repros where the user wants deterministic output even if
   they have a key.
2. ``CHECKWISE_LLM_BACKEND=anthropic`` env → always Anthropic; fail
   loudly if the key is missing. Useful when running an end-to-end
   integration script and you want to be sure the real path runs.
3. No backend override + ``ANTHROPIC_API_KEY`` set → Anthropic.
4. No backend override + no key → mock.

Callers should treat the returned object as opaque; the LLMClient
protocol is the contract.
"""

from __future__ import annotations

from app.core.config import settings
from app.services.reports.llm.base import LLMClient, LLMError


def get_llm_client() -> LLMClient:
    backend = (settings.CHECKWISE_LLM_BACKEND or "").strip().lower()

    if backend == "mock":
        return _build_mock()

    if backend == "anthropic":
        return _build_anthropic()  # raises if no key

    # Auto-detect.
    if settings.ANTHROPIC_API_KEY:
        return _build_anthropic()
    return _build_mock()


def _build_anthropic() -> LLMClient:
    # Imported lazily so the mock-only path doesn't require the
    # anthropic SDK at import time (it still pays for itself once;
    # this keeps tests faster).
    from app.services.reports.llm.anthropic_client import AnthropicLLMClient

    try:
        return AnthropicLLMClient()
    except LLMError:
        raise
    except Exception as exc:  # pragma: no cover — defensive
        raise LLMError(f"Failed to build AnthropicLLMClient: {exc}") from exc


def _build_mock() -> LLMClient:
    from app.services.reports.llm.mock_client import DeterministicMockLLMClient

    return DeterministicMockLLMClient()
