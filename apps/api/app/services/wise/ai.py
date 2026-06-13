"""Wise copilot — LLM fallback for free-text questions.

Deterministic intents (next_action, deadline, rejection, status) are
handled in the frontend by the keyword router. When the router
classifies a prompt as ``unknown`` — e.g. a tester typed "¿cómo voy
con mis uploads del expediente inicial?" — the frontend calls this
service to produce a short Spanish reply grounded in the same
curated state digest the dock already had in memory.

Guardrails baked into the implementation:

  * The model is asked to respond in **casual Mexican Spanish (tú)**
    with at most ~3 short sentences.
  * The model must call a single ``respond_to_provider`` tool, so the
    output is structured (body + optional cta_id) and never free-form
    JSON we have to parse from prose.
  * ``cta_id`` MUST come from the explicit list of allowed CTAs the
    backend passes in. Anything else is dropped silently — compliance
    products cannot ship a copilot that invents URLs.
  * Missing API key, SDK error, malformed tool call → graceful
    deterministic fallback ("No estoy seguro de eso…"). The dock
    never sees a 500.

The cost target is ~$0.001 per Wise free-text reply (claude-haiku-4-5
at ~1.5k input / 200 output tokens). This is a tiny fraction of the
report-generation budget, so no per-vendor cap is enforced today.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic, APIError

from app.core.config import settings
from app.services.wise.context import (
    WiseDocumentFocus,
    WiseStaticContext,
    WiseWorkspaceContext,
    render_document_focus,
    render_static_block,
    render_workspace_block,
)

log = logging.getLogger("checkwise.wise.ai")


# Reuse the same content-tier model the reports stack uses for
# per-block generation. Haiku is the right SKU for short copilot
# replies — quick + cheap + good Spanish.
WISE_MODEL = "claude-haiku-4-5-20251001"

# Hard cap on prompt length. Users typing more than this almost
# certainly want a different surface (email support, the contact
# form). Cap is enforced by the endpoint, restated here for tests.
MAX_PROMPT_CHARS = 500


@dataclass(frozen=True)
class WiseCta:
    """One CTA option the model can attach to its reply.

    ``id`` is the canonical identifier the frontend uses to match a
    suggested-action or upcoming-deadline back to its source. ``label``
    + ``href`` are what the dock renders if the model picks this id.
    """

    id: str
    label: str
    href: str
    description: str


# Phase 4 (2026-05-21) — always-available navigation CTAs. Injected by
# the endpoint into every ``/wise/ask`` call so the model can attach a
# clickable button instead of writing a literal path string like
# ``/portal/onboarding`` into its reply (reported by a tester after
# Wise told them "Todo está en /portal/onboarding"). The ``nav-`` id
# prefix lets the frontend distinguish them from contextual CTAs.
NAVIGATION_CTAS: tuple[WiseCta, ...] = (
    WiseCta(
        id="nav-dashboard",
        label="Ir al dashboard",
        href="/portal/dashboard",
        description="Resumen de cumplimiento + próximos pasos.",
    ),
    WiseCta(
        id="nav-onboarding",
        label="Ver expediente inicial",
        href="/portal/onboarding",
        description="Checklist del expediente que se sube una vez al darse de alta.",
    ),
    WiseCta(
        id="nav-calendar",
        label="Abrir calendario REPSE",
        href="/portal/calendar",
        description="Obligaciones recurrentes del año, mes por mes.",
    ),
    WiseCta(
        id="nav-upload",
        label="Subir un documento",
        href="/portal/upload",
        description="Formulario de carga guiada para resolver una obligación.",
    ),
    WiseCta(
        id="nav-submissions",
        label="Ver mis cargas",
        href="/portal/submissions",
        description="Listado e historial de cada documento subido.",
    ),
    WiseCta(
        id="nav-reports",
        label="Ver reportes",
        href="/portal/reports",
        description="Reportes ejecutivos generados por CheckWise.",
    ),
)


@dataclass(frozen=True)
class WisePageContext:
    """Phase 4 — where the user is right now and what they're doing.

    Surfaced from ``usePathname()`` + URL search params on the dock.
    Every field is optional so a portal page that doesn't have extra
    context can just supply the ``route`` + ``page_label``.
    """

    route: str  # e.g. "/portal/upload"
    page_label: str  # e.g. "Cargar documento"
    requirement_code: str | None = None
    requirement_name: str | None = None
    submission_id: str | None = None
    period_key: str | None = None
    # Cliente-surface context (P0 grounding, 2026-06-12). Previously
    # the cliente endpoint smuggled vendor_id through
    # ``requirement_code`` and report_id through ``submission_id``,
    # which rendered raw UUIDs under misleading labels ("Documento en
    # contexto: <vendor uuid>"). These dedicated fields render under
    # honest labels; the endpoint resolves the human-readable names.
    vendor_id: str | None = None
    vendor_name: str | None = None
    report_id: str | None = None
    report_label: str | None = None


@dataclass(frozen=True)
class WiseAskResult:
    body: str
    cta_id: str | None
    cta_label: str | None
    cta_href: str | None
    source: str  # "llm" | "fallback"


_SYSTEM_RULES = """Eres **Wise**, el copiloto de CheckWise — la plataforma de cumplimiento REPSE de Legal Shelf en México.

Tu trabajo: ayudar al proveedor a resolver dudas concretas sobre **(a)** el estado de su expediente, sus cargas y sus próximos vencimientos, **(b)** los documentos REPSE que CheckWise solicita (qué son, dónde se obtienen, errores comunes), y **(c)** cómo funciona CheckWise (estados de los documentos, semáforo, flujo de revisión, dónde encontrar cada pantalla). Hablas en español **mexicano casual de "tú"**, nunca de "usted".

Estilo obligatorio:
- Máximo 3 oraciones cortas, salvo cuando el proveedor pida una explicación de un documento o concepto — en ese caso, puedes extenderte hasta 5 oraciones y, si ayuda, usar viñetas cortas.
- Directo y útil; nada de cortesías largas ni descargos.
- Cuando la pregunta sea ambigua, asume la interpretación más operativa (qué hacer ahora).
- **NUNCA escribas rutas literales como "/portal/onboarding" o "/portal/calendar" en el cuerpo de la respuesta.** Cuando quieras mandar al usuario a una pantalla, atacha SIEMPRE el ``cta_id`` correspondiente del listado de CTAs y describe la pantalla por su nombre legible (e.g. "tu expediente inicial", "el calendario REPSE"). El dock renderiza un botón clickeable a partir del ``cta_id``; el usuario no debe nunca tener que copiar/pegar una URL.
- Si la respuesta no se beneficia de un CTA, déjalo vacío. Si más de un CTA aplica, elige el más útil para la siguiente acción del usuario.
- Sé consciente del contexto de página: si el bloque "Página actual del usuario" indica que ya está en la pantalla a la que llevarías, no atachés ese mismo CTA — responde sobre lo que hay frente al usuario.
- Si hay un bloque "Documento en pantalla", el proveedor está viendo ESA carga en este momento. Cuando diga "este documento", "esta carga", "esto" o pregunte sin nombrar un documento, asume que habla de ese documento y responde con sus datos (estado, observación del revisor, periodo). No le pidas que aclare cuál documento.
- El bloque "Estado actual del proveedor" incluye la fecha de hoy y los vencimientos por obligación — usa esos datos para responder "¿cuándo vence…?" con fechas concretas; nunca calcules fechas de memoria.
- Nunca inventes datos del usuario (números, fechas, RFCs, archivos) ni ``cta_id`` que no aparezcan en el listado. Si el dato no está disponible, dilo: "no tengo ese dato a la mano".
- Si la pregunta es ajena al cumplimiento REPSE o a CheckWise (chistes, política, IA general), responde brevemente que tu rol es ayudar con el cumplimiento y sugiere reformular.

Llama SIEMPRE al tool ``respond_to_provider`` con ``body`` (la respuesta) y opcionalmente ``cta_id``. No respondas con texto libre fuera del tool."""


def _build_page_block(ctx: WisePageContext) -> str:
    """Render the per-request 'where is the user right now' block.

    Surfaces the route + a Spanish page label and, when present, the
    specific task the user is on (the requirement they're uploading,
    the submission they're inspecting, the period they're filtering
    the calendar by). Lets Wise answer questions like "¿qué es esto
    que estoy viendo?" or "¿qué pongo aquí?" without the user
    re-stating which screen they're on.
    """
    lines = [
        "# Página actual del usuario",
        "",
        f"- Ruta: `{ctx.route}`",
        f"- Pantalla: {ctx.page_label}",
    ]
    if ctx.requirement_code or ctx.requirement_name:
        descriptor = ctx.requirement_name or ctx.requirement_code or ""
        if ctx.requirement_code and ctx.requirement_name:
            descriptor = f"{ctx.requirement_name} (código `{ctx.requirement_code}`)"
        lines.append(f"- Documento en contexto: {descriptor}")
    if ctx.period_key:
        lines.append(f"- Periodo en contexto: {ctx.period_key}")
    if ctx.submission_id:
        lines.append(f"- Carga en contexto: `{ctx.submission_id}`")
    if ctx.vendor_id or ctx.vendor_name:
        descriptor = ctx.vendor_name or f"`{ctx.vendor_id}`"
        lines.append(f"- Proveedor en pantalla: {descriptor}")
    if ctx.report_id or ctx.report_label:
        descriptor = ctx.report_label or f"`{ctx.report_id}`"
        lines.append(f"- Reporte en pantalla: {descriptor}")
    return "\n".join(lines)


def _build_cta_block(ctas: list[WiseCta]) -> str:
    if not ctas:
        return "No hay CTAs disponibles para esta pregunta."
    lines = ["CTAs disponibles (elige ``cta_id`` si alguna aplica):"]
    for cta in ctas:
        lines.append(
            f"- id={cta.id} | etiqueta=\"{cta.label}\" | uso={cta.description}"
        )
    return "\n".join(lines)


_RESPOND_TOOL: dict = {
    "name": "respond_to_provider",
    "description": (
        "Envía la respuesta al proveedor. Llama este tool exactamente "
        "una vez por turno."
    ),
    "input_schema": {
        "type": "object",
        "required": ["body"],
        "properties": {
            "body": {
                "type": "string",
                "description": (
                    "Respuesta en español mexicano, casual de 'tú', "
                    "máximo 3 oraciones cortas. Directo y operativo."
                ),
            },
            "cta_id": {
                "type": "string",
                "description": (
                    "ID exacto de una CTA del listado provisto. "
                    "Deja vacío si ninguna aplica. NUNCA inventes."
                ),
            },
        },
    },
}


def ask_wise(
    *,
    prompt: str,
    workspace: WiseWorkspaceContext,
    static: WiseStaticContext,
    ctas: list[WiseCta],
    page_context: WisePageContext | None = None,
    document_focus: WiseDocumentFocus | None = None,
    api_key: str | None = None,
    client: Anthropic | None = None,
) -> WiseAskResult:
    """Run a single Wise free-text turn with full server-assembled context.

    Phase 3 (2026-05-21) — the request now ships:

      * ``workspace``: per-vendor state (slots + recent uploads +
        reviewer notes), built fresh per call.
      * ``static``: glossary + REPSE catalog guidance, byte-identical
        across vendors so Anthropic's prompt cache hits.
      * ``ctas``: allowed CTAs the model can attach (still validated
        against this exact list before echoing back).

    Anthropic prompt caching is applied to the system rules + the
    static block (rules + glossary + catalog). The cache TTL is
    5 minutes; on a warm cache the per-question cost drops from
    ~$0.01 to ~$0.003.

    ``client`` is injectable for tests. ``api_key`` lets the caller
    pass an explicit key (e.g. a per-tenant key in the future); when
    omitted we read ``settings.ANTHROPIC_API_KEY``.

    Never raises. Logs warnings on graceful fallbacks so an operator
    can diagnose missing config or model errors.
    """
    guard = _validate_prompt_and_key(prompt, api_key, client)
    if guard.fallback is not None:
        return guard.fallback

    # Always merge in the navigation CTAs so the model can hand the
    # user a button instead of writing a path string. Contextual
    # CTAs (dashboard suggested-actions, upcoming-deadlines) come
    # first in the list so the model prefers them when relevant.
    # ``cta_id`` collisions are impossible because nav ids carry a
    # ``nav-`` prefix and contextual ids use ``act-``/``due-``.
    merged_ctas = [*ctas, *NAVIGATION_CTAS]

    # System prompt is a two-part list so we can attach
    # ``cache_control`` to the static prefix only. The runtime
    # rules sit in the first block (rarely change), the glossary
    # + full catalog sits in the second block (also static,
    # versioned per deploy). Both qualify for caching together.
    system_param: list[dict[str, Any]] = [
        {"type": "text", "text": _SYSTEM_RULES},
        {
            "type": "text",
            "text": render_static_block(static),
            "cache_control": {"type": "ephemeral"},
        },
    ]

    page_block = (
        _build_page_block(page_context) + "\n\n" if page_context else ""
    )
    focus_block = (
        render_document_focus(document_focus) + "\n\n" if document_focus else ""
    )
    user_message = (
        f"{page_block}"
        f"{focus_block}"
        f"{render_workspace_block(workspace)}\n\n"
        f"{_build_cta_block(merged_ctas)}\n\n"
        f"# Pregunta del proveedor\n{prompt.strip()}"
    )

    return invoke_and_parse(
        system_param=system_param,
        user_message=user_message,
        ctas=merged_ctas,
        respond_tool_name="respond_to_provider",
        api_key=guard.key,
        client=client,
    )


@dataclass(frozen=True)
class _PromptGuard:
    """Outcome of the early-return checks every surface shares.

    When ``fallback`` is set, the caller MUST return it without
    invoking the model. Otherwise ``key`` is the resolved API key
    (possibly empty if the caller supplied an injected ``client``).
    """

    fallback: WiseAskResult | None
    key: str


def _validate_prompt_and_key(
    prompt: str,
    api_key: str | None,
    client: Anthropic | None,
) -> _PromptGuard:
    """Run the empty-prompt, prompt-too-long, and missing-key checks
    shared by every ``ask_wise_for_*`` variant. Returns a fallback
    when any check fails; the caller short-circuits with it.
    """
    if not prompt or not prompt.strip():
        return _PromptGuard(
            fallback=_fallback(
                "No alcancé a leer tu pregunta. ¿Puedes escribirla de nuevo?"
            ),
            key="",
        )
    if len(prompt) > MAX_PROMPT_CHARS:
        return _PromptGuard(
            fallback=_fallback(
                "Tu pregunta es muy larga para responder por aquí. "
                "Intenta reformularla en una o dos oraciones."
            ),
            key="",
        )
    key = api_key if api_key is not None else getattr(settings, "ANTHROPIC_API_KEY", "")
    if client is None and not key:
        log.warning("wise.ai.no_key", extra={"prompt_len": len(prompt)})
        return _PromptGuard(
            fallback=_fallback(
                "Las preguntas libres todavía están en aprobación interna. "
                "Mientras tanto, usa los botones rápidos de arriba o escríbele "
                "a soporte si necesitas algo puntual."
            ),
            key="",
        )
    return _PromptGuard(fallback=None, key=key)


def invoke_and_parse(
    *,
    system_param: list[dict[str, Any]],
    user_message: str,
    ctas: list[WiseCta],
    respond_tool_name: str,
    api_key: str,
    client: Anthropic | None = None,
) -> WiseAskResult:
    """Surface-agnostic Anthropic invocation + tool-response parse.

    Both ``ask_wise()`` (portal) and ``ask_wise_for_client()`` (cliente
    portfolio) build their own system blocks + user message + merged
    CTA list, then hand off to this helper. The respond tool name is
    parameterized so each surface can label its tool after the audience
    it speaks to (``respond_to_provider`` vs ``respond_to_client``);
    the schema is the same.
    """
    try:
        if client is None:
            client = Anthropic(api_key=api_key)
        respond_tool = _build_respond_tool(respond_tool_name)
        response = client.messages.create(
            model=WISE_MODEL,
            max_tokens=500,
            system=system_param,
            tools=[respond_tool],
            tool_choice={"type": "tool", "name": respond_tool_name},
            messages=[{"role": "user", "content": user_message}],
        )
    except APIError as err:
        log.warning("wise.ai.api_error", extra={"error": str(err)})
        return _fallback(
            "Tuve un problema al pensar la respuesta. Intenta de nuevo en un momento."
        )
    except Exception as err:  # network, SDK changes, etc.
        log.warning("wise.ai.unexpected_error", extra={"error": str(err)})
        return _fallback(
            "Algo falló de mi lado. Intenta de nuevo en un momento."
        )
    return _parse_tool_response(response, ctas, expected_tool_name=respond_tool_name)


def _build_respond_tool(name: str) -> dict:
    """Clone the respond-tool schema with a surface-specific name."""
    tool = dict(_RESPOND_TOOL)
    tool["name"] = name
    return tool


def _parse_tool_response(
    response,
    ctas: list[WiseCta],
    *,
    expected_tool_name: str = "respond_to_provider",
) -> WiseAskResult:
    """Extract the tool-use block and validate the CTA id.

    ``response.content`` is a list of TextBlock | ToolUseBlock. We
    only care about the tool block; anything else is conversational
    filler the model occasionally emits before the tool call. The
    expected tool name varies per surface (``respond_to_provider``
    for portal, ``respond_to_client`` for cliente) so a model that
    emits the wrong tool name on the wrong surface is treated as
    "no tool call" and falls back gracefully.
    """
    cta_index = {cta.id: cta for cta in ctas}
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != expected_tool_name:
            continue
        payload = getattr(block, "input", None) or {}
        # Anthropic SDK returns input as a dict already; some SDK
        # versions or mocks pass a JSON string. Defensive parse.
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        body = (payload.get("body") or "").strip() if isinstance(payload, dict) else ""
        raw_cta_id = (
            (payload.get("cta_id") or "").strip()
            if isinstance(payload, dict)
            else ""
        )
        if not body:
            return _fallback(
                "No pude formular una respuesta clara. ¿Puedes preguntarme algo más concreto?"
            )
        if raw_cta_id and raw_cta_id in cta_index:
            cta = cta_index[raw_cta_id]
            return WiseAskResult(
                body=body,
                cta_id=cta.id,
                cta_label=cta.label,
                cta_href=cta.href,
                source="llm",
            )
        # Either the model didn't pick a CTA, or it invented one —
        # drop it silently. The body alone is still a valid reply.
        if raw_cta_id:
            log.warning(
                "wise.ai.invented_cta",
                extra={"cta_id": raw_cta_id, "allowed": [c.id for c in ctas]},
            )
        return WiseAskResult(
            body=body, cta_id=None, cta_label=None, cta_href=None, source="llm"
        )
    log.warning("wise.ai.no_tool_block")
    return _fallback(
        "No pude formular una respuesta clara. ¿Puedes preguntarme algo más concreto?"
    )


def _fallback(body: str) -> WiseAskResult:
    return WiseAskResult(
        body=body, cta_id=None, cta_label=None, cta_href=None, source="fallback"
    )
