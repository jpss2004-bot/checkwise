"""Document-analysis provider boundary.

Pluggable provider boundary that produces structured ``DocumentSignals``
(the existing intake contract) from an uploaded PDF. Multiple
implementations cohabit behind one ``DocumentAnalysisProvider`` ABC:

* ``HeuristicDocumentAnalysisProvider`` — the pre-Phase-2 regex +
  keyword classifier, kept as the deterministic baseline and the
  shadow-mode source of truth.
* ``AnthropicDocumentAnalysisProvider`` — Claude Sonnet 4.6 reading
  the raw PDF and returning a schema-validated extraction.

Selection happens via ``DOCUMENT_ANALYSIS_PROVIDER``:

* ``disabled`` — no provider runs; intake falls through to the
  existing inline heuristic call in ``submission_service``.
* ``heuristic`` — wrapper around the existing classifier (no
  behaviour change vs. pre-Phase-2).
* ``anthropic`` — Claude runs as the primary provider; the heuristic
  is the safety-net fallback when Claude errors.
* ``shadow`` — Phase-2 default. The heuristic still drives the
  user-visible status; Claude runs in a FastAPI ``BackgroundTask``
  after the intake response is returned and persists its result to
  the new ``shadow_*`` columns for offline comparison.

User-visible behaviour DOES NOT change in shadow mode. The reviewer
admin surface gets a "Comparación IA (interna)" card that diffs the
two providers. The provider-facing portal sees nothing new.
"""

from app.services.document_analysis.base import (
    AnalysisError,
    AnalysisResult,
    DocumentAnalysisProvider,
    ProviderUnavailableError,
)
from app.services.document_analysis.factory import build_document_analysis_provider

__all__ = [
    "AnalysisError",
    "AnalysisResult",
    "DocumentAnalysisProvider",
    "ProviderUnavailableError",
    "build_document_analysis_provider",
]
