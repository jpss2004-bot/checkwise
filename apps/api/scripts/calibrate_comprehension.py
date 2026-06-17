"""Phase-4 calibration harness for the Phase-1 comprehension verdicts.

Before any comprehension finding graduates to the provider-facing
prevalidation signals (Phase 4b), we replay the stored
``obligation_satisfaction`` verdict against the submissions humans already
decided and report how well "the model said it satisfies the obligation"
predicts "the human approved it" — per requirement code and overall.

This is the comprehension sibling of ``calibrate_document_verdicts.py``:
same ground-truth contract, same ≥99% precision unlock bar, same
read-only replay. Where that harness scores ``shadow_confidence`` /
authenticity, this one scores the deep tier's ``obligation_satisfaction``
(verdict + confidence) read from
``DocumentInspection.shadow_signals['comprehension']``.

Ground truth
------------
Terminal reviewer decisions on ``Submission.status``:

    * positive — ``aprobado`` and ``excepcion_legal`` (the human accepted
      the document as valid evidence).
    * negative — ``rechazado``.
    * ``requiere_aclaracion`` is ambiguous: EXCLUDED from the metrics,
      counted separately.

Prediction
----------
The deep tier's ``obligation_satisfaction``:

    * ``verdict`` ∈ satisfied | partial | not_satisfied | indeterminate.
    * ``confidence`` ∈ [0, 1].

The graduation rule simulated here — ``verdict == "satisfied" AND
confidence >= threshold`` — is the exact predicate Phase 4b would use to
let a high-confidence comprehension drive the provider-facing
``requirement_match`` signal. A requirement code only graduates once this
rule clears the precision bar on that code's history.

CAVEAT (stamped into the report): human rejections are frequently
period/type mismatches, illegible scans or wrong-document uploads. A
``not_satisfied`` verdict on a rejected doc is a true negative regardless
of *why* it was rejected; a ``satisfied`` verdict on a rejected doc is the
costly error this harness is built to bound.

Outputs
-------
Markdown report + sibling ``.json``. Default:
``<repo-root>/outputs/comprehension-calibration-<YYYY-MM-DD>.md``.

READ-ONLY: never writes to the database.

USAGE
-----
  cd apps/api
  .venv/bin/python -m scripts.calibrate_comprehension
  .venv/bin/python -m scripts.calibrate_comprehension --limit 200
  .venv/bin/python -m scripts.calibrate_comprehension \
      --requirement-code REC-SAT-OPINION-32D-2026
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
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

VERDICT_VALUES: tuple[str, ...] = (
    "satisfied",
    "partial",
    "not_satisfied",
    "indeterminate",
)

CONFIDENCE_THRESHOLDS: tuple[float, ...] = (0.5, 0.7, 0.8, 0.9, 0.95, 0.97, 0.99)

# The predicate Phase 4b would graduate on, and the precision it must clear
# (mirrors the auto-approve unlock bar).
GRADUATION_CONFIDENCE_THRESHOLD = 0.9
GRADUATION_PRECISION_BAR = 0.99


@dataclass
class ComprehensionRecord:
    """One human-decided document, flattened for the metric functions."""

    submission_id: str
    document_id: str
    requirement_code: str
    status: str
    human_approved: bool
    has_comprehension: bool
    obligation_verdict: str | None  # satisfied | partial | not_satisfied | indeterminate
    obligation_confidence: float | None
    validity: str | None  # valid | expired | indeterminate | None
    currency_ok: bool | None
    discrepancy_count: int = 0


# ---------------------------------------------------------------------------
# Pure metric functions (importable, no DB / no I/O — unit-tested directly)
# ---------------------------------------------------------------------------


def _ratio(num: int, den: int) -> float | None:
    return (num / den) if den else None


def coverage_stats(records: list[ComprehensionRecord]) -> dict[str, Any]:
    """How much of the decided cohort actually carries a comprehension."""
    total = len(records)
    with_comp = sum(1 for r in records if r.has_comprehension)
    with_conf = sum(1 for r in records if r.obligation_confidence is not None)
    return {
        "records": total,
        "with_comprehension": with_comp,
        "missing_comprehension": total - with_comp,
        "with_confidence": with_conf,
    }


def verdict_confusion(records: list[ComprehensionRecord]) -> dict[str, Any]:
    """Confusion of the obligation verdict against the human outcome.

    Only records carrying a comprehension participate.
    """
    judged = [r for r in records if r.has_comprehension and r.obligation_verdict]
    matrix: dict[str, dict[str, int]] = {
        v: {"approved": 0, "rejected": 0} for v in VERDICT_VALUES
    }
    for r in judged:
        verdict = r.obligation_verdict if r.obligation_verdict in matrix else "indeterminate"
        matrix[verdict]["approved" if r.human_approved else "rejected"] += 1

    satisfied = matrix["satisfied"]
    not_satisfied = matrix["not_satisfied"]
    satisfied_total = satisfied["approved"] + satisfied["rejected"]
    not_satisfied_total = not_satisfied["approved"] + not_satisfied["rejected"]
    return {
        "judged": len(judged),
        "matrix": matrix,
        # Of the docs the model called "satisfied", the share a human
        # actually approved — the precision that graduation hinges on.
        "satisfied_precision": _ratio(satisfied["approved"], satisfied_total),
        # Of the docs the model called "not_satisfied", the share a human
        # actually rejected — the model's negative-call reliability.
        "not_satisfied_precision": _ratio(
            not_satisfied["rejected"], not_satisfied_total
        ),
    }


def confidence_threshold_metrics(
    records: list[ComprehensionRecord],
    thresholds: tuple[float, ...] = CONFIDENCE_THRESHOLDS,
) -> list[dict[str, Any]]:
    """Precision/recall of ``verdict==satisfied AND confidence>=t`` predicting
    human approval. The predicted-positive set is the documents the
    graduation rule would let through at each threshold.

        precision = approved-and-predicted / predicted
        recall    = approved-and-predicted / all-approved-with-comprehension
    """
    scored = [
        r
        for r in records
        if r.has_comprehension and r.obligation_confidence is not None
    ]
    positives = sum(1 for r in scored if r.human_approved)
    rows: list[dict[str, Any]] = []
    for t in thresholds:
        predicted = [
            r
            for r in scored
            if r.obligation_verdict == "satisfied"
            and (r.obligation_confidence or 0.0) >= t
        ]
        tp = sum(1 for r in predicted if r.human_approved)
        fp = len(predicted) - tp
        rows.append(
            {
                "threshold": t,
                "predicted_positive": len(predicted),
                "tp": tp,
                "fp": fp,
                "precision": _ratio(tp, len(predicted)),
                "recall": _ratio(tp, positives),
            }
        )
    return rows


def rank_auc(records: list[ComprehensionRecord]) -> float | None:
    """Rank-based AUC (Mann-Whitney) of obligation confidence vs approval.

    Ties count 0.5. ``None`` when either class is empty among scored rows.
    """
    pos = [
        r.obligation_confidence
        for r in records
        if r.obligation_confidence is not None and r.human_approved
    ]
    neg = [
        r.obligation_confidence
        for r in records
        if r.obligation_confidence is not None and not r.human_approved
    ]
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


def graduation_simulation(
    records: list[ComprehensionRecord],
    *,
    confidence_threshold: float = GRADUATION_CONFIDENCE_THRESHOLD,
    precision_bar: float = GRADUATION_PRECISION_BAR,
) -> dict[str, Any]:
    """Simulate the Phase-4b graduation rule on the historical cohort.

    Rule: ``verdict == "satisfied" AND confidence >= confidence_threshold``.
    A record without a comprehension (or confidence) can never clear it.

        precision  — of the docs the rule would surface as provider-facing
            "satisfied", the share a human approved. Unlock bar is
            >= ``precision_bar``.
        approved_clearance — share of ALL approved docs the rule covers.
    """
    cleared = [
        r
        for r in records
        if r.has_comprehension
        and r.obligation_verdict == "satisfied"
        and r.obligation_confidence is not None
        and r.obligation_confidence >= confidence_threshold
    ]
    cleared_approved = sum(1 for r in cleared if r.human_approved)
    approved_total = sum(1 for r in records if r.human_approved)
    precision = _ratio(cleared_approved, len(cleared))
    return {
        "confidence_threshold": confidence_threshold,
        "precision_bar": precision_bar,
        "cleared": len(cleared),
        "cleared_approved": cleared_approved,
        "cleared_rejected": len(cleared) - cleared_approved,
        "approved_total": approved_total,
        "precision": precision,
        "approved_clearance": _ratio(cleared_approved, approved_total),
        # None precision (rule never fires) does NOT meet the bar — no
        # evidence, so the code stays locked.
        "meets_bar": precision is not None and precision >= precision_bar,
    }


def compute_group_metrics(records: list[ComprehensionRecord]) -> dict[str, Any]:
    """Full metric bundle for one cohort (a requirement code, or overall)."""
    return {
        "outcomes": {
            "records": len(records),
            "approved": sum(1 for r in records if r.human_approved),
            "rejected": sum(1 for r in records if not r.human_approved),
        },
        "coverage": coverage_stats(records),
        "verdict_confusion": verdict_confusion(records),
        "thresholds": confidence_threshold_metrics(records),
        "auc": rank_auc(records),
        "graduation": graduation_simulation(records),
    }


# ---------------------------------------------------------------------------
# DB replay (read-only)
# ---------------------------------------------------------------------------


def _extract_comprehension(inspection) -> dict[str, Any]:  # noqa: ANN001
    """Pull the comprehension fields off an inspection row, tolerantly."""
    out: dict[str, Any] = {
        "has_comprehension": False,
        "obligation_verdict": None,
        "obligation_confidence": None,
        "validity": None,
        "currency_ok": None,
        "discrepancy_count": 0,
    }
    if inspection is None:
        return out
    signals = inspection.shadow_signals
    comp = signals.get("comprehension") if isinstance(signals, dict) else None
    if not isinstance(comp, dict):
        return out
    out["has_comprehension"] = True
    ob = comp.get("obligation_satisfaction")
    if isinstance(ob, dict):
        out["obligation_verdict"] = ob.get("verdict")
        conf = ob.get("confidence")
        try:
            out["obligation_confidence"] = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            out["obligation_confidence"] = None
    status = comp.get("status_assessment")
    if isinstance(status, dict):
        out["validity"] = status.get("validity")
        out["currency_ok"] = status.get("currency_ok")
    discrepancies = comp.get("discrepancies")
    if isinstance(discrepancies, list):
        out["discrepancy_count"] = len(discrepancies)
    return out


def collect_records(
    db,  # noqa: ANN001
    *,
    limit: int | None = None,
    client_id: str | None = None,
    requirement_code: str | None = None,
) -> tuple[list[ComprehensionRecord], dict[str, Any]]:
    """Replay terminal-status submissions into ``ComprehensionRecord``s.

    Pure reads: outer-joins ``DocumentInspection`` so documents without a
    comprehension still land in the cohort (as coverage gaps). Returns
    ``(records, replay_meta)``.
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

    records: list[ComprehensionRecord] = []
    for submission, document, inspection in db.execute(stmt):
        comp = _extract_comprehension(inspection)
        records.append(
            ComprehensionRecord(
                submission_id=submission.id,
                document_id=document.id,
                requirement_code=submission.requirement_code or "(sin código)",
                status=submission.status,
                human_approved=submission.status in POSITIVE_STATUSES,
                has_comprehension=comp["has_comprehension"],
                obligation_verdict=comp["obligation_verdict"],
                obligation_confidence=comp["obligation_confidence"],
                validity=comp["validity"],
                currency_ok=comp["currency_ok"],
                discrepancy_count=comp["discrepancy_count"],
            )
        )

    meta = {"ambiguous_excluded": int(ambiguous_count or 0)}
    return records, meta


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _pct(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def _num(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _threshold_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| confianza ≥ | precision | recall | predichos | TP | FP |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['threshold']:.2f} | {_pct(row['precision'])} "
            f"| {_pct(row['recall'])} | {row['predicted_positive']} "
            f"| {row['tp']} | {row['fp']} |"
        )
    return lines


def _group_section(name: str, metrics: dict[str, Any]) -> list[str]:
    out = metrics["outcomes"]
    cov = metrics["coverage"]
    conf = metrics["verdict_confusion"]
    grad = metrics["graduation"]
    bar = "CUMPLE ✓" if grad["meets_bar"] else "NO CUMPLE ✗"
    lines = [
        f"### `{name}`",
        "",
        f"- Decisiones: **{out['records']}** "
        f"(aprobadas+excepción: {out['approved']}, rechazadas: {out['rejected']})",
        f"- Cobertura de comprensión: {cov['with_comprehension']}/{cov['records']} "
        f"({cov['missing_comprehension']} sin comprensión — tier triage / legacy)",
        f"- AUC (confianza de obligación): **{_num(metrics['auc'])}**",
        "",
        "**Veredicto de obligación vs decisión humana** "
        f"({conf['judged']} con comprensión)",
        "",
        "| veredicto | aprobadas | rechazadas |",
        "|---|---|---|",
    ]
    for verdict in VERDICT_VALUES:
        cell = conf["matrix"][verdict]
        lines.append(f"| {verdict} | {cell['approved']} | {cell['rejected']} |")
    lines += [
        "",
        f"- Precisión de `satisfied` (aprobadas / dijo satisfied): "
        f"**{_pct(conf['satisfied_precision'], 2)}**",
        f"- Precisión de `not_satisfied` (rechazadas / dijo not_satisfied): "
        f"{_pct(conf['not_satisfied_precision'], 2)}",
        "",
        "**Precisión por umbral de confianza** "
        "(regla: `satisfied` y confianza ≥ umbral)",
        "",
        *_threshold_table(metrics["thresholds"]),
        "",
        f"**Simulación de graduación** (`satisfied` y confianza ≥ "
        f"{grad['confidence_threshold']})",
        "",
        f"- Surgiría como provider-facing: {grad['cleared']} documentos "
        f"({grad['cleared_approved']} aprobados, {grad['cleared_rejected']} rechazados)",
        f"- Precisión de la regla: **{_pct(grad['precision'], 2)}** — "
        f"barra ≥ {_pct(grad['precision_bar'], 0)}: **{bar}**",
        f"- % de aprobados que cubriría: {_pct(grad['approved_clearance'])}",
        "",
    ]
    return lines


def build_report(
    records: list[ComprehensionRecord],
    *,
    replay_meta: dict[str, Any],
    filters: dict[str, Any],
    generated_at: datetime,
) -> tuple[str, dict[str, Any]]:
    """Render the markdown report + the raw-numbers JSON payload."""
    by_code: dict[str, list[ComprehensionRecord]] = defaultdict(list)
    for record in records:
        by_code[record.requirement_code].append(record)

    overall = compute_group_metrics(records)
    per_code = {
        code: compute_group_metrics(group) for code, group in sorted(by_code.items())
    }

    codes_meeting_bar = sorted(
        code for code, m in per_code.items() if m["graduation"]["meets_bar"]
    )
    codes_missing_bar = sorted(
        code for code, m in per_code.items() if not m["graduation"]["meets_bar"]
    )

    payload = {
        "generated_at": generated_at.isoformat(),
        "filters": filters,
        "replay": replay_meta,
        "contract": {
            "positive_statuses": list(POSITIVE_STATUSES),
            "negative_statuses": list(NEGATIVE_STATUSES),
            "ambiguous_statuses": list(AMBIGUOUS_STATUSES),
            "confidence_thresholds": list(CONFIDENCE_THRESHOLDS),
            "graduation_rule": {
                "verdict": "satisfied",
                "confidence_threshold": GRADUATION_CONFIDENCE_THRESHOLD,
                "precision_bar": GRADUATION_PRECISION_BAR,
            },
        },
        "overall": overall,
        "per_requirement_code": per_code,
        "graduation_codes_meeting_bar": codes_meeting_bar,
        "graduation_codes_missing_bar": codes_missing_bar,
    }

    cov = overall["coverage"]
    grad = overall["graduation"]
    lines: list[str] = [
        "# Calibración de comprensión documental — Fase 4",
        "",
        f"Generado: {generated_at.strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"Cohorte: {len(records)} documentos con decisión humana terminal "
        f"(aprobado/excepción legal = positivo, rechazado = negativo).  ",
        f"Excluidas por ambiguas (`requiere_aclaracion`): "
        f"{replay_meta['ambiguous_excluded']}.  ",
        "Filtros: "
        + (", ".join(f"{k}={v}" for k, v in filters.items() if v) or "ninguno")
        + ".",
        "",
        "> **Caveat:** los rechazos humanos suelen deberse a periodo o tipo "
        "de documento equivocado, escaneos ilegibles o cargas erróneas, no "
        "sólo a incumplimiento. Un veredicto `satisfied` sobre un documento "
        "rechazado es el error costoso que esta calibración acota antes de "
        "graduar el código a provider-facing.",
        "",
        "## Resumen general",
        "",
        f"- Cobertura de comprensión: {cov['with_comprehension']}/{cov['records']} "
        f"({cov['missing_comprehension']} sin comprensión — tier triage / legacy)",
        f"- AUC global (confianza de obligación): {_num(overall['auc'])}",
        f"- Graduación global (`satisfied` ≥ {GRADUATION_CONFIDENCE_THRESHOLD}): "
        f"precisión {_pct(grad['precision'], 2)}, cubriría "
        f"{_pct(grad['approved_clearance'])} de los aprobados",
        f"- Códigos que CUMPLEN la barra de ≥ {_pct(GRADUATION_PRECISION_BAR, 0)}: "
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

    return "\n".join(lines), payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="calibrate_comprehension",
        description=(
            "Replay human-decided submissions against the stored Phase-1 "
            "comprehension verdict and report calibration per requirement "
            "code. Read-only."
        ),
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Max decided rows to replay."
    )
    parser.add_argument("--client-id", default=None, help="Filter by Submission.client_id.")
    parser.add_argument(
        "--requirement-code", default=None, help="Filter by Submission.requirement_code."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Markdown output path (a sibling .json is always written). "
            "Default: <repo-root>/outputs/comprehension-calibration-<date>.md"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    generated_at = datetime.now(UTC)

    out_md: Path = args.out or (
        _REPO_ROOT
        / "outputs"
        / f"comprehension-calibration-{generated_at.date().isoformat()}.md"
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
        )
    finally:
        db.close()  # read-only: nothing to commit, ever.

    filters = {
        "limit": args.limit,
        "client_id": args.client_id,
        "requirement_code": args.requirement_code,
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
    grad = overall["graduation"]
    cov = overall["coverage"]
    meeting = payload["graduation_codes_meeting_bar"]
    print(f"Reporte:  {out_md}")
    print(f"JSON:     {out_json}")
    print(
        f"Cohorte: {cov['records']} decididas "
        f"({overall['outcomes']['approved']} aprobadas, "
        f"{overall['outcomes']['rejected']} rechazadas; "
        f"{replay_meta['ambiguous_excluded']} ambiguas excluidas)"
    )
    print(
        f"Comprensión presente: {cov['with_comprehension']}/{cov['records']} | "
        f"AUC global: {_num(overall['auc'])}"
    )
    print(
        f"Graduación (`satisfied` ≥ {GRADUATION_CONFIDENCE_THRESHOLD}): precisión "
        f"{_pct(grad['precision'], 2)} | códigos que cumplen la barra del "
        f"{_pct(GRADUATION_PRECISION_BAR, 0)}: "
        + (", ".join(meeting) if meeting else "ninguno")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
