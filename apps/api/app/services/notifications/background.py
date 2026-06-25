"""Off-request notification fanout (CW-DOS-002).

In ``active`` dispatch mode the notification emit performs blocking SMTP /
SMS / WhatsApp sends (12–15 s timeouts) inline. When that emit is triggered
from a request handler (password reset, invitation, reviewer decision) the
request inherits that latency and the worker is occupied for the duration of
a slow/failing provider call.

These helpers move the emit off the request's critical path: the handler
schedules one as a FastAPI ``BackgroundTask`` (runs after the response is
sent) and the task owns a FRESH ``SessionLocal()`` — exactly like
``reports._run_report_export_with_fresh_session``. Because a background task
runs after ``get_db`` has torn down the request session, the entities are
re-loaded BY ID here rather than handed across sessions (which would raise
``DetachedInstanceError`` / contaminate sessions).

Each helper is best-effort: a failure is logged and swallowed so a provider
outage can never surface as an error to the user (the legacy transactional
email path already delivered the user-visible message for these flows).
"""

from __future__ import annotations

import logging

from app.db.session import SessionLocal
from app.models import Submission, User

log = logging.getLogger("checkwise.notifications.background")


def emit_password_reset_in_background(
    *, user_id: str, reset_token_id: str, reset_url: str
) -> None:
    """Off-request ``account.password_reset_requested`` fanout."""
    from app.services.notifications import emit_password_reset_requested

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return
        emit_password_reset_requested(
            db,
            user=user,
            reset_token_id=reset_token_id,
            reset_url=reset_url,
            mode="active",
        )
        db.commit()
    except Exception:  # noqa: BLE001 — best-effort; never surface to the user
        log.exception("notif_bg_failed event=account.password_reset_requested")
        db.rollback()
    finally:
        db.close()


def emit_invitation_in_background(
    *, user_id: str, invitation_token_id: str, invitation_url: str
) -> None:
    """Off-request ``account.invitation_sent`` fanout."""
    from app.services.notifications import emit_invitation_sent

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return
        emit_invitation_sent(
            db,
            user=user,
            invitation_token_id=invitation_token_id,
            invitation_url=invitation_url,
            mode="active",
        )
        db.commit()
    except Exception:  # noqa: BLE001 — best-effort
        log.exception("notif_bg_failed event=account.invitation_sent")
        db.rollback()
    finally:
        db.close()


def emit_reviewer_decision_in_background(
    *, submission_id: str, action: str, reason: str | None
) -> None:
    """Off-request reviewer-decision fanout.

    The emit claims its own ``notification_dispatch`` idempotency row and
    commits it on this fresh session — the dedupe is INSERT-first so a retry
    against the same submission+action remains a no-op even though the claim
    now lands just after the response instead of inside the request txn.
    """
    from app.services.notifications import emit_reviewer_decision

    db = SessionLocal()
    try:
        submission = db.get(Submission, submission_id)
        if submission is None:
            return
        emit_reviewer_decision(
            db,
            submission=submission,
            action=action,
            reason=reason,
            mode="active",
        )
        db.commit()
    except Exception:  # noqa: BLE001 — best-effort
        log.exception("notif_bg_failed event=submission.reviewer_decision")
        db.rollback()
    finally:
        db.close()
