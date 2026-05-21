"""Generate the sample PDFs shipped with the boss-demo build.

Run once with the venv's Python to (re)generate the files in
``frontend/public/samples/``. The sample PDFs are not generated at
runtime — they live as static assets so the wizard can fetch them via
``/samples/<file>.pdf`` without any backend round-trip.

Each PDF is small (~3 KB), single page, and clearly labelled
``DOCUMENTO DE MUESTRA`` so a reviewer who opens the file outside
CheckWise immediately understands it is demo data.

Usage:
  cd backend
  .venv/bin/python scripts/generate_sample_pdfs.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

OUT_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "frontend"
    / "public"
    / "samples"
)


def render_sample_pdf(*, path: Path, title: str, subtitle: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER

    # Watermark ribbon along the top so the file reads as demo data
    # even when opened standalone.
    c.setFillColor(HexColor("#FFF7ED"))
    c.rect(0, height - 60, width, 60, fill=1, stroke=0)
    c.setFillColor(HexColor("#9A3412"))
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, height - 38, "DOCUMENTO DE MUESTRA · CHECKWISE 1.7.1 DEMO")

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(72, height - 130, title)

    c.setFont("Helvetica", 12)
    c.drawString(72, height - 160, subtitle)

    body = [
        "",
        "Este archivo se entrega como ejemplo para que CheckWise pueda probar",
        "el flujo de carga documental sin necesidad de un PDF real.",
        "",
        "No tiene validez fiscal, jurídica ni regulatoria.",
        "No reemplaza la documentación oficial requerida por la autoridad.",
        "",
        "Si lo recibes en producción, repórtalo al equipo de cumplimiento.",
        "",
        "Proveedor: Distribuidora Demo S.A. de C.V.",
        "RFC:       DEM010101AB1",
        "Periodo:   Demostración (sin vigencia)",
        "Versión:   CheckWise 1.7.1",
    ]
    text = c.beginText(72, height - 210)
    text.setFont("Helvetica", 11)
    text.setLeading(16)
    for line in body:
        text.textLine(line)
    c.drawText(text)

    c.setFillColor(HexColor("#9CA3AF"))
    c.setFont("Helvetica-Oblique", 9)
    c.drawCentredString(
        width / 2,
        50,
        "Generado automáticamente por scripts/generate_sample_pdfs.py — "
        "regenerable con la misma fuente.",
    )

    c.showPage()
    c.save()


SAMPLES = [
    {
        "filename": "checkwise-demo-document.pdf",
        "title": "Documento de muestra para CheckWise",
        "subtitle": "Pieza demo válida para probar la carga documental.",
    },
]


def main() -> None:
    for spec in SAMPLES:
        path = OUT_DIR / spec["filename"]
        render_sample_pdf(
            path=path, title=spec["title"], subtitle=spec["subtitle"]
        )
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
