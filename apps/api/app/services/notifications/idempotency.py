"""Phase 7 / Slice N1 — insert-first dedupe for the notification fabric.

Mirrors :class:`app.models.RenewalReminder`'s discipline: a single
unique-constraint violation is the entire dedupe mechanism. The
dispatcher calls :func:`claim`, which either succeeds and returns
the newly-created :class:`NotificationDispatch` row (proceed with
fan-out) or returns ``None`` (already dispatched, skip silently).

A SAVEPOINT (``db.begin_nested``) wraps the INSERT so the
IntegrityError on collision does not poison the outer transaction —
this is the same containment pattern used by
:mod:`app.services.renewal_dispatch`.

The caller still owns the outer commit. ``claim`` flushes inside
the nested transaction so the IntegrityError fires at flush time
and we can react to it deterministically.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import NotificationDispatch


def claim(
    db: Session,
    *,
    user_id: str,
    recipient_role: str,
    event_type: str,
    dedupe_key: str,
    severity: str,
    payload: Mapping[str, Any] | None = None,
) -> NotificationDispatch | None:
    """Reserve a dispatch slot for one recipient.

    Returns the inserted row when the slot was free (caller should
    proceed with channel fan-out). Returns ``None`` when a row with
    the same ``(user_id, event_type, dedupe_key)`` already exists
    (caller should skip silently).

    The row materializes ``severity`` and ``payload`` as immutable
    snapshots — subsequent slices append channel-attempt status to
    the SAME row rather than mutating these fields. That keeps the
    historical record of "what we tried to send" stable even if the
    catalog or templates evolve.
    """
    row = NotificationDispatch(
        user_id=user_id,
        recipient_role=recipient_role,
        event_type=event_type,
        dedupe_key=dedupe_key,
        severity=severity,
        payload=dict(payload) if payload is not None else None,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        # Collision on the unique constraint — another emitter (or a
        # cron replay) has already claimed this slot. Treat as a
        # successful no-op; the caller skips fan-out.
        return None
    return row
