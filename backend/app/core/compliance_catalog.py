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
    # Phase 5 — UX enrichment that used to live in frontend mocks.
    # All default to empty; the portal endpoint falls back to an
    # institution-based default copy when blank, so the catalog can be
    # enriched per-item later without breaking the API shape.
    why: str = ""
    format: str = ""
    # Stage 2 (BL-002, 2026-05-20) — first-upload guidance copy. A
    # provider who has never seen a CSF or REPSE registration before
    # needs to know what the document actually contains, where to get
    # it, and what mistakes are common before they upload. All three
    # are optional and fall back to per-institution defaults — see
    # ``onboarding_anatomy`` / ``onboarding_where_to_obtain`` /
    # ``onboarding_common_errors`` below.
    anatomy: str = ""
    where_to_obtain: str = ""
    common_errors: tuple[str, ...] = ()


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
    # Phase 5 — UX enrichment surfaced by the calendar endpoint.
    # ``required_document`` defaults to the requirement name; the
    # ``due_day`` is the conventional 17th-of-month REPSE deadline (SAT
    # annual override is set at build time below).
    required_document: str = ""
    due_day: int = 17


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
        anatomy=(
            "El contrato de servicios especializados firmado entre tu "
            "empresa y el cliente, incluyendo cualquier anexo técnico, "
            "comercial o tabulador que forme parte del acuerdo. Debe "
            "estar firmado por ambas partes y contener objeto, vigencia, "
            "alcance del servicio especializado y el desglose económico."
        ),
        where_to_obtain=(
            "Pídeselo al área legal o comercial del cliente, o súbelo "
            "desde tu propio archivo si tu empresa custodia el original "
            "firmado."
        ),
        common_errors=(
            "Subir solo una propuesta o cotización en lugar del contrato firmado.",
            "Omitir los anexos cuando el contrato hace referencia a ellos.",
            "Subir una copia sin firma de alguna de las dos partes.",
        ),
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
        anatomy=(
            "El acta constitutiva original protocolizada ante notario y "
            "todas las reformas posteriores que modifiquen el objeto "
            "social, capital, representación legal o domicilio. El "
            "objeto social que aparece en el acta vigente debe incluir "
            "los servicios especializados que prestas; ese es el dato "
            "que el cliente revisa primero."
        ),
        where_to_obtain=(
            "Pide el archivo PDF a la notaría que protocolizó el acta, "
            "o usa la copia certificada que ya tengas en custodia legal."
        ),
        common_errors=(
            "Subir solo el acta original sin las reformas posteriores cuando ya existen.",
            "Subir una versión sin sello del notario o sin protocolización.",
            (
                "Falta de coincidencia entre el objeto social y los "
                "servicios que prestas en el contrato."
            ),
        ),
    ),
    OnboardingRequirement(
        code="ONB-CORP-M-002",
        name="Constancia de Situación Fiscal (CSF)",
        section="Documentación Corporativa",
        institution="sat",
        persona_types=("moral",),
        anatomy=(
            "La Constancia de Situación Fiscal vigente emitida por el "
            "SAT. Debe estar a nombre de la empresa proveedora y mostrar "
            "el RFC, la razón social, el régimen fiscal y el domicilio "
            "fiscal actualizado. Aceptamos únicamente la versión emitida "
            "en los últimos 90 días para confirmar que los datos están "
            "al corriente."
        ),
        where_to_obtain=(
            "Descárgala desde el portal del SAT (sat.gob.mx) entrando "
            "con la e.firma o RFC y contraseña, en \"Otros trámites y "
            "servicios → Constancia de Situación Fiscal\"."
        ),
        common_errors=(
            "Subir una CSF de más de 90 días de emisión.",
            "Subir la CSF del representante legal en lugar de la de la empresa.",
            "Subir una captura de pantalla en lugar del PDF oficial del SAT.",
        ),
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
        anatomy=(
            "La Constancia de Situación Fiscal vigente emitida por el "
            "SAT a tu nombre como persona física. Debe mostrar tu RFC, "
            "tu nombre completo tal como aparece en tu identificación, "
            "el régimen fiscal y el domicilio fiscal actualizado. "
            "Aceptamos únicamente la versión emitida en los últimos 90 "
            "días. Si has tenido actualizaciones recientes, sube también "
            "la versión actualizada."
        ),
        where_to_obtain=(
            "Descárgala desde el portal del SAT (sat.gob.mx) entrando "
            "con tu RFC y contraseña o con e.firma, en \"Otros trámites "
            "y servicios → Constancia de Situación Fiscal\"."
        ),
        common_errors=(
            "Subir una CSF de más de 90 días de emisión.",
            "Subir una captura de pantalla en lugar del PDF oficial del SAT.",
            "Subir una versión vieja cuando ya tienes una actualización reciente.",
        ),
    ),
    # Registro REPSE
    OnboardingRequirement(
        code="ONB-REPSE-001",
        name="Registro REPSE original",
        section="Registro REPSE",
        institution="stps_repse",
        persona_types=("moral", "fisica"),
        anatomy=(
            "El acuse oficial del Registro de Prestadoras de Servicios "
            "Especializados u Obras Especializadas (REPSE) emitido por "
            "la STPS. Debe mostrar el folio REPSE, la razón social o "
            "nombre del proveedor, la fecha de registro y la lista de "
            "actividades autorizadas. Este es el documento ancla del "
            "expediente: sin REPSE vigente, tu cliente no puede "
            "contratarte para servicios especializados."
        ),
        where_to_obtain=(
            "Descárgalo desde el portal REPSE de la STPS "
            "(repse.stps.gob.mx) entrando con tu usuario y contraseña, "
            "en la sección \"Mi registro\" o \"Constancia\"."
        ),
        common_errors=(
            "Subir solo el acuse de solicitud en lugar del acuse de registro autorizado.",
            "Subir una versión con folio que ya no corresponde porque hubo renovación posterior.",
            "Falta de coincidencia entre las actividades autorizadas y los servicios del contrato.",
        ),
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
                    # SAT's anual deadline is the 30th of April. We
                    # encode the conservative 30 instead of the strict
                    # legal 30/31 ambiguity, and keep day=17 for every
                    # other recurring item.
                    due_day=30,
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


# ---------------------------------------------------------------------------
# Phase 5 — UX enrichment helpers
# ---------------------------------------------------------------------------
#
# These helpers used to live as inline copy inside frontend mocks
# (``frontend/lib/mock/expediente.ts`` and ``frontend/lib/mock/calendar.ts``).
# Moving them server-side means:
#
# 1. The provider portal's onboarding + calendar pages can drop the
#    adapter layer entirely and render backend data verbatim.
# 2. Any future surface — a client dashboard, a reviewer brief, the
#    sample-PDF generator — sees the same copy without re-inventing it.
# 3. Admin-managed requirement copy (a future phase) can replace this
#    static dict without changing the API shape.


# Default copy per institution. Used when an OnboardingRequirement does
# not carry an explicit ``why`` / ``format`` value. Sticking to per-
# institution defaults (rather than per-code) keeps the diff small while
# the copy remains useful — each institution's documents share enough
# common framing that one paragraph reads cleanly across them.
_ONBOARDING_DEFAULT_WHY: dict[InstitutionCode, str] = {
    "sat": (
        "Este documento valida tu situación fiscal ante el SAT y permite "
        "facturar servicios especializados sin observaciones del cliente."
    ),
    "stps_repse": (
        "Sin un Registro REPSE vigente tu cliente no puede contratarte "
        "para servicios especializados — es el documento ancla del "
        "expediente."
    ),
    "imss": (
        "Comprueba que tu relación patronal está activa ante el IMSS y "
        "que tus trabajadores están dados de alta."
    ),
    "infonavit": (
        "Acredita que tus trabajadores acceden a las prestaciones de "
        "vivienda que exige la ley."
    ),
    "interno_cliente": (
        "Forma parte de tu expediente regulatorio interno con el cliente; "
        "lo necesitamos para soportar la trazabilidad legal del servicio."
    ),
}


_ONBOARDING_DEFAULT_FORMAT: dict[InstitutionCode, str] = {
    "sat": "PDF · descarga oficial desde el portal del SAT.",
    "stps_repse": "PDF · acuse emitido por la STPS.",
    "imss": "PDF · constancia o resumen emitido por el IMSS.",
    "infonavit": "PDF · resumen o liquidación emitida por INFONAVIT.",
    "interno_cliente": "PDF · escaneo legible del documento original.",
}


# Stage 2 (BL-002, 2026-05-20) — first-upload guidance copy.
# Per-institution fallbacks for requirements that don't carry an
# explicit anatomy / where-to-obtain / common-errors override. Keep
# the language non-technical: every string should make sense to a
# provider who has never seen a REPSE expediente before.
_ONBOARDING_DEFAULT_ANATOMY: dict[InstitutionCode, str] = {
    "sat": (
        "Documento oficial emitido por el SAT que respalda tu situación "
        "fiscal o tributaria. Debe contener tu RFC, razón social o "
        "nombre, y los datos vigentes en el padrón del SAT."
    ),
    "stps_repse": (
        "Acuse oficial emitido por la STPS dentro del padrón de "
        "Prestadoras de Servicios Especializados (REPSE). Debe "
        "contener el folio REPSE, la razón social y las actividades "
        "autorizadas."
    ),
    "imss": (
        "Documento oficial del IMSS que comprueba tu relación patronal "
        "y el cumplimiento de tus obligaciones de seguridad social."
    ),
    "infonavit": (
        "Documento oficial de INFONAVIT que acredita el cumplimiento de "
        "tus obligaciones de vivienda con los trabajadores."
    ),
    "interno_cliente": (
        "Documento interno entre tu empresa y el cliente que respalda "
        "la prestación del servicio especializado."
    ),
}

_ONBOARDING_DEFAULT_WHERE: dict[InstitutionCode, str] = {
    "sat": "Descárgalo del portal del SAT (sat.gob.mx) con tu RFC y contraseña o e.firma.",
    "stps_repse": (
        "Descárgalo del portal REPSE de la STPS (repse.stps.gob.mx) "
        "con tu usuario y contraseña."
    ),
    "imss": "Descárgalo del portal IDSE del IMSS (idse.imss.gob.mx) con tu usuario patronal.",
    "infonavit": "Descárgalo del portal empresarial de INFONAVIT con tu NRP y contraseña.",
    "interno_cliente": "Súbelo desde tu archivo legal, o pídelo al área legal del cliente.",
}

_ONBOARDING_DEFAULT_COMMON_ERRORS: dict[InstitutionCode, tuple[str, ...]] = {
    "sat": (
        "Subir capturas de pantalla en lugar del PDF oficial del SAT.",
        "Subir una versión vencida o de más de 90 días de emisión.",
    ),
    "stps_repse": (
        "Subir el acuse de solicitud en lugar del acuse de registro autorizado.",
        "Subir una versión sin folio o sin la firma electrónica de la STPS.",
    ),
    "imss": (
        "Subir reportes internos en lugar de documentos emitidos por el IMSS.",
        "Subir versiones del mes anterior cuando ya tienes la del periodo en curso.",
    ),
    "infonavit": (
        "Subir reportes internos en lugar del documento oficial de INFONAVIT.",
        "Subir el bimestre anterior cuando el cliente espera el bimestre en curso.",
    ),
    "interno_cliente": (
        "Subir el archivo sin firma o sin sello cuando el original sí los tiene.",
        "Subir solo una parte del documento (faltan anexos o páginas).",
    ),
}


def onboarding_why(req: OnboardingRequirement) -> str:
    """Return per-item ``why`` copy with an institution-based fallback."""
    return req.why or _ONBOARDING_DEFAULT_WHY.get(req.institution, "")


def onboarding_format(req: OnboardingRequirement) -> str:
    """Return per-item ``format`` copy with an institution-based fallback."""
    return req.format or _ONBOARDING_DEFAULT_FORMAT.get(req.institution, "PDF.")


def onboarding_anatomy(req: OnboardingRequirement) -> str:
    """Return per-item ``anatomy`` copy with an institution-based fallback."""
    return req.anatomy or _ONBOARDING_DEFAULT_ANATOMY.get(req.institution, "")


def onboarding_where_to_obtain(req: OnboardingRequirement) -> str:
    """Return per-item ``where_to_obtain`` copy with an institution-based fallback."""
    return req.where_to_obtain or _ONBOARDING_DEFAULT_WHERE.get(req.institution, "")


def onboarding_common_errors(req: OnboardingRequirement) -> tuple[str, ...]:
    """Return per-item ``common_errors`` list with an institution-based fallback."""
    return req.common_errors or _ONBOARDING_DEFAULT_COMMON_ERRORS.get(
        req.institution, ()
    )


def recurring_required_document(req: RecurringRequirement) -> str:
    """Return the document the provider is expected to upload.

    Falls back to the requirement name when the catalog row does not
    carry an explicit ``required_document`` value (the requirement name
    is itself the document name for most recurring slots).
    """
    return req.required_document or req.name


__all__ = [
    "onboarding_why",
    "onboarding_format",
    "onboarding_anatomy",
    "onboarding_where_to_obtain",
    "onboarding_common_errors",
    "recurring_required_document",
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
