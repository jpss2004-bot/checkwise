from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# ``pool_pre_ping`` validates a connection before handing it out (catches
# Neon dropping an idle connection). ``pool_recycle`` proactively retires
# connections older than 30 min so we never sit on one past Neon's idle
# ceiling. Both are purely client-side (no wire-protocol / pgbouncer
# interaction), so they're safe against the pooled prod endpoint.
# NOTE (PERF-9): a server-side ``statement_timeout`` is still worth adding
# as a runaway-query backstop, but it must be delivered in a way Neon's
# pgbouncer transaction pooler accepts — see the audit report.
engine = create_engine(
    settings.sqlalchemy_url,
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
