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
    get_comprehension_prompt_for_requirement,
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


# Phase 1 — the comprehension object the deep tier returns IN ADDITION to
# the extraction + authenticity fields. This is where "understanding" goes:
# what the document proves, whether it is current, and whether it actually
# satisfies the obligation (not just whether it is the right type).
_DOCUMENT_UNDERSTANDING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "purpose": {
            "type": "string",
            "description": "Una frase: qué es el documento y qué acredita.",
        },
        "key_facts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["label", "value"],
            },
            "description": (
                "Hechos que dan sentido al documento (sentido/resultado, "
                "montos, conteos, vigencias, folios), no sólo identificadores."
            ),
        },
        "status_assessment": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "validity": {
                    "type": "string",
                    "enum": ["valid", "expired", "indeterminate"],
                },
                "currency_ok": {
                    "type": ["boolean", "null"],
                    "description": (
                        "¿Suficientemente reciente para el periodo/ventana del "
                        "requisito? null si no aplica o no se puede determinar."
                    ),
                },
                "reasoning": {"type": "string"},
            },
            "required": ["validity", "currency_ok", "reasoning"],
        },
        "obligation_satisfaction": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": [
                        "satisfied",
                        "partial",
                        "not_satisfied",
                        "indeterminate",
                    ],
                },
                "confidence": {"type": "number"},
                "reasoning": {
                    "type": "string",
                    "description": (
                        "Por qué cumple o no la obligación esperada, no sólo si "
                        "es del tipo correcto."
                    ),
                },
            },
            "required": ["verdict", "confidence", "reasoning"],
        },
        "discrepancies": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "issue": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["info", "low", "medium", "high"],
                    },
                    "evidence": {"type": "string"},
                },
                "required": ["issue", "severity", "evidence"],
            },
            "description": "Problemas contextuales observados. Vacío si no hay.",
        },
    },
    "required": [
        "purpose",
        "key_facts",
        "status_assessment",
        "obligation_satisfaction",
        "discrepancies",
    ],
}


def _build_comprehension_schema() -> dict[str, Any]:
    schema = _strip_numeric_constraints(copy.deepcopy(_RECORD_TOOL["input_schema"]))
    schema["properties"]["document_understanding"] = copy.deepcopy(
        _DOCUMENT_UNDERSTANDING_SCHEMA
    )
    schema["required"] = [*schema["required"], "document_understanding"]
    return schema


# Deep/comprehension-tier format: extraction + authenticity + the
# document_understanding object, all required and schema-enforced.
_COMPREHENSION_OUTPUT_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "schema": _build_comprehension_schema(),
}

# Phase 3 — generic field-suggestion item. The schema stays generic (a
# free ``field_key`` string) so it is static across document types; the
# concrete field list the model should fill rides in the user prompt
# (volatile per-document context). Numeric ranges are dropped by
# structured outputs, so confidence is validated/clamped in parsing.
_FIELD_SUGGESTION_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "field_key": {"type": "string"},
        "value": {"type": "string"},
        "confidence": {"type": "number"},
        "evidence": {"type": "string"},
    },
    "required": ["field_key", "value", "confidence", "evidence"],
}


def _build_comprehension_with_fields_schema() -> dict[str, Any]:
    schema = _build_comprehension_schema()
    schema["properties"]["field_suggestions"] = {
        "type": "array",
        "items": copy.deepcopy(_FIELD_SUGGESTION_ITEM_SCHEMA),
        "description": (
            "Valores propuestos para los campos de metadata indicados en el "
            "prompt. Omite los que el documento no contenga, excepto "
            "`description`, que puedes redactar brevemente si falta."
        ),
    }
    schema["required"] = [*schema["required"], "field_suggestions"]
    return schema


# Deep tier + metadata field suggestions (Phase 3). Selected per-request
# only when the caller supplies ``metadata_field_schema``; otherwise the
# plain comprehension format above is used and behaviour is unchanged.
_COMPREHENSION_WITH_FIELDS_OUTPUT_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "schema": _build_comprehension_with_fields_schema(),
}

# Valid enum values for tolerant comprehension parsing.
_VALIDITY_VALUES = ("valid", "expired", "indeterminate")
_VERDICT_VALUES = ("satisfied", "partial", "not_satisfied", "indeterminate")
_DISCREPANCY_SEVERITIES = ("info", "low", "medium", "high")


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
        metadata_field_schema: list[dict] | None = None,
    ) -> AnalysisResult:
        _ = org_id  # already enforced by the spend limiter upstream
        # Field suggestions only make sense on the deep tier (structured
        # output + reasoning). The triage tier ignores the schema.
        want_field_suggestions = bool(self._deep_authenticity and metadata_field_schema)
        if self._deep_authenticity:
            # Phase 1 — the deep tier is requirement-aware: the per-type
            # v3 prompt folds extraction + authenticity + the
            # comprehension contract together.
            prompt = get_comprehension_prompt_for_requirement(
                requirement_code=requirement_code,
                requirement_name=requirement_name,
            )
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
            metadata_field_schema=metadata_field_schema if want_field_suggestions else None,
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
                output_config={
                    "format": (
                        _COMPREHENSION_WITH_FIELDS_OUTPUT_FORMAT
                        if want_field_suggestions
                        else _COMPREHENSION_OUTPUT_FORMAT
                    ),
                    "effort": "high",
                },
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

        comprehension: dict | None = None
        field_suggestions: list[dict] | None = None
        if self._deep_authenticity:
            (
                signals,
                raw_meta,
                authenticity,
                comprehension,
                field_suggestions,
            ) = self._parse_structured_response(response)
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
            comprehension=comprehension,
            field_suggestions=field_suggestions,
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
        metadata_field_schema: list[dict] | None = None,
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

        if metadata_field_schema:
            lines += [
                "",
                "Además, propón valores para los siguientes campos de metadata "
                "en `field_suggestions`, usando el `field_key` EXACTO. Toma el "
                "valor del propio documento; si un campo no aparece, omítelo "
                "(no lo inventes). Usa confianza baja cuando no estés seguro. "
                "Estas sugerencias son borradores que revisa el equipo legal, "
                "nunca aprobaciones legales.",
                "Campos:",
            ]
            for field in metadata_field_schema:
                key = str(field.get("field_key") or "").strip()
                if not key:
                    continue
                label = str(field.get("label") or "").strip()
                description = str(field.get("description") or "").strip()
                detail = " — ".join(part for part in [label, description] if part)
                lines.append(f"- {key}: {detail}" if detail else f"- {key}")

            if any(
                str(field.get("field_key") or "").strip() == "description"
                for field in metadata_field_schema
            ):
                lines += [
                    "",
                    "Excepción para `description`: si el documento no incluye una "
                    "descripción explícita, REDÁCTALA tú en una sola frase breve "
                    "(máx. ~20 palabras) que diga qué es el documento y qué "
                    "acredita, con base en su tipo y contenido. Es el ÚNICO campo "
                    "que puedes redactar (los demás solo se extraen); en `evidence` "
                    "aclara que es una descripción generada y usa confianza "
                    "moderada (~0.6).",
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
    ) -> tuple[
        DocumentSignals | None, dict, dict | None, dict | None, list[dict] | None
    ]:
        """Deep path — read schema-valid JSON from the first text block.

        Returns ``(signals, raw_meta, authenticity, comprehension,
        field_suggestions)``.
        Structured outputs guarantee the response text is the JSON object;
        any thinking blocks precede it and are skipped. A truncated or
        non-JSON body returns ``None`` signals so the runner keeps the
        triage result (fail-open).
        """
        raw_meta = self._base_raw_meta(response)
        text: str | None = None
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", None)
                break
        if not text:
            return None, raw_meta, None, None, None
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            return None, raw_meta, None, None, None
        if not isinstance(payload, dict):
            return None, raw_meta, None, None, None
        signals = self._signals_from_payload(payload)
        if signals is None:
            return None, raw_meta, None, None, None
        raw_meta["summary_for_reviewer"] = payload.get("summary_for_reviewer")
        return (
            signals,
            raw_meta,
            self._parse_authenticity(payload),
            self._parse_comprehension(payload),
            self._parse_field_suggestions(payload),
        )

    @staticmethod
    def _parse_field_suggestions(payload: dict) -> list[dict] | None:
        """Normalise the Phase-3 ``field_suggestions`` array.

        Returns ``None`` when absent (plain comprehension format, or the
        model proposed nothing). Malformed entries are dropped — suggestions
        are additive and must never cost the base signals. Confidence is
        coerced to [0,1]; entries without a field_key or value are skipped.
        """
        raw = payload.get("field_suggestions")
        if not isinstance(raw, list):
            return None
        suggestions: list[dict] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            field_key = str(item.get("field_key") or "").strip()
            value = str(item.get("value") or "").strip()
            if not field_key or not value:
                continue
            try:
                confidence = (
                    _clamp01(float(item["confidence"]))
                    if item.get("confidence") is not None
                    else None
                )
            except (TypeError, ValueError):
                confidence = None
            suggestions.append(
                {
                    "field_key": field_key,
                    "value": value,
                    "confidence": confidence,
                    "evidence": str(item.get("evidence") or "").strip(),
                }
            )
        return suggestions or None

    @staticmethod
    def _parse_comprehension(payload: dict) -> dict | None:
        """Normalise the Phase-1 ``document_understanding`` object.

        Returns ``None`` when absent (e.g. a triage payload or a replayed
        v2 run). Malformed sub-entries are dropped rather than failing the
        whole extraction — comprehension is additive and must never cost
        us the base signals.
        """
        raw = payload.get("document_understanding")
        if not isinstance(raw, dict):
            return None

        key_facts: list[dict[str, str]] = []
        for item in raw.get("key_facts") or []:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            value = str(item.get("value") or "").strip()
            if label and value:
                key_facts.append({"label": label, "value": value})

        discrepancies: list[dict[str, str]] = []
        for item in raw.get("discrepancies") or []:
            if not isinstance(item, dict):
                continue
            issue = str(item.get("issue") or "").strip()
            if not issue:
                continue
            severity = item.get("severity")
            if severity not in _DISCREPANCY_SEVERITIES:
                severity = "medium"
            discrepancies.append(
                {
                    "issue": issue,
                    "severity": severity,
                    "evidence": str(item.get("evidence") or "").strip(),
                }
            )

        status = raw.get("status_assessment")
        status = status if isinstance(status, dict) else {}
        validity = status.get("validity")
        if validity not in _VALIDITY_VALUES:
            validity = "indeterminate"
        currency_ok = status.get("currency_ok")
        if currency_ok not in (True, False, None):
            currency_ok = None

        oblig = raw.get("obligation_satisfaction")
        oblig = oblig if isinstance(oblig, dict) else {}
        verdict = oblig.get("verdict")
        if verdict not in _VERDICT_VALUES:
            verdict = "indeterminate"
        try:
            obligation_confidence = (
                _clamp01(float(oblig["confidence"]))
                if oblig.get("confidence") is not None
                else None
            )
        except (TypeError, ValueError):
            obligation_confidence = None

        return {
            "purpose": (str(raw.get("purpose") or "").strip() or None),
            "key_facts": key_facts,
            "status_assessment": {
                "validity": validity,
                "currency_ok": currency_ok,
                "reasoning": (str(status.get("reasoning") or "").strip() or None),
            },
            "obligation_satisfaction": {
                "verdict": verdict,
                "confidence": obligation_confidence,
                "reasoning": (str(oblig.get("reasoning") or "").strip() or None),
            },
            "discrepancies": discrepancies,
        }

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
