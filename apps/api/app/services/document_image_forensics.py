"""Pure-local image tamper forensics on scanned documents (Phase D).

Phase A inspects the PDF *container*; Phase B chases verification
anchors; Phase C asks the LLM. None of them look at the pixels — yet a
scanned official document is forged by editing the scan image itself:
pasting a region over an amount, cloning a stamp, splicing a fresh
digitally-drawn patch into the scanned raster. This module runs two
classic, fully deterministic image-forensics checks on the embedded
scan images of a stored PDF:

    * **ELA** (``ela_anomaly``) — re-encode the scan to JPEG quality 90
      and measure where the re-encode error is *locally* inconsistent
      with the rest of the page. A region whose detail survives in the
      file but cannot survive a standard re-encode was inserted into
      the scan pipeline with a different compression history.
    * **Copy-move** (``copy_move_detected``) — hash quantized 16px
      blocks and look for many block pairs that match at one consistent
      spatial offset: the signature of a region cloned within the page
      (scanner noise makes honest scan blocks pixel-unique, so exact
      duplication only arises from digital copy-paste).

Calibration-first severity policy (the Phase-A lesson): both findings
are CAPPED at ``SEVERITY_MEDIUM`` — image forensics alone can flag a
document *Sospechoso*, never *Alto riesgo* — and every threshold is
deliberately conservative. A missed forgery is recoverable by the
reviewer; a noisy flag kills trust in the badge. The calibration
harness (``scripts/calibrate_document_verdicts.py
--recompute-forensics``) measures the flag rate on human-approved
scanned docs before any threshold is ever loosened.

Scope and cost: pure Pillow + stdlib (no numpy/scipy), intended for the
shadow runner's *escalation* path only — it is CPU-heavy relative to
intake budgets, so it rides the same "something already looks off"
gate as the deep LLM pass. Per-doc work is bounded: first
``MAX_PAGES`` pages, largest embedded image per page, downscaled to
``MAX_ANALYSIS_LONG_EDGE_PX`` before any pixel loop.

Contract: :func:`analyze_image_tampering` swallows everything — any
internal failure returns ``analyzed=False`` with ``error`` set instead
of raising. An analysis error NEVER blocks or marks a document.
"""

from __future__ import annotations

import hashlib
import io
import logging
import statistics
import time
from array import array
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from app.services.document_forensics import SEVERITY_MEDIUM, RiskReason

logger = logging.getLogger(__name__)

# FILE-2 — clamp PIL's decompression-bomb ceiling (default ~178M px) so a
# crafted oversized raster can't balloon to 0.5 GB+ of RAM while these
# forensics decode attacker-supplied embedded images. 64M px still covers
# a 600-DPI A4 scan (~35M px). PIL raises DecompressionBombError past it,
# which the analysis paths already treat as fail-open.
Image.MAX_IMAGE_PIXELS = 64_000_000

# Reason codes emitted here. The shadow runner strip-and-replaces on
# these codes when merging (mirroring the Phase-C LLM merge), so they
# must stay distinct from every other RiskReason code.
ELA_ANOMALY_CODE = "ela_anomaly"
COPY_MOVE_CODE = "copy_move_detected"
IMAGE_TAMPER_REASON_CODES = frozenset({ELA_ANOMALY_CODE, COPY_MOVE_CODE})

# ---------------------------------------------------------------------------
# Work caps — bound worst-case CPU on image-heavy uploads.
# ---------------------------------------------------------------------------

# Official documents put the meaningful content on the first pages.
MAX_PAGES = 3
# Largest embedded image per page is the scan itself; thumbnails, logos
# and stray icons are skipped outright when small on either edge.
MAX_IMAGES_PER_PAGE = 10
MIN_IMAGE_EDGE_PX = 300
# Everything is downscaled (LANCZOS) before analysis so the pure-Python
# loops stay inside the ~2s/doc budget regardless of scan DPI.
MAX_ANALYSIS_LONG_EDGE_PX = 1200

# ---------------------------------------------------------------------------
# ELA thresholds (calibration-first: conservative on purpose).
# ---------------------------------------------------------------------------

ELA_RECOMPRESS_QUALITY = 90
ELA_CELL_PX = 32
# A cell counts as "hot" only above BOTH bars. Empirically (Pillow
# encoder, synthetic + sample scans) clean re-encode cell means sit in
# the 0–5 range whatever the source quality, so 18 only triggers on
# regions carrying detail a standard q90 re-encode cannot reproduce —
# i.e. content inserted with a different compression history.
ELA_ABS_FLOOR = 18.0
ELA_RATIO_FLOOR = 3.5
# Uniform high error across the page = aggressive recompression of the
# whole scan, not localized tampering — skip instead of flagging.
ELA_GLOBAL_MEDIAN_CEILING = 10.0
# Single hot cells are noise; require a localized cluster (4-adjacent).
ELA_MIN_CLUSTER_CELLS = 2

# ---------------------------------------------------------------------------
# Copy-move thresholds.
# ---------------------------------------------------------------------------

CM_BLOCK_PX = 16
CM_STRIDE_PX = 8
# Blocks flatter than this (grayscale variance) are skipped: uniform
# white/black background duplicates trivially and means nothing.
CM_VARIANCE_FLOOR = 25.0
# 4-level posterization (v >> 6) before hashing absorbs residual JPEG
# noise so genuinely identical content hashes identically.
CM_POSTERIZE_SHIFT = 6
# A pasted region yields MANY overlapping block pairs at ONE offset;
# require enough of them, far enough apart, and spread in 2-D (a
# collinear pair set is a repeated line/rule, not a pasted region).
CM_MIN_PAIRS = 4
CM_MIN_OFFSET_PX = 24.0
# Hashes shared by too many blocks are periodic texture (halftone,
# table grid) — skip them rather than explode into pair counting.
CM_MAX_POSITIONS_PER_HASH = 12
# Defensive global cap: beyond this many pairs the page is repetitive
# texture, and a verdict from it would be noise anyway.
CM_MAX_TOTAL_PAIRS = 20000

_DETAIL_ELA_ES = (
    "Forense de imagen: una región de la página {page} muestra un nivel "
    "de error inconsistente con el resto del escaneo — posible edición "
    "posterior."
)
_DETAIL_COPY_MOVE_ES = (
    "Forense de imagen: se detectaron regiones duplicadas dentro de la "
    "página {page} — patrón típico de copiar-y-pegar."
)


@dataclass(frozen=True)
class ImageTamperResult:
    """Outcome of the pixel-level tamper checks for one stored PDF."""

    analyzed: bool
    reasons: list[RiskReason] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def analyze_image_tampering(path: Path) -> ImageTamperResult:
    """Run ELA + copy-move over the embedded scan images of one PDF.

    Never raises: any internal failure returns ``analyzed=False`` with
    ``error`` set (fail-open — the shadow runner records the skip and
    moves on). Severities are capped at medium by construction.
    """
    started = time.monotonic()
    try:
        result = _analyze(Path(path))
    except Exception as exc:  # noqa: BLE001 — fail-open contract.
        logger.warning("Image-tamper analysis failed for %s: %s", path, exc)
        message = str(exc)[:500] or type(exc).__name__
        return ImageTamperResult(
            analyzed=False,
            reasons=[],
            evidence={
                "error": message,
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
            error=message,
        )
    result.evidence["duration_ms"] = int((time.monotonic() - started) * 1000)
    return result


def _analyze(path: Path) -> ImageTamperResult:
    from pypdf import PdfReader

    reader = PdfReader(str(path))

    pages_evidence: list[dict[str, Any]] = []
    # Per check-type: keep ONE reason for the whole document (the
    # strongest page's evidence) so a 3-page forgery does not stack
    # three medium reasons out of one editing action.
    best_ela: tuple[int, RiskReason, dict[str, Any]] | None = None  # (strength, …)
    best_cm: tuple[int, RiskReason, dict[str, Any]] | None = None

    for page_number, page in enumerate(reader.pages[:MAX_PAGES], start=1):
        scan, source_format = _largest_scan_image(page)
        if scan is None:
            pages_evidence.append(
                {"page": page_number, "skipped": "no_scan_image"}
            )
            continue

        original_size = scan.size
        image = _downscaled(scan)
        page_evidence: dict[str, Any] = {
            "page": page_number,
            "source_format": source_format,
            "image_size": list(original_size),
            "analyzed_size": list(image.size),
        }

        if source_format == "JPEG":
            ela_reason, ela_evidence = _ela_check(image, page_number)
            page_evidence["ela"] = ela_evidence
            if ela_reason is not None:
                strength = int(ela_evidence.get("cluster_size") or 0)
                if best_ela is None or strength > best_ela[0]:
                    best_ela = (strength, ela_reason, ela_evidence)
        else:
            # ELA presumes a JPEG compression history to be inconsistent
            # with; lossless-embedded rasters have none.
            page_evidence["ela"] = {"skipped": "not_jpeg_source"}

        cm_reason, cm_evidence = _copy_move_check(image, page_number)
        page_evidence["copy_move"] = cm_evidence
        if cm_reason is not None:
            strength = int(cm_evidence.get("pair_count") or 0)
            if best_cm is None or strength > best_cm[0]:
                best_cm = (strength, cm_reason, cm_evidence)

        pages_evidence.append(page_evidence)

    reasons: list[RiskReason] = []
    evidence: dict[str, Any] = {"pages": pages_evidence}
    if best_ela is not None:
        reasons.append(best_ela[1])
        evidence["ela"] = best_ela[2]
    if best_cm is not None:
        reasons.append(best_cm[1])
        evidence["copy_move"] = best_cm[2]

    return ImageTamperResult(analyzed=True, reasons=reasons, evidence=evidence)


# ---------------------------------------------------------------------------
# Image acquisition (mirrors document_verification's pypdf pattern)
# ---------------------------------------------------------------------------


def _largest_scan_image(page) -> tuple[Image.Image | None, str | None]:  # noqa: ANN001
    """Largest decodable embedded image of one page (the scan itself).

    Images under ``MIN_IMAGE_EDGE_PX`` on either edge (logos, icons,
    QR rasters) are skipped; per-image decode failures are skipped the
    same way ``document_verification._scan_qr_codes`` does.
    """
    try:
        images = list(page.images)
    except Exception:  # noqa: BLE001 — a broken resource dict is not fatal.
        return None, None

    best: Image.Image | None = None
    best_format: str | None = None
    for embedded in images[:MAX_IMAGES_PER_PAGE]:
        try:
            candidate = Image.open(io.BytesIO(embedded.data))
            candidate.load()
        except Exception:  # noqa: BLE001 — undecodable image ≠ failure.
            continue
        width, height = candidate.size
        if min(width, height) < MIN_IMAGE_EDGE_PX:
            continue
        if best is None or width * height > best.size[0] * best.size[1]:
            best = candidate
            best_format = candidate.format
    return best, best_format


def _downscaled(image: Image.Image) -> Image.Image:
    """Cap the long edge at ``MAX_ANALYSIS_LONG_EDGE_PX`` (LANCZOS)."""
    long_edge = max(image.size)
    if long_edge <= MAX_ANALYSIS_LONG_EDGE_PX:
        return image
    scale = MAX_ANALYSIS_LONG_EDGE_PX / long_edge
    new_size = (
        max(1, round(image.size[0] * scale)),
        max(1, round(image.size[1] * scale)),
    )
    return image.resize(new_size, Image.LANCZOS)


# ---------------------------------------------------------------------------
# ELA — error-level analysis
# ---------------------------------------------------------------------------


def _ela_check(
    image: Image.Image, page_number: int
) -> tuple[RiskReason | None, dict[str, Any]]:
    """Localized error-level inconsistency on one (downscaled) scan.

    Re-encode at quality 90, difference, then per-cell mean error on a
    32px grid (the ``Image.BOX`` resize computes exact box means in C —
    no pure-Python pixel walk). Flag only a *cluster* of ≥2 adjacent
    cells over both the absolute floor and 3.5× the median cell, and
    only when the global median is low (uniform high error means the
    whole scan was recompressed aggressively, not edited locally).
    """
    rgb = image.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=ELA_RECOMPRESS_QUALITY)
    recompressed = Image.open(buf)
    recompressed.load()

    diff = ImageChops.difference(rgb, recompressed).convert("L")
    grid_w = max(1, diff.size[0] // ELA_CELL_PX)
    grid_h = max(1, diff.size[1] // ELA_CELL_PX)
    diff = diff.crop((0, 0, grid_w * ELA_CELL_PX, grid_h * ELA_CELL_PX))
    # One byte per cell: BOX resample = exact mean over each 32px cell.
    cells = diff.resize((grid_w, grid_h), Image.BOX).tobytes()

    median_error = float(statistics.median(cells))
    evidence: dict[str, Any] = {
        "page": page_number,
        "grid": [grid_w, grid_h],
        "cell_px": ELA_CELL_PX,
        "median_cell_error": median_error,
        "max_cell_error": float(max(cells)),
        "threshold_abs": ELA_ABS_FLOOR,
        "threshold_ratio": ELA_RATIO_FLOOR,
    }

    if median_error > ELA_GLOBAL_MEDIAN_CEILING:
        evidence["skipped"] = "global_error_high"
        return None, evidence

    threshold = max(ELA_ABS_FLOOR, ELA_RATIO_FLOOR * median_error)
    hot = {
        (index % grid_w, index // grid_w)
        for index, value in enumerate(cells)
        if value > threshold
    }
    evidence["hot_cells"] = len(hot)
    if not hot:
        return None, evidence

    cluster = _largest_cluster(hot)
    evidence["cluster_size"] = len(cluster)
    if len(cluster) < ELA_MIN_CLUSTER_CELLS:
        return None, evidence

    evidence["cluster_cells"] = sorted([x, y] for x, y in cluster)
    evidence["cluster_mean_error"] = round(
        sum(cells[y * grid_w + x] for x, y in cluster) / len(cluster), 2
    )
    reason = RiskReason(
        code=ELA_ANOMALY_CODE,
        severity=SEVERITY_MEDIUM,
        detail_es=_DETAIL_ELA_ES.format(page=page_number),
    )
    return reason, evidence


def _largest_cluster(hot: set[tuple[int, int]]) -> list[tuple[int, int]]:
    """Largest 4-adjacent connected component among hot cells."""
    best: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for start in hot:
        if start in seen:
            continue
        seen.add(start)
        stack = [start]
        component: list[tuple[int, int]] = []
        while stack:
            x, y = stack.pop()
            component.append((x, y))
            for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if neighbor in hot and neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        if len(component) > len(best):
            best = component
    return best


# ---------------------------------------------------------------------------
# Copy-move (clone) detection
# ---------------------------------------------------------------------------

_SQUARE_LUT = [value * value for value in range(256)]
_POSTERIZE_LUT = [value >> CM_POSTERIZE_SHIFT for value in range(256)]


def _copy_move_check(
    image: Image.Image, page_number: int
) -> tuple[RiskReason | None, dict[str, Any]]:
    """Exact-duplicate block detection at a consistent spatial offset.

    16px blocks at stride 8, posterized to 4 gray levels and hashed.
    Variance is computed from per-8px-cell means / mean-squares (both
    via ``Image.BOX`` resizes, so the only pure-Python loop runs over
    the ~16k stride-grid blocks, not over pixels). Flat blocks are
    skipped (uniform background duplicates trivially); a flag requires
    ≥``CM_MIN_PAIRS`` pairs at ONE offset, > ``CM_MIN_OFFSET_PX`` apart,
    with the matched source blocks spread in both axes (collinear
    matches are repeated rules/lines, not a pasted region).
    """
    gray = image.convert("L")
    cells_w = gray.size[0] // CM_STRIDE_PX
    cells_h = gray.size[1] // CM_STRIDE_PX
    evidence: dict[str, Any] = {"page": page_number}
    if cells_w < 2 or cells_h < 2:
        evidence["skipped"] = "too_small"
        return None, evidence

    width, height = cells_w * CM_STRIDE_PX, cells_h * CM_STRIDE_PX
    gray = gray.crop((0, 0, width, height))

    # Exact 8px-cell means and mean-squares via BOX resampling; a 16px
    # block at stride 8 is a 2×2 group of these cells, so its variance
    # is E[x²] − E[x]² over the four cells.
    cell_means = gray.resize((cells_w, cells_h), Image.BOX).tobytes()
    squares = gray.point(_SQUARE_LUT, "I")
    cell_mean_squares = array(
        "i", squares.resize((cells_w, cells_h), Image.BOX).tobytes()
    )
    posterized = gray.point(_POSTERIZE_LUT).tobytes()

    positions_by_hash: defaultdict[bytes, list[tuple[int, int]]] = defaultdict(list)
    blocks_hashed = 0
    for cell_y in range(cells_h - 1):
        top = cell_y * CM_STRIDE_PX
        row0 = cell_y * cells_w
        row1 = row0 + cells_w
        for cell_x in range(cells_w - 1):
            mean = (
                cell_means[row0 + cell_x]
                + cell_means[row0 + cell_x + 1]
                + cell_means[row1 + cell_x]
                + cell_means[row1 + cell_x + 1]
            ) / 4.0
            mean_square = (
                cell_mean_squares[row0 + cell_x]
                + cell_mean_squares[row0 + cell_x + 1]
                + cell_mean_squares[row1 + cell_x]
                + cell_mean_squares[row1 + cell_x + 1]
            ) / 4.0
            if mean_square - mean * mean < CM_VARIANCE_FLOOR:
                continue
            left = cell_x * CM_STRIDE_PX
            block = b"".join(
                posterized[(top + row) * width + left : (top + row) * width + left + CM_BLOCK_PX]
                for row in range(CM_BLOCK_PX)
            )
            positions_by_hash[hashlib.md5(block).digest()].append((left, top))
            blocks_hashed += 1

    evidence["blocks_hashed"] = blocks_hashed

    offset_counts: Counter[tuple[int, int]] = Counter()
    sources_by_offset: defaultdict[tuple[int, int], list[tuple[int, int]]] = (
        defaultdict(list)
    )
    pair_count = 0
    for positions in positions_by_hash.values():
        if len(positions) < 2 or len(positions) > CM_MAX_POSITIONS_PER_HASH:
            continue
        for i, (x1, y1) in enumerate(positions):
            for x2, y2 in positions[i + 1 :]:
                dx, dy = x2 - x1, y2 - y1
                source = (x1, y1)
                if dx < 0 or (dx == 0 and dy < 0):
                    dx, dy = -dx, -dy
                    source = (x2, y2)
                if (dx * dx + dy * dy) ** 0.5 <= CM_MIN_OFFSET_PX:
                    continue
                offset_counts[(dx, dy)] += 1
                sources_by_offset[(dx, dy)].append(source)
                pair_count += 1
                if pair_count > CM_MAX_TOTAL_PAIRS:
                    # Repetitive texture — a verdict here would be
                    # noise. Conservative skip.
                    evidence["skipped"] = "too_many_matches"
                    return None, evidence

    evidence["matched_pairs"] = pair_count
    if not offset_counts:
        return None, evidence

    (dx, dy), count = offset_counts.most_common(1)[0]
    evidence["top_offset"] = [dx, dy]
    evidence["pair_count"] = count
    if count < CM_MIN_PAIRS:
        return None, evidence

    sources = sources_by_offset[(dx, dy)]
    if len({x for x, _ in sources}) < 2 or len({y for _, y in sources}) < 2:
        evidence["skipped"] = "collinear_matches"
        return None, evidence

    evidence["offset"] = [dx, dy]
    reason = RiskReason(
        code=COPY_MOVE_CODE,
        severity=SEVERITY_MEDIUM,
        detail_es=_DETAIL_COPY_MOVE_ES.format(page=page_number),
    )
    return reason, evidence
