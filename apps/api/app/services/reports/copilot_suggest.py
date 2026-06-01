"""Copilot — block-composition suggestions (R6).

The chat copilot is read-only by design (see SYSTEM_PROMPT in
copilot.py — "no mutas el lienzo"). This module sits next to it and
provides a strictly structured alternative: the user asks the
copilot to recommend blocks to ADD, the model is forced through
tool-use to return one validated draft per recommendation, and the
frontend exposes an "Apply" affordance.

Tool-use forcing is the load-bearing decision. We reuse the planner's
catalog (every entry already carries a JSON Schema for the block's
config) and add an optional ``_rationale: str`` field so the model
can attach a per-block reason without us inventing a separate parsing
path on free text. Anything the model returns that doesn't match the
catalog is dropped server-side; the frontend never sees a draft it
can't render.
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

from app.services.reports.block_catalog import (
    KNOWN_BLOCK_TYPES,
    catalog_by_type,
    planner_tool_list,
)
from app.services.reports.context import AssembledContext
from app.services.reports.llm.base import LLMClient, LLMError, PlannerToolResult

logger = logging.getLogger(__name__)


MAX_SUGGESTIONS = 4
"""Hard cap on what we surface in the suggestion card. The system
prompt also tells the model 1-4; this is the server-side enforcement."""


@dataclass(frozen=True)
class BlockSuggestion:
    """One proposed block the user can apply with a single click.

    ``type`` is a known block-registry type (validated against
    KNOWN_BLOCK_TYPES). ``config`` is the validated tool argument
    matching the catalog's input_schema. ``rationale`` is the one-
    sentence reason the model gave — shown on the suggestion card.
    """

    type: str
    config: dict[str, Any]
    rationale: str


@dataclass(frozen=True)
class SuggestResult:
    suggestions: tuple[BlockSuggestion, ...]
    model: str
    stop_reason: str
    usage: dict[str, Any]


SYSTEM_PROMPT = """Eres el copiloto de cumplimiento REPSE de CheckWise.
Tu tarea AHORA es proponer bloques adicionales que reforzarían el
reporte que el usuario está armando. NO estás chateando — debes
emitir tus propuestas EXCLUSIVAMENTE como llamadas a herramientas.

# Reglas duras

1. **Solo herramientas.** Toda propuesta debe ser una llamada a una
   de las herramientas registradas. Cada herramienta corresponde a
   un tipo de bloque válido. No inventes tipos nuevos.
2. **No repitas lo que ya está en el lienzo.** El estado actual del
   reporte viene en <canvas>. Si un bloque del mismo tipo ya está,
   no lo vuelvas a proponer salvo que claramente complemente al
   existente (por ejemplo dos KPI strips con métricas distintas).
3. **Justifica cada propuesta.** Cada llamada a herramienta debe
   incluir el campo opcional ``_rationale`` con UNA frase corta en
   español, registro ejecutivo, explicando por qué ese bloque le
   conviene al reporte tal como está.
4. **Entre 1 y 4 propuestas.** Menos es mejor que más. Si el reporte
   ya está completo, devuelve solo 1 propuesta o ninguna.
5. **Audiencia.** Respeta el campo <scope>.audience. Si la audiencia
   no es interna, no propongas bloques que expondrían nombres o RFCs.
6. **Cero alucinación.** Las cifras concretas que pongas en
   ``custom_prompt`` o ``body`` deben poder derivarse del <scope>;
   si no, deja esos campos vacíos y deja que el ejecutor los rellene.
"""


def suggest_blocks(
    *,
    llm: LLMClient,
    context: AssembledContext,
    canvas_summary: dict,
    intent: str,
) -> SuggestResult:
    """Ask the LLM for block-composition suggestions.

    Args:
        llm: LLM client (mock or anthropic). Tool-use is forced via
            ``plan_with_tools`` — the same surface the planner uses,
            so any provider that ships the planner also ships this.
        context: AssembledContext for the report's scope. Carries
            scope-summary + audience for the system prompt.
        canvas_summary: compact summary of the current canvas (block
            types already present + key signals), produced by the
            frontend. Used as the dedup signal for rule (2).
        intent: the user's natural-language request, e.g.
            "Sugiéreme bloques que cierren mejor el reporte". Wrapped
            in <user_request> delimiters to neutralise prompt
            injection.

    Returns:
        SuggestResult. ``suggestions`` is the validated, deduped,
        capped list. May be empty if the model emits zero valid tool
        calls — callers should render a graceful "no hay sugerencias"
        state, not an error.

    Raises:
        LLMError: transport / auth / quota failures, surfaced to the
            API layer as 502.
    """
    scope_json = json.dumps(
        context.summary.to_planner_payload(), ensure_ascii=False, indent=2
    )
    canvas_json = json.dumps(canvas_summary, ensure_ascii=False, indent=2)
    system = (
        SYSTEM_PROMPT
        + "\n\n# Alcance del reporte\n<scope>\n"
        + scope_json
        + "\n</scope>\n"
        + "\n# Estado actual del lienzo\n<canvas>\n"
        + canvas_json
        + "\n</canvas>\n"
    )

    user = (
        "El usuario te pide:\n<user_request>\n"
        + intent.strip()
        + "\n</user_request>\n\n"
        + f"Emite entre 1 y {MAX_SUGGESTIONS} llamadas a herramientas. Una "
        + "herramienta por bloque propuesto. Recuerda incluir ``_rationale`` "
        + "en cada llamada."
    )

    tools = _suggest_tool_list()

    try:
        result = llm.plan_with_tools(system=system, user_prompt=user, tools=tools)
    except LLMError:
        raise
    except Exception as exc:  # pragma: no cover — defensive
        raise LLMError(f"Suggest-blocks call failed: {exc}") from exc

    suggestions = _validate_and_split(result, canvas_summary=canvas_summary)
    return SuggestResult(
        suggestions=tuple(suggestions[:MAX_SUGGESTIONS]),
        model=result.model,
        stop_reason=result.stop_reason,
        usage=result.usage,
    )


def _suggest_tool_list() -> list[dict]:
    """Like ``planner_tool_list()`` but each tool's input_schema gets
    an optional ``_rationale`` field. Splitting that out server-side
    means we keep the catalog's strict per-block config validation
    while still threading a per-block reason back to the UI."""
    augmented: list[dict] = []
    for tool in planner_tool_list():
        # Deepcopy so we don't mutate the catalog's shared schema dict.
        schema = deepcopy(tool["input_schema"])
        props = schema.setdefault("properties", {})
        props["_rationale"] = {
            "type": "string",
            "description": (
                "Una frase corta en español que justifica por qué este "
                "bloque le conviene al reporte. NO la dejes vacía."
            ),
        }
        # Drop additionalProperties=false on the augmented tool — the
        # planner's strict schemas would reject ``_rationale`` itself
        # otherwise. We re-impose strictness when we validate against
        # the original catalog schema below.
        if schema.get("additionalProperties") is False:
            schema.pop("additionalProperties")
        augmented.append(
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": schema,
            }
        )
    return augmented


def _validate_and_split(
    result: PlannerToolResult,
    *,
    canvas_summary: dict,
) -> list[BlockSuggestion]:
    """Split each tool_use call into (config, rationale), validate the
    config against the catalog's original schema, and dedup against
    the current canvas.

    Anything the model emits that doesn't match a known type, fails
    schema validation after we strip ``_rationale``, or duplicates a
    block already on the canvas is dropped with a warning. Callers
    get only drafts the executor and the frontend can actually
    render.
    """
    catalog = catalog_by_type()
    existing_types = {
        b.get("type")
        for b in (canvas_summary.get("blocks") or [])
        if isinstance(b, dict)
    }
    out: list[BlockSuggestion] = []
    for call in result.tool_calls:
        if call.name not in KNOWN_BLOCK_TYPES:
            logger.warning(
                "[reports.suggest] dropped unknown block type: %s", call.name
            )
            continue
        args = dict(call.arguments or {})
        rationale = str(args.pop("_rationale", "")).strip()
        if not rationale:
            # The system prompt told the model rationale is required;
            # treat empty as a soft fault — drop the suggestion. We
            # never want to surface a card with no explanation.
            logger.warning(
                "[reports.suggest] dropped %s: empty rationale", call.name
            )
            continue
        entry = catalog[call.name]
        try:
            Draft202012Validator(entry.input_schema).validate(args)
        except Exception as exc:
            logger.warning(
                "[reports.suggest] dropped invalid config for %s: %s",
                call.name,
                exc,
            )
            continue
        # Dedup: same-type blocks already on the canvas. We allow a
        # second instance of a multi-instance-friendly type (kpi_strip,
        # text, divider) but for singletons (executive_summary,
        # compliance_state) the canvas already has it, so a second
        # one would be noise.
        if call.name in _SINGLETON_BLOCK_TYPES and call.name in existing_types:
            logger.info(
                "[reports.suggest] skipped duplicate singleton: %s", call.name
            )
            continue
        out.append(
            BlockSuggestion(type=call.name, config=args, rationale=rationale)
        )
    return out


# Block types where having two copies on one canvas is almost always
# wrong — the executive summary always opens the report, the
# compliance state strip is one-per-report. KPI strips, text blocks,
# dividers, and the various AI-aware blocks can legitimately repeat.
_SINGLETON_BLOCK_TYPES: frozenset[str] = frozenset(
    {"executive_summary", "compliance_state"}
)
