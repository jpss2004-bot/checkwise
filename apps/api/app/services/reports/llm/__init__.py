"""LLM client abstraction for the Reports module.

The Reports flagship uses two model tiers:

- claude-sonnet-4-6 — planner + chat refinement (needs strong reasoning
  + tool-use).
- claude-haiku-4-5 — per-block content + inline regenerate (faster,
  cheaper, sufficient for "summarize these rows" tasks).

Two implementations:

- AnthropicLLMClient — real Anthropic SDK. Used in prod and in local
  dev when ANTHROPIC_API_KEY is set. Streaming + prompt caching where
  applicable.
- DeterministicMockLLMClient — returns canned structured outputs based
  on prompt patterns. Used in CI/tests and in dev when no API key is
  present. Same surface, no network, free, deterministic.

`get_llm_client()` picks the right one based on env.

Hard rule (mirrors docs/REPORTS_ARCHITECTURE.md §3, commitment #1):
    The LLM never reads raw data. It only sees data fetched and tenant-
    scoped by the block registry's data_fetcher. The LLM client is
    transport; trust boundaries live above it (Context Assembler) and
    below it (block validators).
"""

from app.services.reports.llm.base import (
    LLMClient,
    LLMError,
    LLMStreamingError,
    PlannerToolCall,
    PlannerToolResult,
)
from app.services.reports.llm.factory import get_llm_client

__all__ = [
    "LLMClient",
    "LLMError",
    "LLMStreamingError",
    "PlannerToolCall",
    "PlannerToolResult",
    "get_llm_client",
]
