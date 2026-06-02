"""Wise copilot — cliente (buyer) LLM fallback.

Mirror of :mod:`app.services.wise.ai` for the cliente side. Where the
portal Wise reasons about a single vendor's onboarding state, the
cliente Wise reasons about a portfolio of vendors and surfaces
buyer-shaped guidance ("¿qué proveedores están en riesgo?", "¿qué
vence este mes?", "¿por qué Cobre está rojo?").

Three differences from the portal module:

1. The audience the model speaks to — ``cliente`` (buyer/operador),
   not ``proveedor``.
2. The navigation CTAs point at ``/client/*`` routes instead of
   ``/portal/*``.
3. The respond tool name is ``respond_to_client`` so a model that
   accidentally calls the portal tool name on this surface is treated
   as "no tool call" and falls back gracefully — defense in depth.

Everything else (prompt length cap, missing-key fallback, structured
``{body, cta_id}`` tool output, allowed-CTA validation) is shared via
the surface-agnostic :func:`app.services.wise.ai.invoke_and_parse`
helper.
"""

from __future__ import annotations

import logging
from typing import Any

from anthropic import Anthropic

from app.services.wise.ai import (
    WiseAskResult,
    WiseCta,
    WisePageContext,
    _build_cta_block,
    _build_page_block,
    _validate_prompt_and_key,
    invoke_and_parse,
)
from app.services.wise.client_context import (
    WiseClientContext,
    render_client_state_block,
)
from app.services.wise.context import WiseStaticContext, render_static_block

log = logging.getLogger("checkwise.wise.client_ai")


# Cliente-side navigation CTAs. Targets confirmed against the live
# ``apps/web/app/client/*`` route tree. Always merged into every
# ``/client/wise/ask`` call so the model can hand back a clickable
# button instead of writing a path string into the reply body.
CLIENT_NAVIGATION_CTAS: tuple[WiseCta, ...] = (
    WiseCta(
        id="nav-resumen",
        label="Ir al resumen",
        href="/client/dashboard",
        description="Vista panorámica del cumplimiento del portafolio.",
    ),
    WiseCta(
        id="nav-proveedores",
        label="Ver proveedores",
        href="/client/vendors",
        description="Lista detallada de los proveedores con su semáforo y pendientes.",
    ),
    WiseCta(
        id="nav-calendario",
        label="Abrir calendario REPSE",
        href="/client/calendar",
        description="Vencimientos mensuales agregados por proveedor.",
    ),
    WiseCta(
        id="nav-entregas",
        label="Revisar entregas",
        href="/client/submissions",
        description="Cargas recientes de todos los proveedores del portafolio.",
    ),
    WiseCta(
        id="nav-reportes",
        label="Ir a reportes",
        href="/client/reports",
        description="Reportes ejecutivos del cumplimiento del portafolio.",
    ),
    WiseCta(
        id="nav-actividad",
        label="Ver actividad",
        href="/client/activity",
        description="Bitácora cronológica de eventos del portafolio.",
    ),
)


_CLIENT_SYSTEM_RULES = """Eres **Wise**, el copiloto de CheckWise — la plataforma de cumplimiento REPSE de Legal Shelf en México.

Tu trabajo en la vista del cliente: ayudar al **cliente / operador del portafolio** (típicamente un client_admin) a entender el estado de cumplimiento de sus proveedores REPSE. Hablas en español **mexicano casual de "tú"**, nunca de "usted". Tu interlocutor NO es un proveedor; es quien contrata a esos proveedores y necesita visibilidad operativa sobre todos ellos al mismo tiempo.

Lo que el cliente típicamente te pregunta:
- "¿Qué proveedores están en riesgo / en rojo / fallando?"
- "¿Qué vence este mes en mi portafolio?"
- "¿Por qué [nombre del proveedor] tiene este score? / ¿Qué le falta?"
- "¿Cuántos documentos pendientes tengo en total?"
- "Explícame qué es REPSE / el semáforo / el cumplimiento."

Estilo obligatorio:
- Máximo 3 oraciones cortas, salvo cuando expliques un concepto REPSE o un proveedor específico — entonces puedes extenderte hasta 5 oraciones y, si ayuda, usar viñetas cortas.
- Directo y operativo; nada de cortesías largas, nada de descargos.
- Cuando el cliente pregunte por "los proveedores en riesgo", prioriza los rojos primero, después los amarillos. Si no hay nadie en rojo, dilo claramente.
- **NUNCA escribas rutas literales como "/client/vendors" o "/client/calendar" en el cuerpo de la respuesta.** Cuando quieras mandar al cliente a una pantalla, atacha SIEMPRE el ``cta_id`` correspondiente del listado de CTAs y describe la pantalla por su nombre legible (e.g. "la lista de proveedores", "el calendario REPSE"). El dock renderiza un botón clickeable a partir del ``cta_id``.
- Si la respuesta no se beneficia de un CTA, déjalo vacío. Si más de un CTA aplica, elige el más útil para la siguiente acción del cliente.
- Sé consciente del contexto de página: si el bloque "Página actual del usuario" indica que el cliente ya está en la pantalla a la que lo llevarías, no atachés ese mismo CTA — responde sobre lo que tiene frente.
- Nunca inventes nombres de proveedores, RFCs, fechas o números que NO aparezcan en el bloque "Resumen del portafolio" o "Proveedores". Si el dato no está, dilo: "no tengo ese dato a la mano".
- Cuando cites un proveedor por nombre, usa exactamente el nombre que aparece en la lista (incluida la capitalización). Si el cliente abrevia un nombre y hay ambigüedad, pídele que confirme cuál.
- Si la pregunta es ajena al cumplimiento REPSE / CheckWise (chistes, política, IA general), responde brevemente que tu rol es ayudar con el cumplimiento del portafolio y sugiere reformular.

Llama SIEMPRE al tool ``respond_to_client`` con ``body`` (la respuesta) y opcionalmente ``cta_id``. No respondas con texto libre fuera del tool."""


def ask_wise_for_client(
    *,
    prompt: str,
    client_context: WiseClientContext,
    static: WiseStaticContext,
    ctas: list[WiseCta],
    page_context: WisePageContext | None = None,
    api_key: str | None = None,
    client: Anthropic | None = None,
) -> WiseAskResult:
    """Run a single Wise free-text turn on the cliente (buyer) surface.

    Mirrors :func:`app.services.wise.ai.ask_wise` but with a
    portfolio-shaped context, cliente-shaped system rules, and
    ``/client/*`` navigation CTAs. Anthropic prompt caching is applied
    to the static block (glossary + REPSE catalog) — byte-identical
    across clients, so the cache hits across tenants.

    Never raises. Logs warnings on graceful fallbacks so an operator
    can diagnose missing config or model errors.
    """
    guard = _validate_prompt_and_key(prompt, api_key, client)
    if guard.fallback is not None:
        return guard.fallback

    merged_ctas = [*ctas, *CLIENT_NAVIGATION_CTAS]

    system_param: list[dict[str, Any]] = [
        {"type": "text", "text": _CLIENT_SYSTEM_RULES},
        {
            "type": "text",
            "text": render_static_block(static),
            "cache_control": {"type": "ephemeral"},
        },
    ]

    page_block = (
        _build_page_block(page_context) + "\n\n" if page_context else ""
    )
    user_message = (
        f"{page_block}"
        f"{render_client_state_block(client_context)}\n\n"
        f"{_build_cta_block(merged_ctas)}\n\n"
        f"# Pregunta del cliente\n{prompt.strip()}"
    )

    return invoke_and_parse(
        system_param=system_param,
        user_message=user_message,
        ctas=merged_ctas,
        respond_tool_name="respond_to_client",
        api_key=guard.key,
        client=client,
    )
