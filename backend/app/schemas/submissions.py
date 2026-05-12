from __future__ import annotations

from pydantic import BaseModel, Field


class ValidationSignal(BaseModel):
    rule_code: str
    rule_type: str
    result: str
    severity: str = "info"
    message: str
    requires_human_review: bool = False


class SubmissionResponse(BaseModel):
    submission_id: str
    document_id: str
    status: str = Field(examples=["pendiente_revision"])
    sha256: str
    storage_key: str
    validations: list[ValidationSignal]
    message: str
