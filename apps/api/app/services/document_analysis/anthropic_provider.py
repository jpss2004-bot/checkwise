"""Claude-backed document analysis.

Implementation of ``DocumentAnalysisProvider`` that sends the uploaded
PDF directly to the Anthropic Messages API (no separate OCR layer —
Claude reads PDFs natively, page-by-page, as vision + text) and
returns a schema-validated ``DocumentSignals`` extraction.

Architecture notes (load-bearing — please read before editing):

* **Schema-validated output via tool use.** The provider declares a
  single ``record_document_analysis`` tool whose ``input_schema``
  matches the ``DocumentSignals`` shape exactly. ``tool_choice`` is
  pinned to that tool, so the model is forced to call it; the
  Messages API enforces JSON-Schema validation, which gives us
  retry-free, parsing-error-free structured output.
* **Prompt caching on the system prompt.** Every requirement type's
  prompt is identical across uploads for that requirement, so the
  ``cache_control: ephemeral`` tag on the system block is worth
  ~80% off the per-call input cost from the second call onward.
  The 5-minute TTL is fine — uploads cluster.
* **Preflight guards** reject files exceeding
  ``DOCUMENT_ANALYSIS_MAX_FILE_MB`` (default 30 MB; Anthropic's hard
  cap is 32 MB) or ``DOCUMENT_ANALYSIS_MAX_PAGES`` (default 100; the
  200k-context limit) BEFORE base64-encoding the payload. This is
  the cheap way to avoid both wasted Anthropic spend and an
  ``api_error`` round-trip.
* **Timeout.** ``DOCUMENT_ANALYSIS_TIMEOUT_SECONDS`` is passed
  explicitly via ``with_options(timeout=...)``. The SDK's default is
  long enough to look like a hang in the shadow runner; we want a
  bounded failure that surfaces as ``error="timeout"``.
* **Never raises.** Every exception path returns an ``AnalysisResult``
  with ``signals=None`` and a categorised ``error`` code. Callers
  treat that as "shadow run failed, persist the diagnostic, move on".
* **Safety against PDF parsing surprises.** ``pypdf`` is called only
  inside a wide ``try`` for the page count (used as a preflight cap).
  If the count cannot be determined the provider accepts the file —
  Anthropic will reject in-band if the underlying PDF is malformed.
"""

from __future__ import annotations

import base64
import copy
import json
import logging
import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.document_analysis.base import (
    AnalysisResult,
    ProviderUnavailableError,
)
from app.services.document_analysis.prompt_registry import (
    PromptBundle,
    get_escalation_prompt,
    get_prompt_for_requirement,
)
from app.services.document_intelligence import DocumentSignals

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool / schema definition — the single forced tool call the model uses
# to return structured data.
# ---------------------------------------------------------------------------

# Allowed enums kept identical to the heuristic provider so the diff
# surface in the reviewer comparison card is signal, not noise.
_INSTITUTION_ENUM = ["sat", "imss", "infonavit", "stps_repse"]

_DOCUMENT_TYPE_ENUM = [
    "opinion_cumplimiento_sat",
    "csf",
    "factura_cfdi",
    "nomina_cfdi",
    "imss_pago",
    "infonavit_pago",
    "repse_constancia",
    "contrato",
    "otro",
]

_ANOMALY_ENUM = [
    "possible_document_type_mismatch",
    "possible_institution_mismatch",
    "period_not_confirmed",
    "pdf_without_readable_text",
    "expiration_visible_in_past",
    "rfc_not_present",
    "signature_or_stamp_missing",
]


_RECORD_TOOL: dict[str, Any] = {
    "name": "record_document_analysis",
    "description": (
        "Registra la evaluación estructurada del documento. Devuelve los "
        "campos extraídos, la confianza de coincidencia con el requisito "
        "esperado y cualquier anomalía detectada. No tomes una decisión "
        "legal final; sólo reporta hechos y señales."
    ),
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "detected_institution": {
                "type": ["string", "null"],
                "enum": [*_INSTITUTION_ENUM, None],
                "description": "Institución que emite el documento.",
            },
            "detected_document_type": {
                "type": ["string", "null"],
                "enum": [*_DOCUMENT_TYPE_ENUM, None],
                "description": "Tipo de documento detectado.",
            },
            "detected_rfcs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Lista de RFC en mayúsculas (12 o 13 caracteres).",
            },
            "detected_dates": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Fechas en formato YYYY-MM-DD cuando sea posible.",
            },
            "period_mentions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Menciones explícitas del periodo cubierto.",
            },
            "requirement_match_confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": (
                    "0.0–1.0. Qué tanto crees que este documento corresponde "
                    "al requisito esperado para el proveedor y periodo dados."
                ),
            },
            "mismatch_reason": {
                "type": ["string", "null"],
                "description": (
                    "Texto corto en español neutro para el equipo legal. "
                    "Null si todo cuadra."
                ),
            },
            "anomaly_codes": {
                "type": "array",
                "items": {"type": "string", "enum": _ANOMALY_ENUM},
                "description": "Etiquetas de triaje (lista cerrada).",
            },
            "summary_for_reviewer": {
                "type": "string",
                "description": (
                    "Resumen interno de 1–2 líneas para el equipo legal. "
                    "No se muestra al proveedor."
                ),
            },
            # Phase C — authenticity judgment (additive). Conservative
            # by design: an empty list is the expected output for the
            # vast majority of documents.
            "authenticity_concerns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "concern": {
                            "type": "string",
                            "description": (
                                "Frase corta en español neutro para el "
                                "equipo legal describiendo la señal de "
                                "posible fabricación observada."
                            ),
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["low", "medium"],
                            "description": (
                                "low = detalle menor que vale la pena "
                                "revisar; medium = señal clara de "
                                "posible fabricación."
                            ),
                        },
                    },
                    "required": ["concern", "severity"],
                },
                "description": (
                    "Señales concretas de fabricación observadas en el "
                    "documento. Vacío cuando no observaste ninguna (lo "
                    "normal)."
                ),
            },
            "looks_fabricated": {
                "type": "boolean",
                "description": (
                    "True sólo cuando la evidencia combinada sugiere que "
                    "el documento fue fabricado o alterado. En caso de "
                    "duda, false."
                ),
            },
            "authenticity_confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": (
                    "0.0–1.0. Confianza en que el documento es auténtico "
                    "(1.0 = sin señales de fabricación)."
                ),
            },
        },
        "required": [
            "detected_institution",
            "detected_document_type",
            "detected_rfcs",
            "detected_dates",
            "period_mentions",
            "requirement_match_confidence",
            "mismatch_reason",
            "anomaly_codes",
            "summary_for_reviewer",
            "authenticity_concerns",
            "looks_fabricated",
            "authenticity_confidence",
        ],
    },
}


def _strip_numeric_constraints(node: Any) -> Any:
    """Recursively drop ``minimum``/``maximum`` from a JSON-Schema tree.

    Structured outputs (``output_config.format``) reject numeric range
    constraints. The tool ``input_schema`` keeps them (the tool path
    validates server-side); the deep tier reuses the same shape minus
    those keywords. We clamp the two confidence fields to [0, 1] when
    parsing instead.
    """
    if isinstance(node, dict):
        return {
            key: _strip_numeric_constraints(value)
            for key, value in node.items()
            if key not in ("minimum", "maximum")
        }
    if isinstance(node, list):
        return [_strip_numeric_constraints(item) for item in node]
    return node


# Deep-tier structured-output format. Same field shape as ``_RECORD_TOOL``
# so the reviewer comparison card renders both tiers identically, but
# delivered via ``output_config.format`` rather than a forced tool call —
# forced ``tool_choice`` is incompatible with adaptive thinking, while
# structured outputs compose with it.
_RECORD_OUTPUT_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "schema": _strip_numeric_constraints(copy.deepcopy(_RECORD_TOOL["input_schema"])),
}


def _clamp01(value: float) -> float:
    """Clamp a confidence to [0.0, 1.0] (structured outputs drop the range)."""
    return min(1.0, max(0.0, value))


class AnthropicDocumentAnalysisProvider:
    """Claude-backed implementation of ``DocumentAnalysisProvider``.

    Constructed by ``factory.build_document_analysis_provider`` when
    ``DOCUMENT_ANALYSIS_PROVIDER`` selects an Anthropic backend. The
    constructor raises ``ProviderUnavailableError`` when the SDK or
    API key are missing; the factory catches that and falls back.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        deep_authenticity: bool = False,
    ) -> None:
        """Build a provider for one analysis tier.

        ``model`` overrides ``DOCUMENT_ANALYSIS_MODEL`` (the factory
        passes ``DOCUMENT_ANALYSIS_TRIAGE_MODEL`` for the triage tier).
        ``deep_authenticity=True`` selects the escalation tier: the
        requirement-specific extraction prompt is replaced by the
        deeper, authenticity-focused ``authenticity_deep`` prompt.
        """
        key = (api_key or settings.ANTHROPIC_API_KEY or "").strip()
        if not key:
            raise ProviderUnavailableError(
                "ANTHROPIC_API_KEY is not configured."
            )
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise ProviderUnavailableError(
                "anthropic SDK is not installed."
            ) from exc

        self._client = Anthropic(api_key=key)
        self._model = (model or settings.DOCUMENT_ANALYSIS_MODEL or "claude-sonnet-4-6").strip()
        self._deep_authenticity = bool(deep_authenticity)
        self._timeout = float(settings.DOCUMENT_ANALYSIS_TIMEOUT_SECONDS or 30.0)
        self._max_file_bytes = int(settings.DOCUMENT_ANALYSIS_MAX_FILE_MB or 30) * 1024 * 1024
        self._max_pages = int(settings.DOCUMENT_ANALYSIS_MAX_PAGES or 100)

    @property
    def provider_id(self) -> str:
        return f"anthropic:{self._model}"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def analyze(
        self,
        *,
        pdf_path: Path,
        requirement_code: str | None,
        requirement_name: str,
        institution_code: str,
        period_code: str,
        org_id: str | None = None,
        expected_provider_rfc: str | None = None,
        expected_provider_name: str | None = None,
        expected_client_name: str | None = None,
        expected_client_rfc: str | None = None,
    ) -> AnalysisResult:
        _ = org_id  # already enforced by the spend limiter upstream
        if self._deep_authenticity:
            prompt = get_escalation_prompt()
        else:
            prompt = get_prompt_for_requirement(
                requirement_code=requirement_code,
                requirement_name=requirement_name,
            )
        start = time.monotonic()

        preflight_error = self._preflight(pdf_path)
        if preflight_error is not None:
            return self._failure(prompt, start, preflight_error)

        try:
            pdf_b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode("ascii")
        except OSError as exc:
            logger.exception("Failed reading PDF for analysis: %s", pdf_path)
            return self._failure(prompt, start, f"read_error:{type(exc).__name__}")

        user_prompt = self._build_user_prompt(
            requirement_name=requirement_name,
            institution_code=institution_code,
            period_code=period_code,
            expected_provider_rfc=expected_provider_rfc,
            expected_provider_name=expected_provider_name,
            expected_client_name=expected_client_name,
            expected_client_rfc=expected_client_rfc,
        )

        system = [
            {
                "type": "text",
                "text": prompt.system_prompt,
                # Save ~80% on input cost for repeat calls with the same
                # prompt — the 5-min TTL is fine since uploads cluster.
                # The volatile per-document context rides in the user turn
                # below, so the cache stays valid.
                "cache_control": {"type": "ephemeral"},
            }
        ]
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": user_prompt},
                ],
            }
        ]

        if self._deep_authenticity:
            # Comprehension tier — let the model reason before answering
            # (adaptive thinking + effort=high) and return schema-valid
            # JSON via structured outputs. Forced ``tool_choice`` is
            # incompatible with thinking, so the deep tier uses
            # ``output_config.format`` instead of a forced tool call.
            request_kwargs: dict[str, Any] = dict(
                model=self._model,
                max_tokens=int(settings.DOCUMENT_ANALYSIS_DEEP_MAX_TOKENS or 8192),
                system=system,
                messages=messages,
                thinking={"type": "adaptive"},
                output_config={"format": _RECORD_OUTPUT_FORMAT, "effort": "high"},
            )
            timeout = float(settings.DOCUMENT_ANALYSIS_DEEP_TIMEOUT_SECONDS or 90.0)
        else:
            # Triage tier (cheap, always-on) — single-pass forced tool
            # call, unchanged from Phase C. No thinking on Haiku.
            request_kwargs = dict(
                model=self._model,
                max_tokens=1024,
                system=system,
                messages=messages,
                tools=[_RECORD_TOOL],
                tool_choice={"type": "tool", "name": _RECORD_TOOL["name"]},
            )
            timeout = self._timeout

        try:
            response = self._client.with_options(timeout=timeout).messages.create(
                **request_kwargs
            )
        except Exception as exc:  # noqa: BLE001 — categorise everything as a known failure
            return self._failure(prompt, start, self._categorise_exception(exc))

        if self._deep_authenticity:
            signals, raw_meta, authenticity = self._parse_structured_response(response)
        else:
            signals, raw_meta, authenticity = self._parse_response(response)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if signals is None:
            return AnalysisResult(
                provider_id=self.provider_id,
                prompt_version=prompt.version,
                latency_ms=elapsed_ms,
                signals=None,
                error="malformed_response",
                raw_meta=raw_meta,
            )

        return AnalysisResult(
            provider_id=self.provider_id,
            prompt_version=prompt.version,
            latency_ms=elapsed_ms,
            signals=signals,
            error=None,
            raw_meta=raw_meta,
            authenticity=authenticity,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _preflight(self, pdf_path: Path) -> str | None:
        """Return an error code if the file should not be sent to Claude."""
        if not pdf_path.exists():
            return "unsupported_size_or_type"
        try:
            size_bytes = pdf_path.stat().st_size
        except OSError:
            return "unsupported_size_or_type"
        if size_bytes <= 0 or size_bytes > self._max_file_bytes:
            return "unsupported_size_or_type"

        # Page count is a best-effort check — if pypdf can't read the
        # file we still let Claude try (Anthropic rejects in-band).
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(pdf_path), strict=False)
            page_count = len(reader.pages)
        except Exception:  # noqa: BLE001 — best-effort
            return None
        if page_count > self._max_pages:
            return "unsupported_size_or_type"
        return None

    def _build_user_prompt(
        self,
        *,
        requirement_name: str,
        institution_code: str,
        period_code: str,
        expected_provider_rfc: str | None = None,
        expected_provider_name: str | None = None,
        expected_client_name: str | None = None,
        expected_client_rfc: str | None = None,
    ) -> str:
        lines = [
            "Analiza el documento adjunto y registra tu evaluación llamando "
            "a la herramienta `record_document_analysis`.",
            "",
            "Contexto del requisito esperado:",
            f"- Nombre del requisito: {requirement_name}",
            f"- Institución esperada: {institution_code}",
            f"- Periodo esperado: {period_code}",
        ]

        provider_bits = []
        if expected_provider_name:
            provider_bits.append(f"nombre/razón social: {expected_provider_name}")
        if expected_provider_rfc:
            provider_bits.append(f"RFC: {expected_provider_rfc}")
        if provider_bits:
            lines.append(
                "- Proveedor esperado (este documento debe identificarlo como "
                f"emisor/titular): {'; '.join(provider_bits)}"
            )

        client_bits = []
        if expected_client_name:
            client_bits.append(f"nombre: {expected_client_name}")
        if expected_client_rfc:
            client_bits.append(f"RFC: {expected_client_rfc}")
        if client_bits:
            lines.append(
                "- Cliente contratante (puede aparecer mencionado pero NO es el "
                f"titular del documento): {'; '.join(client_bits)}"
            )

        lines += [
            "",
            "Usa este contexto para evaluar si el documento realmente "
            "corresponde al proveedor y periodo esperados, y para distinguir "
            "si en realidad pertenece al cliente o a otra entidad. Recuerda: "
            "extrae hechos, no inventes valores, y sé conservador con la "
            "confianza. La decisión final la toma el equipo legal.",
        ]
        return "\n".join(lines)

    @staticmethod
    def _base_raw_meta(response: Any) -> dict[str, Any]:
        raw_meta: dict[str, Any] = {
            "stop_reason": str(getattr(response, "stop_reason", "")),
            "model": str(getattr(response, "model", "")),
        }
        usage = getattr(response, "usage", None)
        if usage is not None:
            try:
                raw_meta["usage"] = usage.model_dump()
            except Exception:  # noqa: BLE001 — usage is best-effort diagnostic
                raw_meta["usage"] = str(usage)
        return raw_meta

    @staticmethod
    def _signals_from_payload(payload: dict) -> DocumentSignals | None:
        """Build ``DocumentSignals`` from a tool-input / structured payload.

        Shared by the triage (tool_use) and deep (structured-output)
        parse paths so both tiers produce identical signal shapes.
        Returns ``None`` on a type error so the caller records
        ``malformed_response`` and falls open to the other tier.
        """
        try:
            confidence = payload.get("requirement_match_confidence")
            return DocumentSignals(
                detected_institution=payload.get("detected_institution"),
                detected_document_type=payload.get("detected_document_type"),
                detected_rfcs=list(payload.get("detected_rfcs") or []),
                detected_dates=list(payload.get("detected_dates") or []),
                period_mentions=list(payload.get("period_mentions") or []),
                requirement_match_confidence=(
                    _clamp01(float(confidence)) if confidence is not None else None
                ),
                mismatch_reason=payload.get("mismatch_reason"),
                anomaly_codes=list(payload.get("anomaly_codes") or []),
            )
        except (TypeError, ValueError):
            return None

    def _parse_response(
        self, response: Any
    ) -> tuple[DocumentSignals | None, dict, dict | None]:
        """Triage path — read the forced ``record_document_analysis`` tool call."""
        raw_meta = self._base_raw_meta(response)
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) != "tool_use":
                continue
            if getattr(block, "name", None) != _RECORD_TOOL["name"]:
                continue
            payload = getattr(block, "input", None) or {}
            if not isinstance(payload, dict):
                try:
                    payload = json.loads(payload)
                except (TypeError, ValueError):
                    return None, raw_meta, None
            signals = self._signals_from_payload(payload)
            if signals is None:
                return None, raw_meta, None
            raw_meta["summary_for_reviewer"] = payload.get("summary_for_reviewer")
            return signals, raw_meta, self._parse_authenticity(payload)

        return None, raw_meta, None

    def _parse_structured_response(
        self, response: Any
    ) -> tuple[DocumentSignals | None, dict, dict | None]:
        """Deep path — read schema-valid JSON from the first text block.

        Structured outputs guarantee the response text is the JSON object;
        any thinking blocks precede it and are skipped. A truncated or
        non-JSON body returns ``None`` so the runner keeps the triage
        result (fail-open).
        """
        raw_meta = self._base_raw_meta(response)
        text: str | None = None
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", None)
                break
        if not text:
            return None, raw_meta, None
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            return None, raw_meta, None
        if not isinstance(payload, dict):
            return None, raw_meta, None
        signals = self._signals_from_payload(payload)
        if signals is None:
            return None, raw_meta, None
        raw_meta["summary_for_reviewer"] = payload.get("summary_for_reviewer")
        return signals, raw_meta, self._parse_authenticity(payload)

    @staticmethod
    def _parse_authenticity(payload: dict) -> dict | None:
        """Extract the Phase-C authenticity judgment, tolerantly.

        Returns ``None`` when the model returned none of the
        authenticity fields (e.g., a cached/replayed v1-prompt run);
        otherwise a normalised dict. Malformed entries are dropped
        rather than failing the whole extraction — authenticity is an
        additive signal and must never cost us the base signals.
        """
        if not any(
            key in payload
            for key in (
                "authenticity_concerns",
                "looks_fabricated",
                "authenticity_confidence",
            )
        ):
            return None

        concerns: list[dict[str, str]] = []
        for item in payload.get("authenticity_concerns") or []:
            if not isinstance(item, dict):
                continue
            concern = str(item.get("concern") or "").strip()
            if not concern:
                continue
            severity = item.get("severity")
            if severity not in ("low", "medium"):
                severity = "medium"
            concerns.append({"concern": concern, "severity": severity})

        try:
            confidence = (
                float(payload["authenticity_confidence"])
                if payload.get("authenticity_confidence") is not None
                else None
            )
        except (TypeError, ValueError):
            confidence = None

        return {
            "concerns": concerns,
            "looks_fabricated": bool(payload.get("looks_fabricated")),
            "confidence": confidence,
        }

    def _categorise_exception(self, exc: BaseException) -> str:
        """Map an SDK exception to one of the public ``error`` codes."""
        name = type(exc).__name__
        # APITimeoutError, anthropic.APIConnectionError subclasses, etc.
        if "Timeout" in name or "Connect" in name:
            return "timeout"
        return f"provider_error:{name}"

    def _failure(
        self,
        prompt: PromptBundle,
        start: float,
        error: str,
    ) -> AnalysisResult:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return AnalysisResult(
            provider_id=self.provider_id,
            prompt_version=prompt.version,
            latency_ms=elapsed_ms,
            signals=None,
            error=error,
        )
