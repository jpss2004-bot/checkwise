from __future__ import annotations

from pydantic import BaseModel


class CatalogOption(BaseModel):
    code: str
    label: str
    description: str | None = None


class ValidationRuleOption(BaseModel):
    code: str
    label: str
    type: str


class RequirementExample(BaseModel):
    code: str
    name: str
    institution: str
    load_type: str
    risk_level: str
    human_review_required: bool


class CatalogResponse(BaseModel):
    document_statuses: list[CatalogOption]
    load_types: list[CatalogOption]
    institutions: list[CatalogOption]
    validation_rules: list[ValidationRuleOption]
    requirement_examples: list[RequirementExample]
