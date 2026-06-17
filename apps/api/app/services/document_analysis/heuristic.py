"""Heuristic provider — wraps the existing regex/keyword classifier.

The pre-Phase-2 ``analyze_document_text`` keeps every existing intake
flow intact. This adapter exposes it through the new
``DocumentAnalysisProvider`` interface so the factory and the
shadow-mode runner can treat heuristic and Claude as interchangeable.

The heuristic re-reads the PDF text from disk because the runner in
``shadow_runner`` deliberately decouples itself from the intake
pipeline's ``PdfInspectionResult``: shadow analysis runs after the
intake transaction has committed and the in-process inspection result
is no longer reachable. Re-reading is cheap (the PDF is on local disk
or pulled from object storage by the runner before invocation).
"""

from __future__ import annotations

import time
from pathlib import Path

from app.services.document_analysis.base import AnalysisResult
from app.services.document_intelligence import analyze_document_text
from app.services.pdf_validation import inspect_pdf


class HeuristicDocumentAnalysisProvider:
    """The pre-Phase-2 regex + keyword classifier behind the provider ABC."""

    provider_id = "heuristic:v1"

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
        _ = requirement_code  # unused by the heuristic; kept for parity
        _ = org_id
        _ = metadata_field_schema  # the heuristic has no deep tier / suggestions
        start = time.monotonic()
        try:
            inspection = inspect_pdf(pdf_path)
            signals = analyze_document_text(
                inspection.text_sample,
                expected_requirement=requirement_name,
                expected_institution=institution_code,
                expected_period=period_code,
                # Phase 0 — the shadow heuristic now receives the same
                # identity context the live intake path already passes,
                # so its ``identity_alignment`` / ``rfc_alignment`` are
                # computed rather than left at ``no_expected``.
                expected_rfc=expected_provider_rfc,
                expected_vendor_name=expected_provider_name,
                expected_client_name=expected_client_name,
                expected_client_rfc=expected_client_rfc,
            )
        except Exception as exc:  # noqa: BLE001 — provider must never raise
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return AnalysisResult(
                provider_id=self.provider_id,
                prompt_version=None,
                latency_ms=elapsed_ms,
                signals=None,
                error=f"heuristic_error:{type(exc).__name__}",
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return AnalysisResult(
            provider_id=self.provider_id,
            prompt_version=None,
            latency_ms=elapsed_ms,
            signals=signals,
            error=None,
        )
