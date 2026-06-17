"""Provider boundary: the ABC every document-analysis backend implements.

The contract is intentionally small: a provider takes the uploaded PDF
path plus the resolved upload context (which requirement / institution /
period the provider was supposed to upload against) and returns an
``AnalysisResult`` carrying a populated ``DocumentSignals`` plus
bookkeeping (provider id, prompt version, latency, error code).

``DocumentSignals`` is the existing intake contract from
``services.document_intelligence`` — keeping it as the boundary means
``submission_service`` and every downstream consumer (status derivation,
reviewer UI, audit events, metadata export) stays untouched.

A provider MUST NOT raise on a per-document failure. Instead it returns
an ``AnalysisResult`` with ``signals=None`` and an opaque ``error`` code
(``timeout`` / ``provider_error`` / ``unsupported_size_or_type`` /
``daily_cap_exceeded`` / ``malformed_response``). The intake pipeline
never aborts because of an analysis failure — that is non-negotiable for
a compliance product.

The only allowed exception is ``ProviderUnavailableError``, raised
synchronously at factory build time when the chosen provider is
mis-configured (no API key, no SDK). That surfaces as a boot-time
warning, not a per-request failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.services.document_intelligence import DocumentSignals


class AnalysisError(Exception):
    """Internal exception used inside a provider; never reaches callers.

    Providers SHOULD catch their own failures and convert them to an
    ``AnalysisResult(error=...)``. This exception exists so the
    Anthropic provider can re-raise with a category code that the
    outer wrapper then maps to the public ``error`` string.
    """


class ProviderUnavailableError(Exception):
    """Raised at factory time when the selected provider can't be built.

    Boot-time configuration failure — missing ``ANTHROPIC_API_KEY``,
    missing SDK, etc. The caller (``factory.build_document_analysis_provider``)
    logs the reason and falls back to the heuristic provider so the
    API still boots. The intake pipeline keeps working.
    """


@dataclass(frozen=True)
class AnalysisResult:
    """Outcome of one document analysis run.

    ``signals`` is populated on success and ``None`` on failure;
    ``error`` is populated on failure and ``None`` on success. The two
    are mutually exclusive in practice, but the dataclass does not
    enforce it — fail-open semantics mean a provider that returns
    partial data (e.g., heuristic ran but Claude timed out) is allowed
    to set both. The shadow-mode comparison surface uses ``error`` to
    short-circuit the diff rendering.

    ``provider_id`` is the canonical identifier used in audit logs and
    the shadow-comparison UI. Format is ``"<backend>:<model_or_version>"``,
    e.g. ``"anthropic:claude-sonnet-4-6"`` or ``"heuristic:v1"``. The
    string is stable across requests so a query like
    ``SELECT * FROM document_inspections WHERE shadow_provider_id LIKE
    'anthropic:%'`` returns the entire Claude-shadowed corpus.

    ``prompt_version`` matches the filename stem of the prompt file
    that produced the result (e.g., ``"csf_sat.v1"``). Heuristic
    provider sets it to ``None``. Persisting it on every row lets us
    replay or A/B-compare prompts later without losing the audit
    trail of which prompt produced which extraction.
    """

    provider_id: str
    prompt_version: str | None
    latency_ms: int
    signals: DocumentSignals | None
    error: str | None = None
    # Optional raw provider response (token usage, stop reason, etc.).
    # Stored in ``shadow_signals['_meta']`` for diagnostics; never
    # surfaced to providers. Kept small (no full document content) so
    # the JSON column does not balloon.
    raw_meta: dict | None = None
    # Phase C — LLM authenticity judgment. ``None`` for providers that
    # do not produce one (heuristic) or when the run failed. Shape:
    #     {"concerns": [{"concern": str, "severity": "low"|"medium"}],
    #      "looks_fabricated": bool,
    #      "confidence": float | None}
    # ``shadow_runner._persist_shadow_result`` translates this into
    # ``llm_authenticity_concern`` RiskReasons (capped at medium) and
    # re-rolls ``DocumentInspection.authenticity_risk``.
    authenticity: dict | None = None
    # Phase 1 — deep-tier comprehension. ``None`` for the triage tier and
    # for providers that do not produce one (heuristic) or when the run
    # failed. Shape (normalised by the provider):
    #     {"purpose": str | None,
    #      "key_facts": [{"label": str, "value": str}],
    #      "status_assessment": {"validity": "valid"|"expired"|"indeterminate",
    #                            "currency_ok": bool | None, "reasoning": str | None},
    #      "obligation_satisfaction": {"verdict": "satisfied"|"partial"|
    #                                  "not_satisfied"|"indeterminate",
    #                                  "confidence": float | None,
    #                                  "reasoning": str | None},
    #      "discrepancies": [{"issue": str, "severity": str, "evidence": str}]}
    # Persisted verbatim under ``shadow_signals['comprehension']``.
    comprehension: dict | None = None
    # Phase 3 — metadata field suggestions. ``None`` unless the caller asked
    # for them (deep tier + ``metadata_field_schema`` supplied + Phase-4
    # gating open). Shape (normalised by the provider):
    #     [{"field_key": str, "value": str, "confidence": float | None,
    #       "evidence": str}]
    # These feed the metadata XLSX's ``ai_assisted`` cells as
    # ``prefilled_needs_review`` — never an approval. Persisted under
    # ``shadow_signals['field_suggestions']``.
    field_suggestions: list[dict] | None = None


class DocumentAnalysisProvider(Protocol):
    """The provider interface every backend implements.

    A provider is a callable that takes (file path, requirement context)
    and returns an ``AnalysisResult``. The ``Protocol`` shape rather
    than an abstract base class keeps the implementations
    duck-typed and trivially mockable in tests.

    Implementations MUST:

    * Be safe to call from a FastAPI ``BackgroundTask`` (no implicit
      DB session, no request-scoped state).
    * Never raise on per-document failure. Convert internal exceptions
      to ``AnalysisResult(error=...)``.
    * Respect the timeout supplied in settings. A run that exceeds the
      timeout returns ``error="timeout"`` rather than blocking the
      worker.
    * Return ``error="unsupported_size_or_type"`` for inputs the
      backend cannot process (e.g., PDFs larger than
      ``DOCUMENT_ANALYSIS_MAX_FILE_MB`` or with more than
      ``DOCUMENT_ANALYSIS_MAX_PAGES`` pages).
    """

    provider_id: str

    def analyze(
        self,
        *,
        pdf_path: Path,
        requirement_code: str | None,
        requirement_name: str,
        institution_code: str,
        period_code: str,
        org_id: str | None = None,
        # Situation context — the expected provider/client identity for
        # this upload. Optional and defaulted so existing callers and the
        # heuristic baseline keep working. The Anthropic provider folds
        # these into the user prompt so the model can reason about whether
        # the document actually belongs to the expected provider (emisor)
        # vs merely mentioning the client — the regex path already had
        # this context; the LLM path did not until Phase 0.
        expected_provider_rfc: str | None = None,
        expected_provider_name: str | None = None,
        expected_client_name: str | None = None,
        expected_client_rfc: str | None = None,
        # Phase 3 — when supplied (deep tier only), the model also proposes
        # values for these metadata fields. Each entry:
        # ``{field_key, label, requirement_level, description}``. Optional and
        # defaulted so the triage tier, the heuristic baseline, and every
        # existing caller keep working unchanged.
        metadata_field_schema: list[dict] | None = None,
    ) -> AnalysisResult:
        ...
