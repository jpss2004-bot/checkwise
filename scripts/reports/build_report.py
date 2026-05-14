from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCE_JSON = ROOT / "outputs" / "checkwise_source_extract.json"
OUT = ROOT / "outputs" / "CheckWise_Reporte_Profesional_Arquitectura_V1.pdf"

NAVY = colors.HexColor("#14213D")
BLUE = colors.HexColor("#2E74B5")
TEAL = colors.HexColor("#0F766E")
GOLD = colors.HexColor("#B7791F")
RED = colors.HexColor("#B42318")
GREEN = colors.HexColor("#17803A")
INK = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#D9E2EC")
LIGHT = colors.HexColor("#F6F8FB")
LIGHT_BLUE = colors.HexColor("#EAF2FB")
LIGHT_TEAL = colors.HexColor("#E6F4F1")
LIGHT_GOLD = colors.HexColor("#FFF7E6")
LIGHT_RED = colors.HexColor("#FDECEC")


def p(txt: str) -> str:
    return txt.replace("\n", "<br/>")


def styles():
    base = getSampleStyleSheet()
    base.add(
        ParagraphStyle(
            name="CoverKicker",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=TEAL,
            leading=13,
            spaceAfter=8,
            alignment=TA_CENTER,
        )
    )
    base.add(
        ParagraphStyle(
            name="CoverTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=30,
            textColor=NAVY,
            leading=35,
            spaceAfter=12,
            alignment=TA_CENTER,
        )
    )
    base.add(
        ParagraphStyle(
            name="CoverSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=13,
            textColor=INK,
            leading=18,
            spaceAfter=18,
            alignment=TA_CENTER,
        )
    )
    base.add(
        ParagraphStyle(
            name="H1x",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=17,
            textColor=NAVY,
            leading=22,
            spaceBefore=4,
            spaceAfter=8,
        )
    )
    base.add(
        ParagraphStyle(
            name="H2x",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.5,
            textColor=BLUE,
            leading=16,
            spaceBefore=10,
            spaceAfter=6,
        )
    )
    base.add(
        ParagraphStyle(
            name="Bodyx",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            textColor=INK,
            leading=13.2,
            spaceAfter=6,
        )
    )
    base.add(
        ParagraphStyle(
            name="Smallx",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.2,
            textColor=MUTED,
            leading=10.5,
        )
    )
    base.add(
        ParagraphStyle(
            name="TableHead",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=colors.white,
            leading=10,
            alignment=TA_LEFT,
        )
    )
    base.add(
        ParagraphStyle(
            name="TableCell",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            textColor=INK,
            leading=10,
        )
    )
    base.add(
        ParagraphStyle(
            name="TableCellBold",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=INK,
            leading=10,
        )
    )
    base.add(
        ParagraphStyle(
            name="Callout",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            textColor=INK,
            leading=12.5,
            leftIndent=0,
            spaceAfter=6,
        )
    )
    return base


S = styles()


def para(text: str, style: str = "Bodyx"):
    return Paragraph(p(text), S[style])


def bullet(items):
    return ListFlowable(
        [ListItem(para(item), leftIndent=10) for item in items],
        bulletType="bullet",
        start="circle",
        leftIndent=14,
        bulletFontName="Helvetica",
        bulletFontSize=7,
        bulletColor=TEAL,
    )


def table(data, widths, header=True, font_size=8, header_color=NAVY):
    rows = []
    for r_idx, row in enumerate(data):
        style = "TableHead" if header and r_idx == 0 else "TableCell"
        rows.append([Paragraph(p(str(cell)), S[style]) for cell in row])
    t = Table(rows, colWidths=widths, hAlign="LEFT", repeatRows=1 if header else 0)
    commands = [
        ("BOX", (0, 0), (-1, -1), 0.45, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if header:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), header_color),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ]
        )
    for idx in range(1 if header else 0, len(data)):
        if idx % 2 == (1 if header else 0):
            commands.append(("BACKGROUND", (0, idx), (-1, idx), colors.white))
        else:
            commands.append(("BACKGROUND", (0, idx), (-1, idx), LIGHT))
    t.setStyle(TableStyle(commands))
    return t


def callout(title: str, body: str, fill=LIGHT_BLUE, border=BLUE):
    data = [[Paragraph(f"<b>{p(title)}</b><br/>{p(body)}", S["Callout"])]]
    t = Table(data, colWidths=[6.45 * inch], hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fill),
                ("BOX", (0, 0), (-1, -1), 0.8, border),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return t


class LayerDiagram(Flowable):
    def __init__(self, width=6.45 * inch):
        super().__init__()
        self.width = width
        self.height = 315

    def draw(self):
        c = self.canv
        layers = [
            ("Usuarios", "Proveedor | Cliente | Equipo CheckWise | Administrador", NAVY),
            ("Experiencia", "Portal guiado V1 + Dashboard interno + puente JotForm", BLUE),
            ("API y dominio", "FastAPI / OpenAPI | RBAC | reglas | workflow documental", TEAL),
            ("Automatización", "Ingestión | hash | OCR/extracción | validaciones | notificaciones", GOLD),
            ("Datos", "PostgreSQL | storage cifrado | audit log | reportes | cache", GREEN),
            ("Integraciónes", "JotForm | Google Sheets bridge | Legal Shelf | email/WhatsApp | Looker", MUTED),
        ]
        x = 0
        y = self.height - 46
        box_h = 42
        for idx, (name, desc, color) in enumerate(layers):
            c.setFillColor(colors.white)
            c.setStrokeColor(color)
            c.setLineWidth(1.3)
            c.roundRect(x, y, self.width, box_h, 5, stroke=1, fill=1)
            c.setFillColor(color)
            c.rect(x, y, 112, box_h, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(x + 10, y + 25, name)
            c.setFont("Helvetica", 7.8)
            c.setFillColor(INK)
            c.drawString(x + 126, y + 25, desc)
            if idx < len(layers) - 1:
                c.setStrokeColor(LINE)
                c.line(self.width / 2, y - 2, self.width / 2, y - 13)
                c.setFillColor(LINE)
                c.circle(self.width / 2, y - 13, 2, stroke=0, fill=1)
            y -= box_h + 13


class FlowDiagram(Flowable):
    def __init__(self, width=6.45 * inch):
        super().__init__()
        self.width = width
        self.height = 112

    def draw(self):
        c = self.canv
        items = [
            ("JotForm", BLUE),
            ("Google Sheets", TEAL),
            ("Revisión legal", GOLD),
            ("Legal Shelf", NAVY),
            ("Reporte", GREEN),
        ]
        box_w = (self.width - 56) / len(items)
        y = 54
        for i, (name, color) in enumerate(items):
            x = i * (box_w + 14)
            c.setFillColor(colors.white)
            c.setStrokeColor(color)
            c.setLineWidth(1.2)
            c.roundRect(x, y, box_w, 38, 5, stroke=1, fill=1)
            c.setFillColor(color)
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(x + box_w / 2, y + 22, name)
            if i < len(items) - 1:
                c.setStrokeColor(MUTED)
                c.line(x + box_w + 3, y + 19, x + box_w + 11, y + 19)
                c.line(x + box_w + 8, y + 23, x + box_w + 12, y + 19)
                c.line(x + box_w + 8, y + 15, x + box_w + 12, y + 19)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7.6)
        c.drawString(0, 24, "Estado actual: cadena funcional, pero dependiente de herramientas sueltas, fórmulas y criterio humano.")


def page_header_footer(canvas, doc):
    canvas.saveState()
    page = canvas.getPageNumber()
    if page > 1:
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, 10.45 * inch, doc.pagesize[0] - doc.rightMargin, 10.45 * inch)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc.leftMargin, 10.55 * inch, "CheckWise | Reporte de diagnóstico, arquitectura y riesgos")
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 0.45 * inch, f"Página {page}")
    canvas.restoreState()


def source_inventory(data):
    rows = [["Fuente", "Que aporta", "Lectura para el producto"]]
    notes = {
        "Checkwise Reporte Status Actual.pdf": (
            "Interpretación estratégica: REPSE, operación actual, visión V1, modelo de datos, estados y roadmap.",
            "La tesis es correcta: pasar de formularios/reportes manuales a una capa operativa trazable.",
        ),
        "C.Documento de Requisitos Funcionales (FRD) - Checkwise.docx": (
            "715 parrafos y 7 tablas de alcance, usuarios, RF/RNF, seguridad, interfaz, datos y comúnicaciones.",
            "Confirma que el MVP necesita roles, carga documental, validación, reporteria, 2FA y auditoría.",
        ),
        "C. of CheckWise _ (PPT Interna).pptx": (
            "Deck interno: problema, competencia, MVP, PMF, Legal Shelf, IA y modularidad.",
            "Posiciona CheckWise como producto modular con validación activa y evolucion a IA.",
        ),
        "C. CheckWise - Comercial - (Tiers) V1.pptx": (
            "Deck comercial: dolor REPSE, resultado prometido, diferenciadores y soporte proveedor.",
            "El mensaje de venta depende de convertir trazabilidad y reportes en experiencia consistente.",
        ),
        "C. Checkwise DATA 2025.xlsx": (
            "13 hojas; captura, paneles, bases matriz, enlaces JotForm, estatus y fórmulas.",
            "Existe data real, pero Sheets no debe ser la fuente de verdad final.",
        ),
        "C. of Lab de Exp Checkwise DATA.xlsx": (
            "11 hojas de laboratorio con duplicados, bases matriz y experimentos de homologacion.",
            "El mayor riesgo técnico ya aparece: normalización de proveedor/documento/período.",
        ),
        "C.of UAT Tester - Checkwise.xlsx": (
            "2 hojas de UAT con pruebas de fórmulas, reflejo de cargas, duplicados y errores #REF.",
            "Hay aprendizaje operativo que debe convertirse en pruebas automatizadas.",
        ),
        "C.of Secciones Formularios _ CheckWise.xlsx": (
            "Secciones de Apartado I y II para formularios.",
            "Sirve como insumo para catalogar campos y diseñar el portal guiado.",
        ),
        "C.Árbol Plataforma Proveedores REPSE VF .xlsx": (
            "Arbol de informacion de proveedores, cliente/filial, documentos y pasos adicionales.",
            "Complementa el modelo de entidades y reglas por cliente/proveedor.",
        ),
    }
    for item in data:
        file = item["file"]
        rows.append([file, *notes.get(file, ("Fuente revisada.", "Requiere clasificacion adicional."))])
    return rows


def build():
    data = json.loads(SOURCE_JSON.read_text(encoding="utf-8"))
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=LETTER,
        leftMargin=0.72 * inch,
        rightMargin=0.72 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.6 * inch,
        title="CheckWise - Reporte profesional de arquitectura V1",
        author="Codex",
    )
    story = []

    story += [
        Spacer(1, 0.55 * inch),
        para("CHECKWISE", "CoverKicker"),
        para("Reporte profesional de diagnóstico y arquitectura V1", "CoverTitle"),
        para(
            "Revisión cruzada de documentos reales, deck interno/comercial, FRD, bases operativas, UAT y reporte de interpretación.",
            "CoverSubtitle",
        ),
        Spacer(1, 0.2 * inch),
        callout(
            "Tesis ejecutiva",
            "CheckWise ya resolvio una parte importante del problema con JotForm, Google Sheets y revisión humana. "
            "El siguiente salto no es rehacer todo: es encapsular lo que funciona, normalizar datos, crear una fuente de verdad, "
            "automatizar validaciones objetivas y dejar el criterio legal en una cola de excepciones auditada.",
            fill=LIGHT_TEAL,
            border=TEAL,
        ),
        Spacer(1, 0.28 * inch),
        table(
            [
                ["Preparado para", "JP Samano / equipo CheckWise"],
                ["Fecha", "12 de mayo de 2026"],
                ["Fuentes revisadas", f"{len(data)} archivos: PDF, FRD, 2 decks y 5 workbooks"],
                ["Advertencia", "Este reporte no constituye asesoría legal; reglas REPSE deben validarse por equipo legal/fiscal."],
            ],
            [1.55 * inch, 4.9 * inch],
            header=False,
        ),
        PageBreak(),
    ]

    story += [
        para("1. Resumen Ejecutivo", "H1x"),
        callout(
            "Conclusión principal",
            "La interpretación del reporte base queda confirmada por los documentos reales. CheckWise debe evolucionar de una operación soportada por formularios, hojas y reportes a una plataforma de cumplimiento documental recurrente: expediente, checklist, validación, semaforo, trazabilidad y reporte ejecutivo.",
            fill=LIGHT_BLUE,
            border=BLUE,
        ),
        Spacer(1, 6),
        table(
            [
                ["Insight", "Evidencia cruzada", "Implicacion"],
                [
                    "Existe mercado/dolor claro",
                    "Decks: riesgo fiscal, vigilancia y compliance; FRD: REPSE y carga operativa del cliente.",
                    "El producto debe vender reducción de riesgo y control operativo, no solo repositorio.",
                ],
                [
                    "Ya hay prototipo funcional",
                    "JotForm alimenta Sheets; paneles y buscadores muestran cumplimiento por proveedor, institución y período.",
                    "V1 debe absorber el flujo actual con una arquitectura puente, no romperlo.",
                ],
                [
                    "La validación sigue siendo fragil",
                    "FRD reconoce que no hay escaneo inteligente; UAT documenta problemas de duplicados, nombres similares y #REF.",
                    "Automatizar solo senales objetivas al inicio; todo dictamen sensible pasa por revisión humana.",
                ],
                [
                    "El reporte es parte del producto",
                    "Decks prometen checklist/reportes en tiempo real; PDF base exige semaforo y proximos pasos.",
                    "El reporte mensual debe explicar faltantes, riesgo, responsable y siguiente acción.",
                ],
            ],
            [1.35 * inch, 2.55 * inch, 2.55 * inch],
        ),
        para("Lectura de direccion", "H2x"),
        bullet(
            [
                "Construir primero el tablero interno, el modelo de datos y el motor de estados; después el portal completo.",
                "Mantener JotForm/Sheets como puente temporal mientras se mide el proceso piloto.",
                "Separar prevalidación automática de dictamen legal para evitar aprobaciones falsas.",
                "Usar IDs, RFC, período y hash de archivo para dejar de depender de nombres escritos manualmente.",
            ]
        ),
        PageBreak(),
    ]

    story += [
        para("2. Revisión de Documentación", "H1x"),
        para(
            "Se revisaron los insumos disponibles en la carpeta actual y se cruzaron contra el reporte de interpretación. "
            "La tabla resume que aporta cada fuente y como cambia la lectura del producto.",
            "Bodyx",
        ),
        table(source_inventory(data), [1.72 * inch, 2.3 * inch, 2.43 * inch]),
        PageBreak(),
    ]

    story += [
        para("3. Problemática del Cliente", "H1x"),
        para(
            "El dolor del cliente no es simplemente almacenar PDFs. El problema real es sostener un ciclo regulatorio repetitivo donde cada proveedor, período e institución puede cambiar el estado de cumplimiento y el riesgo fiscal/laboral del cliente.",
            "Bodyx",
        ),
        table(
            [
                ["Dolor", "Causa observada", "Impacto", "Respuesta V1"],
                [
                    "Correos y archivos dispersos",
                    "Carga por formularios y enlaces sueltos; múltiples bases y paneles.",
                    "Baja trazabilidad, retrabajo y busqueda lenta.",
                    "Expediente por proveedor con source-of-truth en PostgreSQL y storage cifrado.",
                ],
                [
                    "Proveedor confundido",
                    "Checklist no siempre está contextualizado por período/institución.",
                    "Cargas incompletas y dependencia de soporte.",
                    "Carga guiada con requisito, formato, ejemplo, período y motivo de rechazo.",
                ],
                [
                    "Validacion manual variable",
                    "El criterio vive en abogados, fórmulas y comentarios.",
                    "Horas hombre, errores y poca repetibilidad.",
                    "Reglas versionadas + cola de excepciones + audit log.",
                ],
                [
                    "Cliente sin acción clara",
                    "Reportes/paneles pueden mostrar estatus sin explicar causa o siguiente paso.",
                    "Menor valor percibido y riesgo no gestionado.",
                    "Semaforo ejecutivo con faltante, vencimiento, responsable, fecha limite y acción.",
                ],
            ],
            [1.45 * inch, 1.75 * inch, 1.55 * inch, 1.7 * inch],
        ),
        para("Flujo actual validado en los documentos", "H2x"),
        FlowDiagram(),
        callout(
            "Hallazgo clave",
            "El MVP actual prueba la demanda y el flujo operativo, pero su dependencia en hojas, fórmulas y enlaces de JotForm impide escalar con seguridad, auditoría fuerte y consistencia multi-cliente.",
            fill=LIGHT_GOLD,
            border=GOLD,
        ),
        PageBreak(),
    ]

    story += [
        para("4. Arquitectura Propuesta", "H1x"),
        para(
            "La arquitectura recomendada es evolutiva: conservar entradas actuales mientras se introduce un núcleo propio de dominio, datos, validaciones, seguridad y reportes. Este patrón reduce riesgo de transición y permite probar valor con clientes reales.",
            "Bodyx",
        ),
        LayerDiagram(),
        para("Principios de arquitectura", "H2x"),
        bullet(
            [
                "Fuente de verdad única: PostgreSQL gobierna clientes, proveedores, períodos, requisitos, cargas, validaciones y reportes.",
                "Archivos fuera de la base: PDFs/XML/DOCX en object storage cifrado con URLs firmadas y expirables.",
                "Automatizacion idempotente: cada carga se identifica por vendor_id, period_id, requirement_id y hash.",
                "Reglas versionadas: ningun cambio regulatorio entra sin version, fecha de vigencia y responsable legal.",
                "Human-in-the-loop: IA/OCR solo preclasifica y extrae señales; aprobaciones críticas quedan auditadas.",
            ]
        ),
        PageBreak(),
    ]

    story += [
        para("5. Modelo de Datos V1", "H1x"),
        para(
            "El PDF base propone entidades correctas; las hojas reales confirman que el modelo debe separar proveedor, período, institución, documento requerido, carga y validación. Esta separación evita que una columna por documento/mes se vuelva inmanejable.",
            "Bodyx",
        ),
        table(
            [
                ["Entidad", "Campos clave", "Uso"],
                ["clients", "client_id, nombre, RFC, responsable, status", "Organizacion contratante y aislamiento tenant."],
                ["vendors", "vendor_id, RFC, razon_social, contacto, REPSE_id, status", "Proveedor que carga documentos y mantiene expediente."],
                ["periods", "period_id, mes, anio, tipo, fecha_corte", "Ciclo mensual, bimestral, cuatrimestral o anual."],
                ["requirements", "requirement_id, institución, categoría, frecuencia, obligatorio, regla_version", "Checklist esperado por cliente/proveedor/período."],
                ["submissions", "submission_id, vendor_id, period_id, requirement_id, file_id, source", "Carga recibida desde JotForm, portal o migracion."],
                ["validations", "validation_id, submission_id, regla, resultado, severidad, comentario", "Prevalidación automática y revisión humana."],
                ["documents", "file_id, storage_key, hash, mime, size, ocr_status", "Archivo y metadatos técnicos, separado del estado legal."],
                ["notifications", "notification_id, canal, destinatario, evento, resultado", "Recordatorios, rechazos y vencimientos."],
                ["reports", "report_id, client_id, period_id, score, status, file_url", "Salida mensual y evidencia de entrega."],
                ["audit_log", "event_id, actor, acción, objeto, old_value, new_value, timestamp", "Trazabilidad legal, seguridad y soporte."],
            ],
            [1.35 * inch, 2.65 * inch, 2.45 * inch],
        ),
        Spacer(1, 8),
        callout(
            "Decision recomendada",
            "Sheets debe quedar como interfaz puente o export operativo, no como modelo canónico. Las fórmulas actuales son evidencia de reglas de negocio que deben convertirse en código probado y versionado.",
            fill=LIGHT_TEAL,
            border=TEAL,
        ),
        PageBreak(),
    ]

    story += [
        para("6. Stack Tecnológico Recomendado", "H1x"),
        table(
            [
                ["Capa", "Stack recomendado", "Razon"],
                ["Frontend", "Next.js + TypeScript + Tailwind/shadcn", "Portal y dashboard rápido, tipado, UI consistente y reusable."],
                ["Backend/API", "FastAPI + Python + OpenAPI", "Excelente para procesamiento documental, OCR, reglas y contratos API claros."],
                ["Base de datos", "PostgreSQL + SQLAlchemy/Alembic", "Modelo relacional para tenant, proveedor, período, requisito, estados y auditoría."],
                ["Archivos", "S3 compatible: AWS S3, Cloudflare R2 o GCS", "Cifrado, versionado, URLs firmadas y costos controlables."],
                ["Procesamiento", "Redis + RQ/Celery workers", "Colas para OCR, hash, extracción, notificaciones y generacion de reportes."],
                ["OCR/IA", "pypdf/PyMuPDF + OCR externo opcional + OpenAI para extracción asistida", "Empezar con reglas deterministicas y usar IA solo donde aporte confianza medible."],
                ["Auth/RBAC", "Auth0, Clerk o Supabase Auth con 2FA para administradores", "MFA, sesiones, roles y menor carga de seguridad propia."],
                ["Reportes", "Metabase/Looker Studio puente + PDFs automatizados", "Conservar visualizacion rapida y generar entregables acciónables."],
                ["Automatización", "n8n temporal; workers propios para core", "n8n acelera piloto, pero la lógica crítica debe vivir en código versionado."],
                ["DevOps", "Docker + GitHub Actions + Sentry/OpenTelemetry", "Ambientes reproducibles, CI, observabilidad y trazabilidad de errores."],
            ],
            [1.25 * inch, 2.45 * inch, 2.75 * inch],
        ),
        para("Integraciónes V1", "H2x"),
        bullet(
            [
                "JotForm: webhooks/export para seguir capturando sin friccion durante piloto.",
                "Google Sheets: sincronización controlada para reportes existentes, no escritura manual crítica.",
                "Legal Shelf: export/carga asistida al inicio; API cuando exista contrato técnico estable.",
                "Correo/WhatsApp Business: notificaciones y soporte, registrando evento y resultado.",
            ]
        ),
        PageBreak(),
    ]

    story += [
        para("7. Roadmap V1", "H1x"),
        table(
            [
                ["Fase", "Objetivo", "Entregable"],
                ["0. Inventario", "Auditar JotForm, Sheets, fórmulas, Drive, reportes y reglas.", "Diccionario de datos + mapa as-is + brechas."],
                ["1. Núcleo de datos", "Crear modelo canónico y migrar entidades mínimas.", "PostgreSQL + IDs + import desde Sheets/JotForm."],
                ["2. Validación piloto", "Hash, formato, legibilidad, duplicados, período y RFC parcial.", "Motor de prevalidación + log + cola de excepciones."],
                ["3. Dashboard interno", "Operar revisiones por prioridad, proveedor, período e institución.", "Vista CheckWise con semáforo y comentarios."],
                ["4. Reporte mensual", "Generar salida ejecutiva con acción y evidencia.", "PDF/DOCX mensual por cliente y período."],
                ["5. Portal proveedor/cliente", "Reemplazar gradualmente JotForm con login y carga guiada.", "Portal V1 con checklist, historial y feedback."],
            ],
            [1.15 * inch, 2.65 * inch, 2.65 * inch],
        ),
        Spacer(1, 8),
        callout(
            "Piloto recomendado",
            "Un cliente, 3 a 5 proveedores, un ciclo mensual y 5 a 8 documentos representativos. Metas: 30%-50% menos tiempo de revisión, 80%+ detección automática de faltantes, cero aprobaciones automáticas críticas sin humano y un reporte mensual generado desde datos trazables.",
            fill=LIGHT_BLUE,
            border=BLUE,
        ),
        PageBreak(),
    ]

    story += [
        para("8. Riesgos Identificados", "H1x"),
        table(
            [
                ["Riesgo", "Severidad", "Por que importa", "Mitigacion"],
                ["Reglas REPSE mal interpretadas", "Alta", "Un error puede generar falsa seguridad legal/fiscal.", "Rulebook versionado, aprobacion legal y trazabilidad de cambios."],
                ["Aprobacion automática incorrecta", "Alta", "El sistema podria validar documentos vencidos o ajenos.", "Prevalidación, umbrales de confianza y human-in-the-loop."],
                ["Exposicion de datos entre clientes", "Alta", "Documentos contienen datos sensibles y obligaciones de privacidad.", "RBAC, tenant isolation, cifrado, URLs firmadas y audit log."],
                ["Dependencia de Sheets", "Media-Alta", "Formulas y rangos se rompen; UAT ya muestra #REF y duplicados.", "Migrar core a PostgreSQL y dejar Sheets como vista/export."],
                ["Nombres de proveedor inconsistentes", "Media-Alta", "La homologacion por texto genera duplicados o merges incorrectos.", "vendor_id, RFC, normalizacion y confirmacion humana de fuzzy matches."],
                ["Costo/latencia de OCR e IA", "Media", "Procesar documentos repetidos puede ser caro y lento.", "Hash, cache, colas, limites de reintento y medición por documento."],
                ["Scope creep por portal completo", "Media", "Puede retrasar valor si se intenta reemplazar todo al inicio.", "Dashboard interno primero; portal despues de validar flujo."],
                ["Reportes poco acciónables", "Media", "Un semaforo sin responsable no cambia conducta.", "Cada hallazgo con causa, responsable, fecha limite y siguiente acción."],
            ],
            [1.5 * inch, 0.8 * inch, 2.0 * inch, 2.15 * inch],
            header_color=RED,
        ),
        para("Controles no negociables", "H2x"),
        bullet(
            [
                "2FA para roles administrativos y bitacora de todo cambio sensible.",
                "Separacion de permisos por cliente, filial, proveedor y rol.",
                "Respaldo diario, pruebas de restauración y versionado de archivos.",
                "Pruebas automatizadas para reglas de período: mensual, bimestral, cuatrimestral y anual.",
            ]
        ),
        PageBreak(),
    ]

    story += [
        para("9. Backlog Inmediato para JP / Equipo", "H1x"),
        table(
            [
                ["Prioridad", "Tarea", "Resultado esperado"],
                ["P0", "Exportar estructura completa de JotForm: campos, validaciones, archivos, emails y lógica condicional.", "Mapa de entrada y brechas de UX."],
                ["P0", "Auditar Sheets: hojas, columnas, fórmulas críticas, duplicados, #REF, nombres de proveedor y enlaces.", "Diccionario de datos + riesgos técnicos."],
                ["P0", "Definir fuente de verdad temporal y reglas de sincronizacion.", "Decision clara: que se edita, donde y por quien."],
                ["P1", "Crear catálogo de documentos/requisitos por institución, frecuencia y aplicabilidad.", "Checklist V1 reusable y versionado."],
                ["P1", "Diseñar estados y transiciones documentales.", "Workflow operativo: pendiente, recibido, revisión, aprobado, rechazado, vencido, no aplica."],
                ["P1", "Implementar importador JotForm/Sheets a modelo canónico.", "Primer dataset normalizado para piloto."],
                ["P2", "Generar reporte mensual desde datos normalizados.", "Entregable ejecutivo acciónable para cliente."],
            ],
            [0.8 * inch, 3.25 * inch, 2.4 * inch],
            header_color=TEAL,
        ),
        Spacer(1, 10),
        callout(
            "Siguiente decisión",
            "La decisión técnica más importante no es el framework; es declarar que el estado documental vive en una entidad propia, versionada y auditada. Una vez eso existe, JotForm, Sheets, Legal Shelf y reportes pueden integrarse sin dominar la arquitectura.",
            fill=LIGHT_TEAL,
            border=TEAL,
        ),
        para("Fuentes revisadas", "H2x"),
        bullet([item["file"] for item in data]),
    ]

    doc.build(story, onFirstPage=page_header_footer, onLaterPages=page_header_footer)
    print(OUT)


if __name__ == "__main__":
    build()
