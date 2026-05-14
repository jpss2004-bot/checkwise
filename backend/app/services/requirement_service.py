"""Resolve a requirement and a period from intake input.

Two paths:

- Canonical — the caller supplied ``requirement_code`` (or ``period_key``)
  that matches the in-code compliance catalog. The DB row is found or
  created from the catalog item.
- Legacy — the caller supplied free-text ``requirement_name`` and a raw
  ``period_code``. A slug-based requirement code is generated and a
  ``legacy_*_intake`` validation event is recorded by the submission service.

Both paths return strongly-typed result objects so the router can branch
on ``used_legacy`` for telemetry without re-resolving.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.statuses import DocumentStatus
from app.core.compliance_catalog import (
    OnboardingRequirement,
    RecurringRequirement,
    lookup_onboarding_by_code,
    lookup_recurring_by_code,
)
from app.models import Period, Requirement, RequirementVersion


@dataclass(frozen=True)
class ResolvedRequirement:
    """Result of resolving a submission requirement, canonical or legacy."""

    requirement: Requirement
    requirement_version: RequirementVersion
    canonical_name: str
    canonical_code: str | None
    used_legacy: bool


@dataclass(frozen=True)
class ResolvedPeriod:
    """Result of resolving a submission period, canonical or legacy."""

    period: Period
    canonical_period_key: str | None
    used_legacy: bool


def parse_year_month(code: str) -> tuple[int | None, int | None]:
    """Pull (year, month) out of strings like ``2026-09`` or ``2026/9``."""
    match = re.search(r"(20\d{2})[-/ ]?(0?[1-9]|1[0-2])?", code)
    if not match:
        return None, None
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else None
    return year, month


def requirement_slug_code(institution_code: str, load_type: str, name: str) -> str:
    """Build a deterministic REQ-<INST>-<LOAD>-<SLUG> code for legacy intake."""
    slug = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", slug).strip("-").upper()
    slug = slug[:34] or "REQUISITO"
    return f"REQ-{institution_code.upper()}-{load_type.upper()}-{slug}"


def lookup_canonical_requirement(
    code: str,
) -> RecurringRequirement | OnboardingRequirement | None:
    """Resolve a canonical requirement_code against the in-code catalog."""
    rec = lookup_recurring_by_code(code)
    if rec is not None:
        return rec
    return lookup_onboarding_by_code(code)


def _get_or_create_period(
    db: Session,
    *,
    code: str,
    period_type: str,
    period_key: str | None = None,
) -> Period:
    """Find by canonical key first, then by (code, type). Backfill key on hit."""
    period: Period | None = None
    if period_key:
        period = db.scalar(select(Period).where(Period.period_key == period_key).limit(1))
    if period is None:
        period = db.scalar(
            select(Period).where(Period.code == code, Period.period_type == period_type).limit(1)
        )
    if period is not None:
        if period_key and not period.period_key:
            period.period_key = period_key
        return period

    year, month = parse_year_month(code)
    period = Period(
        code=code,
        year=year,
        month=month,
        period_type=period_type,
        period_key=period_key,
    )
    db.add(period)
    db.flush()
    return period


def _get_or_create_legacy_requirement(
    db: Session,
    *,
    institution_id: str,
    institution_code: str,
    load_type: str,
    requirement_name: str,
) -> tuple[Requirement, RequirementVersion]:
    """Create a Requirement + initial RequirementVersion from free-text intake."""
    code = requirement_slug_code(institution_code, load_type, requirement_name)
    requirement = db.scalar(select(Requirement).where(Requirement.code == code).limit(1))
    if not requirement:
        requirement = Requirement(
            code=code,
            name=requirement_name,
            institution_id=institution_id,
            load_type=load_type,
            frequency=load_type,
            risk_level="alto",
            current_version=1,
        )
        db.add(requirement)
        db.flush()

    version = db.scalar(
        select(RequirementVersion)
        .where(
            RequirementVersion.requirement_id == requirement.id,
            RequirementVersion.version == requirement.current_version,
        )
        .limit(1)
    )
    if not version:
        version = RequirementVersion(
            requirement_id=requirement.id,
            version=requirement.current_version,
            legal_basis="Pendiente de semilla completa desde matriz regulatoria REPSE 2026.",
            applicability_rule="Aplica según cliente, proveedor, contrato, periodo e institución.",
            minimum_validation="Archivo legible, tipo permitido, hash calculado y revisión humana.",
            automatic_signals=(
                "archivo existe; tipo permitido; tamaño máximo; hash; duplicado por hash"
            ),
            human_review_required=True,
            missing_state=DocumentStatus.PENDIENTE_REVISION.value,
            implementation_notes=(
                "Requisito creado desde carga inicial; debe reconciliarse con catálogo oficial."
            ),
        )
        db.add(version)
        db.flush()
    return requirement, version


def _get_requirement_for_catalog_item(
    db: Session,
    catalog_item: RecurringRequirement | OnboardingRequirement,
    *,
    institution_id: str,
) -> tuple[Requirement, RequirementVersion]:
    """Find or create the DB row mirroring a canonical catalog item."""
    requirement = db.scalar(
        select(Requirement).where(Requirement.code == catalog_item.code).limit(1)
    )
    if requirement is None:
        if isinstance(catalog_item, RecurringRequirement):
            frequency = catalog_item.frequency
            load_type_value = catalog_item.frequency
        else:
            frequency = "alta_inicial"
            load_type_value = "alta_inicial"
        requirement = Requirement(
            code=catalog_item.code,
            name=catalog_item.name,
            institution_id=institution_id,
            load_type=load_type_value,
            frequency=frequency,
            risk_level="alto",
            current_version=1,
        )
        db.add(requirement)
        db.flush()

    version = db.scalar(
        select(RequirementVersion)
        .where(
            RequirementVersion.requirement_id == requirement.id,
            RequirementVersion.version == requirement.current_version,
        )
        .limit(1)
    )
    if version is None:
        version = RequirementVersion(
            requirement_id=requirement.id,
            version=requirement.current_version,
            legal_basis=(
                "Sembrado desde compliance_catalog en el flujo de Reconciliación "
                "(canonical_code)."
            ),
            applicability_rule=(
                "Aplica según cliente, proveedor, contrato, periodo e institución."
            ),
            minimum_validation=(
                "Archivo legible, tipo permitido, hash calculado y revisión humana."
            ),
            automatic_signals=(
                "archivo existe; tipo permitido; tamaño máximo; hash; duplicado por hash"
            ),
            human_review_required=True,
            missing_state=DocumentStatus.PENDIENTE_REVISION.value,
            implementation_notes=(
                "Requisito creado desde canonical_code. La semilla completa de "
                "requirement_versions ocurrirá en una migración posterior."
            ),
        )
        db.add(version)
        db.flush()
    return requirement, version


def resolve_requirement(
    db: Session,
    *,
    requirement_code: str | None,
    requirement_name: str,
    institution_id: str,
    institution_code: str,
    load_type: str,
) -> ResolvedRequirement:
    """Resolve a requirement from canonical code when present, else legacy."""
    if requirement_code:
        catalog_item = lookup_canonical_requirement(requirement_code)
        if catalog_item is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"requirement_code desconocido: {requirement_code}",
            )
        requirement, version = _get_requirement_for_catalog_item(
            db, catalog_item, institution_id=institution_id
        )
        return ResolvedRequirement(
            requirement=requirement,
            requirement_version=version,
            canonical_name=catalog_item.name,
            canonical_code=catalog_item.code,
            used_legacy=False,
        )

    requirement, version = _get_or_create_legacy_requirement(
        db,
        institution_id=institution_id,
        institution_code=institution_code,
        load_type=load_type,
        requirement_name=requirement_name,
    )
    return ResolvedRequirement(
        requirement=requirement,
        requirement_version=version,
        canonical_name=requirement_name,
        canonical_code=None,
        used_legacy=True,
    )


def resolve_period(
    db: Session,
    *,
    period_key: str | None,
    period_code: str,
    load_type: str,
) -> ResolvedPeriod:
    """Resolve a Period from canonical key when present, else legacy code."""
    canonical_key = period_key.strip() if period_key else None
    period = _get_or_create_period(
        db,
        code=period_code,
        period_type=load_type,
        period_key=canonical_key,
    )
    return ResolvedPeriod(
        period=period,
        canonical_period_key=canonical_key,
        used_legacy=canonical_key is None,
    )
