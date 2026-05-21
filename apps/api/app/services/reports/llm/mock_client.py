"""Deterministic mock LLM client.

Used in:
- CI tests (no network, no quota, no flake).
- Local dev when ANTHROPIC_API_KEY is not set.
- AI-safety tests that need predictable model output to assert the
  surrounding plumbing (Context Assembler, validators) behaves
  correctly.

Behavior is deliberately deterministic and lightweight. The mock
inspects the user_prompt for a few keywords and emits a canned
ReportPlan-shaped sequence of tool_use blocks. The tool argument
shapes match the catalog's JSON Schemas so downstream validation
passes for happy-path tests.

This is NOT a "smart" mock — it doesn't try to do NLP. It's a stub
that lets the planner contract be tested end-to-end. Tests that need
specific model behavior should set up explicit MockLLMClient.fixture
plans via the public hook ``MockLLMClient.next_plan(...)``.
"""

from __future__ import annotations

from collections import deque
from collections.abc import AsyncIterator, Iterable
from typing import Any

from app.services.reports.llm.base import PlannerToolCall, PlannerToolResult


class DeterministicMockLLMClient:
    """In-memory mock implementing the LLMClient protocol.

    The class holds a queue of pre-canned plans. Tests push specific
    plans via ``next_plan(...)``. If the queue is empty, the client
    falls back to a default minimal plan ([executive_summary,
    kpi_strip]) so casual callers (e.g. the API in dev mode) get a
    sensible response without ceremony.
    """

    name = "mock"
    planner_model = "mock-planner"
    content_model = "mock-content"

    def __init__(self) -> None:
        self._queued_plans: deque[list[PlannerToolCall]] = deque()
        self._queued_rationales: deque[str] = deque()
        self._queued_streams: deque[list[str]] = deque()

    # ──────────────────────────────────────────────────────────────
    # Test hooks
    # ──────────────────────────────────────────────────────────────

    def next_plan(
        self,
        tool_calls: list[PlannerToolCall],
        rationale: str = "Plan generado por el mock determinista.",
    ) -> None:
        """Queue a plan to be returned by the next plan_with_tools call."""
        self._queued_plans.append(tool_calls)
        self._queued_rationales.append(rationale)

    def next_stream(self, chunks: list[str]) -> None:
        """Queue a stream to be returned by the next stream_text call."""
        self._queued_streams.append(list(chunks))

    def reset(self) -> None:
        self._queued_plans.clear()
        self._queued_rationales.clear()
        self._queued_streams.clear()

    # ──────────────────────────────────────────────────────────────
    # LLMClient protocol — plan_with_tools
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
        # If a test queued a specific plan, hand it back.
        if self._queued_plans:
            tool_calls = self._queued_plans.popleft()
            rationale = self._queued_rationales.popleft() if self._queued_rationales else ""
        else:
            tool_calls = _default_plan(user_prompt, tools)
            rationale = _default_rationale(user_prompt)

        return PlannerToolResult(
            tool_calls=tuple(tool_calls),
            rationale=rationale,
            stop_reason="end_turn",
            model=model or self.planner_model,
            usage={"input_tokens": 0, "output_tokens": 0, "mock": True},
        )

    # ──────────────────────────────────────────────────────────────
    # LLMClient protocol — stream_text
    # ──────────────────────────────────────────────────────────────

    def stream_text(
        self,
        *,
        system: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> Iterable[str]:
        if self._queued_streams:
            yield from self._queued_streams.popleft()
            return
        yield "[mock] "
        yield "Resumen generado por el cliente determinista."

    async def astream_text(
        self,
        *,
        system: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        for chunk in self.stream_text(
            system=system,
            user_prompt=user_prompt,
            model=model,
            max_tokens=max_tokens,
        ):
            yield chunk


# ──────────────────────────────────────────────────────────────────
# Default-plan helpers — picked from the catalog by simple keyword
# heuristics. Not "AI"; just enough to keep dev surface working.
# ──────────────────────────────────────────────────────────────────


def _default_plan(prompt: str, tools: list[dict]) -> list[PlannerToolCall]:
    """A minimal compliance summary, adapted by prompt keywords."""
    available = {t["name"] for t in tools}
    plan: list[PlannerToolCall] = []

    # Always lead with executive_summary if it's in the catalog.
    if "executive_summary" in available:
        focus = _infer_focus(prompt)
        plan.append(
            PlannerToolCall(
                id="mock-block-1",
                name="executive_summary",
                arguments={"focus": focus, "include_metrics": True},
            )
        )

    # Add a vendor_risk_matrix if the prompt mentions vendors / proveedores / risk.
    keywords_for_matrix = ("vendor", "proveedor", "riesgo", "risk", "sat", "imss", "infonavit")
    if "vendor_risk_matrix" in available and any(k in prompt.lower() for k in keywords_for_matrix):
        cfg: dict[str, Any] = {
            "filter": {},
            "columns": ["sat", "imss", "infonavit", "stps_repse", "risk_score"],
            "sort": "risk_desc",
            "max_rows": 25,
        }
        prompt_lower = prompt.lower()
        if "sat" in prompt_lower:
            cfg["filter"] = {"missing_institution": "sat"}
        elif "imss" in prompt_lower:
            cfg["filter"] = {"missing_institution": "imss"}
        elif "infonavit" in prompt_lower:
            cfg["filter"] = {"missing_institution": "infonavit"}
        plan.append(
            PlannerToolCall(id="mock-block-2", name="vendor_risk_matrix", arguments=cfg)
        )

    # KPI strip closes the report.
    if "kpi_strip" in available:
        plan.append(
            PlannerToolCall(
                id="mock-block-3",
                name="kpi_strip",
                arguments={
                    "metrics": [
                        {
                            "label": "Cumplimiento",
                            "metric_key": "completion_pct",
                            "format": "percent",
                        },
                        {
                            "label": "En riesgo",
                            "metric_key": "vendors_at_risk",
                            "format": "number",
                        },
                        {
                            "label": "En revisión",
                            "metric_key": "in_review_count",
                            "format": "number",
                        },
                        {
                            "label": "Próximo en",
                            "metric_key": "days_to_next_deadline",
                            "format": "duration_days",
                        },
                    ],
                },
            )
        )

    return plan


def _infer_focus(prompt: str) -> str:
    text = prompt.lower()
    if any(k in text for k in ("riesgo", "risk", "missing", "falta")):
        return "risk"
    if any(k in text for k in ("expediente", "onboarding")):
        return "expediente"
    if any(k in text for k in ("auditoría", "audit", "compliance audit")):
        return "audit"
    return "compliance"


def _default_rationale(prompt: str) -> str:
    return (
        "Plan determinista del mock: resumen ejecutivo + (si aplica) matriz de "
        "riesgo + tira de KPIs. Prompt: "
        + (prompt[:120] + ("…" if len(prompt) > 120 else ""))
    )
