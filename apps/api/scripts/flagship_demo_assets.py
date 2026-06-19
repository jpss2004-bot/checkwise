"""Branded synthetic PDF generator for the CheckWise flagship demo.

Produces realistic one-page Mexican compliance documents (Acta Constitutiva,
Constancia de Situación Fiscal, Registro REPSE, Contrato de servicios, Registro
patronal IMSS) stamped with the demo provider's exact legal name, RFC, folio and
dates — so a prospect who opens a document in the demo sees the SAME company
they are looking at in the portal, instead of a mismatched sample vendor.

Honest but unobtrusive: every page carries a small grey footer marking it a
CheckWise demonstration document with fictional RFCs/folios — never a real
official record.

Self-contained: depends only on ``reportlab`` (already in apps/api) + stdlib.
Used by ``seed_flagship_demo.py`` for the high-touch onboarding expediente; the
139-item recurring calendar keeps using the real ``_reference/sample-docs`` PDFs.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

_PAGE_W, _PAGE_H = letter
_MARGIN = 18 * mm

# Institution identity: (entity line, sub-entity line, brand colour).
# Colours echo the real Mexican federal palette (SAT/STPS guinda, IMSS verde).
_INSTITUTIONS = {
    "sat": (
        "Servicio de Administración Tributaria",
        "Secretaría de Hacienda y Crédito Público",
        colors.HexColor("#611232"),
    ),
    "stps_repse": (
        "Secretaría del Trabajo y Previsión Social",
        "Registro de Prestadoras de Servicios Especializados (REPSE)",
        colors.HexColor("#9D2449"),
    ),
    "imss": (
        "Instituto Mexicano del Seguro Social",
        "Dirección de Incorporación y Recaudación",
        colors.HexColor("#16604A"),
    ),
    "interno_cliente": (
        "",
        "",
        colors.HexColor("#0B2A4A"),
    ),
}

_FOOTER = (
    "Documento generado para la demostración de CheckWise · RFC, folios y sellos "
    "son ficticios y sin validez oficial."
)


@dataclass(frozen=True)
class DocSpec:
    """Resolved content for one branded page."""

    institution: str           # key in _INSTITUTIONS
    title: str                 # big document title
    subtitle: str              # line under the title
    fields: list[tuple[str, str]]
    folio_label: str = "Folio"
    seal_caption: str = "Sello digital"
    expired: bool = False


# --------------------------------------------------------------------------
# Low-level drawing helpers
# --------------------------------------------------------------------------

def _folio_for(legal_name: str, rfc: str, kind: str) -> str:
    """Deterministic, official-looking folio derived from identity."""
    digest = hashlib.sha256(f"{kind}:{rfc}:{legal_name}".encode()).hexdigest().upper()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}"


def _seal_block(c: canvas.Canvas, x: float, y: float, seed: str) -> None:
    """A faux digital-seal hex block — visual texture, never a real sello."""
    raw = hashlib.sha256(seed.encode()).hexdigest()
    line = "".join(raw[i % len(raw)] for i in range(96))
    c.setFont("Courier", 5.4)
    c.setFillColor(colors.HexColor("#8A8A8A"))
    for row in range(4):
        c.drawString(x, y - row * 6, line[row * 24:(row + 1) * 24])


def _header(c: canvas.Canvas, spec: DocSpec) -> float:
    entity, sub_entity, brand = _INSTITUTIONS[spec.institution]

    # Colour band
    c.setFillColor(brand)
    c.rect(0, _PAGE_H - 30 * mm, _PAGE_W, 30 * mm, stroke=0, fill=1)

    # Coat-of-arms placeholder glyph
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(_MARGIN, _PAGE_H - 16 * mm, "⬡")

    c.setFont("Helvetica-Bold", 12.5)
    if entity:
        c.drawString(_MARGIN + 11 * mm, _PAGE_H - 12.5 * mm, entity)
        c.setFont("Helvetica", 8.2)
        c.drawString(_MARGIN + 11 * mm, _PAGE_H - 17 * mm, sub_entity)
    else:
        c.drawString(_MARGIN + 11 * mm, _PAGE_H - 14.5 * mm, "Expediente corporativo")

    c.setFont("Helvetica", 7.5)
    c.drawRightString(_PAGE_W - _MARGIN, _PAGE_H - 11 * mm, "ESTADOS UNIDOS MEXICANOS")

    return _PAGE_H - 30 * mm  # y of band bottom


def _watermark_expired(c: canvas.Canvas) -> None:
    c.saveState()
    c.translate(_PAGE_W / 2, _PAGE_H / 2)
    c.rotate(32)
    c.setFont("Helvetica-Bold", 84)
    c.setFillColor(colors.Color(0.78, 0.10, 0.10, alpha=0.16))
    c.drawCentredString(0, 0, "VENCIDO")
    c.restoreState()


def _footer(c: canvas.Canvas) -> None:
    c.setFont("Helvetica-Oblique", 6.8)
    c.setFillColor(colors.HexColor("#9A9A9A"))
    c.drawCentredString(_PAGE_W / 2, 12 * mm, _FOOTER)
    c.setStrokeColor(colors.HexColor("#D8D8D8"))
    c.setLineWidth(0.4)
    c.line(_MARGIN, 16 * mm, _PAGE_W - _MARGIN, 16 * mm)


def render(spec: DocSpec, *, legal_name: str, rfc: str, issued_on: date) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setTitle(spec.title)
    c.setAuthor("CheckWise Demo")

    entity, _sub, brand = _INSTITUTIONS[spec.institution]
    band_bottom = _header(c, spec)
    if spec.expired:
        _watermark_expired(c)

    y = band_bottom - 14 * mm
    c.setFillColor(brand)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(_MARGIN, y, spec.title)
    y -= 6.5 * mm
    c.setFillColor(colors.HexColor("#444444"))
    c.setFont("Helvetica", 9.5)
    c.drawString(_MARGIN, y, spec.subtitle)

    # Holder block
    y -= 12 * mm
    c.setFillColor(colors.HexColor("#111111"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(_MARGIN, y, legal_name)
    y -= 5.5 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#333333"))
    c.drawString(_MARGIN, y, f"RFC: {rfc}")

    # Fields table
    y -= 10 * mm
    folio = _folio_for(legal_name, rfc, spec.institution + spec.title)
    rows = [
        (spec.folio_label, folio),
        ("Fecha de emisión", issued_on.strftime("%d/%m/%Y")),
        *spec.fields,
    ]
    c.setLineWidth(0.5)
    for label, value in rows:
        c.setStrokeColor(colors.HexColor("#E4E4E4"))
        c.line(_MARGIN, y + 3.5 * mm, _PAGE_W - _MARGIN, y + 3.5 * mm)
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawString(_MARGIN, y, label.upper())
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#111111"))
        c.drawString(_MARGIN + 62 * mm, y, value)
        y -= 9 * mm

    # Seal + folio box — sits a clear gap below the last field row.
    box_h = 26 * mm
    box_y = (y - 6 * mm) - box_h
    c.setStrokeColor(colors.HexColor("#CFCFCF"))
    c.setLineWidth(0.6)
    c.rect(_MARGIN, box_y, _PAGE_W - 2 * _MARGIN, box_h, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#666666"))
    c.drawString(_MARGIN + 4 * mm, box_y + 20 * mm, spec.seal_caption.upper())
    _seal_block(c, _MARGIN + 4 * mm, box_y + 14 * mm, folio + rfc)
    c.setFont("Courier", 6.4)
    c.setFillColor(colors.HexColor("#777777"))
    c.drawString(_MARGIN + 4 * mm, box_y + 3.5 * mm, f"Cadena original: ||{rfc}|{folio}|{issued_on.isoformat()}||")

    _footer(c)
    c.showPage()
    c.save()
    return buf.getvalue()


# --------------------------------------------------------------------------
# High-level builders (one per onboarding requirement)
# --------------------------------------------------------------------------

def acta_constitutiva(*, legal_name: str, rfc: str, issued_on: date, notaria: int, ciudad: str) -> bytes:
    return render(
        DocSpec(
            institution="interno_cliente",
            title="Acta Constitutiva",
            subtitle="Escritura pública de constitución de sociedad mercantil",
            fields=[
                ("Tipo de sociedad", "S.A. de C.V."),
                ("Instrumento público", f"No. {10000 + notaria * 7}"),
                ("Notaría", f"Notaría Pública No. {notaria}, {ciudad}"),
                ("Objeto social", "Prestación de servicios especializados"),
                ("Capital social", "$1,500,000.00 M.N."),
            ],
            folio_label="Folio de instrumento",
            seal_caption="Razón de inscripción · RPPyC",
        ),
        legal_name=legal_name, rfc=rfc, issued_on=issued_on,
    )


def constancia_situacion_fiscal(*, legal_name: str, rfc: str, issued_on: date, ciudad: str, expired: bool = False) -> bytes:
    return render(
        DocSpec(
            institution="sat",
            title="Constancia de Situación Fiscal",
            subtitle="Cédula de Identificación Fiscal — Artículo 27 CFF",
            fields=[
                ("Régimen", "Régimen General de Ley Personas Morales"),
                ("Estatus en el padrón", "ACTIVO" if not expired else "ACTIVO (constancia vencida)"),
                ("Domicilio fiscal", f"{ciudad}, México"),
                ("Obligación", "Retenciones y entero de ISR / IVA"),
                ("Vigencia de la constancia", "90 días naturales"),
            ],
            folio_label="Folio (idCIF)",
            seal_caption="Sello digital SAT",
            expired=expired,
        ),
        legal_name=legal_name, rfc=rfc, issued_on=issued_on,
    )


def registro_repse(*, legal_name: str, rfc: str, issued_on: date, repse_folio: str) -> bytes:
    return render(
        DocSpec(
            institution="stps_repse",
            title="Constancia de Registro REPSE",
            subtitle="Registro de Prestadoras de Servicios Especializados u Obras Especializadas",
            fields=[
                ("Número de registro", repse_folio),
                ("Actividad registrada", "Servicios especializados (Art. 15 LFT)"),
                ("Vigencia del registro", "3 años · renovación anual de avisos"),
                ("Estatus", "VIGENTE"),
            ],
            folio_label="Folio de aviso",
            seal_caption="Sello STPS",
        ),
        legal_name=legal_name, rfc=rfc, issued_on=issued_on,
    )


def contrato_servicios(*, legal_name: str, rfc: str, issued_on: date, client_name: str) -> bytes:
    return render(
        DocSpec(
            institution="interno_cliente",
            title="Contrato de Prestación de Servicios",
            subtitle="Servicios especializados conforme al Art. 15 de la LFT",
            fields=[
                ("Contratante", client_name),
                ("Prestador", legal_name),
                ("Objeto", "Servicios especializados no inherentes al objeto social del contratante"),
                ("Vigencia", "12 meses, renovable"),
                ("Cláusula REPSE", "El prestador acredita su registro REPSE vigente"),
            ],
            folio_label="Folio de contrato",
            seal_caption="Firmas de las partes",
        ),
        legal_name=legal_name, rfc=rfc, issued_on=issued_on,
    )


def registro_patronal(*, legal_name: str, rfc: str, issued_on: date) -> bytes:
    digest = hashlib.sha256(rfc.encode()).hexdigest().upper()
    reg = f"{digest[0]}{digest[1:3]}{digest[3:8]}10{digest[8]}"
    return render(
        DocSpec(
            institution="imss",
            title="Tarjeta de Identificación Patronal",
            subtitle="Registro patronal ante el IMSS",
            fields=[
                ("Registro patronal", reg),
                ("Clase de riesgo", "Clase III · Prima media"),
                ("Estatus", "VIGENTE"),
                ("Delegación", "Subdelegación administrativa correspondiente"),
            ],
            folio_label="Folio de tarjeta",
            seal_caption="Sello IMSS",
        ),
        legal_name=legal_name, rfc=rfc, issued_on=issued_on,
    )


__all__ = [
    "acta_constitutiva",
    "constancia_situacion_fiscal",
    "registro_repse",
    "contrato_servicios",
    "registro_patronal",
    "render",
    "DocSpec",
]
