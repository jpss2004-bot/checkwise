"""B2 — durable intake queue tests."""

from __future__ import annotations

from datetime import UTC, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import IntakeQueueJob
from app.models.entities import utc_now
from app.services import intake_queue as q


@pytest.fixture
def db_factory(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    # enqueue / _mark / consumer open their own SessionLocal — point it at the
    # test engine.
    monkeypatch.setattr(q, "SessionLocal", factory)
    return factory


def _seed_job(db_factory, **overrides):
    db = db_factory()
    try:
        job = IntakeQueueJob(
            submission_id=overrides.get("submission_id", "sub-1"),
            storage_key=overrides.get("storage_key", "local://s.pdf"),
            intake_source=overrides.get("intake_source", "portal"),
            status=overrides.get("status", "pending"),
            attempts=overrides.get("attempts", 0),
            available_at=overrides.get("available_at", utc_now()),
            claimed_at=overrides.get("claimed_at"),
            claimed_by=overrides.get("claimed_by"),
        )
        db.add(job)
        db.commit()
        return job.id
    finally:
        db.close()


def _jobs(db_factory):
    db = db_factory()
    try:
        return {j.submission_id: j for j in db.scalars(select(IntakeQueueJob)).all()}
    finally:
        db.close()


# -- enqueue ----------------------------------------------------------------


def test_enqueue_inserts_pending(db_factory):
    assert q.enqueue_intake_job(
        submission_id="sub-1", storage_key="k", intake_source="portal"
    )
    jobs = _jobs(db_factory)
    assert jobs["sub-1"].status == "pending"
    assert jobs["sub-1"].attempts == 0


def test_enqueue_is_idempotent(db_factory):
    q.enqueue_intake_job(submission_id="sub-1", storage_key="k", intake_source="portal")
    q.enqueue_intake_job(submission_id="sub-1", storage_key="k2", intake_source="portal")
    db = db_factory()
    try:
        assert db.scalar(select(IntakeQueueJob.id).where(IntakeQueueJob.submission_id == "sub-1"))
        assert len(db.scalars(select(IntakeQueueJob)).all()) == 1
    finally:
        db.close()


# -- claim ------------------------------------------------------------------


def test_claim_marks_claimed_and_bumps_attempts(db_factory):
    _seed_job(db_factory, submission_id="sub-1")
    db = db_factory()
    try:
        claimed = q.claim_intake_jobs(
            db, worker_id="w1", limit=10, claim_timeout_minutes=15, max_attempts=5
        )
    finally:
        db.close()
    assert len(claimed) == 1
    assert claimed[0]["submission_id"] == "sub-1"
    assert claimed[0]["attempts"] == 1
    job = _jobs(db_factory)["sub-1"]
    assert job.status == "claimed"
    assert job.claimed_by == "w1"


def test_claim_skips_future_available(db_factory):
    _seed_job(db_factory, submission_id="sub-1", available_at=utc_now() + timedelta(hours=1))
    db = db_factory()
    try:
        claimed = q.claim_intake_jobs(
            db, worker_id="w1", limit=10, claim_timeout_minutes=15, max_attempts=5
        )
    finally:
        db.close()
    assert claimed == []


def test_claim_reclaims_stale_claimed(db_factory):
    _seed_job(
        db_factory,
        submission_id="sub-1",
        status="claimed",
        claimed_at=utc_now() - timedelta(minutes=30),
        attempts=1,
    )
    db = db_factory()
    try:
        claimed = q.claim_intake_jobs(
            db, worker_id="w2", limit=10, claim_timeout_minutes=15, max_attempts=5
        )
    finally:
        db.close()
    assert len(claimed) == 1
    assert claimed[0]["attempts"] == 2  # reclaim bumps attempts


def test_claim_does_not_reclaim_fresh_claimed(db_factory):
    _seed_job(
        db_factory,
        submission_id="sub-1",
        status="claimed",
        claimed_at=utc_now() - timedelta(minutes=1),
    )
    db = db_factory()
    try:
        claimed = q.claim_intake_jobs(
            db, worker_id="w2", limit=10, claim_timeout_minutes=15, max_attempts=5
        )
    finally:
        db.close()
    assert claimed == []


def test_claim_fails_job_past_max_attempts(db_factory):
    _seed_job(db_factory, submission_id="sub-1", attempts=5)
    db = db_factory()
    try:
        claimed = q.claim_intake_jobs(
            db, worker_id="w1", limit=10, claim_timeout_minutes=15, max_attempts=5
        )
    finally:
        db.close()
    assert claimed == []
    assert _jobs(db_factory)["sub-1"].status == "failed"


def test_claim_respects_limit(db_factory):
    for i in range(5):
        _seed_job(db_factory, submission_id=f"sub-{i}")
    db = db_factory()
    try:
        claimed = q.claim_intake_jobs(
            db, worker_id="w1", limit=2, claim_timeout_minutes=15, max_attempts=5
        )
    finally:
        db.close()
    assert len(claimed) == 2


# -- process + consumer -----------------------------------------------------


def _job_dict(job_id, submission_id="sub-1"):
    return {
        "id": job_id,
        "submission_id": submission_id,
        "storage_key": "k",
        "intake_source": "portal",
    }


def test_process_marks_done_when_receipt_advanced(db_factory, monkeypatch):
    job_id = _seed_job(db_factory, submission_id="sub-1", status="claimed")
    finalize = MagicMock()
    monkeypatch.setattr(
        "app.services.submission_service.finalize_intake_submission_background", finalize
    )
    monkeypatch.setattr(q, "_receipt_finalized", lambda _sid: True)
    status = q.process_intake_job(_job_dict(job_id))
    assert status == "done"
    finalize.assert_called_once_with(
        submission_id="sub-1", storage_key="k", intake_source="portal"
    )
    assert _jobs(db_factory)["sub-1"].status == "done"


def test_process_requeues_when_finalize_did_not_advance(db_factory, monkeypatch):
    # finalize returns cleanly (it never raises) but the receipt is still
    # recibido → the queue must requeue, not silently mark done.
    job_id = _seed_job(db_factory, submission_id="sub-1", status="claimed", attempts=1)
    monkeypatch.setattr(
        "app.services.submission_service.finalize_intake_submission_background", MagicMock()
    )
    monkeypatch.setattr(q, "_receipt_finalized", lambda _sid: False)
    status = q.process_intake_job(_job_dict(job_id))
    assert status == "pending"
    job = _jobs(db_factory)["sub-1"]
    assert job.status == "pending"
    assert "recibido" in (job.last_error or "")
    assert job.claimed_at is None


def test_receipt_finalized_states(db_factory):
    from app.models import Submission

    db = db_factory()
    try:
        db.add(
            Submission(
                id="sub-recibido",
                client_id="c",
                vendor_id="v",
                period_id="p",
                institution_id="i",
                requirement_id="r",
                load_type="mensual",
                status="recibido",
            )
        )
        db.add(
            Submission(
                id="sub-derived",
                client_id="c",
                vendor_id="v",
                period_id="p",
                institution_id="i",
                requirement_id="r",
                load_type="mensual",
                status="derivado",
            )
        )
        db.commit()
    finally:
        db.close()
    assert q._receipt_finalized("sub-missing") is True  # gone → nothing to retry
    assert q._receipt_finalized("sub-recibido") is False  # still recibido
    assert q._receipt_finalized("sub-derived") is True  # advanced


def test_process_failure_requeues_with_backoff(db_factory, monkeypatch):
    job_id = _seed_job(db_factory, submission_id="sub-1", status="claimed", attempts=2)
    boom = MagicMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(
        "app.services.submission_service.finalize_intake_submission_background", boom
    )
    status = q.process_intake_job(
        {
            "id": job_id,
            "submission_id": "sub-1",
            "storage_key": "k",
            "intake_source": "portal",
        }
    )
    assert status == "pending"
    job = _jobs(db_factory)["sub-1"]
    assert job.status == "pending"
    assert job.last_error
    assert job.claimed_at is None  # released for reclaim
    # Backed off into the future (SQLite returns naive datetimes → normalize).
    available_at = job.available_at
    if available_at.tzinfo is None:
        available_at = available_at.replace(tzinfo=UTC)
    assert available_at > utc_now()


def test_consumer_once_claims_and_processes(db_factory, monkeypatch):
    for i in range(3):
        _seed_job(db_factory, submission_id=f"sub-{i}")
    finalize = MagicMock()
    monkeypatch.setattr(
        "app.services.submission_service.finalize_intake_submission_background", finalize
    )
    monkeypatch.setattr(q, "_receipt_finalized", lambda _sid: True)
    out = q.run_intake_queue_consumer_once(worker_id="w1", batch_size=10)
    assert out == {"claimed": 3, "done": 3, "requeued": 0}
    assert finalize.call_count == 3
    assert all(j.status == "done" for j in _jobs(db_factory).values())


def test_consumer_once_counts_requeued(db_factory, monkeypatch):
    _seed_job(db_factory, submission_id="sub-1")
    monkeypatch.setattr(
        "app.services.submission_service.finalize_intake_submission_background", MagicMock()
    )
    monkeypatch.setattr(q, "_receipt_finalized", lambda _sid: False)
    out = q.run_intake_queue_consumer_once(worker_id="w1", batch_size=10)
    assert out == {"claimed": 1, "done": 0, "requeued": 1}


def test_prune_terminal_jobs(db_factory):
    old = utc_now() - timedelta(days=30)
    _seed_job(db_factory, submission_id="done-old", status="done")
    _seed_job(db_factory, submission_id="failed-old", status="failed")
    _seed_job(db_factory, submission_id="pending-now", status="pending")
    # Backdate the terminal rows' updated_at past the cutoff.
    db = db_factory()
    try:
        for sid in ("done-old", "failed-old"):
            row = next(j for j in db.scalars(select(IntakeQueueJob)).all() if j.submission_id == sid)
            row.updated_at = old
        db.commit()
    finally:
        db.close()

    deleted = q.prune_terminal_intake_jobs(older_than_days=14)
    assert deleted == 2
    remaining = set(_jobs(db_factory).keys())
    assert remaining == {"pending-now"}


def test_prune_disabled_when_zero(db_factory):
    _seed_job(db_factory, submission_id="done-old", status="done")
    assert q.prune_terminal_intake_jobs(older_than_days=0) == 0
    assert "done-old" in _jobs(db_factory)
