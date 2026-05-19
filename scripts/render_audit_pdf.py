#!/usr/bin/env python3
"""Render the System UX Audit Report as a polished PDF.

Reads docs/SYSTEM_UX_AUDIT_REPORT.md and emits
docs/SYSTEM_UX_AUDIT_REPORT.pdf using ReportLab.

This is a one-shot helper for the 2026-05-18 audit, not a general
markdown-to-pdf converter. It handles the specific structural
elements used in that report (headings, bullets, fenced tables,
inline code, links).
"""
from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "SYSTEM_UX_AUDIT_REPORT.md"
OUT = ROOT / "docs" / "SYSTEM_UX_AUDIT_REPORT.pdf"

# ── Palette (kept calm — this is an executive report, not marketing) ──
INK = colors.HexColor("#0f172a")
INK_MUTED = colors.HexColor("#475569")
INK_FAINT = colors.HexColor("#94a3b8")
BRAND = colors.HexColor("#0d8475")
HAIRLINE = colors.HexColor("#e2e8f0")
BAND = colors.HexColor("#f8fafc")
ACCENT_BAND = colors.HexColor("#0d8475")
WARN = colors.HexColor("#c2410c")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=9.8,
        leading=14,
        textColor=INK,
        alignment=TA_LEFT,
        spaceAfter=6,
    )
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=26,
            leading=30,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=body,
            fontName="Helvetica",
            fontSize=12,
            leading=16,
            textColor=INK_MUTED,
            spaceAfter=18,
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
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=INK,
            spaceBefore=18,
            spaceAfter=8,
            keepWithNext=1,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=16,
            textColor=INK,
            spaceBefore=12,
            spaceAfter=5,
            keepWithNext=1,
        ),
        "h3": ParagraphStyle(
            "H3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=INK,
            spaceBefore=10,
            spaceAfter=3,
            keepWithNext=1,
        ),
        "body": body,
        "bullet": ParagraphStyle(
            "Bullet",
            parent=body,
            leftIndent=14,
            bulletIndent=2,
            spaceAfter=3,
        ),
        "quote": ParagraphStyle(
            "Quote",
            parent=body,
            fontName="Helvetica-Oblique",
            textColor=INK_MUTED,
            leftIndent=10,
            borderColor=HAIRLINE,
            borderPadding=4,
            spaceBefore=4,
            spaceAfter=10,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=body,
            fontSize=8.5,
            leading=11,
            textColor=INK_MUTED,
        ),
        "cellHead": ParagraphStyle(
            "CellHead",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.white,
            spaceAfter=0,
        ),
        "cell": ParagraphStyle(
            "Cell",
            parent=body,
            fontSize=8.4,
            leading=10.5,
            textColor=INK,
            spaceAfter=0,
        ),
        "cellMuted": ParagraphStyle(
            "CellMuted",
            parent=body,
            fontSize=8.4,
            leading=10.5,
            textColor=INK_MUTED,
            spaceAfter=0,
        ),
    }


# ── Markdown → ReportLab inline conversion ──
_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _inline(md: str) -> str:
    """Convert a single line of markdown to ReportLab paragraph markup.

    Order matters: extract `code` first (and stash it behind a sentinel)
    so its contents — especially `*` and `[` — don't get interpreted as
    italics or links. Then links, then bold, then italic. Finally
    re-inject the code spans.
    """
    # XML-escape the raw text first.
    s = md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Stash code spans.
    stash: list[str] = []

    def _stash_code(m: re.Match) -> str:
        idx = len(stash)
        stash.append(m.group(1))
        return f"\x00CODE{idx}\x00"

    s = _INLINE_CODE.sub(_stash_code, s)

    # Now apply the inline transforms — safe, no `*` inside code spans.
    s = _LINK.sub(
        lambda m: f'<font color="#0d8475">{m.group(1)}</font>',
        s,
    )
    s = _BOLD.sub(r"<b>\1</b>", s)
    s = _ITALIC.sub(r"<i>\1</i>", s)

    # Re-inject code spans.
    def _unstash(m: re.Match) -> str:
        idx = int(m.group(1))
        return f'<font face="Courier" size="8.5" color="#334155">{stash[idx]}</font>'

    s = re.sub(r"\x00CODE(\d+)\x00", _unstash, s)
    return s


def _split_table_row(line: str) -> list[str]:
    parts = [c.strip() for c in line.strip().strip("|").split("|")]
    return parts


def _is_table_separator(line: str) -> bool:
    s = line.strip().strip("|")
    return all(re.fullmatch(r":?-+:?", c.strip()) for c in s.split("|"))


def _table_flowable(rows: list[list[str]], styles: dict) -> Table:
    """Render a markdown table as a ReportLab Table."""
    # Detect a tag column (Status, Severity, etc.) to add subtle background
    n_cols = len(rows[0])

    def cell(text: str, head: bool) -> Paragraph:
        st = styles["cellHead"] if head else styles["cell"]
        # Mute strings that are obvious placeholders
        if text in ("—", ""):
            return Paragraph("—", styles["cellMuted"])
        return Paragraph(_inline(text), st)

    rendered = [
        [cell(c, head=(i == 0)) for c in row] for i, row in enumerate(rows)
    ]
    # Heuristic column widths — proportional to header label width, then
    # clipped to fit the printable page (Letter w/ 0.6in margins = 7.3in).
    total_w = 7.3 * inch
    raw_widths = [max(len(rows[0][i]), 6) for i in range(n_cols)]
    scale = total_w / sum(raw_widths)
    col_widths = [w * scale for w in raw_widths]

    tbl = Table(rendered, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), ACCENT_BAND),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BAND]),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, HAIRLINE),
                ("LINEBELOW", (0, 1), (-1, -1), 0.25, HAIRLINE),
            ]
        )
    )
    return tbl


def render() -> None:
    md = SRC.read_text(encoding="utf-8")
    lines = md.split("\n")
    styles = _styles()

    story: list = []
    i = 0
    in_table = False
    table_rows: list[list[str]] = []
    in_code = False
    code_lines: list[str] = []
    cover_done = False

    def flush_table():
        nonlocal table_rows, in_table
        if not table_rows:
            in_table = False
            return
        story.append(Spacer(1, 4))
        story.append(_table_flowable(table_rows, styles))
        story.append(Spacer(1, 6))
        table_rows = []
        in_table = False

    def flush_code():
        nonlocal code_lines, in_code
        if not code_lines:
            in_code = False
            return
        block = "\n".join(code_lines)
        text = block.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        para = Paragraph(
            f'<font face="Courier" size="8.5">{text.replace(chr(10), "<br/>")}</font>',
            ParagraphStyle(
                "Code",
                parent=styles["body"],
                fontName="Courier",
                fontSize=8.5,
                leading=11,
                backColor=BAND,
                borderColor=HAIRLINE,
                borderWidth=0.5,
                borderPadding=6,
                spaceBefore=4,
                spaceAfter=8,
                textColor=INK,
            ),
        )
        story.append(para)
        code_lines = []
        in_code = False

    while i < len(lines):
        line = lines[i]
        rstrip = line.rstrip()

        # Fenced code blocks
        if rstrip.startswith("```"):
            if in_code:
                flush_code()
            else:
                if in_table:
                    flush_table()
                in_code = True
            i += 1
            continue
        if in_code:
            code_lines.append(line)
            i += 1
            continue

        # Skip the H1 title line ("# CheckWise — System UX Audit Report") —
        # we'll render a custom cover instead.
        if line.startswith("# ") and not cover_done:
            title = line[2:].strip()
            story.append(Paragraph("Reporte de auditoría", styles["eyebrow"]))
            story.append(Paragraph(_inline(title), styles["title"]))
            cover_done = True
            i += 1
            continue

        # Blockquote (the report frontmatter)
        if line.startswith("> "):
            content = line[2:].strip()
            story.append(Paragraph(_inline(content), styles["quote"]))
            i += 1
            continue

        # Horizontal rule
        if rstrip in ("---", "***", "___"):
            story.append(Spacer(1, 6))
            story.append(
                Table(
                    [[" "]],
                    colWidths=[7.3 * inch],
                    style=TableStyle(
                        [("LINEABOVE", (0, 0), (-1, 0), 0.5, HAIRLINE)]
                    ),
                )
            )
            story.append(Spacer(1, 6))
            i += 1
            continue

        # Tables — start when we see |...|...| followed by a separator row
        if (
            line.strip().startswith("|")
            and i + 1 < len(lines)
            and _is_table_separator(lines[i + 1])
        ):
            in_table = True
            table_rows = [_split_table_row(line)]
            # Skip separator row
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_rows.append(_split_table_row(lines[i]))
                i += 1
            flush_table()
            continue

        # Headings (H2..H4)
        if line.startswith("## "):
            story.append(Paragraph(_inline(line[3:].strip()), styles["h1"]))
            i += 1
            continue
        if line.startswith("### "):
            story.append(Paragraph(_inline(line[4:].strip()), styles["h2"]))
            i += 1
            continue
        if line.startswith("#### "):
            story.append(Paragraph(_inline(line[5:].strip()), styles["h3"]))
            i += 1
            continue

        # Bulleted lists
        if line.startswith("- "):
            story.append(
                Paragraph(_inline(line[2:].strip()), styles["bullet"], bulletText="•")
            )
            i += 1
            continue

        # Numbered lists
        m = re.match(r"^(\d+)\.\s+(.*)", line)
        if m:
            story.append(
                Paragraph(_inline(m.group(2).strip()), styles["bullet"], bulletText=f"{m.group(1)}.")
            )
            i += 1
            continue

        # Blank line
        if not rstrip:
            story.append(Spacer(1, 4))
            i += 1
            continue

        # Default: plain paragraph
        story.append(Paragraph(_inline(rstrip), styles["body"]))
        i += 1

    # Flush trailing state
    if in_table:
        flush_table()
    if in_code:
        flush_code()

    # ── Build PDF ──
    def _on_page(canvas, _doc):
        canvas.saveState()
        # Header band on every page
        canvas.setFillColor(INK_FAINT)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(
            0.6 * inch,
            LETTER[1] - 0.4 * inch,
            "CheckWise · System UX Audit · 2026-05-18",
        )
        canvas.drawRightString(
            LETTER[0] - 0.6 * inch,
            LETTER[1] - 0.4 * inch,
            f"Página {canvas.getPageNumber()}",
        )
        canvas.setStrokeColor(HAIRLINE)
        canvas.setLineWidth(0.5)
        canvas.line(
            0.6 * inch,
            LETTER[1] - 0.5 * inch,
            LETTER[0] - 0.6 * inch,
            LETTER[1] - 0.5 * inch,
        )
        # Footer hairline + brand
        canvas.setFillColor(INK_FAINT)
        canvas.drawString(
            0.6 * inch,
            0.4 * inch,
            "Generado por Claude Code · Auditoría interna · No para distribución externa sin revisión",
        )
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=LETTER,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.6 * inch,
        title="CheckWise — System UX Audit",
        author="Claude Code (Opus 4.7)",
        subject="System UX audit report — 2026-05-18",
    )
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    render()
