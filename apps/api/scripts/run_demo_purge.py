"""Demo purge sweep — hard-delete demos frozen past the grace window.

For every demo org that has been ``frozen`` longer than DEMO_GRACE_PERIOD_DAYS
(so an upgrade could no longer restore it in place), delete its tenant data +
storage blobs via ``purge_org`` and audit it as ``org.demo.purged`` (counts
persisted in the audit row BEFORE the org is deleted).

IRREVERSIBLE. The default is a DRY-RUN that only logs what would be purged;
pass ``--apply`` to actually delete, and the cron is additionally gated by the
``DEMO_PURGE_ENABLED`` env (set to ``0`` to neuter it during the soak). Snapshot
the DB before the first real ``--apply`` run.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.constants.plans import DEMO_GRACE_PERIOD_DAYS, Plan  # noqa: E402
from app.core.time import utc_now  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import Organization  # noqa: E402
from app.services.audit_log import add_audit_event  # noqa: E402
from app.services.org_purge import purge_org  # noqa: E402
from app.services.storage import get_storage_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually delete. Default is a dry-run that only logs.",
    )
    parser.add_argument(
        "--grace-days", type=int, default=DEMO_GRACE_PERIOD_DAYS,
        help="Frozen-for-at-least this many days to be purge-eligible.",
    )
    args = parser.parse_args()
    apply = args.apply and os.environ.get("DEMO_PURGE_ENABLED", "1") != "0"

    db = SessionLocal()
    cutoff = utc_now() - timedelta(days=args.grace_days)
    purged = 0
    try:
        orgs = list(
            db.scalars(
                select(Organization)
                .where(
                    Organization.kind == "client",
                    Organization.plan == Plan.DEMO.value,
                    Organization.status == "frozen",
                    Organization.updated_at < cutoff,
                )
                .order_by(Organization.id)
            )
        )
        storage = get_storage_service()
        for org in orgs:
            if not apply:
                print(
                    f"# DRY-RUN would purge org={org.id} client={org.client_id} "
                    f"name={org.name!r}",
                    file=sys.stderr,
                )
                continue
            # Persist identity in the audit row BEFORE the org row is deleted.
            org_id, client_id, name = org.id, org.client_id, org.name
            try:
                result = purge_org(db, org, storage=storage)
                add_audit_event(
                    db,
                    action="org.demo.purged",
                    entity_type="organization",
                    entity_id=org_id,
                    actor_type="system",
                    actor_id=None,
                    before={"status": "frozen"},
                    after=None,
                    metadata={
                        "source": "cron.demo_purge",
                        "client_id": client_id,
                        "name": name,
                        **result.counts,
                    },
                )
                db.commit()
                purged += 1
            except Exception as exc:  # pragma: no cover — operational guard
                db.rollback()
                print(f"# {org_id}: purge failed, rolled back ({exc})", file=sys.stderr)
                continue
        mode = "PURGED" if apply else "DRY-RUN"
        print(
            f"# {mode}: purged={purged} candidates={len(orgs)} "
            f"grace_days={args.grace_days}",
            file=sys.stderr,
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
