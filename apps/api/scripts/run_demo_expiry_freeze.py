"""Demo expiry sweep — freeze demos whose 14-day deadline has passed.

Flips ``organizations.status`` from ``active`` to ``frozen`` for every demo
org past ``demo_expires_at``, and audits each as ``org.demo.frozen``. Freezing
is reversible (an admin upgrade reactivates), so this commits by default;
``--dry-run`` rolls back. Idempotent — already-frozen orgs aren't matched.

Schedule: daily, AFTER the renewal/reporting crons so a freeze never races a
same-day notification (the renewal/reporting crons also skip frozen orgs).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.services.audit_log import add_audit_event  # noqa: E402
from app.services.subscription import freeze_expired_demos  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="Run but roll back instead of commit."
    )
    args = parser.parse_args()

    db = SessionLocal()
    frozen = 0
    try:
        for org in freeze_expired_demos(db):
            add_audit_event(
                db,
                action="org.demo.frozen",
                entity_type="organization",
                entity_id=org.id,
                actor_type="system",
                actor_id=None,
                before={"status": "active"},
                after={"status": "frozen"},
                metadata={"source": "cron.demo_expiry", "client_id": org.client_id},
            )
            frozen += 1
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
        mode = "DRY-RUN" if args.dry_run else "COMMITTED"
        print(f"# {mode}: froze={frozen}", file=sys.stderr)
        return 0
    except Exception as exc:  # pragma: no cover — operational guard
        db.rollback()
        print(f"# demo-expiry sweep failed, rolled back ({exc})", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
