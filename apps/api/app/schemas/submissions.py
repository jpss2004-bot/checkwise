from __future__ import annotations

from pydantic import BaseModel, Field


class ValidationSignal(BaseModel):
    rule_code: str
    rule_type: str
    result: str
    severity: str = "info"
    message: str
    requires_human_review: bool = False
    confidence: float | None = None


class DocumentInspectionSummary(BaseModel):
    is_pdf: bool
    is_corrupt: bool
    is_encrypted: bool
    page_count: int | None = None
    text_char_count: int
    has_text: bool
    is_probably_scanned: bool


class DocumentSignalsSummary(BaseModel):
    detected_institution: str | None = None
    detected_document_type: str | None = None
    detected_rfcs: list[str] = []
    expected_rfc: str | None = None
    rfc_alignment: str | None = None
    identity_alignment: str | None = None
    detected_dates: list[str] = []
    period_mentions: list[str] = []
    period_alignment: str | None = None
    requirement_match_confidence: float | None = None
    mismatch_reason: str | None = None
    anomaly_codes: list[str] = []


class ValidationEventSummary(BaseModel):
    event_type: str
    result: str
    severity: str
    message: str | None = None
    confidence: float | None = None


class SupportInfo(BaseModel):
    whatsapp_url: str | None = None
    qr_placeholder_url: str | None = None
    message: str


class MatchFeedback(BaseModel):
    """Phase C — provider-facing soft feedback at upload time (match only).

    Populated when the intake heuristic is confident the provider
    attached the wrong file for the requirement (low
    ``requirement_match_confidence`` or an explicit
    ``mismatch_reason``), so an honest mistake is caught before a
    review cycle is burned. ``None`` when there is no match concern.

    ANTI-TIPPING CONTRACT (agreed with product, 2026-06-11): this block
    carries ONLY requirement-match information. Authenticity / forensic
    / QR-verification risk signals are reviewer-facing and must NEVER
    appear here or anywhere else in a provider-facing response — a
    flagged document routes silently to human review.
    """

    confidence: float | None = None
    warning_es: str
    # Display name of the requirement the provider was asked for
    # ("Comprobante de pago bancario", …) so the frontend can render
    # the expectation next to the warning without re-resolving the slot.
    expected_label: str | None = None


class SubmissionResponse(BaseModel):
    submission_id: str
    document_id: str
    status: str = Field(examples=["pendiente_revision"])
    sha256: str
    storage_key: str
    validations: list[ValidationSignal]
    validation_events: list[ValidationEventSummary] = []
    inspection: DocumentInspectionSummary | None = None
    document_signals: DocumentSignalsSummary | None = None
    support: SupportInfo | None = None
    message: str
    # Phase C — soft match-only feedback (see MatchFeedback docstring).
    # Additive + default None so pre-Phase-C clients are unaffected.
    match_feedback: MatchFeedback | None = None


# Stage 2.7-b — Multi-document submission response.
#
# The data model already supports 1 Submission → N Documents
# (``Submission.documents`` 1:N). The multi-file endpoint at
# ``POST /portal/workspaces/{id}/submissions/batch`` creates a single
# Submission row with N Documents underneath; this response carries the
# per-document detail back so the wizard can render a per-file status
# list.


class DocumentBatchEntry(BaseModel):
    document_id: str
    original_filename: str
    sha256: str
    storage_key: str
    status: str
    inspection: DocumentInspectionSummary | None = None
    document_signals: DocumentSignalsSummary | None = None
    validations: list[ValidationSignal]
    validation_events: list[ValidationEventSummary] = []
    # Phase C — per-file soft match-only feedback (see MatchFeedback
    # docstring). Lives on the entry, not the envelope, because each
    # attached file is matched against the slot independently.
    match_feedback: MatchFeedback | None = None


class MultiSubmissionResponse(BaseModel):
    submission_id: str
    status: str = Field(
        examples=["pendiente_revision"],
        description=(
            "Worst-case status across the batch's documents. "
            "Mirrors the single-file derivation: a REQUIERE_ACLARACION "
            "doc beats a POSIBLE_MISMATCH doc, which beats a "
            "PENDIENTE_REVISION doc."
        ),
    )
    documents: list[DocumentBatchEntry]
    support: SupportInfo | None = None
    message: str
