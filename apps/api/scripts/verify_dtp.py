"""Verify the DTP demo: prints the EXACT per-vendor and aggregate compliance %
the client dashboard will show, by calling the same helpers the /client/overview
endpoint uses. Read-only."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.api.v1 import client as C
from app.db.session import SessionLocal
from app.models import Client

MARKER = "DTP_DEMO_2026_06_09"


def main() -> None:
    with SessionLocal() as db:
        today = date.today()
        year = today.year
        rows = list(
            db.scalars(select(Client).where(Client.notes.like(f"{MARKER}%")).order_by(Client.notes))
        )
        if not rows:
            print("No DTP demo clients found.")
            return
        for cl in rows:
            wss = C._scoped_workspaces(db, cl.id)
            subs_by_vendor, inst_by_id = C._portfolio_slot_inputs(db, cl.id)
            pcts = []
            for ws in wss:
                summ = C._vendor_compliance(
                    db, ws, today=today, year=year,
                    prefetched_submissions=subs_by_vendor.get(ws.vendor_id, []),
                    institutions_by_id=inst_by_id,
                )
                pcts.append((ws.display_name or "?", summ["compliance_pct"], summ["semaphore_level"]))
            agg = round(sum(p[1] for p in pcts) / len(pcts)) if pcts else 100
            tone = "green" if agg >= 85 else ("yellow" if agg >= 60 else "red")
            label = cl.notes.split("·")[1].strip() if "·" in cl.notes else cl.notes
            print(f"\n{label:>7}  →  AGG={agg:>3}%  ({tone})   [{len(pcts)} proveedores]")
            for n, p, lvl in sorted(pcts, key=lambda x: x[1]):
                print(f"    {p:>3}%  {lvl:<7}  {n[:50]}")


if __name__ == "__main__":
    main()
