"""Backfill metadata workbooks for already-stored documents (CW-14).

Metadata XLSX tables are generated at intake. Documents uploaded before the
automatic export existed — or whose export failed — have none, so they never
reach the client master ("si tengo documentos ya aprobados de todo el año,
¿por qué no hay metadata?"). This regenerates them from the persisted
DocumentInspection signals (no OCR / LLM / re-parse), pulling each PDF from
storage on demand, then rebuilds each affected client's master once.

Idempotent: a slot that already has a latest_metadata.xlsx is skipped unless
--force. Dry-run by default; pass --apply to write.

Usage:
  cd apps/api
  .venv/bin/python -m scripts.backfill_metadata                 # dry-run, all
  .venv/bin/python -m scripts.backfill_metadata --apply
  .venv/bin/python -m scripts.backfill_metadata --client-id <id> --apply
  .venv/bin/python -m scripts.backfill_metadata --vendor-id <id> \
      --period 2026-M05 --limit 50 --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.services.metadata_export import backfill_metadata_exports  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--client-id", default=None)
    parser.add_argument("--vendor-id", default=None)
    parser.add_argument(
        "--period", default=None, help="canonical period_key, e.g. 2026-M05"
    )
    parser.add_argument(
        "--status",
        action="append",
        default=None,
        help="submission status filter; repeatable (default: all statuses)",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--force",
        action="store_true",
        help="regenerate even when a latest_metadata.xlsx already exists",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write workbooks (default is a dry-run that only reports)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = backfill_metadata_exports(
            db,
            client_id=args.client_id,
            vendor_id=args.vendor_id,
            period_key=args.period,
            statuses=tuple(args.status) if args.status else None,
            force=args.force,
            dry_run=not args.apply,
            limit=args.limit,
            log=print,
        )
    finally:
        db.close()

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(
        f"\n[{mode}] scanned={result.scanned} generated={result.generated} "
        f"skipped_existing={result.skipped_existing} "
        f"skipped_unresolved={result.skipped_unresolved} "
        f"failed={result.failed} clients_rebuilt={result.clients_rebuilt}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
