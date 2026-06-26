"""Durable intake-queue consumer (B2) — drains ``intake_queue``.

When ``INTAKE_QUEUE_CONSUMER_ENABLED`` is on, the provider upload endpoint
enqueues a durable ``intake_queue`` row instead of scheduling an in-process
BackgroundTask. THIS process is the worker that drains the queue by running the
idempotent ``finalize_intake_submission_background`` for each claimed job.

PROVISIONING this as a long-running worker service (e.g. a Render "worker"
process, or a systemd unit) is the OPERATOR/INFRA decision B2 flags. The
behaviour is intentionally a thin loop so it can run either:

* one-shot (``--once``) from a cron, draining whatever is pending, or
* as a daemon (default) polling every ``--poll-seconds``.

Safe to run with N replicas: ``claim_intake_jobs`` uses ``FOR UPDATE SKIP
LOCKED`` so workers never double-claim, and a crash mid-finalize leaves the job
``claimed`` to be reclaimed after the visibility timeout (the finalize is
idempotent). Like the reconcile cron, on prod it MUST run with
``STORAGE_BACKEND=s3`` so it can re-read the PDF bytes from durable storage.

Usage::

    cd apps/api
    .venv/bin/python -m scripts.run_intake_queue_consumer --once
    .venv/bin/python -m scripts.run_intake_queue_consumer --poll-seconds 5
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.services.intake_queue import (  # noqa: E402
    prune_terminal_intake_jobs,
    run_intake_queue_consumer_once,
)

logger = logging.getLogger(__name__)


def _worker_id() -> str:
    # A stable-ish per-process id for the ``claimed_by`` audit column.
    return f"{os.uname().nodename}:{os.getpid()}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Drain one batch and exit (cron mode) instead of polling forever.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=5.0,
        help="Daemon poll interval when the queue is empty (default 5).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Jobs claimed per poll (default INTAKE_QUEUE_BATCH_SIZE).",
    )
    parser.add_argument(
        "--prune-days",
        type=int,
        default=14,
        help="Delete done/failed rows older than this on idle (0 disables).",
    )
    args = parser.parse_args()

    if not settings.INTAKE_QUEUE_CONSUMER_ENABLED:
        print(
            "INTAKE_QUEUE_CONSUMER_ENABLED is false — nothing to consume. "
            "Enable it (and the enqueue path) before running this worker.",
            file=sys.stderr,
        )
        # Exit 0: this is a no-op, not an error, so a misconfigured cron is quiet.
        return 0

    worker_id = _worker_id()
    print(f"intake-queue consumer starting (worker={worker_id}, once={args.once})")

    done_total = 0
    requeued_total = 0
    while True:
        try:
            result = run_intake_queue_consumer_once(
                worker_id=worker_id, batch_size=args.batch_size
            )
        except Exception:  # noqa: BLE001
            # A poll-time failure (e.g. SessionLocal() can't reach the DB during
            # a transient outage) is raised BEFORE the inner per-job try/except
            # can swallow it. In --once mode let it propagate so a cron surfaces
            # the error; as a daemon, log and back off so the worker self-heals
            # instead of crash-looping on the platform supervisor.
            if args.once:
                raise
            logger.exception("intake-queue poll failed; backing off and retrying")
            time.sleep(max(0.1, args.poll_seconds))
            continue
        done_total += result["done"]
        requeued_total += result["requeued"]
        if result["claimed"]:
            print(
                f"claimed={result['claimed']}\tdone={result['done']}\t"
                f"requeued={result['requeued']}"
            )
        if args.once:
            prune_terminal_intake_jobs(older_than_days=args.prune_days)
            break
        if result["claimed"] == 0:
            # Idle — prune terminal rows, then back off.
            prune_terminal_intake_jobs(older_than_days=args.prune_days)
            time.sleep(max(0.1, args.poll_seconds))

    print(f"done — {done_total} finalized, {requeued_total} requeued.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
