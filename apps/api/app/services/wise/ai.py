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

from anthropic import Anthropic, APIError

from app.core.config import settings

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


@dataclass(frozen=True)
class WiseStateDigest:
    """Snapshot of the provider's current compliance state.

    Curated — never the raw dashboard JSON. Just enough for the
    model to answer "how am I doing?" / "what's left?" / "which
    documents are pending?" accurately without seeing submission
    ids, filenames, or other PII.
    """

    vendor_name: str
    persona_type: str  # "moral" | "fisica"
    onboarding_completed: bool
    compliance_pct: int
    on_track: int
    total_tracked: int
    needs_action: int
    in_review: int
    completed_required: int
    total_required: int
    approved_count: int
    pending_count: int
    rejected_count: int
    expired_count: int
    next_action_titles: tuple[str, ...]  # top 3
    upcoming_deadline_titles: tuple[str, ...]  # top 3


@dataclass(frozen=True)
class WiseAskResult:
    body: str
    cta_id: str | None
    cta_label: str | None
    cta_href: str | None
    source: str  # "llm" | "fallback"


_SYSTEM_PROMPT = """Eres **Wise**, el copiloto de CheckWise — la plataforma de cumplimiento REPSE de Legal Shelf en México.

Tu trabajo: responder dudas concretas del proveedor sobre el estado de su expediente, sus cargas de documentos, sus revisiones y sus próximos vencimientos. Hablas en español **mexicano casual de "tú"**, nunca de "usted".

Estilo obligatorio:
- Máximo 3 oraciones cortas.
- Directo y útil; nada de cortesías largas ni descargos.
- Cuando la pregunta sea ambigua, asume la interpretación más operativa (qué hacer ahora).
- Si necesitas mandar al usuario a otra pantalla, usa SIEMPRE el campo ``cta_id`` del tool y elige uno de los IDs de la lista que se te entrega. **Nunca inventes URLs, IDs, ni nombres de documentos.** Si ningún CTA aplica, deja ``cta_id`` vacío.
- Nunca inventes datos del usuario (números, fechas, RFCs). Si el dato no está en el contexto, dilo claramente: "no tengo ese dato a la mano".
- Si la pregunta es ajena al expediente REPSE (chistes, política, IA general), responde brevemente que tu rol es ayudar con el cumplimiento y sugiere reformular.

Llama SIEMPRE al tool ``respond_to_provider`` con ``body`` (la respuesta) y opcionalmente ``cta_id``. No respondas con texto libre fuera del tool."""


def _build_state_block(digest: WiseStateDigest) -> str:
    """Format the state digest as a compact pseudo-table the model
    can scan. Plain text over JSON — Anthropic responds slightly
    better to readable contexts on small payloads like this."""
    lines = [
        f"Proveedor: {digest.vendor_name}",
        f"Persona: {'moral' if digest.persona_type == 'moral' else 'física'}",
        f"Expediente inicial: {'completo' if digest.onboarding_completed else 'incompleto'}",
        f"Cumplimiento: {digest.compliance_pct}% ({digest.on_track}/{digest.total_tracked} obligaciones al día)",
        f"Expediente obligatorio: {digest.completed_required}/{digest.total_required} completados",
        f"Aprobados: {digest.approved_count}",
        f"En revisión: {digest.in_review}",
        f"Por atender: {digest.needs_action}",
        f"Pendientes (sin subir): {digest.pending_count}",
        f"Rechazados: {digest.rejected_count}",
        f"Vencidos: {digest.expired_count}",
    ]
    if digest.next_action_titles:
        actions = "\n  - " + "\n  - ".join(digest.next_action_titles)
        lines.append(f"Próximas acciones sugeridas:{actions}")
    if digest.upcoming_deadline_titles:
        deadlines = "\n  - " + "\n  - ".join(digest.upcoming_deadline_titles)
        lines.append(f"Próximos vencimientos:{deadlines}")
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
    digest: WiseStateDigest,
    ctas: list[WiseCta],
    api_key: str | None = None,
    client: Anthropic | None = None,
) -> WiseAskResult:
    """Run a single Wise free-text turn.

    ``client`` is injectable for tests. ``api_key`` lets the caller
    pass an explicit key (e.g. a per-tenant key in the future); when
    omitted we read ``settings.ANTHROPIC_API_KEY``.

    Never raises. Logs warnings on graceful fallbacks so an operator
    can diagnose missing config or model errors.
    """
    if not prompt or not prompt.strip():
        return _fallback("No alcancé a leer tu pregunta. ¿Puedes escribirla de nuevo?")

    if len(prompt) > MAX_PROMPT_CHARS:
        return _fallback(
            "Tu pregunta es muy larga para responder por aquí. "
            "Intenta reformularla en una o dos oraciones."
        )

    key = api_key if api_key is not None else getattr(settings, "ANTHROPIC_API_KEY", "")
    if client is None and not key:
        log.warning("wise.ai.no_key", extra={"prompt_len": len(prompt)})
        return _fallback(
            "Por ahora no tengo cerebro para responder preguntas libres — "
            "pero puedes usar los botones de arriba o escribirle a soporte."
        )

    try:
        if client is None:
            client = Anthropic(api_key=key)
        user_message = (
            f"Estado actual del proveedor:\n{_build_state_block(digest)}\n\n"
            f"{_build_cta_block(ctas)}\n\n"
            f"Pregunta del proveedor:\n{prompt.strip()}"
        )
        response = client.messages.create(
            model=WISE_MODEL,
            max_tokens=400,
            system=_SYSTEM_PROMPT,
            tools=[_RESPOND_TOOL],
            tool_choice={"type": "tool", "name": "respond_to_provider"},
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

    return _parse_tool_response(response, ctas)


def _parse_tool_response(response, ctas: list[WiseCta]) -> WiseAskResult:
    """Extract the tool-use block and validate the CTA id.

    ``response.content`` is a list of TextBlock | ToolUseBlock. We
    only care about the tool block; anything else is conversational
    filler the model occasionally emits before the tool call.
    """
    cta_index = {cta.id: cta for cta in ctas}
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != "respond_to_provider":
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
