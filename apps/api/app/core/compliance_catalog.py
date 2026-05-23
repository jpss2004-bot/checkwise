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

import logging
from dataclasses import asdict, dataclass, field
from typing import Literal

from app.core.config import settings

logger = logging.getLogger(__name__)

CATALOG_SOURCE = "C.Árbol Plataforma Proveedores REPSE VF"
CATALOG_VERSION = "2026.06.0"

PersonaType = Literal["moral", "fisica"]
Frequency = Literal["mensual", "bimestral", "cuatrimestral", "anual", "alta_inicial"]
InstitutionCode = Literal["sat", "imss", "infonavit", "stps_repse", "interno_cliente"]


# Bugfix (2026-05-21) — Jay Luna calendar empty-grid bug.
#
# ``recurring_for_year``/``expediente_for_persona`` filter strictly on
# ``persona_type in r.persona_types`` where the row's persona_types
# tuple uses canonical tokens ``"moral"`` / ``"fisica"``. Several data
# entry paths in the wild stored full-label variants instead
# (``"persona_moral"``, ``"persona_fisica"``, etc.) — the catalog
# silently returned ``[]`` for those workspaces and the provider
# calendar rendered as "Sin obligaciones".
#
# This normalizer is the single source of truth for resolving any
# stored persona_type into the canonical token. Call it at every
# boundary that reads ``workspace.persona_type`` /
# ``vendor.persona_type`` before passing to the catalog. Unknown
# values fall back to ``"moral"`` with a WARNING log so the calendar
# never silently empties — preferring a wrong-but-visible default
# over a silent zero. Operators can grep the log for
# ``compliance_catalog: unrecognized persona_type`` to find the bad
# rows and clean them up.


_PERSONA_TYPE_ALIASES: dict[str, PersonaType] = {
    "moral": "moral",
    "fisica": "fisica",
    "física": "fisica",
    "persona_moral": "moral",
    "persona_fisica": "fisica",
    "persona_física": "fisica",
    "persona moral": "moral",
    "persona fisica": "fisica",
    "persona física": "fisica",
    "pm": "moral",
    "pf": "fisica",
}


def normalize_persona_type(value: str | None) -> PersonaType:
    """Resolve any stored persona_type string into a canonical token.

    Accepts the canonical ``"moral"`` / ``"fisica"`` as well as the
    full-label variants (``"persona_moral"``, ``"persona física"``,
    case-insensitive, with or without underscores), and a handful of
    short codes (``"PM"`` / ``"PF"``).

    Unknown values fall back to ``"moral"`` and emit a WARNING. The
    fallback is deliberate: an empty calendar is the worst possible
    outcome (Jay Luna bug). A wrong-but-visible calendar lets the
    provider see SOMETHING and lets ops notice the bad row in the log.
    """
    if value is None:
        logger.warning(
            "compliance_catalog: persona_type is None; defaulting to 'moral'"
        )
        return "moral"
    key = value.strip().lower()
    if key in _PERSONA_TYPE_ALIASES:
        return _PERSONA_TYPE_ALIASES[key]
    logger.warning(
        "compliance_catalog: unrecognized persona_type=%r; defaulting to 'moral'",
        value,
    )
    return "moral"
# Catalog v2 — how many of the ``accepts_documents`` must be submitted
# for a row to be considered satisfied. ``"one"`` matches the
# "either / or / both" semantics Jose Pablo described on 2026-05-20:
# a single acceptable doc is enough. ``"all"`` is the stricter
# all-of-N package mode (e.g. bank receipt + CFDI + cédula together).
MinimumDocuments = Literal["one", "all"]

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
    # Phase 6 — renewal cadence for onboarding docs that lose validity
    # over time (CSF every 90 days, REPSE every ~3 years, registro
    # patronal every ~3 years). ``None`` means the requirement is a
    # one-time onboarding piece with no scheduled renewal — that is
    # still the default for every onboarding row that doesn't carry an
    # explicit cadence, including the opt-in ``-002`` / ``-003``
    # "updates" / "renewals" rows for REPSE and patronal (those are
    # provider-driven uploads, not schedule-driven).
    renewal_frequency_days: int | None = None


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
    # Stage 2.7 (T5 parity, 2026-05-20) — recurring obligations need the
    # same first-upload guidance shape as onboarding requirements: what
    # the document contains, where to obtain it, and the recurring
    # mistakes the calendar drawer should call out. All three default to
    # empty; the calendar endpoint falls back to per-doc-name overrides
    # (``_RECURRING_DOC_OVERRIDES``) and then to per-institution
    # defaults so the catalog can be enriched per item without changing
    # the API shape.
    anatomy: str = ""
    where_to_obtain: str = ""
    common_errors: tuple[str, ...] = ()
    # Catalog v2 (2026-05-20) — accepted-document alternatives. On v1
    # rows these stay empty (the row is its own single doc). On v2
    # rows ``accepts_documents`` lists every doc type that can satisfy
    # the obligation (e.g. comprobante de pago bancario / CFDI / cédula
    # / resumen all evidence the same IMSS monthly payment), and
    # ``minimum_documents`` decides whether the provider needs to
    # submit one of them (default) or all of them. v2 is gated by
    # ``settings.RECURRING_CATALOG_V2``; existing v1 callers see no
    # behavior change while the flag stays off.
    accepts_documents: tuple[str, ...] = ()
    minimum_documents: MinimumDocuments = "one"


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
            (
                "Subir una versión vencida del contrato cuando ya existe una "
                "renovación o adenda."
            ),
            (
                "Subir un archivo en cualquier formato distinto a PDF "
                "(Word, imagen, foto del documento)."
            ),
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
            (
                "Subir una versión escaneada borrosa o ilegible en lugar "
                "del PDF protocolizado por el notario."
            ),
            (
                "Subir el acta de otra empresa del grupo en lugar de la "
                "del proveedor que firma el contrato."
            ),
        ),
    ),
    OnboardingRequirement(
        code="ONB-CORP-M-002",
        name="Constancia de Situación Fiscal (CSF)",
        section="Documentación Corporativa",
        institution="sat",
        persona_types=("moral",),
        renewal_frequency_days=90,
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
            (
                "Subir una CSF cuyo domicilio fiscal ya no coincide con "
                "el domicilio actualizado del proveedor."
            ),
            (
                "Subir una CSF en estado 'no localizado' o 'cancelado': "
                "el cliente no puede contratarte mientras estés en ese "
                "estado ante el SAT."
            ),
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
        renewal_frequency_days=90,
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
            (
                "Subir la CSF de una persona moral relacionada en lugar "
                "de la tuya como persona física."
            ),
            (
                "Subir una CSF cuyo nombre no coincide con la "
                "identificación oficial que también está en el expediente."
            ),
        ),
    ),
    # Registro REPSE
    OnboardingRequirement(
        code="ONB-REPSE-001",
        name="Registro REPSE original",
        section="Registro REPSE",
        institution="stps_repse",
        persona_types=("moral", "fisica"),
        renewal_frequency_days=1095,
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
            (
                "Subir una imagen o captura del portal REPSE en lugar "
                "del PDF oficial con folio y firma electrónica de la "
                "STPS."
            ),
            (
                "Subir una versión cuyo registro está suspendido o "
                "cancelado en el padrón REPSE."
            ),
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
        renewal_frequency_days=1095,
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


# ---------------------------------------------------------------------------
# Catalog v2 — collapsed recurring obligations (Session 1, 2026-05-20)
# ---------------------------------------------------------------------------
#
# Jose Pablo confirmed on 2026-05-20 that some recurring obligations are
# satisfied by *any* of several acceptable doc types. The classic
# example: IMSS monthly compliance is fully evidenced by a comprobante
# de pago bancario OR the CFDI de pago OR the cédula obrero patronal
# OR the resumen de liquidación — or any combination. The v1 catalog
# generates one row per doc type, which forces providers to navigate
# to 4 separate calendar cells and upload each separately.
#
# The v2 generator collapses those alternatives into one row per
# (institution, period). Each v2 row carries:
#
#   - ``accepts_documents``: the list of doc names the provider may
#     submit. The existing ``_RECURRING_DOC_OVERRIDES`` map keys per
#     (institution, doc_name) so the per-accepted-doc anatomy /
#     where_to_obtain / common_errors are reused verbatim — no second
#     copy of authored content.
#   - ``minimum_documents``: ``"one"`` by default (any one satisfies)
#     or ``"all"`` for the stricter all-of-N package mode. Per-row
#     override so we can mark, e.g., IMSS monthly as "one" but a future
#     "complete payment package" requirement as "all".
#
# This module exposes both shapes side by side. Session 1 (this commit)
# is foundation-only: the v2 generator + the accessor return a clean
# data shape; nothing in evidence_slots, the API endpoints, or the
# frontend consumes them yet. Session 2 wires the slot resolver under
# ``settings.RECURRING_CATALOG_V2``. Until that flag flips, v1 remains
# authoritative.


# v2 row labels by institution+frequency. Kept here (not inlined into
# the generator) so they can be tuned in one place when product / copy
# changes the obligation phrasing.
_V2_ROW_LABELS: dict[tuple[InstitutionCode, Frequency], str] = {
    ("imss", "mensual"): "Pago mensual de cuotas IMSS",
    ("sat", "mensual"): "Declaración y pago mensual SAT",
    ("infonavit", "bimestral"): "Pago bimestral de aportaciones INFONAVIT",
    ("stps_repse", "cuatrimestral"): "Reporte cuatrimestral SISUB / ICSOE",
    ("sat", "anual"): "Declaración anual SAT",
}


def _v2_row(
    *,
    code: str,
    institution: InstitutionCode,
    frequency: Frequency,
    due_month: int,
    period_label: str,
    period_key: str,
    accepts_documents: tuple[str, ...],
    due_day: int = 17,
    minimum_documents: MinimumDocuments = "one",
) -> RecurringRequirement:
    name = _V2_ROW_LABELS.get(
        (institution, frequency),
        f"Obligación {institution} {period_label}",
    )
    return RecurringRequirement(
        code=code,
        name=name,
        institution=institution,
        frequency=frequency,
        due_month=due_month,
        period_label=period_label,
        period_key=period_key,
        persona_types=("moral", "fisica"),
        due_day=due_day,
        accepts_documents=accepts_documents,
        minimum_documents=minimum_documents,
    )


def recurring_for_year_v2(
    year: int, persona_type: PersonaType = "moral"
) -> list[RecurringRequirement]:
    """Return the collapsed v2 recurring catalog for a given year.

    One row per (institution, period). Each row's ``accepts_documents``
    enumerates the doc names that satisfy the obligation; the existing
    Stage 2.7 ``_RECURRING_DOC_OVERRIDES`` map already covers
    per-doc-name anatomy / where_to_obtain / common_errors, so v2 reuses
    that authored content without a second copy.

    Row code shape: ``REC-<INSTITUTION>-<YEAR>-<DUE_MONTH:02d>``, with a
    ``-anual`` suffix for the SAT annual row. This is distinct from v1
    codes (which carry a per-doc suffix), so v1 and v2 coexist in the
    database without collision.

    Row counts (2026, persona moral):
      * IMSS monthly:        12
      * SAT monthly:         12
      * INFONAVIT bimestral:  6
      * STPS cuatrimestral:   3
      * SAT anual:            1
      * Total:               34   (vs ~139 in v1)
    """
    rows: list[RecurringRequirement] = []

    for due_month in range(1, 13):
        # IMSS monthly — accepts any combination of the 4 evidence docs.
        rows.append(
            _v2_row(
                code=f"REC-IMSS-{year}-{due_month:02d}",
                institution="imss",
                frequency="mensual",
                due_month=due_month,
                period_label=f"IMSS {_previous_month_label(due_month, year=year)}",
                period_key=_monthly_period_key(due_month, year=year),
                accepts_documents=_IMSS_DOCS,
            )
        )

        # SAT monthly — declaración + comprobante + CFDI nómina, any
        # combination satisfies the obligation.
        rows.append(
            _v2_row(
                code=f"REC-SAT-{year}-{due_month:02d}",
                institution="sat",
                frequency="mensual",
                due_month=due_month,
                period_label=f"SAT {_previous_month_label(due_month, year=year)}",
                period_key=_monthly_period_key(due_month, year=year),
                accepts_documents=_SAT_DOCS,
            )
        )

        # INFONAVIT bimestral — 6 bimesters per year.
        if due_month in _INFONAVIT_DUE_MONTH_TO_PERIOD:
            rows.append(
                _v2_row(
                    code=f"REC-INFONAVIT-{year}-{due_month:02d}",
                    institution="infonavit",
                    frequency="bimestral",
                    due_month=due_month,
                    period_label=(
                        f"INFONAVIT {_INFONAVIT_DUE_MONTH_TO_PERIOD[due_month]}"
                    ),
                    period_key=_bimonthly_period_key(due_month, year=year),
                    accepts_documents=_INFONAVIT_DOCS,
                )
            )

        # STPS cuatrimestral — SISUB and ICSOE. The classic "either /
        # or / both" obligation: some providers only file one, others
        # file both. ``minimum_documents="one"`` is correct here.
        if due_month in _ACUSES_DUE_MONTH_TO_PERIOD:
            rows.append(
                _v2_row(
                    code=f"REC-STPS-{year}-{due_month:02d}",
                    institution="stps_repse",
                    frequency="cuatrimestral",
                    due_month=due_month,
                    period_label=(
                        f"STPS {_ACUSES_DUE_MONTH_TO_PERIOD[due_month]}"
                    ),
                    period_key=_quarter_period_key(due_month, year=year),
                    accepts_documents=_ACUSES_DOCS,
                )
            )

        # SAT anual — single doc (acuse declaración anual). Day 30
        # deadline matches the v1 catalog override.
        if due_month == 4:
            rows.append(
                _v2_row(
                    code=f"REC-SAT-{year}-04-anual",
                    institution="sat",
                    frequency="anual",
                    due_month=4,
                    period_label=f"SAT Anual {year - 1}",
                    period_key=_annual_period_key(year=year),
                    accepts_documents=("Acuse declaración anual de impuestos",),
                    due_day=30,
                )
            )

    return [r for r in rows if persona_type in r.persona_types]


def catalog_metadata() -> dict[str, str]:
    return {"source": CATALOG_SOURCE, "version": CATALOG_VERSION}


def expediente_as_dicts(persona_type: PersonaType) -> list[dict]:
    return [asdict(r) for r in expediente_for_persona(persona_type)]


def recurring_as_dicts(year: int, persona_type: PersonaType) -> list[dict]:
    return [asdict(r) for r in recurring_for_year(year, persona_type)]


def is_v2_recurring_code(code: str) -> bool:
    """True iff ``code`` matches one of the catalog v2 row shapes.

    v2 shapes (Session 1):
      * ``REC-<INST>-<YYYY>-<MM>``       — monthly / bimestral / cuatrimestral
      * ``REC-SAT-<YYYY>-04-anual``      — annual

    v1 codes always carry a per-doc-name slug (multi-token, hyphenated),
    so they never collide with either shape above. The check is
    structural — no catalog iteration needed — so it's cheap enough
    for hot paths (URL builders run once per calendar item per
    request).

    Used by the calendar / dashboard URL builders to decide whether
    to append ``?v2=1`` so the frontend wizard switches to the
    alternatives radio picker. Session 3 audit found four href
    surfaces that needed this and only one was wired through.
    """
    parts = code.split("-")
    if not parts or parts[0] != "REC":
        return False
    if len(parts) == 4:
        # REC-INST-YYYY-MM
        return (
            parts[2].isdigit()
            and len(parts[2]) == 4
            and parts[3].isdigit()
            and len(parts[3]) == 2
        )
    if len(parts) == 5:
        # REC-SAT-YYYY-04-anual
        return (
            parts[1] == "SAT"
            and parts[2].isdigit()
            and len(parts[2]) == 4
            and parts[3] == "04"
            and parts[4] == "anual"
        )
    return False


def lookup_onboarding_by_code(code: str) -> OnboardingRequirement | None:
    """Lookup an onboarding requirement by canonical ``ONB-*`` code."""
    for req in _ONBOARDING_MORAL:
        if req.code == code:
            return req
    return None


def lookup_recurring_by_code(code: str) -> RecurringRequirement | None:
    """Lookup a recurring requirement by canonical ``REC-*`` code.

    The catalog generates recurring items per year, so the year is
    recovered from the code itself.

    v1 codes carry a per-doc suffix:
        ``REC-<INST>-<YEAR>-<DUE_MONTH>-<slug>``

    v2 codes (Session 1, 2026-05-20) collapse to one row per
    (institution, period):
        ``REC-<INST>-<YEAR>-<DUE_MONTH>``         (monthly / bimestral / cuatrimestral)
        ``REC-SAT-<YEAR>-04-anual``               (annual exception)

    This function tries v2 first when ``settings.RECURRING_CATALOG_V2``
    is on, then falls back to v1. With the flag off, behavior is
    identical to the v1-only world.

    The v1 fallback runs unconditionally so submissions written under
    the legacy code shape continue to resolve even after the flag
    flips — the compatibility-join story Session 2 locks in (legacy
    data never appears missing).

    Returns ``None`` when the code does not parse to any known shape.
    """
    parts = code.split("-")
    if len(parts) < 4 or parts[0] != "REC":
        return None
    try:
        year = int(parts[2])
    except ValueError:
        return None

    # v2-first when the flag is on. Iterating only the year's v2 rows
    # is cheap (~34 entries) and keeps the lookup deterministic.
    if settings.RECURRING_CATALOG_V2:
        for req in recurring_for_year_v2(year):
            if req.code == code:
                return req

    # v1 lookup. Runs whether the flag is on or off so legacy codes
    # remain resolvable forever — required for compatibility-join slot
    # resolution and for replaying historical audit-log entries.
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
# (``apps/web/lib/mock/expediente.ts`` and ``apps/web/lib/mock/calendar.ts``).
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


def onboarding_renewal_frequency_days(req: OnboardingRequirement) -> int | None:
    """Return the renewal cadence in days for an onboarding requirement.

    ``None`` for one-time onboarding rows (the default). A positive int
    for documents that lose validity over time — CSF (90), REPSE (1095),
    registro patronal (1095). The Phase 6 renewal helpers in
    :mod:`app.services.evidence_slots` consume this value.
    """
    return req.renewal_frequency_days


def recurring_required_document(req: RecurringRequirement) -> str:
    """Return the document the provider is expected to upload.

    Falls back to the requirement name when the catalog row does not
    carry an explicit ``required_document`` value (the requirement name
    is itself the document name for most recurring slots).
    """
    return req.required_document or req.name


# ---------------------------------------------------------------------------
# Stage 2.7 — Recurring requirement first-upload guidance
# ---------------------------------------------------------------------------
#
# Onboarding requirements ship anatomy / where_to_obtain / common_errors
# already (see the ``_ONBOARDING_DEFAULT_*`` dicts above). The transcript
# T5 + handoff §2.7-c ask is to mirror the same shape on the recurring
# calendar so the provider sees the same first-upload guidance when they
# click into a monthly / bimestral / cuatrimestral / annual slot.
#
# Recurring obligations are *generated* per year by ``recurring_for_year``
# from a small template set (4 IMSS docs, 4 INFONAVIT docs, 5 SAT docs,
# 2 acuses STPS, 1 annual SAT acuse). The dataclass field stays on the
# instance for parity, but the authored content lives here in two
# fallback layers:
#
# 1. ``_RECURRING_DOC_OVERRIDES`` — keyed by ``(institution, doc_name)``.
#    Highest priority. Used for the highest-volume documents the
#    handoff calls out: IMSS opinion (cuotas / resumen), INFONAVIT
#    certificate (cuotas / resumen), ISR mensual, SAT acuse anual,
#    STPS cuatrimestral SISUB/ICSOE.
# 2. ``_RECURRING_DEFAULT_*`` — keyed by institution. Used when no
#    per-doc override exists. Framed around the periodicity, not around
#    the document, so the same paragraph reads cleanly for every monthly
#    or bimestral slot from that institution.


_RECURRING_DEFAULT_ANATOMY: dict[InstitutionCode, str] = {
    "imss": (
        "Documento mensual emitido por el IMSS o el banco que comprueba "
        "el pago de cuotas obrero patronales del periodo y el alta de tus "
        "trabajadores. Debe corresponder al mes que pide el calendario."
    ),
    "infonavit": (
        "Documento bimestral emitido por INFONAVIT o el banco que "
        "comprueba el pago de las aportaciones de vivienda del bimestre "
        "y el cumplimiento por trabajador. Debe corresponder al bimestre "
        "que pide el calendario."
    ),
    "sat": (
        "Documento mensual emitido por el SAT o el banco que comprueba "
        "la declaración o el pago de impuestos del periodo. Debe "
        "corresponder al mes que pide el calendario y estar emitido a "
        "nombre del proveedor."
    ),
    "stps_repse": (
        "Acuse cuatrimestral emitido por la STPS dentro del padrón "
        "REPSE que reporta los contratos vigentes del cuatrimestre. "
        "Debe corresponder al periodo Q1, Q2 o Q3 que pide el calendario."
    ),
    "interno_cliente": (
        "Documento interno entre tu empresa y el cliente que respalda "
        "el cumplimiento del periodo correspondiente del contrato."
    ),
}


_RECURRING_DEFAULT_WHERE: dict[InstitutionCode, str] = {
    "imss": (
        "Descárgalo del portal IDSE del IMSS (idse.imss.gob.mx) con tu "
        "usuario patronal, o pídeselo al banco si es un comprobante de "
        "pago."
    ),
    "infonavit": (
        "Descárgalo del portal empresarial de INFONAVIT con tu NRP y "
        "contraseña, o pídeselo al banco si es un comprobante de pago."
    ),
    "sat": (
        "Descárgalo del portal del SAT (sat.gob.mx) con tu RFC y "
        "contraseña o e.firma. Los comprobantes de pago se descargan "
        "desde el portal del banco."
    ),
    "stps_repse": (
        "Descárgalo del portal SISUB o ICSOE de la STPS según "
        "corresponda, usando tu usuario y contraseña REPSE."
    ),
    "interno_cliente": (
        "Súbelo desde tu archivo interno o pídeselo al área legal del "
        "cliente."
    ),
}


_RECURRING_DEFAULT_COMMON_ERRORS: dict[InstitutionCode, tuple[str, ...]] = {
    "imss": (
        "Subir el comprobante del mes anterior cuando el cliente espera "
        "el del mes en curso.",
        "Subir un reporte interno en lugar del documento oficial del IMSS o del banco.",
        "Subir una captura de pantalla en lugar del PDF oficial.",
    ),
    "infonavit": (
        "Subir el bimestre anterior cuando el calendario pide el bimestre en curso.",
        "Subir un reporte interno en lugar del documento oficial de INFONAVIT o del banco.",
        "Subir una versión sin folio o sin la información del trabajador.",
    ),
    "sat": (
        "Subir el comprobante del mes anterior cuando el calendario pide el actual.",
        "Subir solo la declaración cuando también se requiere el comprobante de pago.",
        "Subir un acuse de presentación pendiente en lugar del acuse aceptado.",
    ),
    "stps_repse": (
        "Subir el acuse SISUB cuando el periodo pide ICSOE (o viceversa).",
        "Subir el cuatrimestre anterior en lugar del cuatrimestre vigente.",
        "Subir una captura de pantalla en lugar del PDF oficial con folio.",
    ),
    "interno_cliente": (
        "Subir un documento sin firma o sin sello cuando el original sí los tiene.",
        "Subir solo una parte del documento (faltan anexos o páginas).",
    ),
}


_RECURRING_DOC_OVERRIDES: dict[tuple[InstitutionCode, str], dict[str, object]] = {
    # IMSS — "opinión" / pago de cuotas mensual.
    ("imss", "Cuotas obrero patronales"): {
        "anatomy": (
            "Resumen mensual del IMSS que detalla las cuotas obrero "
            "patronales pagadas en el mes (cuotas obreras + cuotas "
            "patronales) por cada trabajador. Es el documento que el "
            "cliente cruza contra el listado de tu plantilla y contra "
            "el comprobante de pago bancario para confirmar que "
            "efectivamente pagaste lo que reportaste."
        ),
        "where_to_obtain": (
            "Descárgalo del portal IDSE del IMSS "
            "(idse.imss.gob.mx) en \"Reportes → Cédula de "
            "determinación de cuotas\" usando tu usuario patronal."
        ),
        "common_errors": (
            "Subir la cédula de un mes que no es el que pide el calendario.",
            "Subir un cálculo manual en lugar del PDF oficial del IMSS.",
            "Subir solo la cédula sin el comprobante de pago bancario asociado.",
            "Subir una cédula provisional en lugar de la versión definitiva del mes.",
            (
                "Subir una cédula que no incluye a todos los "
                "trabajadores que tienes dados de alta ante el IMSS."
            ),
        ),
    },
    ("imss", "Resumen de liquidación"): {
        "anatomy": (
            "Resumen mensual emitido por el IMSS que totaliza la "
            "liquidación del mes — base salarial, días cotizados, "
            "ramos de seguro y total a pagar. Acompaña a la cédula de "
            "determinación y al comprobante bancario como evidencia "
            "del cumplimiento de seguridad social del periodo."
        ),
        "where_to_obtain": (
            "Descárgalo del SUA o del portal IDSE del IMSS junto con "
            "la cédula del mes correspondiente."
        ),
        "common_errors": (
            "Subir un resumen interno en lugar del oficial del IMSS o del SUA.",
            "Subir el resumen de un mes distinto al que pide el calendario.",
            "Subir un resumen sin total a pagar o sin folio de liquidación.",
        ),
    },
    # INFONAVIT — certificado / pago bimestral.
    ("infonavit", "Cuotas obrero patronales"): {
        "anatomy": (
            "Resumen bimestral de INFONAVIT que detalla las "
            "aportaciones del 5 % de vivienda por trabajador del "
            "bimestre. Es el equivalente a la cédula del IMSS para "
            "vivienda y el documento que el cliente revisa contra el "
            "comprobante de pago bancario del bimestre."
        ),
        "where_to_obtain": (
            "Descárgalo del portal empresarial de INFONAVIT en "
            "\"Pagos → Resumen de liquidación\" usando tu NRP y "
            "contraseña."
        ),
        "common_errors": (
            "Subir el bimestre anterior cuando el calendario pide el bimestre en curso.",
            "Subir un cálculo manual en lugar del PDF oficial de INFONAVIT.",
            "Subir solo la liquidación sin el comprobante de pago bancario asociado.",
            (
                "Subir un resumen que no incluye a todos los "
                "trabajadores dados de alta en el periodo."
            ),
            (
                "Subir un resumen con monto cero cuando sí hubo trabajadores activos."
            ),
        ),
    },
    ("infonavit", "Resumen de liquidación"): {
        "anatomy": (
            "Resumen bimestral oficial de INFONAVIT que totaliza la "
            "liquidación del bimestre por trabajador y por concepto "
            "(5 % vivienda + abono a créditos). Acompaña a la cédula "
            "de cuotas y al comprobante bancario como evidencia "
            "completa del bimestre."
        ),
        "where_to_obtain": (
            "Descárgalo del portal empresarial de INFONAVIT junto con "
            "la liquidación del bimestre."
        ),
        "common_errors": (
            "Subir un resumen interno en lugar del oficial de INFONAVIT.",
            "Subir el bimestre incorrecto.",
            "Subir un resumen sin folio o sin total bimestral.",
        ),
    },
    # SAT — ISR mensual.
    ("sat", "Declaración ISR por retención sueldos y salarios"): {
        "anatomy": (
            "Declaración mensual del ISR por retenciones de sueldos y "
            "salarios que presentaste ante el SAT. Incluye el periodo, "
            "el ISR retenido a los trabajadores en el mes y el acuse "
            "de presentación. Acompaña al comprobante de pago como "
            "evidencia del cumplimiento mensual de retenciones."
        ),
        "where_to_obtain": (
            "Descárgala del portal del SAT (sat.gob.mx) en "
            "\"Declaraciones → Mensuales\" usando tu RFC y contraseña "
            "o e.firma."
        ),
        "common_errors": (
            "Subir la declaración de un mes distinto al que pide el calendario.",
            "Subir solo el acuse en lugar del PDF completo de la declaración.",
            "Subir una declaración con estatus 'pendiente de pago' sin el comprobante asociado.",
            (
                "Subir una declaración complementaria sin la declaración "
                "normal correspondiente."
            ),
            "Subir una declaración cuyos importes no cuadran con los CFDI de nómina del mes.",
        ),
    },
    ("sat", "Comprobante entero pago ISR"): {
        "anatomy": (
            "Comprobante bancario o línea de captura pagada del ISR "
            "retenido por sueldos y salarios del mes. Debe coincidir "
            "en monto, periodo y RFC con la declaración mensual del "
            "ISR ya presentada ante el SAT."
        ),
        "where_to_obtain": (
            "Descárgalo del portal del banco con el que pagaste la "
            "línea de captura, o del SAT si pagaste por NetPay/SPEI."
        ),
        "common_errors": (
            "Subir el comprobante de IVA en lugar del de ISR.",
            "Subir un comprobante cuyo monto no coincide con la declaración.",
            "Subir un comprobante de un mes distinto.",
        ),
    },
    # SAT — acuse anual.
    ("sat", "Acuse declaración anual de impuestos"): {
        "anatomy": (
            "Acuse oficial del SAT que confirma la presentación de tu "
            "declaración anual de impuestos del ejercicio fiscal "
            "anterior. Debe contener el RFC del proveedor, el "
            "ejercicio declarado, el folio del acuse y la firma "
            "electrónica del SAT. El plazo legal es el 30 de abril "
            "de cada año."
        ),
        "where_to_obtain": (
            "Descárgalo del portal del SAT (sat.gob.mx) en "
            "\"Declaraciones → Anuales\" después de presentar la "
            "declaración con tu e.firma."
        ),
        "common_errors": (
            "Subir el acuse de un ejercicio distinto al que pide el calendario.",
            "Subir solo la declaración sin el acuse de aceptación del SAT.",
            "Subir un acuse con estatus 'pendiente' sin el folio definitivo.",
            (
                "Subir una declaración complementaria sin la declaración "
                "anual normal correspondiente."
            ),
            (
                "Subir un acuse cuyo RFC no corresponde al proveedor del "
                "contrato."
            ),
        ),
    },
    # STPS — cuatrimestral SISUB.
    ("stps_repse", "Acuse SISUB"): {
        "anatomy": (
            "Acuse oficial del Sistema de Información de Subcontratación "
            "(SISUB) que reporta a la STPS los contratos y trabajadores "
            "involucrados en servicios especializados durante el "
            "cuatrimestre. Debe contener el folio SISUB, el "
            "cuatrimestre reportado y la firma electrónica de la "
            "STPS."
        ),
        "where_to_obtain": (
            "Descárgalo del portal SISUB de la STPS "
            "(sisub.stps.gob.mx) con tu usuario y contraseña REPSE, "
            "después de cargar la información del cuatrimestre."
        ),
        "common_errors": (
            "Subir el acuse del cuatrimestre anterior cuando el calendario pide el vigente.",
            "Subir el acuse de carga en lugar del acuse de presentación con folio.",
            "Subir una captura de pantalla en lugar del PDF oficial con firma de la STPS.",
            (
                "Subir un acuse cuyo número de trabajadores no cuadra con "
                "tu plantilla del IMSS del periodo."
            ),
            (
                "Subir un acuse SISUB de un proveedor distinto al que firma el contrato."
            ),
        ),
    },
    ("stps_repse", "Acuse ICSOE"): {
        "anatomy": (
            "Acuse oficial del Informe de Contratos de Servicios u "
            "Obras Especializadas (ICSOE) que reporta al IMSS los "
            "contratos vigentes del cuatrimestre. Es el complemento "
            "del SISUB ante el IMSS. Debe contener el folio ICSOE, el "
            "cuatrimestre y la firma electrónica del IMSS."
        ),
        "where_to_obtain": (
            "Descárgalo del portal ICSOE del IMSS "
            "(icsoe.imss.gob.mx) con tu usuario patronal después de "
            "cargar la información del cuatrimestre."
        ),
        "common_errors": (
            "Subir el ICSOE del cuatrimestre anterior cuando el calendario pide el vigente.",
            "Subir el SISUB en lugar del ICSOE (son trámites distintos).",
            "Subir el acuse de carga en lugar del acuse final con folio.",
            (
                "Subir un acuse cuyo número de trabajadores no cuadra con "
                "tu plantilla del IMSS del periodo."
            ),
            "Subir una captura de pantalla en lugar del PDF oficial.",
        ),
    },
}


def recurring_anatomy(req: RecurringRequirement) -> str:
    """Return per-item ``anatomy`` copy with override + institution fallback.

    Resolution order:
    1. Instance-level ``req.anatomy`` (rarely set — the generator does
       not stamp anatomy at build time).
    2. ``_RECURRING_DOC_OVERRIDES[(institution, name)]["anatomy"]``.
    3. ``_RECURRING_DEFAULT_ANATOMY[institution]``.
    """
    if req.anatomy:
        return req.anatomy
    override = _RECURRING_DOC_OVERRIDES.get((req.institution, req.name))
    if override and override.get("anatomy"):
        return str(override["anatomy"])
    return _RECURRING_DEFAULT_ANATOMY.get(req.institution, "")


def recurring_where_to_obtain(req: RecurringRequirement) -> str:
    """Return per-item ``where_to_obtain`` copy with override + institution fallback."""
    if req.where_to_obtain:
        return req.where_to_obtain
    override = _RECURRING_DOC_OVERRIDES.get((req.institution, req.name))
    if override and override.get("where_to_obtain"):
        return str(override["where_to_obtain"])
    return _RECURRING_DEFAULT_WHERE.get(req.institution, "")


def recurring_common_errors(req: RecurringRequirement) -> tuple[str, ...]:
    """Return per-item ``common_errors`` list with override + institution fallback."""
    if req.common_errors:
        return req.common_errors
    override = _RECURRING_DOC_OVERRIDES.get((req.institution, req.name))
    if override and override.get("common_errors"):
        return tuple(override["common_errors"])  # type: ignore[arg-type]
    return _RECURRING_DEFAULT_COMMON_ERRORS.get(req.institution, ())


def recurring_accepted_documents(
    req: RecurringRequirement,
) -> list[dict[str, object]]:
    """Return the per-accepted-doc detail list for a v2 catalog row.

    Each entry has the shape ``{"name": str, "anatomy": str,
    "where_to_obtain": str, "common_errors": list[str]}`` so the frontend
    drawer can render one disclosure per acceptable doc type without
    re-fetching the override map. Reuses the Stage 2.7
    ``_RECURRING_DOC_OVERRIDES`` map (per-doc-name authored content)
    with the per-institution defaults as the final fallback.

    Returns an empty list when ``accepts_documents`` is empty (a v1
    row), so legacy callers see ``[]`` and don't have to branch on the
    flag.
    """
    if not req.accepts_documents:
        return []

    institution_anatomy = _RECURRING_DEFAULT_ANATOMY.get(req.institution, "")
    institution_where = _RECURRING_DEFAULT_WHERE.get(req.institution, "")
    institution_errors = _RECURRING_DEFAULT_COMMON_ERRORS.get(req.institution, ())

    entries: list[dict[str, object]] = []
    for doc_name in req.accepts_documents:
        override = _RECURRING_DOC_OVERRIDES.get((req.institution, doc_name)) or {}
        entries.append(
            {
                "name": doc_name,
                "anatomy": str(override.get("anatomy") or institution_anatomy),
                "where_to_obtain": str(
                    override.get("where_to_obtain") or institution_where
                ),
                "common_errors": list(
                    override.get("common_errors")  # type: ignore[arg-type]
                    or institution_errors
                ),
            }
        )
    return entries


__all__ = [
    "onboarding_why",
    "onboarding_format",
    "onboarding_anatomy",
    "onboarding_where_to_obtain",
    "onboarding_common_errors",
    "onboarding_renewal_frequency_days",
    "recurring_required_document",
    "recurring_anatomy",
    "recurring_where_to_obtain",
    "recurring_common_errors",
    "recurring_accepted_documents",
    "recurring_for_year_v2",
    "normalize_persona_type",
    "CATALOG_SOURCE",
    "CATALOG_VERSION",
    "MinimumDocuments",
    "lookup_onboarding_by_code",
    "lookup_recurring_by_code",
    "MONTHS_ES",
    "OnboardingRequirement",
    "PersonaType",
    "RecurringRequirement",
    "catalog_metadata",
    "expediente_as_dicts",
    "expediente_for_persona",
    "recurring_as_dicts",
    "recurring_for_year",
]


# Field aliases for ``field`` import compatibility (kept for future expansion).
_ = field  # noqa: F841
