"""Versioned regulatory catalog derived from ``C.Árbol Plataforma Proveedores REPSE VF``.

This module encodes the provider compliance tree as typed Python data. It is
the single source of truth for:

- The Expediente Corporativo (one-time onboarding) per persona type.
- The Cumplimiento REPSE recurring calendar (monthly, bimonthly, cuatrimestral,
  annual obligations) by year.

It is intentionally a pure-Python catalog (no DB seed yet) so the frontend can
mirror it for the demo while V1.3 can ingest the same shape into
``requirement_versions``.

Source: ``C.Árbol Plataforma Proveedores REPSE VF`` (sheet "Árbol Plataforma").
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

CATALOG_SOURCE = "C.Árbol Plataforma Proveedores REPSE VF"
CATALOG_VERSION = "2026.06.0"

PersonaType = Literal["moral", "fisica"]
Frequency = Literal["mensual", "bimestral", "cuatrimestral", "anual", "alta_inicial"]
InstitutionCode = Literal["sat", "imss", "infonavit", "stps_repse", "interno_cliente"]

MONTHS_ES: tuple[str, ...] = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)


@dataclass(frozen=True)
class OnboardingRequirement:
    """A single document expected during Expediente Corporativo (onboarding)."""

    code: str
    name: str
    section: str
    institution: InstitutionCode
    persona_types: tuple[PersonaType, ...]
    required: bool = True
    note: str | None = None


@dataclass(frozen=True)
class RecurringRequirement:
    """A single recurring document expected for a given period of a given year."""

    code: str
    name: str
    institution: InstitutionCode
    frequency: Frequency
    # 1-12, the month in which the document is DUE / expected to be uploaded.
    due_month: int
    # Human readable description of the period the document covers
    # (e.g. "Enero", "Diciembre año anterior", "B1 Enero-Febrero", "Q1 Enero-Abril").
    period_label: str
    # Canonical, machine-friendly key for the period the document COVERS (not
    # the month it is due). Examples: "2026-M01", "2025-M12", "2026-B1",
    # "2025-B6", "2026-Q1", "2025-Q3", "2025-A". Stable across years and the
    # canonical join key against ``periods.period_key``.
    period_key: str
    # Persona types this applies to (both by default).
    persona_types: tuple[PersonaType, ...] = ("moral", "fisica")


# ---------------------------------------------------------------------------
# Onboarding (Expediente Corporativo)
# ---------------------------------------------------------------------------

_ONBOARDING_MORAL: tuple[OnboardingRequirement, ...] = (
    # Contrato
    OnboardingRequirement(
        code="ONB-CONT-001",
        name="Contrato original y anexos",
        section="Contrato",
        institution="interno_cliente",
        persona_types=("moral", "fisica"),
    ),
    OnboardingRequirement(
        code="ONB-CONT-002",
        name="Modificaciones al contrato",
        section="Contrato",
        institution="interno_cliente",
        persona_types=("moral", "fisica"),
        required=False,
        note="Solo si existen modificaciones.",
    ),
    OnboardingRequirement(
        code="ONB-CONT-003",
        name="Órdenes de servicio",
        section="Contrato",
        institution="interno_cliente",
        persona_types=("moral", "fisica"),
        required=False,
        note="En caso de aplicar.",
    ),
    # Documentación Corporativa (Moral)
    OnboardingRequirement(
        code="ONB-CORP-M-001",
        name="Acta constitutiva / reformas (objeto social vigente)",
        section="Documentación Corporativa",
        institution="interno_cliente",
        persona_types=("moral",),
    ),
    OnboardingRequirement(
        code="ONB-CORP-M-002",
        name="Constancia de Situación Fiscal (CSF)",
        section="Documentación Corporativa",
        institution="sat",
        persona_types=("moral",),
    ),
    # Documentación Corporativa (Física)
    OnboardingRequirement(
        code="ONB-CORP-F-001",
        name="Identificación oficial",
        section="Documentación Corporativa",
        institution="interno_cliente",
        persona_types=("fisica",),
    ),
    OnboardingRequirement(
        code="ONB-CORP-F-002",
        name="Constancia de Situación Fiscal (CSF) y actualizaciones",
        section="Documentación Corporativa",
        institution="sat",
        persona_types=("fisica",),
    ),
    # Registro REPSE
    OnboardingRequirement(
        code="ONB-REPSE-001",
        name="Registro REPSE original",
        section="Registro REPSE",
        institution="stps_repse",
        persona_types=("moral", "fisica"),
    ),
    OnboardingRequirement(
        code="ONB-REPSE-002",
        name="Actualizaciones REPSE",
        section="Registro REPSE",
        institution="stps_repse",
        persona_types=("moral", "fisica"),
        required=False,
        note="Si hubo actualizaciones desde el alta.",
    ),
    OnboardingRequirement(
        code="ONB-REPSE-003",
        name="Renovaciones REPSE",
        section="Registro REPSE",
        institution="stps_repse",
        persona_types=("moral", "fisica"),
        required=False,
        note="Si ya pasó el periodo de renovación.",
    ),
    # Registro Patronal
    OnboardingRequirement(
        code="ONB-PATR-001",
        name="Registro patronal original",
        section="Registro Patronal",
        institution="imss",
        persona_types=("moral", "fisica"),
    ),
    OnboardingRequirement(
        code="ONB-PATR-002",
        name="Renovaciones de registro patronal",
        section="Registro Patronal",
        institution="imss",
        persona_types=("moral", "fisica"),
        required=False,
        note="Si aplica para el periodo vigente.",
    ),
)


# Document templates for recurring institutions (same docs repeat each period).
_IMSS_DOCS: tuple[str, ...] = (
    "Comprobante de pago bancario",
    "CFDI de pago de cuotas",
    "Cuotas obrero patronales",
    "Resumen de liquidación",
)
_INFONAVIT_DOCS: tuple[str, ...] = _IMSS_DOCS
_SAT_DOCS: tuple[str, ...] = (
    "Declaración ISR por retención sueldos y salarios",
    "Declaración IVA",
    "Comprobante entero pago ISR",
    "Comprobante entero pago IVA",
    "Comprobantes de nómina de los trabajadores",
)
_ACUSES_DOCS: tuple[str, ...] = ("Acuse SISUB", "Acuse ICSOE")

# INFONAVIT bimonthly slots: due month -> covered period label.
# Per the Árbol: B6 covers Nov-Dic año anterior and is due in Enero of current year,
# then B1 Ene-Feb due Marzo, B2 Mar-Abr due Mayo, etc.
_INFONAVIT_DUE_MONTH_TO_PERIOD: dict[int, str] = {
    1: "B6 Noviembre-Diciembre año anterior",
    3: "B1 Enero-Febrero",
    5: "B2 Marzo-Abril",
    7: "B3 Mayo-Junio",
    9: "B4 Julio-Agosto",
    11: "B5 Septiembre-Octubre",
}

# INFONAVIT bimonthly slots: due month -> (year offset, bimester number 1..6).
# B6 (the November-December bimester) is due in January and covers the previous
# year, hence the -1 offset.
_INFONAVIT_DUE_MONTH_TO_BIMESTER: dict[int, tuple[int, int]] = {
    1: (-1, 6),
    3: (0, 1),
    5: (0, 2),
    7: (0, 3),
    9: (0, 4),
    11: (0, 5),
}

# Acuses Contratos-Reportes cuatrimestral: due month -> covered period label.
_ACUSES_DUE_MONTH_TO_PERIOD: dict[int, str] = {
    1: "Q3 Septiembre-Diciembre año anterior",
    5: "Q1 Enero-Abril",
    9: "Q2 Mayo-Agosto",
}

# Acuses cuatrimestral: due month -> (year offset, quarter number 1..3).
_ACUSES_DUE_MONTH_TO_QUARTER: dict[int, tuple[int, int]] = {
    1: (-1, 3),
    5: (0, 1),
    9: (0, 2),
}


def _previous_month_label(due_month: int, *, year: int) -> str:
    """Return the human label of the month covered by a monthly obligation."""
    if due_month == 1:
        return f"Diciembre {year - 1}"
    return MONTHS_ES[due_month - 2]


def _monthly_period_key(due_month: int, *, year: int) -> str:
    """Return the canonical period_key for a monthly obligation due in ``due_month``.

    Monthly obligations cover the month *before* the due month. The January
    slot covers December of the previous year.
    """
    if due_month == 1:
        return f"{year - 1}-M12"
    return f"{year}-M{due_month - 1:02d}"


def _bimonthly_period_key(due_month: int, *, year: int) -> str:
    """Return the canonical period_key for an INFONAVIT bimestral slot."""
    offset, bimester = _INFONAVIT_DUE_MONTH_TO_BIMESTER[due_month]
    return f"{year + offset}-B{bimester}"


def _quarter_period_key(due_month: int, *, year: int) -> str:
    """Return the canonical period_key for an Acuses cuatrimestral slot."""
    offset, quarter = _ACUSES_DUE_MONTH_TO_QUARTER[due_month]
    return f"{year + offset}-Q{quarter}"


def _annual_period_key(*, year: int) -> str:
    """Return the canonical period_key for the annual SAT obligation.

    The acuse de declaración anual filed in April covers the previous fiscal
    year, so the period_key always points one year back.
    """
    return f"{year - 1}-A"


def expediente_for_persona(persona_type: PersonaType) -> list[OnboardingRequirement]:
    """Return the onboarding requirements applicable to a persona type."""
    return [req for req in _ONBOARDING_MORAL if persona_type in req.persona_types]


def recurring_for_year(
    year: int, persona_type: PersonaType = "moral"
) -> list[RecurringRequirement]:
    """Compute the full recurring requirement list for a given year and persona type."""
    result: list[RecurringRequirement] = []

    for due_month in range(1, 13):
        # IMSS monthly (covers previous month).
        imss_period = _previous_month_label(due_month, year=year)
        monthly_key = _monthly_period_key(due_month, year=year)
        for doc_name in _IMSS_DOCS:
            result.append(
                RecurringRequirement(
                    code=f"REC-IMSS-{year}-{due_month:02d}-{_slug(doc_name)}",
                    name=doc_name,
                    institution="imss",
                    frequency="mensual",
                    due_month=due_month,
                    period_label=f"IMSS {imss_period}",
                    period_key=monthly_key,
                    persona_types=("moral", "fisica"),
                )
            )

        # SAT monthly (covers previous month).
        sat_period = _previous_month_label(due_month, year=year)
        for doc_name in _SAT_DOCS:
            result.append(
                RecurringRequirement(
                    code=f"REC-SAT-{year}-{due_month:02d}-{_slug(doc_name)}",
                    name=doc_name,
                    institution="sat",
                    frequency="mensual",
                    due_month=due_month,
                    period_label=f"SAT {sat_period}",
                    period_key=monthly_key,
                    persona_types=("moral", "fisica"),
                )
            )

        # INFONAVIT bimonthly.
        if due_month in _INFONAVIT_DUE_MONTH_TO_PERIOD:
            inf_period = _INFONAVIT_DUE_MONTH_TO_PERIOD[due_month]
            bimonthly_key = _bimonthly_period_key(due_month, year=year)
            for doc_name in _INFONAVIT_DOCS:
                result.append(
                    RecurringRequirement(
                        code=f"REC-INFONAVIT-{year}-{due_month:02d}-{_slug(doc_name)}",
                        name=doc_name,
                        institution="infonavit",
                        frequency="bimestral",
                        due_month=due_month,
                        period_label=f"INFONAVIT {inf_period}",
                        period_key=bimonthly_key,
                        persona_types=("moral", "fisica"),
                    )
                )

        # Acuses SISUB / ICSOE cuatrimestral.
        if due_month in _ACUSES_DUE_MONTH_TO_PERIOD:
            ac_period = _ACUSES_DUE_MONTH_TO_PERIOD[due_month]
            quarter_key = _quarter_period_key(due_month, year=year)
            for doc_name in _ACUSES_DOCS:
                result.append(
                    RecurringRequirement(
                        code=f"REC-ACUSES-{year}-{due_month:02d}-{_slug(doc_name)}",
                        name=doc_name,
                        institution="stps_repse",
                        frequency="cuatrimestral",
                        due_month=due_month,
                        period_label=f"Acuses Contratos-Reportes {ac_period}",
                        period_key=quarter_key,
                        persona_types=("moral", "fisica"),
                    )
                )

        # Annual: Acuse declaración anual de impuestos, due in Abril.
        if due_month == 4:
            result.append(
                RecurringRequirement(
                    code=f"REC-SAT-{year}-04-acuse-anual",
                    name="Acuse declaración anual de impuestos",
                    institution="sat",
                    frequency="anual",
                    due_month=4,
                    period_label=f"SAT Anual {year - 1}",
                    period_key=_annual_period_key(year=year),
                    persona_types=("moral", "fisica"),
                )
            )

    return [r for r in result if persona_type in r.persona_types]


def catalog_metadata() -> dict[str, str]:
    return {"source": CATALOG_SOURCE, "version": CATALOG_VERSION}


def expediente_as_dicts(persona_type: PersonaType) -> list[dict]:
    return [asdict(r) for r in expediente_for_persona(persona_type)]


def recurring_as_dicts(year: int, persona_type: PersonaType) -> list[dict]:
    return [asdict(r) for r in recurring_for_year(year, persona_type)]


def lookup_onboarding_by_code(code: str) -> OnboardingRequirement | None:
    """Lookup an onboarding requirement by canonical ``ONB-*`` code."""
    for req in _ONBOARDING_MORAL:
        if req.code == code:
            return req
    return None


def lookup_recurring_by_code(code: str) -> RecurringRequirement | None:
    """Lookup a recurring requirement by canonical ``REC-*`` code.

    The catalog generates recurring items per year, so the year is recovered
    from the code itself (``REC-<INST>-<YEAR>-<DUE_MONTH>-<slug>``). When the
    code does not parse to a known shape the function returns ``None`` and the
    caller should treat the input as unknown.
    """
    parts = code.split("-")
    if len(parts) < 4 or parts[0] != "REC":
        return None
    try:
        year = int(parts[2])
    except ValueError:
        return None
    for req in recurring_for_year(year):
        if req.code == code:
            return req
    return None


def _slug(value: str) -> str:
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return normalized[:60] or "doc"


__all__ = [
    "CATALOG_SOURCE",
    "CATALOG_VERSION",
    "lookup_onboarding_by_code",
    "lookup_recurring_by_code",
    "MONTHS_ES",
    "OnboardingRequirement",
    "RecurringRequirement",
    "catalog_metadata",
    "expediente_as_dicts",
    "expediente_for_persona",
    "recurring_as_dicts",
    "recurring_for_year",
]


# Field aliases for ``field`` import compatibility (kept for future expansion).
_ = field  # noqa: F841
