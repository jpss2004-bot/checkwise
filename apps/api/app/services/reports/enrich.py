"""AI prose enrichment for insight blocks.

Optional polish step in the generation pipeline. The deterministic engine has
already computed the verdict + findings (correct, structured, fact-grounded);
when AI is configured this asks the LLM to REWRITE ONLY the wording into
sharper, more natural Spanish — every number, name, date, and fact stays
identical. The LLM never picks blocks, never invents data, and never gets to
change the structure.

Bulletproof by contract: any failure (no key, LLM error, malformed output,
shape mismatch) returns the original blocks unchanged. The deterministic prose
is always an acceptable result.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.reports.context import ReportScope

logger = logging.getLogger(__name__)

_SYSTEM = (
    "Eres un analista de cumplimiento REPSE en México. Reescribes el texto de "
    "un reporte para que sea más claro, directo y natural, SIN cambiar ningún "
    "dato: números, porcentajes, nombres de proveedores, fechas y hechos deben "
    "quedar idénticos. No agregues ni inventes información, no agregues ni "
    "quites elementos. Responde ÚNICAMENTE con JSON válido y con la misma "
    "estructura que recibes."
)

_AUDIENCE_VOICE = {
    "client_facing": "Tono ejecutivo, dirigido a la dirección del cliente.",
    "vendor_facing": "Tono directo y accionable, dirigido al proveedor.",
    "internal_only": "Tono operativo, dirigido al equipo interno de LegalShelf.",
}


def _ai_configured() -> bool:
    backend = (settings.CHECKWISE_LLM_BACKEND or "").strip().lower()
    if backend == "mock":
        return False
    return bool((settings.ANTHROPIC_API_KEY or "").strip())


def _parse_json(text: str) -> dict | None:
    """Best-effort JSON extraction — tolerates code fences + surrounding prose."""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    a, b = t.find("{"), t.rfind("}")
    if a == -1 or b == -1 or b <= a:
        return None
    try:
        out = json.loads(t[a : b + 1])
        return out if isinstance(out, dict) else None
    except Exception:  # noqa: BLE001
        return None


def enrich_report_prose(
    db: Session, *, scope: ReportScope, blocks: list[dict], audience: str
) -> list[dict]:
    """Rewrite the verdict/findings PROSE in place via the LLM. Returns the
    blocks unchanged on any problem."""
    if not _ai_configured():
        return blocks

    verdict_block = next((b for b in blocks if b.get("type") == "report_verdict"), None)
    findings_block = next((b for b in blocks if b.get("type") == "key_findings"), None)
    verdict = (verdict_block or {}).get("data", {}).get("verdict") if verdict_block else None
    findings = (findings_block or {}).get("data", {}).get("findings") if findings_block else None
    if not verdict and not findings:
        return blocks

    payload = {
        "verdict": (
            {"headline": verdict.get("headline"), "subhead": verdict.get("subhead")}
            if isinstance(verdict, dict)
            else None
        ),
        "findings": (
            [{"title": f.get("title"), "detail": f.get("detail")} for f in findings]
            if isinstance(findings, list)
            else None
        ),
    }
    user = (
        f"{_AUDIENCE_VOICE.get(audience, '')}\n"
        "Reescribe SOLO los campos de texto (headline, subhead, title, detail) "
        "del siguiente JSON, conservando exactamente los números, nombres "
        "propios y hechos. Mantén el mismo número de findings y la misma "
        "estructura JSON. No agregues claves nuevas.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    try:
        from app.services.reports.llm import get_llm_client

        llm = get_llm_client()
        text = "".join(llm.stream_text(system=_SYSTEM, user_prompt=user))
        data = _parse_json(text)
        if data is None:
            return blocks

        # Apply verdict prose (only non-empty strings overwrite).
        nv = data.get("verdict")
        if isinstance(verdict, dict) and isinstance(nv, dict):
            for k in ("headline", "subhead"):
                val = nv.get(k)
                if isinstance(val, str) and val.strip():
                    verdict[k] = val.strip()

        # Apply findings prose — only when counts match (no add/drop).
        nf = data.get("findings")
        if isinstance(findings, list) and isinstance(nf, list) and len(nf) == len(findings):
            for original, new in zip(findings, nf):
                if not isinstance(new, dict):
                    continue
                for k in ("title", "detail"):
                    val = new.get(k)
                    if isinstance(val, str) and val.strip():
                        original[k] = val.strip()

        return blocks
    except Exception:  # noqa: BLE001 — never let enrichment break generation
        logger.exception("[reports.enrich] enrichment failed; keeping deterministic prose")
        return blocks


__all__ = ["enrich_report_prose"]
