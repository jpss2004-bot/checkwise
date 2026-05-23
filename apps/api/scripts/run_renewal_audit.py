"""Phase 6 / Slice 6A — manual renewal-audit CLI.

Walks every :class:`ProviderWorkspace`, finds the onboarding
requirements that carry a ``renewal_frequency_days`` (CSF moral, CSF
física, REPSE original, registro patronal original), resolves the
current submission per slot, computes the next renewal due date and
the coarse status (``ok`` / ``due_soon`` / ``overdue`` /
``never_approved``), and prints a tab-separated table to stdout.

This is read-only: it never writes to the database and it never emits
notifications. The point of Slice 6A is to land the rule layer and
have a way to sanity-check it against real seed data before Slice 6B
wires the notification emit-site (and before Slice 6C picks a
scheduler / runner).

Usage::

    cd apps/api
    .venv/bin/python -m scripts.run_renewal_audit
    .venv/bin/python -m scripts.run_renewal_audit --today 2026-06-01
    .venv/bin/python -m scripts.run_renewal_audit --only-due

The ``--today`` override lets you check the cadence math against a
known future date without changing the system clock. ``--only-due``
filters the output to rows with status ``due_soon`` or ``overdue`` so
you can spot-check the ones that would page someone if Slice 6B were
already wired.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

# Make ``app`` importable when running this script directly. Mirrors
# the pattern in the sibling scripts (add_test_provider.py etc).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.compliance_catalog import (  # noqa: E402
    expediente_for_persona,
    normalize_persona_type,
)
from app.db.session import SessionLocal  # noqa: E402
from app.models import ProviderWorkspace, Vendor  # noqa: E402
from app.services.evidence_slots import (  # noqa: E402
    current_submission_for_slot,
    next_renewal_due_date,
    renewal_anchor_date,
    renewal_status,
)


def _parse_today(raw: str | None) -> date:
    if raw is None:
        return date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise SystemExit(f"--today must be an ISO date (YYYY-MM-DD): {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--today",
        help="Override 'today' for the cadence math (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--only-due",
        action="store_true",
        help="Only print rows with status due_soon or overdue.",
    )
    args = parser.parse_args()
    today = _parse_today(args.today)

    db = SessionLocal()
    try:
        workspaces = list(db.scalars(select(ProviderWorkspace)))
        vendors_by_id = {v.id: v for v in db.scalars(select(Vendor))}

        print(
            "\t".join(
                [
                    "vendor",
                    "client_id",
                    "requirement",
                    "frequency_days",
                    "anchor",
                    "due",
                    "status",
                ]
            )
        )

        rows_printed = 0
        for ws in workspaces:
            persona = normalize_persona_type(ws.persona_type)
            for req in expediente_for_persona(persona):
                if req.renewal_frequency_days is None:
                    continue
                current = current_submission_for_slot(
                    db,
                    client_id=ws.client_id,
                    vendor_id=ws.vendor_id,
                    requirement_code=req.code,
                    period_key=None,
                )
                anchor = renewal_anchor_date(current)
                due = next_renewal_due_date(
                    anchor=anchor,
                    frequency_days=req.renewal_frequency_days,
                )
                status = (
                    renewal_status(due, today)
                    if due is not None
                    else "never_approved"
                )
                if args.only_due and status not in ("due_soon", "overdue"):
                    continue
                vendor = vendors_by_id.get(ws.vendor_id)
                vendor_label = vendor.name if vendor else ws.vendor_id
                print(
                    "\t".join(
                        [
                            vendor_label,
                            ws.client_id,
                            req.code,
                            str(req.renewal_frequency_days),
                            anchor.isoformat() if anchor else "-",
                            due.isoformat() if due else "-",
                            status,
                        ]
                    )
                )
                rows_printed += 1

        if rows_printed == 0:
            print("# no rows matched", file=sys.stderr)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
