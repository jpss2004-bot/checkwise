"""Durable intake-finalize queue (B2).

When ``INTAKE_QUEUE_CONSUMER_ENABLED`` is on, the async-intake endpoint enqueues
an ``intake_queue`` row (committed with the ``recibido`` receipt) instead of
scheduling an in-process FastAPI BackgroundTask, and a separate worker process
(``scripts/run_intake_queue_consumer.py``) drains the queue by running the
ALREADY-idempotent ``finalize_intake_submission_background``. This moves the heavy
back-half off the web tier and makes it survive a dyno restart.

Mechanics:

* **Enqueue is insert-if-absent** (``submission_id`` is UNIQUE) so a retried
  upload never duplicates work. Never raises into the request.
* **Claim** selects ``pending`` jobs whose ``available_at`` has arrived, PLUS
  ``claimed`` jobs whose worker died (``claimed_at`` older than the visibility
  timeout), with ``FOR UPDATE SKIP LOCKED`` so concurrent workers never grab the
  same row (Postgres; SQLite ignores the hint, which is fine for the single-
  threaded test path). Each claim bumps ``attempts``; a job past
  ``INTAKE_QUEUE_MAX_ATTEMPTS`` is marked ``failed`` instead of re-claimed so a
  poison row can't loop forever.
* **Process** runs the idempotent finalize (which never raises) and marks the job
  ``done``. A worker crash between claim and done leaves the row ``claimed`` →
  reclaimed after the timeout → re-run (idempotent). The existing reconcile cron
  remains the final backstop for receipts that never made it into the queue.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import IntakeQueueJob
from app.models.entities import utc_now

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_CLAIMED = "claimed"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


def enqueue_intake_job(
    *,
    submission_id: str,
    storage_key: str,
    intake_source: str,
) -> bool:
    """Enqueue a durable finalize job for a receipt (insert-if-absent).

    Opens its own session and commits so the job is durable independently of the
    request transaction. Idempotent: a second enqueue for the same submission is
    a no-op. Returns True when a row was inserted (or already present), False on
    a hard failure. Never raises into the caller.
    """
    db = SessionLocal()
    try:
        existing = db.scalar(
            select(IntakeQueueJob).where(
                IntakeQueueJob.submission_id == submission_id
            )
        )
        if existing is not None:
            return True
        db.add(
            IntakeQueueJob(
                submission_id=submission_id,
                storage_key=storage_key,
                intake_source=intake_source,
                status=STATUS_PENDING,
                available_at=utc_now(),
            )
        )
        db.commit()
        return True
    except Exception:  # noqa: BLE001 — a unique-race or DB error must not crash intake
        logger.exception("Failed enqueuing intake job; submission_id=%s", submission_id)
        db.rollback()
        # A concurrent insert that lost the unique race still means the job is
        # queued, so treat an existing row as success.
        try:
            return (
                db.scalar(
                    select(IntakeQueueJob.id).where(
                        IntakeQueueJob.submission_id == submission_id
                    )
                )
                is not None
            )
        except Exception:  # noqa: BLE001
            return False
    finally:
        db.close()


def claim_intake_jobs(
    db: Session,
    *,
    worker_id: str,
    limit: int,
    claim_timeout_minutes: int,
    max_attempts: int,
    now=None,  # noqa: ANN001 — datetime | None (injected for tests)
) -> list[dict]:
    """Claim up to ``limit`` runnable jobs; return them as primitive dicts.

    Runnable = pending-and-available OR claimed-but-stale (worker died). Uses
    ``FOR UPDATE SKIP LOCKED`` so parallel consumers never double-claim. Bumps
    ``attempts`` and marks ``claimed``; a job already past ``max_attempts`` is
    marked ``failed`` and skipped. Commits the claim so it is durable before any
    processing. Returns ``[]`` on error (fail-safe — the next poll retries).
    """
    moment = now or utc_now()
    stale_before = moment - timedelta(minutes=max(0, claim_timeout_minutes))
    try:
        rows = (
            db.scalars(
                select(IntakeQueueJob)
                .where(
                    or_(
                        (IntakeQueueJob.status == STATUS_PENDING)
                        & (IntakeQueueJob.available_at <= moment),
                        (IntakeQueueJob.status == STATUS_CLAIMED)
                        & (IntakeQueueJob.claimed_at < stale_before),
                    )
                )
                .order_by(IntakeQueueJob.available_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            .all()
        )
        claimed: list[dict] = []
        for job in rows:
            if job.attempts >= max_attempts:
                job.status = STATUS_FAILED
                job.last_error = f"exceeded max_attempts={max_attempts}"
                continue
            job.attempts += 1
            job.status = STATUS_CLAIMED
            job.claimed_at = moment
            job.claimed_by = worker_id
            claimed.append(
                {
                    "id": job.id,
                    "submission_id": job.submission_id,
                    "storage_key": job.storage_key,
                    "intake_source": job.intake_source,
                    "attempts": job.attempts,
                }
            )
        db.commit()
        return claimed
    except Exception:  # noqa: BLE001 — a claim failure must not crash the consumer loop
        logger.exception("Failed claiming intake jobs (worker=%s)", worker_id)
        db.rollback()
        return []


def process_intake_job(job: dict) -> str:
    """Run the idempotent finalize for one claimed job; mark it done or requeue.

    ``finalize_intake_submission_background`` NEVER raises — it swallows every
    internal failure (e.g. a transient storage outage re-reading the PDF) and
    returns ``None`` with the receipt still at ``recibido``. So a clean return is
    NOT proof of success: we confirm the receipt actually advanced past
    ``recibido`` and, if it did not, requeue with backoff so the queue's
    retry / max_attempts / poison-detection machinery engages instead of a
    silent ``done``. Returns the terminal status. Never raises.
    """
    # Imported here to avoid a heavy import at module load (and a cycle:
    # submission_service does not import this module, but keep it lazy anyway).
    from app.services.submission_service import finalize_intake_submission_background

    try:
        finalize_intake_submission_background(
            submission_id=job["submission_id"],
            storage_key=job["storage_key"],
            intake_source=job["intake_source"],
        )
    except Exception as exc:  # noqa: BLE001 — finalize shouldn't raise; defence in depth
        logger.exception("Intake job finalize raised; job_id=%s", job["id"])
        _mark(job["id"], STATUS_PENDING, error=f"{type(exc).__name__}: {exc}", backoff=True)
        return STATUS_PENDING

    if _receipt_finalized(job["submission_id"]):
        _mark(job["id"], STATUS_DONE)
        return STATUS_DONE
    _mark(
        job["id"],
        STATUS_PENDING,
        error="finalize did not advance the receipt past recibido",
        backoff=True,
    )
    return STATUS_PENDING


def _receipt_finalized(submission_id: str) -> bool:
    """True when the submission advanced past ``recibido`` (or is gone).

    A missing submission counts as finalized (nothing to retry); only an
    existing, still-``recibido`` receipt is an incomplete finalize. A read error
    also counts as finalized (fail toward ``done``) so a transient glitch can't
    hot-loop the job — the reconcile cron remains the backstop for a receipt
    that genuinely never advanced.
    """
    from app.constants.statuses import DocumentStatus
    from app.models import Submission

    db = SessionLocal()
    try:
        submission = db.get(Submission, submission_id)
        if submission is None:
            return True
        return submission.status != DocumentStatus.RECIBIDO.value
    except Exception:  # noqa: BLE001 — fail toward done to avoid a hot retry loop
        logger.exception(
            "Failed reading receipt status; treating as finalized. submission_id=%s",
            submission_id,
        )
        return True
    finally:
        db.close()


def _mark(job_id: str, status: str, *, error: str | None = None, backoff: bool = False) -> None:
    db = SessionLocal()
    try:
        job = db.get(IntakeQueueJob, job_id)
        if job is None:
            return
        job.status = status
        if error is not None:
            job.last_error = error[:1000]
        if backoff:
            # Re-queue with a simple linear backoff so a transient failure is
            # retried later rather than hot-looped.
            job.available_at = utc_now() + timedelta(minutes=max(1, job.attempts))
            job.claimed_at = None
            job.claimed_by = None
        db.commit()
    except Exception:  # noqa: BLE001 — a status-write failure must not crash the worker
        logger.exception("Failed marking intake job %s as %s", job_id, status)
        db.rollback()
    finally:
        db.close()


def run_intake_queue_consumer_once(*, worker_id: str, batch_size: int | None = None) -> dict:
    """Claim one batch and process it.

    Returns ``{"claimed", "done", "requeued"}`` — counting by the REAL outcome of
    each job (a finalize that did not advance the receipt is ``requeued``, not a
    silent success) so the worker's logs/metrics don't overstate progress. The
    consumer script calls this in a loop. Opens its own session for the claim;
    each ``process_intake_job`` owns its finalize + status sessions.
    """
    limit = int(batch_size or settings.INTAKE_QUEUE_BATCH_SIZE or 10)
    db = SessionLocal()
    try:
        jobs = claim_intake_jobs(
            db,
            worker_id=worker_id,
            limit=limit,
            claim_timeout_minutes=int(settings.INTAKE_QUEUE_CLAIM_TIMEOUT_MINUTES or 15),
            max_attempts=int(settings.INTAKE_QUEUE_MAX_ATTEMPTS or 5),
        )
    finally:
        db.close()

    done = 0
    requeued = 0
    for job in jobs:
        if process_intake_job(job) == STATUS_DONE:
            done += 1
        else:
            requeued += 1
    return {"claimed": len(jobs), "done": done, "requeued": requeued}


def prune_terminal_intake_jobs(*, older_than_days: int) -> int:
    """Delete ``done`` / ``failed`` rows older than ``older_than_days``.

    Terminal rows accumulate one-per-finalized-submission forever otherwise. The
    claim index keeps the hot path selective regardless, so this is housekeeping,
    not correctness — run it periodically from the consumer. ``<= 0`` disables.
    Returns the row count deleted. Never raises.
    """
    if older_than_days <= 0:
        return 0
    cutoff = utc_now() - timedelta(days=older_than_days)
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(IntakeQueueJob).where(
                IntakeQueueJob.status.in_((STATUS_DONE, STATUS_FAILED)),
                IntakeQueueJob.updated_at < cutoff,
            )
        ).all()
        for row in rows:
            db.delete(row)
        db.commit()
        return len(rows)
    except Exception:  # noqa: BLE001 — a prune failure must not crash the worker
        logger.exception("Failed pruning terminal intake-queue rows")
        db.rollback()
        return 0
    finally:
        db.close()
