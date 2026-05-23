"""Phase 6 / Slice 6B — manual renewal dispatch driver.

Walks every :class:`ProviderWorkspace`, calls
:func:`app.services.renewal_dispatch.dispatch_renewals_for_workspace`,
and commits per workspace so a failure in one provider's dispatch
does not roll back the others.

Pair with ``scripts/run_renewal_audit.py``:

* The audit CLI is read-only — it tells you what *would* be reported
  on the dashboards given the current rule state.
* This dispatch CLI is the write path — it inserts ``renewal_reminders``
  rows and the matching client + provider notifications.

Usage::

    cd apps/api
    .venv/bin/python -m scripts.run_renewal_dispatch --dry-run
    .venv/bin/python -m scripts.run_renewal_dispatch
    .venv/bin/python -m scripts.run_renewal_dispatch --today 2026-06-15
    .venv/bin/python -m scripts.run_renewal_dispatch --workspace-id <uuid>

``--dry-run`` opens the session, runs the dispatcher, prints the
intended outcomes, and rolls back instead of committing. Use this
before the first real run on production to confirm no surprise
emit-storm.

Until Slice 6C wires this to a scheduler, this CLI is the only way
renewal notifications fire. Run it manually after each release until
the runner lands; expect each invocation to fire at most one
threshold per cycle.
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
from app.services.renewal_dispatch import (  # noqa: E402
    DispatchOutcome,
    dispatch_renewals_for_workspace,
)


def _parse_today(raw: str | None) -> date:
    if raw is None:
        return date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise SystemExit(f"--today must be an ISO date (YYYY-MM-DD): {exc}") from exc


def _fmt_outcome(vendor_label: str, o: DispatchOutcome) -> str:
    if o.skip_reason:
        return (
            f"{vendor_label}\t{o.requirement_code}\tskip={o.skip_reason}"
        )
    fired = ",".join(str(t) for t in o.thresholds_fired) or "-"
    skipped = ",".join(str(t) for t in o.thresholds_skipped_existing) or "-"
    return (
        f"{vendor_label}\t{o.requirement_code}\t"
        f"anchor={o.cycle_anchor_date}\tdue={o.due_date}\t"
        f"fired={fired}\tskipped={skipped}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--today",
        help="Override 'today' for the cadence math (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the dispatch but roll back instead of committing.",
    )
    parser.add_argument(
        "--workspace-id",
        help="Only dispatch for one workspace (UUID).",
    )
    args = parser.parse_args()
    today = _parse_today(args.today)

    db = SessionLocal()
    try:
        stmt = select(ProviderWorkspace)
        if args.workspace_id:
            stmt = stmt.where(ProviderWorkspace.id == args.workspace_id)
        workspaces = list(db.scalars(stmt))
        vendors_by_id = {v.id: v for v in db.scalars(select(Vendor))}

        total_fired = 0
        total_skipped = 0
        for ws in workspaces:
            vendor = vendors_by_id.get(ws.vendor_id)
            vendor_label = vendor.name if vendor else ws.vendor_id
            try:
                outcomes = dispatch_renewals_for_workspace(db, ws, today=today)
            except Exception as exc:  # pragma: no cover — operational guard
                db.rollback()
                print(
                    f"# {vendor_label}: dispatch failed, rolled back ({exc})",
                    file=sys.stderr,
                )
                continue

            for o in outcomes:
                print(_fmt_outcome(vendor_label, o))
                total_fired += len(o.thresholds_fired)
                total_skipped += len(o.thresholds_skipped_existing)

            if args.dry_run:
                db.rollback()
            else:
                db.commit()

        mode = "DRY-RUN" if args.dry_run else "COMMITTED"
        print(
            f"# {mode}: fired={total_fired} skipped_existing={total_skipped} "
            f"workspaces={len(workspaces)}",
            file=sys.stderr,
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
