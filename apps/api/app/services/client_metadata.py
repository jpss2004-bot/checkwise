"""Helpers for the client-facing metadata workbook."""

from __future__ import annotations

import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from fastapi import HTTPException, status

from app.core.config import settings
from app.models import Client


@dataclass(frozen=True)
class MetadataSheetPreview:
    name: str
    rows: list[list[str]]


def client_master_file_path(client: Client) -> Path:
    return (
        Path(settings.METADATA_EXPORT_PATH).expanduser().resolve()
        / _export_slug(client.name)
        / "client_master_metadata.xlsx"
    )


def display_export_path(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value).expanduser().resolve()
    export_root = Path(settings.METADATA_EXPORT_PATH).expanduser().resolve()
    try:
        return str(path.relative_to(export_root))
    except ValueError:
        return path.name


def read_xlsx_preview(
    path: Path, *, max_rows_per_sheet: int = 40, max_columns: int = 12
) -> list[MetadataSheetPreview]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            workbook_xml = archive.read("xl/workbook.xml")
            sheet_names = _xlsx_sheet_names(workbook_xml)
            previews = []
            for index, name in enumerate(sheet_names, start=1):
                worksheet_path = f"xl/worksheets/sheet{index}.xml"
                if worksheet_path not in archive.namelist():
                    continue
                previews.append(
                    MetadataSheetPreview(
                        name=name,
                        rows=_xlsx_sheet_rows(
                            archive.read(worksheet_path),
                            max_rows=max_rows_per_sheet,
                            max_columns=max_columns,
                        ),
                    )
                )
            return previews
    except (KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No se pudo leer el XLSX de metadata: {exc}",
        ) from exc


def _export_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    clean = re.sub(
        r"\s+",
        " ",
        re.sub(r"[^a-zA-Z0-9]+", " ", ascii_text).lower(),
    ).strip()
    return re.sub(r"[^a-z0-9-]+", "-", clean.replace(" ", "-")).strip("-") or "unknown"


def _xlsx_sheet_names(workbook_xml: bytes) -> list[str]:
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(workbook_xml)
    return [
        sheet.attrib.get("name", f"Sheet {index}")
        for index, sheet in enumerate(root.findall(".//x:sheet", namespace), start=1)
    ]


def _xlsx_sheet_rows(
    worksheet_xml: bytes, *, max_rows: int, max_columns: int
) -> list[list[str]]:
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(worksheet_xml)
    parsed_rows: list[list[str]] = []
    for row in root.findall(".//x:sheetData/x:row", namespace)[:max_rows]:
        values = [""] * max_columns
        for cell in row.findall("x:c", namespace):
            column_index = _xlsx_column_index(cell.attrib.get("r", "A1")) - 1
            if not 0 <= column_index < max_columns:
                continue
            values[column_index] = _xlsx_cell_text(cell, namespace)
        while values and values[-1] == "":
            values.pop()
        parsed_rows.append(values)
    return parsed_rows


def _xlsx_column_index(cell_ref: str) -> int:
    index = 0
    for char in cell_ref:
        if not char.isalpha():
            break
        index = index * 26 + (ord(char.upper()) - 64)
    return max(index, 1)


def _xlsx_cell_text(cell: ET.Element, namespace: dict[str, str]) -> str:
    inline = cell.find("x:is", namespace)
    if inline is not None:
        return "".join(node.text or "" for node in inline.findall(".//x:t", namespace))
    value = cell.find("x:v", namespace)
    return value.text if value is not None and value.text is not None else ""
