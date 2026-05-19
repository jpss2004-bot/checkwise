"""Anthropic implementation of the LLM client.

Wraps the Anthropic SDK. Used in prod and in local dev when
ANTHROPIC_API_KEY is set.

Model selection (per docs/REPORTS_ARCHITECTURE.md §7):
- claude-sonnet-4-6 for planning + chat refinement.
- claude-haiku-4-5 for per-block content + inline regenerate.

Prompt caching is requested on the system prompt so the catalog + the
audience rules don't re-bill on every planning call. The catalog text
is large enough (~3 kB) that caching pays for itself after the
second call.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import Any

from anthropic import Anthropic, APIError

from app.core.config import settings
from app.services.reports.llm.base import (
    LLMError,
    LLMStreamingError,
    PlannerToolCall,
    PlannerToolResult,
)


class AnthropicLLMClient:
    """Real-Anthropic client. Holds a single SDK instance."""

    name = "anthropic"
    planner_model = "claude-sonnet-4-6"
    content_model = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or getattr(settings, "ANTHROPIC_API_KEY", None)
        if not key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not configured. Set it in backend/.env "
                "or fall back to DeterministicMockLLMClient via "
                "CHECKWISE_LLM_BACKEND=mock."
            )
        self._client = Anthropic(api_key=key)

    # ──────────────────────────────────────────────────────────────
    # Planning
    # ──────────────────────────────────────────────────────────────

    def plan_with_tools(
        self,
        *,
        system: str,
        user_prompt: str,
        tools: list[dict],
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> PlannerToolResult:
        try:
            # Cache the system prompt so the catalog + audience rules
            # don't re-bill on every plan call. Anthropic's cache TTL
            # is 5 minutes by default.
            system_param: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                },
            ]
            response = self._client.messages.create(
                model=model or self.planner_model,
                max_tokens=max_tokens,
                system=system_param,
                tools=tools,
                # Force the model to use tools — otherwise it tends
                # to "explain what it would do" instead of planning.
                tool_choice={"type": "any"},
                messages=[{"role": "user", "content": user_prompt}],
            )
        except APIError as exc:
            raise LLMError(f"Anthropic planning call failed: {exc}") from exc

        rationale_parts: list[str] = []
        tool_calls: list[PlannerToolCall] = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                rationale_parts.append(getattr(block, "text", "") or "")
            elif block_type == "tool_use":
                tool_calls.append(
                    PlannerToolCall(
                        id=getattr(block, "id", ""),
                        name=getattr(block, "name", ""),
                        arguments=dict(getattr(block, "input", {}) or {}),
                    )
                )

        usage = response.usage.model_dump() if response.usage else {}

        return PlannerToolResult(
            tool_calls=tuple(tool_calls),
            rationale="\n".join(p for p in rationale_parts if p).strip(),
            stop_reason=str(response.stop_reason),
            model=response.model,
            usage=usage,
        )

    # ──────────────────────────────────────────────────────────────
    # Streaming text — used by Phase 3.3b per-block content generator
    # ──────────────────────────────────────────────────────────────

    def stream_text(
        self,
        *,
        system: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> Iterable[str]:
        # Cache the system prompt across per-block streams. A single
        # report generation fires this method once per AI-aware block
        # (executive_summary, ai_recommendation, …); the system prompt
        # is identical across those calls, so the ephemeral 5-minute
        # cache pays for itself from the second block onward.
        system_param: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            },
        ]
        try:
            with self._client.messages.stream(
                model=model or self.content_model,
                max_tokens=max_tokens,
                system=system_param,
                messages=[{"role": "user", "content": user_prompt}],
            ) as stream:
                yield from stream.text_stream
        except APIError as exc:
            raise LLMStreamingError(f"Anthropic stream failed: {exc}") from exc

    async def astream_text(
        self,
        *,
        system: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        # 3.3c will need async; 3.3a doesn't. Punt with a clean error.
        raise NotImplementedError(
            "Async streaming arrives in Phase 3.3c when the copilot needs "
            "concurrent per-block streams."
        )
        # Unreachable but keeps the function shape an async generator.
        if False:  # pragma: no cover
            yield ""
