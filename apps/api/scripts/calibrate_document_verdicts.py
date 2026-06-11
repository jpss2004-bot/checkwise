"""Phase-A calibration harness for the document-revalidation verdicts.

Before any confidence threshold is trusted (and long before auto-approve
unlocks) we replay the verdict pipeline against submissions humans already
decided, and report how well the stored scores predict those decisions —
per requirement code and overall.

Ground truth
------------
Terminal reviewer decisions on ``Submission.status``:

    * positive — ``aprobado`` and ``excepcion_legal`` (the human accepted
      the document as valid evidence).
    * negative — ``rechazado``.
    * ``requiere_aclaracion`` is ambiguous: EXCLUDED from the metrics by
      default, counted separately in the coverage section.

Signals replayed (from ``DocumentInspection``)
----------------------------------------------
    * match confidence — ``shadow_confidence`` (AI) preferred when
      present, else ``requirement_match_confidence`` (heuristic).
    * authenticity — ``authenticity_risk`` (Phase A; NULL on legacy
      rows). With ``--recompute-forensics`` the analyzer is re-run fresh
      against the stored file when it still exists on disk, so legacy
      rows get a verdict for calibration too.
    * verification (Phase B) — with ``--recompute-forensics`` the
      QR/folio extractor ALSO runs fresh per document, and the report
      adds ``qr_found_rate`` / ``qr_official_rate`` / folio kind counts
      per requirement code and overall. This measures real-world QR
      coverage so ``missing_expected_qr`` can be promoted above info.

IMPORTANT CAVEAT (also stamped into the report header): human rejections
are frequently period/type mismatches, illegible scans or wrong-document
uploads — NOT fraud. The authenticity confusion numbers therefore bound
the false-positive rate well, but "rejected yet clean" is expected and
does not by itself mean the forensics missed a forgery.

Outputs
-------
Markdown report + sibling ``.json`` with the raw numbers. The default
path is ``<repo-root>/outputs/calibration-<YYYY-MM-DD>.md`` where the
repo root is two levels above ``apps/api`` (i.e. the ``CheckWise``
checkout — the same ``outputs/`` directory the deck and capture
harnesses use). Override with ``--out``.

READ-ONLY: the script never writes to the database (no flush, no
commit). ``--recompute-forensics`` only reads stored files.

USAGE
-----
  cd apps/api

  # Everything decided, stored columns only.
  .venv/bin/python -m scripts.calibrate_document_verdicts

  # Demo-scale smoke run.
  .venv/bin/python -m scripts.calibrate_document_verdicts --limit 200

  # Re-run the forensics analyzer for rows whose file is still on disk.
  .venv/bin/python -m scripts.calibrate_document_verdicts --recompute-forensics

  # Narrow the cohort.
  .venv/bin/python -m scripts.calibrate_document_verdicts \
      --client-id <uuid> --requirement-code sat:opinion_cumplimiento:mensual

``DATABASE_URL`` comes from the environment / ``apps/api/.env`` exactly
like every other script here (``app.core.config.settings``).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
_API_DIR = _SCRIPTS_DIR.parent
_REPO_ROOT = _API_DIR.parent.parent
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))  # apps/api → `app` package

from app.constants.statuses import DocumentStatus  # noqa: E402

# ---------------------------------------------------------------------------
# Calibration contract
# ---------------------------------------------------------------------------

POSITIVE_STATUSES: tuple[str, ...] = (
    DocumentStatus.APROBADO.value,
    DocumentStatus.EXCEPCION_LEGAL.value,
)
NEGATIVE_STATUSES: tuple[str, ...] = (DocumentStatus.RECHAZADO.value,)
AMBIGUOUS_STATUSES: tuple[str, ...] = (DocumentStatus.REQUIERE_ACLARACION.value,)
TERMINAL_STATUSES: tuple[str, ...] = POSITIVE_STATUSES + NEGATIVE_STATUSES

THRESHOLDS: tuple[float, ...] = (0.5, 0.7, 0.8, 0.9, 0.95, 0.97)

AUTO_APPROVE_MATCH_THRESHOLD = 0.97
AUTO_APPROVE_PRECISION_BAR = 0.99  # the agreed unlock bar

RISK_FLAGGED = ("suspicious", "high_risk")
RISK_LEVELS = ("clean", "suspicious", "high_risk")


@dataclass
class CalibrationRecord:
    """One human-decided document, flattened for the metric functions."""

    submission_id: str
    document_id: str
    requirement_code: str
    period_key: str | None
    status: str
    human_approved: bool
    match_confidence: float | None
    confidence_source: str | None  # "shadow" | "heuristic" | None
    authenticity_risk: str | None  # clean | suspicious | high_risk | None
    risk_recomputed: bool = False
    risk_reason_codes: list[str] = field(default_factory=list)
    # Phase B — fresh QR/folio extraction (``--recompute-forensics``
    # only; verification anchors are not replayed from stored columns
    # because legacy rows predate them). ``qr_count is None`` means
    # "not scanned"; these feed :func:`verification_stats`, which
    # measures real-world QR coverage so ``missing_expected_qr`` can be
    # promoted from info once the found-rate justifies it.
    qr_count: int | None = None
    qr_all_official: bool | None = None  # None until ≥1 QR decoded
    folio_kinds: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure metric functions (importable, no DB / no I/O — unit-tested directly)
# ---------------------------------------------------------------------------


def _ratio(num: int, den: int) -> float | None:
    return (num / den) if den else None


def threshold_metrics(
    records: list[CalibrationRecord],
    thresholds: tuple[float, ...] = THRESHOLDS,
) -> list[dict[str, Any]]:
    """Precision/recall of "match confidence >= t predicts human approval".

    Only records carrying a confidence participate; coverage gaps are
    reported separately by :func:`coverage_stats`. For each threshold:

        precision = approved-and-cleared / cleared
        recall    = approved-and-cleared / approved   (with confidence)

    Denominator-zero cells come back as ``None`` (rendered "n/a").
    """
    scored = [r for r in records if r.match_confidence is not None]
    positives = sum(1 for r in scored if r.human_approved)
    rows: list[dict[str, Any]] = []
    for t in thresholds:
        tp = sum(1 for r in scored if r.human_approved and r.match_confidence >= t)
        fp = sum(1 for r in scored if not r.human_approved and r.match_confidence >= t)
        fn = positives - tp
        tn = len(scored) - tp - fp - fn
        rows.append(
            {
                "threshold": t,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
                "predicted_positive": tp + fp,
                "precision": _ratio(tp, tp + fp),
                "recall": _ratio(tp, positives),
            }
        )
    return rows


def rank_auc(records: list[CalibrationRecord]) -> float | None:
    """Rank-based AUC (Mann-Whitney): P(score_approved > score_rejected).

    Ties count 0.5. Pure O(P*N) pairwise count — calibration cohorts are
    thousands of rows, not millions, so no need for the sorted variant.
    Returns ``None`` when either class is empty among scored records.
    """
    pos = [r.match_confidence for r in records if r.match_confidence is not None and r.human_approved]
    neg = [r.match_confidence for r in records if r.match_confidence is not None and not r.human_approved]
    if not pos or not neg:
        return None
    wins = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(pos) * len(neg))


def authenticity_confusion(records: list[CalibrationRecord]) -> dict[str, Any]:
    """Confusion of authenticity risk-level vs the human outcome.

    Only records with a verdict (stored or recomputed) participate.

        false_positive_rate — approved docs flagged suspicious/high_risk
            (forensics friction on docs a human accepted).
        rejected_clean_rate — rejected docs the forensics called clean.
            CAVEAT: rejections are usually period/type mismatches, not
            fraud, so this is an upper bound on "missed", not a miss rate.
    """
    judged = [r for r in records if r.authenticity_risk is not None]
    matrix: dict[str, dict[str, int]] = {
        level: {"approved": 0, "rejected": 0} for level in RISK_LEVELS
    }
    for r in judged:
        level = r.authenticity_risk if r.authenticity_risk in matrix else "clean"
        matrix[level]["approved" if r.human_approved else "rejected"] += 1

    approved_total = sum(matrix[lvl]["approved"] for lvl in RISK_LEVELS)
    rejected_total = sum(matrix[lvl]["rejected"] for lvl in RISK_LEVELS)
    approved_flagged = sum(matrix[lvl]["approved"] for lvl in RISK_FLAGGED)
    rejected_clean = matrix["clean"]["rejected"]
    return {
        "judged": len(judged),
        "matrix": matrix,
        "approved_total": approved_total,
        "rejected_total": rejected_total,
        "approved_flagged": approved_flagged,
        "false_positive_rate": _ratio(approved_flagged, approved_total),
        "rejected_clean": rejected_clean,
        "rejected_clean_rate": _ratio(rejected_clean, rejected_total),
    }


def auto_approve_simulation(
    records: list[CalibrationRecord],
    *,
    match_threshold: float = AUTO_APPROVE_MATCH_THRESHOLD,
    precision_bar: float = AUTO_APPROVE_PRECISION_BAR,
) -> dict[str, Any]:
    """Simulate the agreed auto-approve rule on the historical cohort.

    Rule: ``match_confidence >= match_threshold AND authenticity_risk ==
    "clean"``. A record missing either signal can never clear the rule
    (it stays in the human queue), so it counts against clearance but is
    excluded from nothing.

        precision  — of the docs the rule would auto-approve, the share a
            human actually approved. The unlock bar is >= ``precision_bar``.
        approved_clearance — share of ALL historically-approved docs the
            rule would have cleared (the workload the rule absorbs).
    """
    cleared = [
        r
        for r in records
        if r.match_confidence is not None
        and r.match_confidence >= match_threshold
        and r.authenticity_risk == "clean"
    ]
    cleared_approved = sum(1 for r in cleared if r.human_approved)
    approved_total = sum(1 for r in records if r.human_approved)
    precision = _ratio(cleared_approved, len(cleared))
    return {
        "match_threshold": match_threshold,
        "precision_bar": precision_bar,
        "cleared": len(cleared),
        "cleared_approved": cleared_approved,
        "cleared_rejected": len(cleared) - cleared_approved,
        "approved_total": approved_total,
        "precision": precision,
        "approved_clearance": _ratio(cleared_approved, approved_total),
        # None precision (rule never fires) does NOT meet the bar: there
        # is no evidence, so the code stays locked.
        "meets_bar": precision is not None and precision >= precision_bar,
    }


def coverage_stats(records: list[CalibrationRecord]) -> dict[str, Any]:
    """How much of the cohort actually carries each signal (legacy gaps)."""
    total = len(records)
    with_conf = sum(1 for r in records if r.match_confidence is not None)
    with_risk = sum(1 for r in records if r.authenticity_risk is not None)
    return {
        "records": total,
        "with_confidence": with_conf,
        "missing_confidence": total - with_conf,
        "confidence_from_shadow": sum(
            1 for r in records if r.confidence_source == "shadow"
        ),
        "confidence_from_heuristic": sum(
            1 for r in records if r.confidence_source == "heuristic"
        ),
        "with_authenticity": with_risk,
        "missing_authenticity": total - with_risk,
        "authenticity_recomputed": sum(1 for r in records if r.risk_recomputed),
    }


def top_risk_reasons(
    records: list[CalibrationRecord], limit: int = 10
) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for r in records:
        counter.update(r.risk_reason_codes)
    return counter.most_common(limit)


def verification_stats(records: list[CalibrationRecord]) -> dict[str, Any]:
    """Phase-B QR/folio coverage for one cohort (recomputed rows only).

        qr_found_rate    — share of scanned docs with ≥1 decoded QR.
        qr_official_rate — of the QR-bearing docs, share where EVERY
            decoded QR resolves to an official government domain.
        folio_kinds      — counts per extracted folio kind.

    This is the measurement that decides whether ``missing_expected_qr``
    can be promoted above info: only once real-world docs reliably
    carry a decodable QR does its absence become evidence.
    """
    scanned = [r for r in records if r.qr_count is not None]
    qr_bearing = [r for r in scanned if (r.qr_count or 0) >= 1]
    all_official = sum(1 for r in qr_bearing if r.qr_all_official)
    folio_counter: Counter[str] = Counter()
    for r in scanned:
        folio_counter.update(r.folio_kinds)
    return {
        "scanned": len(scanned),
        "qr_found": len(qr_bearing),
        "qr_found_rate": _ratio(len(qr_bearing), len(scanned)),
        "qr_all_official": all_official,
        "qr_official_rate": _ratio(all_official, len(qr_bearing)),
        "folio_kinds": dict(folio_counter.most_common()),
    }


def compute_group_metrics(records: list[CalibrationRecord]) -> dict[str, Any]:
    """Full metric bundle for one cohort (a requirement code, or overall)."""
    return {
        "outcomes": {
            "records": len(records),
            "approved": sum(1 for r in records if r.human_approved),
            "rejected": sum(1 for r in records if not r.human_approved),
        },
        "thresholds": threshold_metrics(records),
        "auc": rank_auc(records),
        "authenticity": authenticity_confusion(records),
        "auto_approve": auto_approve_simulation(records),
        "coverage": coverage_stats(records),
        "verification": verification_stats(records),
    }


# ---------------------------------------------------------------------------
# DB replay (read-only)
# ---------------------------------------------------------------------------


def collect_records(
    db,
    *,
    limit: int | None = None,
    client_id: str | None = None,
    requirement_code: str | None = None,
    recompute_forensics: bool = False,
    storage=None,
) -> tuple[list[CalibrationRecord], dict[str, Any]]:
    """Replay terminal-status submissions into :class:`CalibrationRecord`s.

    Pure reads: outer-joins ``DocumentInspection`` so legacy documents
    without an inspection row still land in the cohort (as coverage
    gaps). Returns ``(records, replay_meta)`` where the meta carries the
    ambiguous (``requiere_aclaracion``) count and the recompute tallies.
    """
    from sqlalchemy import func, select

    from app.models import Document, DocumentInspection, Submission

    def _filtered(stmt):
        if client_id:
            stmt = stmt.where(Submission.client_id == client_id)
        if requirement_code:
            stmt = stmt.where(Submission.requirement_code == requirement_code)
        return stmt

    stmt = _filtered(
        select(Submission, Document, DocumentInspection)
        .join(Document, Document.submission_id == Submission.id)
        .outerjoin(DocumentInspection, DocumentInspection.document_id == Document.id)
        .where(Submission.status.in_(TERMINAL_STATUSES))
        .order_by(Submission.created_at.desc(), Document.id)
    )
    if limit is not None:
        stmt = stmt.limit(limit)

    ambiguous_count = db.scalar(
        _filtered(
            select(func.count(Submission.id)).where(
                Submission.status.in_(AMBIGUOUS_STATUSES)
            )
        )
    )

    if recompute_forensics and storage is None:
        from app.services.storage import get_storage_service

        storage = get_storage_service()

    records: list[CalibrationRecord] = []
    recomputed = 0
    recompute_file_missing = 0
    recompute_failed = 0
    verification_scanned = 0

    for submission, document, inspection in db.execute(stmt):
        confidence: float | None = None
        source: str | None = None
        risk: str | None = None
        reason_codes: list[str] = []
        risk_recomputed = False
        qr_count: int | None = None
        qr_all_official: bool | None = None
        folio_kinds: list[str] = []

        if inspection is not None:
            if inspection.shadow_confidence is not None:
                confidence = inspection.shadow_confidence
                source = "shadow"
            elif inspection.requirement_match_confidence is not None:
                confidence = inspection.requirement_match_confidence
                source = "heuristic"
            risk = inspection.authenticity_risk
            for reason in inspection.risk_reasons or []:
                if isinstance(reason, dict) and reason.get("code"):
                    reason_codes.append(str(reason["code"]))

        if recompute_forensics:
            path = _resolve_stored_path(storage, document.storage_key)
            if path is None:
                recompute_file_missing += 1
            else:
                fresh = _recompute_forensics(
                    path,
                    period_key=submission.period_key,
                    pdf_metadata=(inspection.raw_metadata if inspection else None),
                )
                if fresh.risk is None:
                    recompute_failed += 1
                else:
                    risk = fresh.risk
                    reason_codes = [reason.code for reason in fresh.reasons]
                    risk_recomputed = True
                    recomputed += 1

                # Phase B — fresh QR/folio extraction over the same file
                # (verification is never stored for legacy rows, so the
                # coverage measurement only exists on recompute runs).
                verification = _recompute_verification(
                    path,
                    detected_institution=(
                        inspection.detected_institution if inspection else None
                    ),
                )
                if verification.analyzed:
                    verification_scanned += 1
                    qr_count = len(verification.qr_codes)
                    qr_all_official = (
                        all(qr.get("official") for qr in verification.qr_codes)
                        if verification.qr_codes
                        else None
                    )
                    folio_kinds = [folio["kind"] for folio in verification.folios]

        records.append(
            CalibrationRecord(
                submission_id=submission.id,
                document_id=document.id,
                requirement_code=submission.requirement_code or "(sin código)",
                period_key=submission.period_key,
                status=submission.status,
                human_approved=submission.status in POSITIVE_STATUSES,
                match_confidence=confidence,
                confidence_source=source,
                authenticity_risk=risk,
                risk_recomputed=risk_recomputed,
                risk_reason_codes=reason_codes,
                qr_count=qr_count,
                qr_all_official=qr_all_official,
                folio_kinds=folio_kinds,
            )
        )

    meta = {
        "ambiguous_excluded": int(ambiguous_count or 0),
        "recompute_forensics": recompute_forensics,
        "recomputed": recomputed,
        "recompute_file_missing": recompute_file_missing,
        "recompute_failed": recompute_failed,
        "verification_scanned": verification_scanned,
    }
    return records, meta


def _resolve_stored_path(storage, storage_key) -> Path | None:
    """Resolve the stored file like the reviewer download endpoint does
    (``storage.open_for_read`` returns a local ``Path``, NOT a context
    manager). ``None`` when the blob is gone — a coverage gap, not a
    crash."""
    try:
        path = storage.open_for_read(storage_key)
    except Exception:  # noqa: BLE001 — missing blob == coverage gap, not a crash.
        return None
    return path if path.exists() else None


def _recompute_forensics(path, *, period_key, pdf_metadata):
    """Re-run the Phase-A analyzer against a resolved local file.
    Returns a ``ForensicsResult`` with ``risk=None`` when analysis
    failed open."""
    from app.services.document_forensics import analyze_pdf_forensics

    return analyze_pdf_forensics(
        path, period_key=period_key, pdf_metadata=pdf_metadata
    )


def _recompute_verification(path, *, detected_institution):
    """Re-run the Phase-B QR/folio extractor against a resolved local
    file. ``extracted_text=None`` makes the service re-extract the text
    layer itself (the inspection row does not retain it). Fail-open:
    ``analyzed=False`` when extraction errored."""
    from app.services.document_verification import extract_verification

    return extract_verification(
        path, detected_institution=detected_institution, extracted_text=None
    )


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _pct(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def _num(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _threshold_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| umbral | precision | recall | TP | FP | FN | TN |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| ≥ {row['threshold']:.2f} | {_pct(row['precision'])} "
            f"| {_pct(row['recall'])} | {row['tp']} | {row['fp']} "
            f"| {row['fn']} | {row['tn']} |"
        )
    return lines


def _group_section(name: str, metrics: dict[str, Any]) -> list[str]:
    out = metrics["outcomes"]
    auth = metrics["authenticity"]
    auto = metrics["auto_approve"]
    cov = metrics["coverage"]
    bar = "CUMPLE ✓" if auto["meets_bar"] else "NO CUMPLE ✗"
    lines = [
        f"### `{name}`",
        "",
        f"- Decisiones: **{out['records']}** "
        f"(aprobadas+excepción: {out['approved']}, rechazadas: {out['rejected']})",
        f"- Cobertura: confianza en {cov['with_confidence']}/{cov['records']} "
        f"(shadow {cov['confidence_from_shadow']}, heurística "
        f"{cov['confidence_from_heuristic']}), autenticidad en "
        f"{cov['with_authenticity']}/{cov['records']}"
        + (
            f" ({cov['authenticity_recomputed']} recalculadas)"
            if cov["authenticity_recomputed"]
            else ""
        ),
        f"- AUC (rank-based): **{_num(metrics['auc'])}**",
        "",
        "**Confianza de match vs decisión humana**",
        "",
        *_threshold_table(metrics["thresholds"]),
        "",
        "**Autenticidad vs decisión humana** "
        f"({auth['judged']} con veredicto)",
        "",
        "| riesgo | aprobadas | rechazadas |",
        "|---|---|---|",
    ]
    for level in RISK_LEVELS:
        cell = auth["matrix"][level]
        lines.append(f"| {level} | {cell['approved']} | {cell['rejected']} |")
    lines += [
        "",
        f"- Falsos positivos (aprobadas marcadas suspicious/high_risk): "
        f"{auth['approved_flagged']}/{auth['approved_total']} "
        f"= {_pct(auth['false_positive_rate'])}",
        f"- Rechazadas con veredicto clean: {auth['rejected_clean']}/"
        f"{auth['rejected_total']} = {_pct(auth['rejected_clean_rate'])} "
        "(ver caveat del encabezado)",
        "",
        f"**Simulación auto-approve** (match ≥ {auto['match_threshold']} "
        "y riesgo == clean)",
        "",
        f"- Liberaría {auto['cleared']} documentos "
        f"({auto['cleared_approved']} aprobados, {auto['cleared_rejected']} rechazados)",
        f"- Precisión de la regla: **{_pct(auto['precision'], 2)}** — "
        f"barra ≥ {_pct(auto['precision_bar'], 0)}: **{bar}**",
        f"- % de aprobados históricos que liberaría: "
        f"{_pct(auto['approved_clearance'])}",
        "",
    ]
    ver = metrics["verification"]
    if ver["scanned"]:
        folio_cells = (
            ", ".join(f"`{kind}` × {count}" for kind, count in ver["folio_kinds"].items())
            or "ninguno"
        )
        lines += [
            "**Verificación QR/folios** (Fase B — solo filas escaneadas en frío)",
            "",
            f"- Con QR decodificado: {ver['qr_found']}/{ver['scanned']} "
            f"= {_pct(ver['qr_found_rate'])}",
            f"- De los docs con QR, 100% dominios oficiales: "
            f"{ver['qr_all_official']}/{ver['qr_found']} "
            f"= {_pct(ver['qr_official_rate'])}",
            f"- Folios extraídos: {folio_cells}",
            "",
        ]
    else:
        lines += [
            "**Verificación QR/folios**: sin escaneo en esta corrida "
            "(requiere `--recompute-forensics`).",
            "",
        ]
    return lines


def build_report(
    records: list[CalibrationRecord],
    *,
    replay_meta: dict[str, Any],
    filters: dict[str, Any],
    generated_at: datetime,
) -> tuple[str, dict[str, Any]]:
    """Render the markdown report + the raw-numbers JSON payload."""
    by_code: dict[str, list[CalibrationRecord]] = defaultdict(list)
    for record in records:
        by_code[record.requirement_code].append(record)

    overall = compute_group_metrics(records)
    per_code = {
        code: compute_group_metrics(group) for code, group in sorted(by_code.items())
    }
    reasons = top_risk_reasons(records)

    codes_meeting_bar = sorted(
        code for code, m in per_code.items() if m["auto_approve"]["meets_bar"]
    )
    codes_missing_bar = sorted(
        code for code, m in per_code.items() if not m["auto_approve"]["meets_bar"]
    )

    payload = {
        "generated_at": generated_at.isoformat(),
        "filters": filters,
        "replay": replay_meta,
        "contract": {
            "positive_statuses": list(POSITIVE_STATUSES),
            "negative_statuses": list(NEGATIVE_STATUSES),
            "ambiguous_statuses": list(AMBIGUOUS_STATUSES),
            "thresholds": list(THRESHOLDS),
            "auto_approve_rule": {
                "match_threshold": AUTO_APPROVE_MATCH_THRESHOLD,
                "risk": "clean",
                "precision_bar": AUTO_APPROVE_PRECISION_BAR,
            },
        },
        "overall": overall,
        "per_requirement_code": per_code,
        "top_risk_reasons": [
            {"code": code, "count": count} for code, count in reasons
        ],
        "auto_approve_codes_meeting_bar": codes_meeting_bar,
        "auto_approve_codes_missing_bar": codes_missing_bar,
    }

    cov = overall["coverage"]
    auto = overall["auto_approve"]
    lines: list[str] = [
        "# Calibración de veredictos documentales — Fase A",
        "",
        f"Generado: {generated_at.strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"Cohorte: {len(records)} documentos con decisión humana terminal "
        f"(aprobado/excepción legal = positivo, rechazado = negativo).  ",
        f"Excluidas por ambiguas (`requiere_aclaracion`): "
        f"{replay_meta['ambiguous_excluded']}.  ",
        "Filtros: "
        + (
            ", ".join(f"{k}={v}" for k, v in filters.items() if v)
            or "ninguno (todo el histórico)"
        )
        + ".",
        "",
        "> **Caveat:** los rechazos humanos suelen deberse a periodo o tipo "
        "de documento equivocado, escaneos ilegibles o cargas erróneas — "
        "NO a fraude. Que un documento rechazado tenga veredicto de "
        "autenticidad `clean` es esperado y no implica que el análisis "
        "forense haya fallado en detectar una falsificación.",
        "",
        "## Resumen general",
        "",
        f"- Cobertura de confianza: {cov['with_confidence']}/{cov['records']} "
        f"({cov['missing_confidence']} sin señal — filas legacy)",
        f"- Cobertura de autenticidad: {cov['with_authenticity']}/{cov['records']} "
        f"({cov['missing_authenticity']} sin veredicto)"
        + (
            f"; recalculadas en frío: {replay_meta['recomputed']} "
            f"(archivo ausente: {replay_meta['recompute_file_missing']}, "
            f"análisis falló: {replay_meta['recompute_failed']})"
            if replay_meta["recompute_forensics"]
            else ""
        ),
        f"- AUC global: {_num(overall['auc'])}",
        f"- Auto-approve global (match ≥ {AUTO_APPROVE_MATCH_THRESHOLD}, "
        f"clean): precisión {_pct(auto['precision'], 2)}, liberaría "
        f"{_pct(auto['approved_clearance'])} de los aprobados",
        (
            f"- Verificación QR (Fase B, en frío): QR en "
            f"{overall['verification']['qr_found']}/"
            f"{overall['verification']['scanned']} "
            f"= {_pct(overall['verification']['qr_found_rate'])}; "
            f"100% oficial entre los que tienen QR: "
            f"{_pct(overall['verification']['qr_official_rate'])}"
            if replay_meta.get("recompute_forensics")
            else "- Verificación QR (Fase B): sin escaneo "
            "(corre con `--recompute-forensics`)"
        ),
        f"- Códigos que CUMPLEN la barra de ≥ "
        f"{_pct(AUTO_APPROVE_PRECISION_BAR, 0)}: "
        + (", ".join(f"`{c}`" for c in codes_meeting_bar) or "ninguno"),
        "- Códigos que NO cumplen: "
        + (", ".join(f"`{c}`" for c in codes_missing_bar) or "ninguno"),
        "",
        "## Métricas globales",
        "",
        *_group_section("(todos los códigos)", overall)[2:],
        "## Por código de requisito",
        "",
    ]
    for code, metrics in sorted(per_code.items()):
        lines += _group_section(code, metrics)

    lines += ["## Razones de riesgo más frecuentes", ""]
    if reasons:
        lines += ["| código | frecuencia |", "|---|---|"]
        lines += [f"| `{code}` | {count} |" for code, count in reasons]
    else:
        lines.append("Sin razones de riesgo registradas en la cohorte.")
    lines.append("")

    return "\n".join(lines), payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="calibrate_document_verdicts",
        description=(
            "Replay human-decided submissions against the stored verdict "
            "signals and report calibration per requirement code. Read-only."
        ),
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Max decided rows to replay (default: all)."
    )
    parser.add_argument("--client-id", default=None, help="Filter by Submission.client_id.")
    parser.add_argument(
        "--requirement-code", default=None, help="Filter by Submission.requirement_code."
    )
    parser.add_argument(
        "--recompute-forensics",
        action="store_true",
        help=(
            "Re-run analyze_pdf_forensics AND the Phase-B QR/folio extractor "
            "against stored files still on disk (gives legacy rows a verdict "
            "and measures QR coverage). Reads files only — no DB writes."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Markdown output path (a sibling .json is always written). "
            "Default: <repo-root>/outputs/calibration-<YYYY-MM-DD>.md"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    generated_at = datetime.now(UTC)

    out_md: Path = args.out or (
        _REPO_ROOT / "outputs" / f"calibration-{generated_at.date().isoformat()}.md"
    )
    out_json = out_md.with_suffix(".json")

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        records, replay_meta = collect_records(
            db,
            limit=args.limit,
            client_id=args.client_id,
            requirement_code=args.requirement_code,
            recompute_forensics=args.recompute_forensics,
        )
    finally:
        db.close()  # read-only: nothing to commit, ever.

    filters = {
        "limit": args.limit,
        "client_id": args.client_id,
        "requirement_code": args.requirement_code,
        "recompute_forensics": args.recompute_forensics,
    }
    markdown, payload = build_report(
        records, replay_meta=replay_meta, filters=filters, generated_at=generated_at
    )

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(markdown, encoding="utf-8")
    out_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    overall = payload["overall"]
    auto = overall["auto_approve"]
    cov = overall["coverage"]
    print(f"Reporte:  {out_md}")
    print(f"JSON:     {out_json}")
    print(
        f"Cohorte: {cov['records']} decididas "
        f"({overall['outcomes']['approved']} aprobadas, "
        f"{overall['outcomes']['rejected']} rechazadas; "
        f"{replay_meta['ambiguous_excluded']} ambiguas excluidas)"
    )
    print(
        f"Cobertura: confianza {cov['with_confidence']}/{cov['records']}, "
        f"autenticidad {cov['with_authenticity']}/{cov['records']} | "
        f"AUC global: {_num(overall['auc'])}"
    )
    meeting = payload["auto_approve_codes_meeting_bar"]
    print(
        f"Auto-approve (≥{AUTO_APPROVE_MATCH_THRESHOLD} + clean): precisión "
        f"{_pct(auto['precision'], 2)} | códigos que cumplen la barra del "
        f"{_pct(AUTO_APPROVE_PRECISION_BAR, 0)}: "
        + (", ".join(meeting) if meeting else "ninguno")
    )
    if replay_meta["recompute_forensics"]:
        ver = overall["verification"]
        print(
            f"Verificación QR (Fase B): {ver['qr_found']}/{ver['scanned']} con QR "
            f"({_pct(ver['qr_found_rate'])}) | 100% oficial entre los con QR: "
            f"{_pct(ver['qr_official_rate'])} | folios: "
            + (
                ", ".join(f"{k}×{v}" for k, v in ver["folio_kinds"].items())
                or "ninguno"
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
