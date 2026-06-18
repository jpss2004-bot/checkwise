from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# ``pool_pre_ping`` validates a connection before handing it out (catches
# Neon dropping an idle connection). ``pool_recycle`` proactively retires
# connections older than 30 min so we never sit on one past Neon's idle
# ceiling. Both are purely client-side (no wire-protocol / pgbouncer
# interaction), so they're safe against the pooled prod endpoint.
_engine_kwargs: dict[str, object] = {
    "pool_pre_ping": True,
    "pool_recycle": 1800,
}
# B-PERF-10 — QueuePool sizing for the server-backed (Postgres) engine. The
# SQLAlchemy default (pool_size=5 + max_overflow=10 = 15) sits below the
# ~40-thread sync threadpool of a single uvicorn worker, so under modest
# concurrency requests queue waiting for a pooled connection — tail latency
# that reads as "the database is slow" when it is really pool starvation
# (worsened by the sync handlers that hold a connection while doing the LLM /
# PDF / large-list work). Size it up, tunable via env and kept under Neon's
# connection ceiling (mind pgbouncer). SQLite (tests / local) uses its own
# pool and ignores these knobs, so only set them for Postgres.
if settings.sqlalchemy_url.startswith("postgresql"):
    _engine_kwargs["pool_size"] = int(os.environ.get("DB_POOL_SIZE", "10"))
    _engine_kwargs["max_overflow"] = int(
        os.environ.get("DB_POOL_MAX_OVERFLOW", "20")
    )
engine = create_engine(settings.sqlalchemy_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# PERF-9 — runaway-query / lock-wait backstop. Without these, a statement
# that blocks on a lock or runs away hangs the request *forever*: the
# connection never returns, the client spins, and uvicorn never logs the
# request (the access line is only emitted on response). That is exactly
# the failure mode behind the "reports section spinner never resolves"
# incident. We deliver the timeouts per-transaction with ``SET LOCAL`` from
# an ``after_begin`` hook so they survive Neon's pgbouncer *transaction*
# pooler (a ``SET SESSION`` on connect would not stick across the pooler's
# server-connection multiplexing). Tunable via env; ``0`` disables either
# backstop. Postgres-only so the SQLite test engine is untouched.
_STATEMENT_TIMEOUT_MS = int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "30000"))
_LOCK_TIMEOUT_MS = int(os.environ.get("DB_LOCK_TIMEOUT_MS", "10000"))


@event.listens_for(SessionLocal, "after_begin")
def _apply_query_timeouts(session, transaction, connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    if _STATEMENT_TIMEOUT_MS > 0:
        connection.exec_driver_sql(
            f"SET LOCAL statement_timeout = {_STATEMENT_TIMEOUT_MS}"
        )
    if _LOCK_TIMEOUT_MS > 0:
        connection.exec_driver_sql(f"SET LOCAL lock_timeout = {_LOCK_TIMEOUT_MS}")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
