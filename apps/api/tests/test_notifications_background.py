"""CW-DOS-002 — off-request notification fanout helpers."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import entities  # noqa: F401 — register mappers
from app.services.notifications import background as bg


@pytest.fixture
def session_factory(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(bg, "SessionLocal", factory)
    return factory


def test_missing_user_is_a_noop_and_never_raises(session_factory) -> None:
    # No user with this id exists → the helper must return cleanly.
    bg.emit_invitation_in_background(
        user_id="does-not-exist",
        invitation_token_id="t1",
        invitation_url="https://example.test/activate",
    )
    bg.emit_password_reset_in_background(
        user_id="does-not-exist",
        reset_token_id="t2",
        reset_url="https://example.test/reset",
    )


def test_missing_submission_is_a_noop_and_never_raises(session_factory) -> None:
    bg.emit_reviewer_decision_in_background(
        submission_id="does-not-exist", action="approve", reason=None
    )


def test_emit_failure_is_swallowed(session_factory, monkeypatch) -> None:
    """Even if the underlying emit raises, the helper must not propagate."""

    def _seed_user() -> str:
        from app.models import User
        from app.services.auth import hash_password

        db = session_factory()
        try:
            user = User(
                email="bg@checkwise.test",
                password_hash=hash_password("Correct horse battery 4"),
                full_name="BG User",
                status="active",
            )
            db.add(user)
            db.commit()
            return user.id
        finally:
            db.close()

    user_id = _seed_user()

    def _boom(*args, **kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(
        "app.services.notifications.emit_password_reset_requested", _boom
    )
    # Must not raise despite the emit blowing up.
    bg.emit_password_reset_in_background(
        user_id=user_id, reset_token_id="t", reset_url="https://example.test/r"
    )
