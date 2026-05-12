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
    detected_dates: list[str] = []
    period_mentions: list[str] = []
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
