from __future__ import annotations

import re
import textwrap
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEMO_ASSETS_DIR = ROOT_DIR / "demo_assets"
SAMPLE_DOCUMENTS_DIR = DEMO_ASSETS_DIR / "sample_documents"
SAMPLE_PDF_PATH = SAMPLE_DOCUMENTS_DIR / "checkwise_demo_opinion_sat.pdf"
FRONTEND_DEMO_DIR = ROOT_DIR / "frontend" / "public" / "demo"
FRONTEND_SAMPLE_PDF_PATH = FRONTEND_DEMO_DIR / "checkwise_demo_opinion_sat.pdf"
DEMO_GUIDE_MD_PATH = ROOT_DIR / "docs" / "DEMO_GUIDE.md"
DEMO_GUIDE_PDF_PATH = DEMO_ASSETS_DIR / "CheckWise_Demo_Guide.pdf"


def main() -> None:
    SAMPLE_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    FRONTEND_DEMO_DIR.mkdir(parents=True, exist_ok=True)
    _write_pdf(
        SAMPLE_PDF_PATH,
        [
            [
                "CheckWise V1 Demo",
                "Opinion de cumplimiento SAT - Documento de demostracion",
                "",
                "Proveedor demo: Servicios Especializados Demo SA de CV",
                "RFC proveedor: DEM260512AB1",
                "Cliente demo: Cliente Piloto CheckWise",
                "Periodo: 2026-05",
                "Institucion: SAT",
                "Resultado de ejemplo: Positiva",
                "Folio ficticio: SAT-DEMO-2026-05-0001",
                "Fecha de emision ficticia: 2026-05-12",
                "",
                "Texto visible para pruebas de lectura:",
                "SAT opinion de cumplimiento positiva RFC DEM260512AB1 periodo 2026-05.",
                "Documento fiscal de demostracion para evidencia REPSE.",
                "",
                "Aviso:",
                "Documento ficticio generado para demo CheckWise.",
                "No tiene validez oficial y no contiene datos reales sensibles.",
            ]
        ],
        title="CheckWise Demo Opinion SAT",
    )
    FRONTEND_SAMPLE_PDF_PATH.write_bytes(SAMPLE_PDF_PATH.read_bytes())

    if DEMO_GUIDE_MD_PATH.exists():
        _write_pdf(
            DEMO_GUIDE_PDF_PATH,
            _markdown_to_pdf_pages(DEMO_GUIDE_MD_PATH.read_text(encoding="utf-8")),
            title="CheckWise Demo Guide",
        )

    print(f"OK sample PDF: {SAMPLE_PDF_PATH.relative_to(ROOT_DIR)}")
    print(f"OK frontend demo PDF: {FRONTEND_SAMPLE_PDF_PATH.relative_to(ROOT_DIR)}")
    if DEMO_GUIDE_PDF_PATH.exists():
        print(f"OK demo guide PDF: {DEMO_GUIDE_PDF_PATH.relative_to(ROOT_DIR)}")


def _markdown_to_pdf_pages(markdown: str) -> list[list[str]]:
    lines: list[str] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("!["):
            match = re.search(r"\]\(([^)]+)\)", line)
            lines.append(f"Screenshot: {match.group(1) if match else line}")
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = line.replace("**", "").replace("`", "")
        if not line:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(line, width=88) or [""])

    pages: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        current.append(line)
        if len(current) >= 44:
            pages.append(current)
            current = []
    if current:
        pages.append(current)
    return pages or [["CheckWise V1 Demo Guide"]]


def _write_pdf(path: Path, pages: list[list[str]], *, title: str) -> None:
    objects: list[bytes] = []
    page_object_ids: list[int] = []
    content_object_ids: list[int] = []

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    next_id = 4
    for page_lines in pages:
        page_object_ids.append(next_id)
        content_object_ids.append(next_id + 1)
        next_id += 2

        content = _page_content(page_lines, title=title)
        objects.append(
            (
                f"<< /Length {len(content)} >>\n"
                "stream\n"
            ).encode("ascii")
            + content
            + b"\nendstream"
        )

        page_id = page_object_ids[-1]
        content_id = content_object_ids[-1]
        objects.insert(
            page_id - 1,
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("ascii"),
        )

    kids = " ".join(f"{page_id} 0 R" for page_id in page_object_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>".encode(
        "ascii"
    )

    _write_pdf_objects(path, objects)


def _page_content(lines: list[str], *, title: str) -> bytes:
    commands = ["BT", "/F1 10 Tf", "72 738 Td", "14 TL"]
    commands.append(f"({_escape_pdf_text(title)}) Tj")
    commands.append("T*")
    commands.append("T*")
    for line in lines:
        commands.append(f"({_escape_pdf_text(line)}) Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1", errors="replace")


def _escape_pdf_text(value: str) -> str:
    asciiish = value.encode("latin-1", errors="replace").decode("latin-1")
    return asciiish.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_pdf_objects(path: Path, objects: list[bytes]) -> None:
    payload = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]

    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{object_number} 0 obj\n".encode("ascii"))
        payload.extend(body)
        payload.extend(b"\nendobj\n")

    xref_offset = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    payload.extend(
        (
            "trailer\n"
            f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            "startxref\n"
            f"{xref_offset}\n"
            "%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(bytes(payload))


if __name__ == "__main__":
    main()
