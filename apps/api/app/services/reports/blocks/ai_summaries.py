"""Per-block AI summary generators.

A block's ``ai_summary`` is short, grounded markdown the LLM writes
based on the data the server already fetched. The LLM never re-
queries — it gets the dict from the data fetcher inside delimiters
and is told to interpret only that.

Each generator returns an iterable of string chunks (the LLM's
streaming output). The executor wraps these chunks in SSE events.

Audience tone rules:

- internal_only      direct analyst register.
- client_facing      consultative, action-oriented.
- vendor_facing      instructive, name-of-action.
- external_signed    neutral + factual, minimum claim surface.

Not every block has AI summary. ``kpi_strip``, ``vendor_risk_matrix``,
``text``, ``divider`` ship in 3.3b without one (the data IS the
signal). 3.3b adds AI summaries to ``executive_summary`` and the new
``ai_recommendation`` block.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from typing import Any

from app.constants.reports import ReportAudience
from app.services.reports.llm.base import LLMClient

# ─── Generators ────────────────────────────────────────────────


def _audience_register(audience: ReportAudience) -> str:
    return {
        ReportAudience.INTERNAL_ONLY: (
            "Tono de analista interno: directo, denso en señales, sin filler."
        ),
        ReportAudience.CLIENT_FACING: (
            "Tono consultivo para cliente: orientado a próximas acciones, sin "
            "exponer eventos operativos internos."
        ),
        ReportAudience.VENDOR_FACING: (
            "Tono instructivo para el proveedor: qué tiene que hacer y cuándo. "
            "Nada de comparar con otros proveedores."
        ),
        ReportAudience.EXTERNAL_SIGNED: (
            "Tono neutral y factual para un destinatario externo (auditor, "
            "regulador). Máxima precisión, mínima superficie de afirmación."
        ),
    }[audience]


def _executive_summary_prompt(data: dict, audience: ReportAudience) -> tuple[str, str]:
    system = (
        "Eres CheckWise, un analista de cumplimiento REPSE. Recibes una "
        "fotografía cuantitativa del alcance del reporte. Devuelve un "
        "párrafo de 3 a 4 frases en español que abre el reporte. "
        + _audience_register(audience)
        + "\n\n"
        "Reglas duras:\n"
        "1. No inventes cifras: usa solo las que aparecen en <data>.\n"
        "2. No menciones nombres de proveedores ni RFCs.\n"
        "3. Si una métrica es 0, dilo como un dato positivo, no como ausencia "
        "de información.\n"
        "4. Cierra con la acción más importante para el período.\n"
    )
    user = (
        "Datos del alcance:\n"
        "<data>\n"
        f"{json.dumps(data, ensure_ascii=False, indent=2)}\n"
        "</data>\n\n"
        "Escribe el párrafo de apertura."
    )
    return system, user


def _ai_recommendation_prompt(
    data: dict, audience: ReportAudience
) -> tuple[str, str]:
    priority_count = int(data.get("priority_count", 3))
    upstream = data.get("upstream_block_summaries") or []
    system = (
        "Eres CheckWise, asesor de cumplimiento REPSE. A partir del "
        "resumen de los bloques anteriores del reporte, propones las "
        f"{priority_count} acciones más importantes que deben pasar "
        "esta semana. "
        + _audience_register(audience)
        + "\n\n"
        "Cada recomendación debe contener:\n"
        "1. Quién actúa (rol, no nombre).\n"
        "2. Qué tiene que hacer (verbo en infinitivo).\n"
        "3. Para cuándo (período o plazo claro, no fecha inventada).\n"
        "4. Por qué importa (1 frase, ligada a una métrica de los datos).\n"
        "\n"
        "REGLA CRÍTICA DE GROUNDING: solo puedes citar números, "
        "porcentajes, nombres de proveedores y conteos que aparezcan "
        "EXPLÍCITAMENTE en el bloque ``<upstream>`` de abajo. Si el "
        "dato que quieres mencionar no está en ese bloque, no lo "
        "inventes — reformula la recomendación sin la cifra. Está "
        "PROHIBIDO redondear, interpolar, sumar mentalmente o estimar "
        "valores que no aparezcan tal cual.\n"
        "\n"
        "Formato: lista numerada en Markdown, una recomendación por entrada.\n"
        "No incluyas encabezado, no añadas conclusión final.\n"
    )
    user = (
        "Resumen de los bloques anteriores (en orden de aparición):\n"
        "<upstream>\n"
        f"{json.dumps(upstream, ensure_ascii=False, indent=2)}\n"
        "</upstream>\n\n"
        "Genera la lista de acciones priorizadas."
    )
    return system, user


def _stream_or_string(
    llm: LLMClient, *, system: str, user: str, max_tokens: int = 600
) -> Iterable[str]:
    """Wrap llm.stream_text for graceful behavior on the mock client.

    The deterministic mock yields a small canned text; the real
    Anthropic client streams from the model. Both are iterables of
    strings — the executor wraps each chunk into an SSE event.
    """
    yield from llm.stream_text(system=system, user_prompt=user, max_tokens=max_tokens)


# ─── Dispatcher ────────────────────────────────────────────────


def _gen_executive_summary(
    config: dict, data: dict | None, audience: ReportAudience, llm: LLMClient
) -> Iterable[str]:
    if not data:
        return
    system, user = _executive_summary_prompt(data, audience)
    yield from _stream_or_string(llm, system=system, user=user)


def _gen_ai_recommendation(
    config: dict, data: dict | None, audience: ReportAudience, llm: LLMClient
) -> Iterable[str]:
    if not data:
        return
    system, user = _ai_recommendation_prompt(data, audience)
    yield from _stream_or_string(llm, system=system, user=user, max_tokens=800)


_GENERATORS: dict[
    str,
    Callable[[dict, dict | None, ReportAudience, LLMClient], Iterable[str]],
] = {
    "executive_summary": _gen_executive_summary,
    "ai_recommendation": _gen_ai_recommendation,
}


def has_ai_summary(block_type: str) -> bool:
    """True if the block carries an AI-generated text field."""
    return block_type in _GENERATORS


def stream_ai_summary(
    *,
    block_type: str,
    config: dict,
    data: dict | None,
    audience: ReportAudience,
    llm: LLMClient,
) -> Iterable[str]:
    """Public entry point. Returns an empty iterator if the block
    doesn't carry an AI summary."""
    gen = _GENERATORS.get(block_type)
    if gen is None:
        return
        yield  # pragma: no cover — unreachable; here for typing
    yield from gen(config, data, audience, llm)


def collect_summary(
    *,
    block_type: str,
    config: dict,
    data: dict | None,
    audience: ReportAudience,
    llm: LLMClient,
) -> str:
    """Eagerly accumulate the streamed summary as one string. Used by
    the synchronous version-persistence path so we can write the
    final markdown into ``content_json``."""
    out: list[str] = []
    for chunk in stream_ai_summary(
        block_type=block_type,
        config=config,
        data=data,
        audience=audience,
        llm=llm,
    ):
        out.append(chunk)
    return "".join(out)


def upstream_summary_for_recommendation(
    *, block_id: str, block_type: str, data: Any
) -> dict:
    """Compact extract the executor sends to the AI recommendation
    block as its grounding context. Stays tight — the recommendation
    LLM only needs the headline numbers, not whole row sets."""
    if data is None:
        return {"block_id": block_id, "type": block_type, "key_metric": None}
    if block_type == "executive_summary":
        return {
            "block_id": block_id,
            "type": block_type,
            "key_metric": data.get("headline_metrics"),
        }
    if block_type == "kpi_strip":
        return {
            "block_id": block_id,
            "type": block_type,
            "key_metric": {
                item["metric_key"]: item.get("value")
                for item in data.get("resolved", [])
            },
        }
    if block_type == "vendor_risk_matrix":
        rows = data.get("rows") or []
        return {
            "block_id": block_id,
            "type": block_type,
            "key_metric": {
                "vendor_count": len(rows),
                "max_risk_score": max((r["risk_score"] for r in rows), default=0),
            },
        }
    if block_type == "compliance_radar":
        # M4-followup (2026-06-02) — when the cliente Resumen
        # ejecutivo leads with the radar, the recommendation block
        # needs the radar's headline counts as grounding or the LLM
        # hallucinates ("73% de completitud" / "7 proveedores en
        # riesgo" when reality is 35% / 3). Pass the live counters
        # and the full per-vendor ranking (name + semaphore +
        # compliance_pct) so the recommendation can cite real
        # vendors and real numbers without inventing.
        semaphore = data.get("semaphore_counts") or {}
        top_vendors = data.get("top_vendors") or []
        return {
            "block_id": block_id,
            "type": block_type,
            "key_metric": {
                "client_name": data.get("client_name"),
                "vendor_count": data.get("vendor_count"),
                "overall_compliance_pct": data.get("overall_compliance_pct"),
                "green_count": semaphore.get("green", 0),
                "yellow_count": semaphore.get("yellow", 0),
                "red_count": semaphore.get("red", 0),
                "vendors_at_risk": (
                    semaphore.get("yellow", 0) + semaphore.get("red", 0)
                ),
                # Top vendors are already ranked worst-first in the
                # radar's data; pass them through so the LLM can name
                # the actually-at-risk ones in its recommendations.
                "vendors": [
                    {
                        "name": v.get("vendor_name"),
                        "semaphore": v.get("semaphore_level"),
                        "compliance_pct": v.get("compliance_pct"),
                        "missing_required": v.get("missing_required_count"),
                        "pending_reviews": v.get("pending_reviews_count"),
                    }
                    for v in top_vendors
                ],
            },
        }
    return {"block_id": block_id, "type": block_type, "key_metric": None}
