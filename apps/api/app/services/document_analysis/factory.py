"""Provider factory — selects the right backend from settings.

A single entry point that the rest of the codebase imports:

    from app.services.document_analysis import build_document_analysis_provider

The factory reads ``DOCUMENT_ANALYSIS_PROVIDER`` and returns one of:

* ``None`` — provider is disabled. The shadow runner skips entirely.
* ``HeuristicDocumentAnalysisProvider`` — the regex baseline.
* ``AnthropicDocumentAnalysisProvider`` — Claude Sonnet 4.6 (or
  whatever ``DOCUMENT_ANALYSIS_MODEL`` is set to).

If ``DOCUMENT_ANALYSIS_PROVIDER=anthropic`` but the Anthropic client
cannot be built (no API key, missing SDK), the factory logs a warning
and falls back to the heuristic provider rather than booting in a
crash loop. Picking the "wrong" provider once does not take down the
intake pipeline.

The factory is intentionally NOT a ``lru_cache``. Each call returns a
fresh provider instance so test fixtures that monkey-patch settings
get an instance built against the patched settings.
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.services.document_analysis.base import (
    DocumentAnalysisProvider,
    ProviderUnavailableError,
)
from app.services.document_analysis.heuristic import HeuristicDocumentAnalysisProvider

logger = logging.getLogger(__name__)


def build_document_analysis_provider() -> DocumentAnalysisProvider | None:
    """Return the configured shadow-analysis provider, or None.

    The router-level intake pipeline (``submission_service``) is
    unaffected by this function — it always runs the inline heuristic
    classifier exactly as today. This factory only powers the
    background shadow runner: when it returns ``None`` the runner is
    a no-op.

    Settings:
        DOCUMENT_ANALYSIS_PROVIDER:
            ``"disabled"`` (default) — no shadow runs.
            ``"heuristic"``         — shadow runs but uses the regex
                                      baseline (useful only for testing
                                      the shadow plumbing).
            ``"anthropic"``         — shadow runs Claude.
            ``"shadow"``            — alias for ``"anthropic"`` reserved
                                      for the Phase-2 default.
    """
    provider_name = (settings.DOCUMENT_ANALYSIS_PROVIDER or "disabled").strip().lower()

    if provider_name in {"disabled", ""}:
        return None
    if provider_name == "heuristic":
        return HeuristicDocumentAnalysisProvider()
    if provider_name in {"anthropic", "shadow"}:
        # Import lazily so a missing anthropic SDK in a heuristic-only
        # deployment never blocks boot.
        try:
            from app.services.document_analysis.anthropic_provider import (
                AnthropicDocumentAnalysisProvider,
            )

            return AnthropicDocumentAnalysisProvider()
        except ProviderUnavailableError as exc:
            logger.warning(
                "Anthropic document-analysis provider unavailable (%s); "
                "falling back to heuristic provider for shadow runs.",
                exc,
            )
            return HeuristicDocumentAnalysisProvider()

    logger.warning(
        "Unknown DOCUMENT_ANALYSIS_PROVIDER=%r; treating as disabled.",
        provider_name,
    )
    return None
