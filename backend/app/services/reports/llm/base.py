"""LLM client interface — provider-agnostic surface used by the
planner and the per-block content generator.

The interface is tiny on purpose. Two operations:

1. `plan_with_tools` — single non-streaming call with a tool catalog.
   The model is expected to emit one or more tool_use blocks; we
   return them as PlannerToolCall objects. The planner translates
   those into the ReportPlan.

2. `stream_text` — streaming text completion for per-block AI summary
   generation in Phase 3.3b.

Adding a new provider means: implement the protocol and register in
the factory. Nothing else changes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


class LLMError(Exception):
    """Base for LLM-client failures.

    Service callers catch this; the API layer translates to a 502 or
    503 depending on whether the failure is transient.
    """


class LLMStreamingError(LLMError):
    """Raised when a streaming response is interrupted mid-flight."""


@dataclass(frozen=True)
class PlannerToolCall:
    """One tool_use block the model emitted during planning.

    `name` is the tool's name (= block type). `arguments` is the
    parsed JSON the model passed; the caller is responsible for
    validating against the catalog's input_schema.
    """

    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class PlannerToolResult:
    """Result of a planning call.

    `tool_calls` is the ordered list of tools the model wanted to
    invoke (= blocks to render, in order).

    `rationale` is the natural-language paragraph the model emitted
    alongside the tool calls — captured for the version's
    llm_metadata + shown in the chat copilot in 3.3c.

    `stop_reason` mirrors the Anthropic SDK's stop_reason. We treat
    anything other than "end_turn" / "tool_use" as a transient
    failure worth retrying.

    `usage` captures token counts + cost telemetry; persisted on the
    version's llm_metadata.
    """

    tool_calls: tuple[PlannerToolCall, ...]
    rationale: str
    stop_reason: str
    model: str
    usage: dict[str, Any]


@runtime_checkable
class LLMClient(Protocol):
    """The narrow surface every implementation exposes.

    Stays sync where possible; async is reserved for streaming. The
    planner is single-call non-streaming, so we get away with sync
    for it — and sync is easier to test deterministically.
    """

    name: str
    """Identifier of the implementation. Persisted on llm_metadata so
    we can tell mock-generated content from real-Anthropic content
    when auditing version rows."""

    planner_model: str
    """Default model id used for planning. Concrete clients can ignore
    if they only support one model."""

    content_model: str
    """Default model id used for per-block content generation."""

    def plan_with_tools(
        self,
        *,
        system: str,
        user_prompt: str,
        tools: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> PlannerToolResult:
        """Issue a planning call. Returns the tool_use blocks the
        model emitted. May raise LLMError on transport / quota / auth
        failures. Implementations must NOT silently swallow."""
        ...

    def stream_text(
        self,
        *,
        system: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> Iterable[str]:
        """Stream a plain-text completion. Yields incremental string
        chunks. Used by per-block content generation in 3.3b.

        Stays sync over an iterable for now — FastAPI's
        StreamingResponse accepts that shape. We'll graduate to
        AsyncIterator if 3.3c needs concurrent streams."""
        ...

    async def astream_text(
        self,
        *,
        system: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Async stream — reserved for 3.3c when the copilot needs to
        run multiple per-block streams concurrently. Implementations
        can raise NotImplementedError until then.

        Note: implementations should yield via `yield` inside an
        async generator; type-system-wise this returns an
        AsyncIterator[str].
        """
        ...
