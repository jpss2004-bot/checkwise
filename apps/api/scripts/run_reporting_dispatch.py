"""Phase 7 cutover Slice D — periodic-reporting dispatch driver.

Walks every active :class:`ProviderWorkspace`, calls
:func:`app.services.notifications.emit_reporting_for_workspace`
in active mode, and commits per workspace so a failure in one
provider's emit does not roll back the others.

This is the cron entry that makes periodic-reporting events
(``reporting.window.opened``, ``reporting.due.t-7``,
``reporting.due.t-1``, ``reporting.due.t-0``,
``reporting.overdue.t+3``) actually fire — they have no legacy
parallel, so this script IS the source of truth.

Pair with ``scripts/run_renewal_dispatch.py``:

* That script runs the renewal threshold cadence (CSF / patronal /
  REPSE expediente) — separate event family, separate cron entry
  in production.
* This script walks the recurring REPSE calendar (mensual IMSS+SAT,
  bimestral INFONAVIT, cuatrimestral SISUB/ICSOE, anual SAT).

Usage::

    cd apps/api
    .venv/bin/python -m scripts.run_reporting_dispatch --dry-run
    .venv/bin/python -m scripts.run_reporting_dispatch
    .venv/bin/python -m scripts.run_reporting_dispatch --today 2026-06-15
    .venv/bin/python -m scripts.run_reporting_dispatch --workspace-id <uuid>

``--dry-run`` opens the session, walks the workspaces, prints the
intended outcomes, and rolls back instead of committing. Use this
before the first real run to confirm no surprise emit-storm.

In production this runs as a daily Render Cron Job at 07:00
America/Mexico_City; see ``render.yaml`` for the schedule.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models import ProviderWorkspace, Vendor  # noqa: E402
from app.services.notifications import (  # noqa: E402
    ReportingEmitOutcome,
    emit_reporting_for_workspace,
)
from app.services.subscription import blocked_client_ids  # noqa: E402


def _parse_today(raw: str | None) -> date:
    if raw is None:
        return date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise SystemExit(
            f"--today must be an ISO date (YYYY-MM-DD): {exc}"
        ) from exc


def _fmt_outcome(vendor_label: str, o: ReportingEmitOutcome) -> str:
    if o.skip_reason:
        return (
            f"{vendor_label}\t{o.requirement_code}\t"
            f"period={o.period_key}\tskip={o.skip_reason}"
        )
    queued = ",".join(o.thresholds_queued) or "-"
    deduped = ",".join(o.thresholds_deduped) or "-"
    return (
        f"{vendor_label}\t{o.requirement_code}\t"
        f"period={o.period_key}\tdue={o.due_date.isoformat()}\t"
        f"queued={queued}\tdeduped={deduped}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Walk active workspaces and emit reporting threshold "
            "notifications via the unified fabric."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Roll back per-workspace transactions instead of committing.",
    )
    parser.add_argument(
        "--today",
        default=None,
        help="Override today's date (YYYY-MM-DD) for deterministic runs.",
    )
    parser.add_argument(
        "--workspace-id",
        default=None,
        help="Restrict the walk to a single workspace id.",
    )
    args = parser.parse_args()
    today = _parse_today(args.today)

    db = SessionLocal()
    try:
        # Skip workspaces whose client org is frozen/expired (lapsed demos).
        blocked = blocked_client_ids(db)
        stmt = select(ProviderWorkspace).where(
            ProviderWorkspace.status == "active"
        )
        if args.workspace_id:
            stmt = stmt.where(ProviderWorkspace.id == args.workspace_id)
        workspaces = [w for w in db.scalars(stmt) if w.client_id not in blocked]
        vendors_by_id = {v.id: v for v in db.scalars(select(Vendor))}

        total_queued = 0
        total_deduped = 0
        for ws in workspaces:
            vendor = vendors_by_id.get(ws.vendor_id)
            vendor_label = vendor.name if vendor else ws.vendor_id
            try:
                outcomes = emit_reporting_for_workspace(
                    db, ws, today=today, mode="active"
                )
            except Exception as exc:  # pragma: no cover — operational guard
                db.rollback()
                print(
                    f"# {vendor_label}: reporting emit failed, rolled back ({exc})",
                    file=sys.stderr,
                )
                continue

            for o in outcomes:
                print(_fmt_outcome(vendor_label, o))
                total_queued += len(o.thresholds_queued)
                total_deduped += len(o.thresholds_deduped)

            if args.dry_run:
                db.rollback()
            else:
                db.commit()

        mode = "DRY-RUN" if args.dry_run else "COMMITTED"
        print(
            f"# {mode}: queued={total_queued} deduped={total_deduped} "
            f"workspaces={len(workspaces)} today={today.isoformat()}",
            file=sys.stderr,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
