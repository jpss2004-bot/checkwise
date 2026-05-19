#!/usr/bin/env python3
"""Render the System UX Audit Report as a visual, executive PDF.

This is a hand-tuned generator, not a general markdown-to-PDF
converter. It composes:

  Page 1   — Cover (brand, title, date, headline KPIs)
  Page 2   — Executive summary (one-paragraph narrative + readiness
              dial + "what's strong / what to fix" grid)
  Page 3   — Visual tour overview (one tile per audited page,
              grouped by role)
  Pages 4-N — Per-page hero spreads (full-bleed screenshot + page
              name + status pill + one-line takeaway)
  Page N+1 — Issue matrix (severity-colored status pills)
  Page N+2 — Demo path + recommended next steps

Inputs:
  docs/audit-screenshots/2026-05-18-system-audit/*.png
  docs/SYSTEM_UX_AUDIT_REPORT.md (for narrative content only)

Output:
  docs/SYSTEM_UX_AUDIT_REPORT.pdf
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "audit-screenshots" / "2026-05-18-system-audit"
OUT = ROOT / "docs" / "SYSTEM_UX_AUDIT_REPORT.pdf"

# ── Palette ──────────────────────────────────────────────────────
INK = colors.HexColor("#0f172a")
INK_BODY = colors.HexColor("#1f2937")
INK_MUTED = colors.HexColor("#475569")
INK_FAINT = colors.HexColor("#94a3b8")
BRAND = colors.HexColor("#0d8475")
BRAND_DARK = colors.HexColor("#0a665b")
BRAND_TINT = colors.HexColor("#e6f4f1")
BAND = colors.HexColor("#f8fafc")
HAIRLINE = colors.HexColor("#e2e8f0")
GOOD = colors.HexColor("#16a34a")
GOOD_TINT = colors.HexColor("#dcfce7")
WARN = colors.HexColor("#c2410c")
WARN_TINT = colors.HexColor("#ffedd5")
LOW = colors.HexColor("#475569")
LOW_TINT = colors.HexColor("#f1f5f9")

PAGE_W, PAGE_H = LETTER
M = 0.55 * inch  # standard margin

# ── Audited pages ────────────────────────────────────────────────


@dataclass
class Page:
    n: str
    filename: str
    role: str
    route: str
    title: str
    takeaway: str
    status: str = "working"  # 'working' | 'fixed' | 'attn'


PAGES: list[Page] = [
    # Public
    Page("01", "01-landing.png", "Público", "/", "Landing", "Hero claro + único CTA primario + propuesta REPSE legible en 5s."),
    Page("02", "02-login.png", "Público", "/login", "Inicio de sesión", "Formulario único; subtítulo explica el flujo de contraseña temporal."),
    Page("02b", "02b-login-error.png", "Público", "/login", "Login · error", "Mensaje en español, no expone si el correo existe."),
    Page("99", "99-not-found.png", "Público", "/* (404)", "Página no encontrada", "Reemplazo branded del 404 default de Next.js (corregido en esta auditoría)."),
    # Admin
    Page("03", "03-admin-reviewer-queue.png", "Admin", "/admin/reviewer", "Bandeja de revisión", "Subtítulo establece la doctrina: ningún documento se aprueba sin humano."),
    Page("08", "08-admin-reviewer-detail.png", "Admin", "/admin/reviewer/[id]", "Detalle de revisión", "4 acciones explícitas + sidebar de trazabilidad con todos los IDs."),
    Page("04", "04-admin-dashboard.png", "Admin", "/admin/dashboard", "Resumen operativo", "Métricas alineadas; usa solo 50% del ancho — oportunidad de densificar."),
    Page("05", "05-admin-clients.png", "Admin", "/admin/clients", "Clientes", "CRUD limpio: búsqueda + Nuevo cliente + Editar inline."),
    Page("06", "06-admin-vendors.png", "Admin", "/admin/vendors", "Proveedores", "Lista cruzada con filtro por cliente y RFC visible."),
    Page("07", "07-admin-requirements.png", "Admin", "/admin/requirements", "Catálogo de requisitos", "151 obligaciones REPSE catalogadas; tabla pesada pero funcional."),
    Page("09", "09-admin-calendar.png", "Admin", "/admin/calendar", "Calendario operativo", "Distribución mensual + drilldown por mes."),
    Page("10", "10-admin-audit-log.png", "Admin", "/admin/audit-log", "Bitácora", "Estado vacío con copy honesto: 'Sin eventos'."),
    Page("11", "11-admin-reports-list.png", "Admin", "/admin/reports", "Reportes", "6 plantillas operativas + reportes recientes con filtros."),
    Page("12", "12-admin-report-editor.png", "Admin", "/admin/reports/[id]", "Editor de reporte", "Toolbar P1.8 completo: IA, Copiloto, Actualizar datos, Vista PDF, Descargar PDF."),
    # Client
    Page("13", "13-client-dashboard.png", "Cliente", "/client/dashboard", "Resumen del cliente", "Headline humano: '3 proveedores en amarillo · 432 hallazgos'."),
    Page("14", "14-client-vendors.png", "Cliente", "/client/vendors", "Proveedores", "Barra de riesgo del portafolio antes de la tabla."),
    Page("15", "15-client-vendor-detail.png", "Cliente", "/client/vendors/[id]", "Detalle de proveedor", "6 secciones: acciones, atención, entregas, estado, vencimientos, notas."),
    Page("16", "16-client-submissions.png", "Cliente", "/client/submissions", "Entregas", "Vista cruzada de todos los proveedores."),
    Page("17", "17-client-activity.png", "Cliente", "/client/activity", "Actividad", "Bitácora cronológica del portafolio."),
    Page("18", "18-client-calendar.png", "Cliente", "/client/calendar", "Calendario del cliente", "Ritmo anual agregado + detalle mensual."),
    Page("19", "19-client-reports.png", "Cliente", "/client/reports", "Reportes", "3 plantillas para dirección + reportes recientes."),
    # Provider
    Page("20", "20-portal-entry.png", "Proveedor", "/portal/entra-a-tu-espacio", "Entrada al espacio", "Onramp humano: pide datos de contacto antes de entrar."),
    Page("21", "21-portal-dashboard.png", "Proveedor", "/portal/dashboard", "Dashboard del proveedor", "Centrado en 'Tu siguiente acción' — exactamente lo que el proveedor necesita."),
    Page("22", "22-portal-onboarding.png", "Proveedor", "/portal/onboarding", "Expediente inicial", "Checklist numerado de 5 documentos iniciales."),
    Page("23", "23-portal-upload.png", "Proveedor", "/portal/upload", "Carga documental", "Wizard de 5 pasos con contexto regulatorio explícito."),
    Page("24", "24-portal-calendar.png", "Proveedor", "/portal/calendar", "Tu año de cumplimiento", "Grid 12 meses × 4 instituciones con legend completo."),
    Page("25", "25-portal-reports.png", "Proveedor", "/portal/reports", "Reportes (Compliance Pulse)", "El surface más fuerte: KPI strip + plantillas + recientes."),
    Page("26", "26-portal-report-print.png", "Proveedor", "/portal/reports/[id]/print", "Reporte imprimible (P1.8)", "Cover con sello de frescura + toolbar 'Imprimir'."),
]

# ── Issue matrix rows ────────────────────────────────────────────


@dataclass
class Issue:
    id: str
    page: str
    severity: str  # 'Critical' | 'High' | 'Medium' | 'Low' | 'Polish'
    status: str  # 'fixed' | 'documented'
    summary: str


ISSUES: list[Issue] = [
    Issue("I-01", "(none)", "—", "—", "Sin issues críticos. Cero crashes. Cero flujos rotos."),
    Issue("I-02", "/* 404", "Medium", "fixed", "404 default de Next.js en inglés → reemplazado por página branded en español."),
    Issue("I-03", "/portal/reports/[id]/print", "Low", "fixed", "Botón de toolbar 'Imprimir / Guardar como PDF' acortado a 'Imprimir'."),
    Issue("I-06", "Editor de bloques", "Low", "fixed", "Tokens de bloque (text, kpi_strip, divider) ahora sólo visibles en modo edición."),
    Issue("I-04", "/admin/reviewer", "Medium", "documented", "Tabla se trunca en tablet portrait (912px); columna PROVEEDOR colapsa a 'P'."),
    Issue("I-05", "/admin/reviewer", "Low", "documented", "Lista de tabs overflows horizontalmente en viewports angostos."),
    Issue("I-07", "/admin/dashboard", "Polish", "documented", "Layout de columna única desperdicia ~50% del ancho en desktop."),
    Issue("I-08", "/portal/*", "Polish", "documented", "Chip flotante de ayuda muy pequeño / esquina inferior izquierda."),
    Issue("I-09", "Editor de reportes", "Low", "documented", "Botones IA habilitados aún cuando backend está en modo mock."),
]

# ── Styles ───────────────────────────────────────────────────────


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=INK_BODY,
        alignment=TA_LEFT,
        spaceAfter=6,
    )
    return {
        "cover_eyebrow": ParagraphStyle(
            "CoverEyebrow",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=BRAND,
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "cover_title": ParagraphStyle(
            "CoverTitle",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=42,
            leading=46,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSubtitle",
            parent=body,
            fontName="Helvetica",
            fontSize=14,
            leading=20,
            textColor=INK_MUTED,
            alignment=TA_LEFT,
            spaceAfter=18,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=INK,
            spaceBefore=4,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=INK,
            spaceBefore=10,
            spaceAfter=5,
        ),
        "lead": ParagraphStyle(
            "Lead",
            parent=body,
            fontSize=11.5,
            leading=17,
            textColor=INK_BODY,
            spaceAfter=10,
        ),
        "body": body,
        "small": ParagraphStyle(
            "Small",
            parent=body,
            fontSize=8.5,
            leading=11,
            textColor=INK_MUTED,
            spaceAfter=2,
        ),
        "eyebrow": ParagraphStyle(
            "Eyebrow",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=BRAND,
            spaceAfter=2,
        ),
        "stat_value": ParagraphStyle(
            "StatValue",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=32,
            leading=36,
            textColor=INK,
            alignment=TA_CENTER,
            spaceAfter=0,
        ),
        "stat_label": ParagraphStyle(
            "StatLabel",
            parent=body,
            fontSize=8.5,
            leading=11,
            textColor=INK_MUTED,
            alignment=TA_CENTER,
            spaceAfter=0,
        ),
        "page_card_title": ParagraphStyle(
            "PageCardTitle",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=13,
            textColor=INK,
            spaceAfter=2,
        ),
        "page_card_route": ParagraphStyle(
            "PageCardRoute",
            parent=body,
            fontName="Courier",
            fontSize=8,
            leading=10,
            textColor=INK_MUTED,
            spaceAfter=4,
        ),
        "page_card_take": ParagraphStyle(
            "PageCardTake",
            parent=body,
            fontSize=9.2,
            leading=12,
            textColor=INK_BODY,
            spaceAfter=0,
        ),
        "footer": ParagraphStyle(
            "Footer",
            parent=body,
            fontSize=8,
            leading=10,
            textColor=INK_FAINT,
        ),
    }


# ── Page furniture ───────────────────────────────────────────────


def header_footer(canvas, _doc, *, brand_bar: bool = True):
    canvas.saveState()
    if brand_bar:
        # Thin brand bar at the top
        canvas.setFillColor(BRAND)
        canvas.rect(0, PAGE_H - 0.18 * inch, PAGE_W, 0.18 * inch, stroke=0, fill=1)
    # Running header text
    canvas.setFillColor(INK_MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(M, PAGE_H - 0.32 * inch, "CheckWise · Auditoría de UX del sistema · 2026-05-18")
    canvas.drawRightString(PAGE_W - M, PAGE_H - 0.32 * inch, f"Página {canvas.getPageNumber()}")
    # Footer
    canvas.setFillColor(INK_FAINT)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(M, 0.35 * inch, "Generado por Claude Code · Documento interno")
    canvas.drawRightString(
        PAGE_W - M, 0.35 * inch, "checkwise · Plataforma de cumplimiento REPSE"
    )
    canvas.restoreState()


def cover_canvas(canvas, _doc):
    """Cover page furniture — bigger brand bar, no running header text."""
    canvas.saveState()
    # Tall accent bar on the left
    canvas.setFillColor(BRAND)
    canvas.rect(0, 0, 0.4 * inch, PAGE_H, stroke=0, fill=1)
    # Cover-only header band
    canvas.setFillColor(BRAND)
    canvas.rect(0, PAGE_H - 0.18 * inch, PAGE_W, 0.18 * inch, stroke=0, fill=1)
    # Brand mark in header band
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(M, PAGE_H - 0.125 * inch, "CHECKWISE · LEGAL SHELF")
    # Footer
    canvas.setFillColor(INK_FAINT)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(M, 0.45 * inch, "Documento interno · No para distribución externa sin revisión")
    canvas.drawRightString(PAGE_W - M, 0.45 * inch, "2026-05-18 · Claude Code (Opus 4.7)")
    canvas.restoreState()


# ── Composition helpers ──────────────────────────────────────────


def severity_pill(text: str, sty: dict) -> Table:
    if text == "Critical":
        bg, fg = colors.HexColor("#dc2626"), colors.white
    elif text == "High":
        bg, fg = colors.HexColor("#ea580c"), colors.white
    elif text == "Medium":
        bg, fg = colors.HexColor("#d97706"), colors.white
    elif text == "Low":
        bg, fg = colors.HexColor("#475569"), colors.white
    elif text == "Polish":
        bg, fg = colors.HexColor("#94a3b8"), colors.white
    else:
        bg, fg = colors.HexColor("#e2e8f0"), INK_MUTED
    pill = Table([[text]], colWidths=[0.7 * inch], hAlign="LEFT")
    pill.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("TEXTCOLOR", (0, 0), (-1, -1), fg),
                ("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 7),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("ROUNDEDCORNERS", [3, 3, 3, 3]),
            ]
        )
    )
    return pill


def status_pill_text(status: str) -> tuple[str, colors.Color, colors.Color]:
    if status == "fixed":
        return ("CORREGIDO", GOOD, colors.white)
    if status == "documented":
        return ("DOCUMENTADO", LOW, colors.white)
    if status == "attn":
        return ("REVISAR", WARN, colors.white)
    return ("FUNCIONA", BRAND, colors.white)


def stat_card(value: str, label: str, sty: dict) -> Table:
    tbl = Table(
        [[Paragraph(value, sty["stat_value"])], [Paragraph(label, sty["stat_label"])]],
        colWidths=[1.5 * inch],
        rowHeights=[0.55 * inch, 0.25 * inch],
    )
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BAND),
                ("BOX", (0, 0), (-1, -1), 0.5, HAIRLINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return tbl


def role_color(role: str) -> colors.Color:
    return {
        "Público": colors.HexColor("#64748b"),
        "Admin": colors.HexColor("#0d8475"),
        "Cliente": colors.HexColor("#2563eb"),
        "Proveedor": colors.HexColor("#7c3aed"),
    }.get(role, INK_MUTED)


def role_pill(role: str) -> Table:
    bg = role_color(role)
    pill = Table([[role.upper()]], colWidths=[0.85 * inch])
    pill.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                ("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 7),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return pill


def status_pill(status: str) -> Table:
    text, bg, fg = status_pill_text(status)
    pill = Table([[text]], colWidths=[1.0 * inch])
    pill.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("TEXTCOLOR", (0, 0), (-1, -1), fg),
                ("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 7),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return pill


def shot_image(filename: str, *, width_in: float) -> Image | None:
    path = SHOTS / filename
    if not path.exists():
        return None
    img = Image(str(path))
    img._restrictSize(width_in * inch, 10 * inch)
    return img


# ── Story builders ───────────────────────────────────────────────


def build_cover(story: list, sty: dict) -> None:
    story.append(Spacer(1, 2.0 * inch))
    story.append(Paragraph("REPORTE DE AUDITORÍA · UX DEL SISTEMA", sty["cover_eyebrow"]))
    story.append(Paragraph("CheckWise", sty["cover_title"]))
    story.append(
        Paragraph(
            "Auditoría completa de extremo a extremo, en navegador, "
            "como tres roles distintos. Producto listo para demo.",
            sty["cover_subtitle"],
        )
    )

    # Cover stats — 4-up
    stats = [
        ("9.0", "PUNTUACIÓN GENERAL"),
        ("33", "RUTAS AUDITADAS"),
        ("0", "ISSUES CRÍTICOS"),
        ("3", "FIXES APLICADOS"),
    ]
    row = [stat_card(v, l, sty) for v, l in stats]
    grid = Table([row], colWidths=[1.55 * inch] * 4, hAlign="LEFT")
    grid.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
    story.append(grid)

    story.append(Spacer(1, 0.7 * inch))
    # Date + author block
    info = Table(
        [
            [Paragraph("Fecha", sty["small"]), Paragraph("2026-05-18", sty["body"])],
            [Paragraph("Auditor", sty["small"]), Paragraph("Claude Code (Opus 4.7)", sty["body"])],
            [Paragraph("Stack", sty["small"]), Paragraph("Next.js 15 · FastAPI · Postgres", sty["body"])],
            [Paragraph("Repositorio", sty["small"]), Paragraph('<font name="Courier">CheckWise</font>, rama <font name="Courier">main</font>', sty["body"])],
            [Paragraph("Método", sty["small"]), Paragraph("Smoke en vivo con Playwright + Chromium + sesiones JWT inyectadas", sty["body"])],
        ],
        colWidths=[1.2 * inch, 4.5 * inch],
        hAlign="LEFT",
    )
    info.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -2), 0.5, HAIRLINE),
            ]
        )
    )
    story.append(info)
    story.append(PageBreak())


def build_executive_summary(story: list, sty: dict) -> None:
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph("Resumen ejecutivo", sty["h1"]))
    story.append(
        Paragraph(
            "CheckWise está en estado <b>listo para demo</b> en los tres shells "
            "de rol. Cada ruta auditada carga, navega, autentica y renderiza "
            "contenido de calidad de producción. El producto se lee como un "
            "asistente guiado de cumplimiento REPSE, no como una herramienta "
            "de desarrollador — títulos, subtítulos, CTAs y estados vacíos "
            "están uniformemente en español claro, y la jerarquía visual es "
            "consistente entre shells. La superficie de reportes (P1.1–P1.9) "
            "es la pieza más fuerte del producto.",
            sty["lead"],
        )
    )
    story.append(
        Paragraph(
            "Sin bloqueadores. Sin rutas rotas. Sin crashes. La brecha restante "
            "es una lista corta de mejoras polish (404 branded, layout de "
            "dashboard, texto en flujo IA). Ninguna bloquea una demo a "
            "cliente o inversor.",
            sty["lead"],
        )
    )

    # "Lo fuerte" + "Lo que falta" grid
    story.append(Spacer(1, 0.1 * inch))
    strong = [
        "Flujo de impresión / PDF (P1.8) totalmente operativo en los tres shells.",
        "Reportes del proveedor con Compliance Pulse + plantillas + freshness seal.",
        "Onramp de proveedor humano: pide datos antes de entrar al dashboard.",
        "Dashboard de cliente con un headline ejecutivo en una sola frase.",
        "Bandeja del revisor con doctrina explícita: ningún doc auto-aprueba.",
        "Empty states con copy honesto (audit log, búsquedas vacías, etc.).",
    ]
    fix = [
        "Tabla del revisor se trunca en tablet portrait (I-04, documentado).",
        "Layout del dashboard admin usa ~50% del ancho (I-07, documentado).",
        "Chip de ayuda en /portal/* visualmente pequeño (I-08, documentado).",
        "Banner de IA permite click cuando backend está en modo mock (I-09).",
    ]
    fixed = [
        "404 default de Next.js → página branded en español (I-02).",
        "Botón 'Imprimir / Guardar como PDF' → 'Imprimir' (I-03).",
        "Tokens de bloque (text, kpi_strip, divider) ocultos fuera de modo edición (I-06).",
    ]

    def bullet_list(items: list[str]) -> list:
        return [Paragraph("• " + it, sty["body"]) for it in items]

    grid = Table(
        [
            [
                Paragraph("<b>Qué está fuerte</b>", sty["h2"]),
                Paragraph("<b>Corregido en esta auditoría</b>", sty["h2"]),
            ],
            [bullet_list(strong), bullet_list(fixed)],
            [
                Paragraph("<b>Pendiente (documentado)</b>", sty["h2"]),
                Paragraph(""),
            ],
            [bullet_list(fix), Paragraph("")],
        ],
        colWidths=[(PAGE_W - 2 * M) / 2 - 0.1 * inch] * 2,
        hAlign="LEFT",
    )
    grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("BACKGROUND", (0, 0), (0, 1), GOOD_TINT),
                ("BACKGROUND", (1, 0), (1, 1), BRAND_TINT),
                ("BACKGROUND", (0, 2), (0, 3), WARN_TINT),
                ("BOX", (0, 0), (0, 1), 0.5, GOOD),
                ("BOX", (1, 0), (1, 1), 0.5, BRAND),
                ("BOX", (0, 2), (0, 3), 0.5, WARN),
            ]
        )
    )
    story.append(grid)
    story.append(PageBreak())


def build_visual_tour(story: list, sty: dict) -> None:
    """Per-page hero: full-bleed shot + role pill + status pill + take."""
    story.append(Paragraph("Recorrido visual", sty["h1"]))
    story.append(
        Paragraph(
            "Cada página auditada en orden: shell público → admin → cliente → proveedor. "
            "Las capturas se tomaron con sesiones reales en Chromium headless "
            "vía Playwright a viewport 1440 × 900.",
            sty["body"],
        )
    )
    story.append(Spacer(1, 0.15 * inch))

    last_role = None
    for p in PAGES:
        if p.role != last_role:
            story.append(Spacer(1, 0.1 * inch))
            story.append(Paragraph(p.role.upper(), sty["eyebrow"]))
            story.append(Spacer(1, 0.06 * inch))
            last_role = p.role

        # Build a per-page hero block: shot on left, meta + take on right.
        img = shot_image(p.filename, width_in=4.6)
        if img is None:
            continue

        meta_inner = Table(
            [
                [role_pill(p.role), status_pill(p.status)],
            ],
            colWidths=[0.85 * inch + 0.05 * inch, 1.0 * inch],
            hAlign="LEFT",
        )
        meta_inner.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )

        meta = Table(
            [
                [meta_inner],
                [Paragraph(p.title, sty["page_card_title"])],
                [Paragraph(p.route, sty["page_card_route"])],
                [Paragraph(p.takeaway, sty["page_card_take"])],
            ],
            colWidths=[2.4 * inch],
            hAlign="LEFT",
        )
        meta.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )

        hero = Table(
            [[img, meta]],
            colWidths=[4.7 * inch, 2.6 * inch],
            hAlign="LEFT",
        )
        hero.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, HAIRLINE),
                ]
            )
        )
        story.append(KeepTogether(hero))
    story.append(PageBreak())


def build_issue_matrix(story: list, sty: dict) -> None:
    story.append(Paragraph("Matriz de hallazgos", sty["h1"]))
    story.append(
        Paragraph(
            "9 hallazgos. 3 corregidos en esta auditoría, 6 documentados para "
            "una siguiente pasada de polish responsivo. Ningún hallazgo es "
            "crítico ni bloqueante.",
            sty["body"],
        )
    )
    story.append(Spacer(1, 0.1 * inch))

    header = [
        Paragraph("<b>ID</b>", sty["small"]),
        Paragraph("<b>Página</b>", sty["small"]),
        Paragraph("<b>Severidad</b>", sty["small"]),
        Paragraph("<b>Estado</b>", sty["small"]),
        Paragraph("<b>Resumen</b>", sty["small"]),
    ]
    rows = [header]
    for it in ISSUES:
        rows.append(
            [
                Paragraph(f"<font name='Courier'>{it.id}</font>", sty["small"]),
                Paragraph(it.page, sty["small"]),
                severity_pill(it.severity, sty),
                status_pill(it.status),
                Paragraph(it.summary, sty["body"]),
            ]
        )

    tbl = Table(
        rows,
        colWidths=[0.45 * inch, 1.4 * inch, 0.8 * inch, 1.1 * inch, 3.6 * inch],
        repeatRows=1,
    )
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BAND),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, HAIRLINE),
            ]
        )
    )
    story.append(tbl)
    story.append(PageBreak())


def build_demo_path(story: list, sty: dict) -> None:
    story.append(Paragraph("Ruta de demo recomendada", sty["h1"]))
    story.append(
        Paragraph(
            "Esta ruta evita los detalles documentados (sin vistas en tablet "
            "portrait, sin URLs desconocidas, sin botones de IA bajo modo mock) "
            "y muestra lo más fuerte del producto en ~5 minutos:",
            sty["body"],
        )
    )

    steps = [
        ("1.", "Landing →", "Login → boss.demo@checkwise.mx / BossDemo!2026"),
        ("2.", "/portal/dashboard", "Resalta 'Tu siguiente acción'"),
        ("3.", "/portal/reports", "Compliance Pulse + plantillas"),
        ("4.", "Documentos faltantes", "Vista previa PDF → cover con sello de frescura"),
        ("5.", "Cierra sesión → login cliente.demo", "/client/dashboard headline ejecutivo"),
        ("6.", "Abre un proveedor", "Narrativa de 6 secciones"),
        ("7.", "Cierra sesión → login ada@legalshelf.mx", "/admin/reviewer + abre un submission"),
    ]
    rows = [
        [
            Paragraph(f"<b>{n}</b>", sty["body"]),
            Paragraph(action, sty["body"]),
            Paragraph(detail, sty["small"]),
        ]
        for n, action, detail in steps
    ]
    tbl = Table(rows, colWidths=[0.4 * inch, 2.6 * inch, 4.3 * inch])
    tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, BAND]),
            ]
        )
    )
    story.append(tbl)

    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Siguiente slice recomendado", sty["h2"]))
    story.append(
        Paragraph(
            "<b>P2.0 — Fixtures de bloques del proveedor en <font name='Courier'>dev_seed.py</font>.</b> "
            "Los reportes sembrados sólo usan <font name='Courier'>text</font> / "
            "<font name='Courier'>kpi_strip</font> / <font name='Courier'>divider</font> hoy, por lo que "
            "los cuatro bloques del proveedor (compliance_state, attention_list, "
            "upcoming_deadlines, prioritized_actions) — la superficie de más valor demo — sólo "
            "se pueden ver vía el planner LLM. Sembrarlos desbloquea smoke en vivo "
            "del print + cierra el último gap documentado por esta auditoría.",
            sty["body"],
        )
    )
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph("Cosas que NO hacer", sty["h2"]))
    story.append(
        Paragraph(
            "• <b>No empezar P1.6</b> — ya está enviado (commit <font name='Courier'>464b2ba</font>). El siguiente slice es P2.0.<br/>"
            "• <b>No re-diseñar el shell</b> — la auditoría dio 9.0/10. No perturbar.<br/>"
            "• <b>No agregar Playwright al pipeline de prod</b> — el zero-dep "
            "<font name='Courier'>npm run check:print</font> de P1.9 cubre el caso de regresión.",
            sty["body"],
        )
    )


# ── Build ────────────────────────────────────────────────────────


def render() -> None:
    sty = styles()
    story: list = []

    # Cover (first page uses the cover canvas)
    build_cover(story, sty)
    # Subsequent sections use the brand-bar canvas
    build_executive_summary(story, sty)
    build_visual_tour(story, sty)
    build_issue_matrix(story, sty)
    build_demo_path(story, sty)

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=LETTER,
        leftMargin=M,
        rightMargin=M,
        topMargin=M + 0.05 * inch,
        bottomMargin=M,
        title="CheckWise — Auditoría de UX del sistema",
        author="Claude Code (Opus 4.7)",
        subject="Auditoría UX completa — 2026-05-18",
    )
    doc.build(story, onFirstPage=cover_canvas, onLaterPages=header_footer)
    size_kb = OUT.stat().st_size // 1024
    print(f"Wrote {OUT}  ({size_kb} KB)")


if __name__ == "__main__":
    render()
