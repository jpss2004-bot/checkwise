"""Idempotent catalog seeding.

Reads the in-code compliance catalog and writes equivalent rows into the
``institutions``, ``requirements`` and ``requirement_versions`` tables.

Called from two places:

- The Alembic data migration ``0005_seed_catalog`` so a fresh deployment
  comes up with the canonical catalog already present in PostgreSQL.
- Test fixtures that need to exercise canonical-path behavior without
  relying on the on-the-fly fallback in
  ``services.requirement_service._get_requirement_for_catalog_item``.

Idempotent on purpose: every insertion is gated by a presence check against
the canonical ``code``. Re-running the seed (across deploys or test setUps)
inserts only what is missing.

Never deletes. Catalog evolution happens through *new versions*
(``current_version += 1``), not by deleting historic rows that may be
referenced by submissions.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.statuses import DocumentStatus
from app.core.catalogs import INSTITUTIONS
from app.core.compliance_catalog import (
    CATALOG_SOURCE,
    CATALOG_VERSION,
    OnboardingRequirement,
    RecurringRequirement,
    expediente_for_persona,
    recurring_for_year,
)
from app.models import Institution, Requirement, RequirementVersion


@dataclass(frozen=True)
class SeedResult:
    """Small report returned by :func:`seed_catalog`.

    ``inserted`` counts are zero on a fully-seeded re-run.
    """

    institutions_inserted: int
    requirements_inserted: int
    requirement_versions_inserted: int


def seed_catalog(session: Session, *, years: Iterable[int] = (2026,)) -> SeedResult:
    """Idempotently seed institutions + requirements + requirement_versions.

    The seed covers:

    - Every institution declared in :mod:`app.core.catalogs`.
    - Every onboarding requirement across both persona types (deduped by
      canonical ``code``).
    - Every recurring requirement for each year in ``years``.

    Returns a :class:`SeedResult` describing what was inserted; useful for
    migration logs and tests.
    """
    institutions_inserted = _seed_institutions(session)

    requirements_inserted = 0
    requirement_versions_inserted = 0

    institution_id_by_code = _institution_lookup(session)
    existing_requirement_codes = set(session.scalars(select(Requirement.code)).all())
    existing_versions: set[tuple[str, int]] = {
        (req_id, version)
        for req_id, version in session.execute(
            select(RequirementVersion.requirement_id, RequirementVersion.version)
        ).all()
    }

    for item in _all_onboarding_items():
        r, v = _seed_onboarding_requirement(
            session,
            item,
            institution_id_by_code=institution_id_by_code,
            existing_requirement_codes=existing_requirement_codes,
            existing_versions=existing_versions,
        )
        requirements_inserted += r
        requirement_versions_inserted += v

    for year in years:
        for item in recurring_for_year(year):
            r, v = _seed_recurring_requirement(
                session,
                item,
                institution_id_by_code=institution_id_by_code,
                existing_requirement_codes=existing_requirement_codes,
                existing_versions=existing_versions,
            )
            requirements_inserted += r
            requirement_versions_inserted += v

    session.flush()
    return SeedResult(
        institutions_inserted=institutions_inserted,
        requirements_inserted=requirements_inserted,
        requirement_versions_inserted=requirement_versions_inserted,
    )


def _institution_lookup(session: Session) -> dict[str, str]:
    rows = session.execute(select(Institution.code, Institution.id)).all()
    return {row[0]: row[1] for row in rows}


def _seed_institutions(session: Session) -> int:
    existing_codes = set(session.scalars(select(Institution.code)).all())
    inserted = 0
    for inst in INSTITUTIONS:
        if inst["code"] in existing_codes:
            continue
        session.add(Institution(code=inst["code"], name=inst["label"]))
        inserted += 1
    if inserted:
        session.flush()
    return inserted


def _all_onboarding_items() -> list[OnboardingRequirement]:
    """Return every onboarding item across both persona types, deduped by code."""
    seen: dict[str, OnboardingRequirement] = {}
    for item in (*expediente_for_persona("moral"), *expediente_for_persona("fisica")):
        seen.setdefault(item.code, item)
    return list(seen.values())


def _seed_onboarding_requirement(
    session: Session,
    item: OnboardingRequirement,
    *,
    institution_id_by_code: dict[str, str],
    existing_requirement_codes: set[str],
    existing_versions: set[tuple[str, int]],
) -> tuple[int, int]:
    institution_id = institution_id_by_code.get(item.institution)
    if institution_id is None:
        return (0, 0)

    requirement_inserted = 0
    if item.code not in existing_requirement_codes:
        requirement = Requirement(
            code=item.code,
            name=item.name,
            institution_id=institution_id,
            load_type="alta_inicial",
            frequency="alta_inicial",
            risk_level=_default_risk_for_onboarding(item),
            current_version=1,
        )
        session.add(requirement)
        session.flush()
        existing_requirement_codes.add(item.code)
        requirement_inserted = 1
        requirement_id = requirement.id
    else:
        requirement_id = session.scalar(
            select(Requirement.id).where(Requirement.code == item.code)
        )

    version_inserted = 0
    if requirement_id and (requirement_id, 1) not in existing_versions:
        session.add(
            RequirementVersion(
                requirement_id=requirement_id,
                version=1,
                legal_basis=_legal_basis_for_onboarding(item),
                applicability_rule=_applicability_for_onboarding(item),
                minimum_validation=_minimum_validation_text(),
                automatic_signals=_automatic_signals_text(),
                human_review_required=True,
                missing_state=DocumentStatus.PENDIENTE_REVISION.value,
                implementation_notes=_implementation_notes_text(),
                required=item.required,
            )
        )
        session.flush()
        existing_versions.add((requirement_id, 1))
        version_inserted = 1

    return (requirement_inserted, version_inserted)


def _seed_recurring_requirement(
    session: Session,
    item: RecurringRequirement,
    *,
    institution_id_by_code: dict[str, str],
    existing_requirement_codes: set[str],
    existing_versions: set[tuple[str, int]],
) -> tuple[int, int]:
    institution_id = institution_id_by_code.get(item.institution)
    if institution_id is None:
        return (0, 0)

    requirement_inserted = 0
    if item.code not in existing_requirement_codes:
        requirement = Requirement(
            code=item.code,
            name=item.name,
            institution_id=institution_id,
            load_type=item.frequency,
            frequency=item.frequency,
            risk_level="alto",
            current_version=1,
        )
        session.add(requirement)
        session.flush()
        existing_requirement_codes.add(item.code)
        requirement_inserted = 1
        requirement_id = requirement.id
    else:
        requirement_id = session.scalar(
            select(Requirement.id).where(Requirement.code == item.code)
        )

    version_inserted = 0
    if requirement_id and (requirement_id, 1) not in existing_versions:
        session.add(
            RequirementVersion(
                requirement_id=requirement_id,
                version=1,
                legal_basis=_legal_basis_for_recurring(item),
                applicability_rule="Aplica al periodo regulatorio indicado por period_key.",
                minimum_validation=_minimum_validation_text(),
                automatic_signals=_automatic_signals_text(),
                human_review_required=True,
                missing_state=DocumentStatus.PENDIENTE_REVISION.value,
                implementation_notes=_implementation_notes_text(),
                required=True,
                temporal_rule=item.period_label,
            )
        )
        session.flush()
        existing_versions.add((requirement_id, 1))
        version_inserted = 1

    return (requirement_inserted, version_inserted)


def _default_risk_for_onboarding(item: OnboardingRequirement) -> str:
    if item.section == "Registro REPSE":
        return "critico"
    return "alto"


def _legal_basis_for_onboarding(item: OnboardingRequirement) -> str:
    personas = ", ".join(item.persona_types)
    return (
        f"Catálogo: {CATALOG_SOURCE} (versión {CATALOG_VERSION}). "
        f"Sección: {item.section}. Persona: {personas}."
    )


def _applicability_for_onboarding(item: OnboardingRequirement) -> str:
    base = "Aplica al alta inicial del expediente corporativo."
    if not item.required and item.note:
        return f"{base} {item.note}"
    if not item.required:
        return f"{base} Opcional según aplicabilidad."
    return base


def _legal_basis_for_recurring(item: RecurringRequirement) -> str:
    return (
        f"Catálogo: {CATALOG_SOURCE} (versión {CATALOG_VERSION}). "
        f"Frecuencia: {item.frequency}. "
        f"Periodo: {item.period_label} ({item.period_key})."
    )


def _minimum_validation_text() -> str:
    return (
        "Archivo PDF legible, tipo permitido, hash calculado, "
        "duplicado controlado y revisión humana autorizada."
    )


def _automatic_signals_text() -> str:
    return "archivo existe; tipo permitido; tamaño máximo; hash; duplicado por hash"


def _implementation_notes_text() -> str:
    return (
        f"Sembrado desde compliance_catalog ({CATALOG_VERSION}). "
        "Cualquier cambio regulatorio debe entrar como nueva versión "
        "(current_version += 1), no como edición destructiva."
    )


__all__ = ["SeedResult", "seed_catalog"]
