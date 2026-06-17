"""Reconcile stranded intake receipts — async-upload durability safeguard.

The provider upload endpoint (``POST /portal/workspaces/{id}/submissions``)
persists a ``recibido`` receipt and runs the heavy validation pipeline in
a FastAPI ``BackgroundTask`` (``finalize_intake_submission_background``).
Those tasks run in-process and do NOT survive a worker restart — and
Render redeploys the API on every push to ``main``. A receipt whose
finalize task died mid-flight would otherwise sit at ``recibido``
forever, never transitioning to its derived status.

This driver re-finalizes every submission still at ``recibido`` older
than ``--older-than-minutes`` (default 5) by calling the SAME idempotent
background function. Safe to run repeatedly and concurrently with live
uploads: the function skips any receipt that has already moved past
``recibido``, and the age cutoff keeps the sweep from pre-empting a
finalize task that is merely a few milliseconds into its happy path.

Usage::

    cd apps/api
    .venv/bin/python -m scripts.run_intake_reconcile --dry-run
    .venv/bin/python -m scripts.run_intake_reconcile
    .venv/bin/python -m scripts.run_intake_reconcile --older-than-minutes 10

IMPORTANT: this re-reads the PDF bytes from durable storage, so on prod
the process MUST run with ``STORAGE_BACKEND=s3`` (the ``.env.production``
file omits it — the Render cron sets it explicitly).
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.constants.statuses import DocumentStatus  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import Submission  # noqa: E402
from app.models.entities import utc_now  # noqa: E402
from app.services.submission_service import (  # noqa: E402
    INTAKE_SOURCE_WORKSPACE_PORTAL,
    finalize_intake_submission_background,
)


def _stranded_receipts(db, *, older_than_minutes: int) -> list[tuple[str, str]]:
    """Return ``(submission_id, storage_key)`` for receipts stuck at recibido.

    Only rows older than the cutoff are returned so an in-flight finalize
    task (the normal happy path, milliseconds old) is never pre-empted by
    the sweep. A receipt with no document row is skipped (nothing to
    re-read) and logged by the caller.
    """
    cutoff = utc_now() - timedelta(minutes=older_than_minutes)
    submissions = (
        db.scalars(
            select(Submission)
            .where(
                Submission.status == DocumentStatus.RECIBIDO.value,
                Submission.created_at < cutoff,
            )
            .order_by(Submission.created_at)
        )
        .all()
    )
    pairs: list[tuple[str, str]] = []
    for submission in submissions:
        document = submission.documents[0] if submission.documents else None
        if document is None:
            print(f"skip\t{submission.id}\tno-document", file=sys.stderr)
            continue
        pairs.append((submission.id, document.storage_key))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--older-than-minutes",
        type=int,
        default=5,
        help="Only reconcile receipts older than this many minutes (default 5).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the stranded receipts without re-finalizing them.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        pairs = _stranded_receipts(db, older_than_minutes=args.older_than_minutes)
    finally:
        db.close()

    if not pairs:
        print("No stranded receipts found.")
        return 0

    print(f"Found {len(pairs)} stranded receipt(s) at 'recibido':")
    for submission_id, storage_key in pairs:
        print(f"  {submission_id}\t{storage_key}")

    if args.dry_run:
        print("--dry-run: not re-finalizing.")
        return 0

    reconciled = 0
    for submission_id, storage_key in pairs:
        # Each call opens its own session, is idempotent, and never
        # raises — a single bad row can't abort the sweep.
        finalize_intake_submission_background(
            submission_id=submission_id,
            storage_key=storage_key,
            intake_source=INTAKE_SOURCE_WORKSPACE_PORTAL,
        )
        reconciled += 1

    print(f"Re-finalized {reconciled} receipt(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
