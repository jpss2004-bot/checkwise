"""Unit tests for the metadata XLSX preview parse-cache (perf audit P0-1/P3-6).

``read_xlsx_preview`` used to unzip + XML-parse the master workbook on every
request and echoed parser internals into the 422 detail. These tests lock in:
  * a repeated read of an unchanged file returns the cached object (no re-parse);
  * re-writing the file (new mtime/size) busts the entry and re-parses;
  * a corrupt workbook yields a static Spanish message, not the exception text.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from app.services import client_metadata


@pytest.fixture(autouse=True)
def _clear_cache():
    client_metadata._preview_cache.clear()
    yield
    client_metadata._preview_cache.clear()


def _write_workbook(path: Path, *, rows: int) -> None:
    wb = Workbook()
    sheet = wb.active
    sheet.title = "01 Metadata"
    for i in range(rows):
        # numeric cells avoid shared-strings so the parser returns real values
        sheet.append([i, i * 2])
    wb.save(path)


def test_repeated_read_hits_cache(tmp_path: Path):
    path = tmp_path / "master.xlsx"
    _write_workbook(path, rows=3)

    first = client_metadata.read_xlsx_preview(path, max_rows_per_sheet=500, max_columns=20)
    second = client_metadata.read_xlsx_preview(path, max_rows_per_sheet=500, max_columns=20)

    # Same object identity => served from cache, not re-parsed.
    assert first is second
    assert len(client_metadata._preview_cache) == 1


def test_rewrite_busts_cache(tmp_path: Path):
    path = tmp_path / "master.xlsx"
    _write_workbook(path, rows=3)
    first = client_metadata.read_xlsx_preview(path, max_rows_per_sheet=500, max_columns=20)

    # Ensure a distinct mtime even on coarse-resolution clocks, and change size.
    time.sleep(0.01)
    _write_workbook(path, rows=10)
    second = client_metadata.read_xlsx_preview(path, max_rows_per_sheet=500, max_columns=20)

    assert first is not second
    # Old entry evicted/replaced is not required; a fresh entry must exist.
    assert any(key[0] == str(path) for key in client_metadata._preview_cache)


def test_corrupt_file_returns_static_message(tmp_path: Path):
    path = tmp_path / "broken.xlsx"
    path.write_bytes(b"this is not a zip archive")

    with pytest.raises(HTTPException) as excinfo:
        client_metadata.read_xlsx_preview(path)

    assert excinfo.value.status_code == 422
    # No parser internals / path fragments leaked across the trust boundary.
    assert excinfo.value.detail == "No se pudo leer el archivo de metadata."


def test_cache_is_lru_bounded(tmp_path: Path):
    # Writing more distinct files than the cap keeps the cache bounded.
    for i in range(client_metadata._PREVIEW_CACHE_MAX_ENTRIES + 5):
        path = tmp_path / f"m{i}.xlsx"
        _write_workbook(path, rows=2)
        client_metadata.read_xlsx_preview(path, max_rows_per_sheet=500, max_columns=20)

    assert len(client_metadata._preview_cache) <= client_metadata._PREVIEW_CACHE_MAX_ENTRIES
