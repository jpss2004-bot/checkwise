"""Phase 7 / Slice N7 — admin / operations emitter (shadow mode).

Three admin events surface internal-only signals to LegalShelf's
operators:

  * ``support.ticket_opened``     — important. Mirror of the
                                    existing Slack notification path
                                    in the in-app bell + email
                                    inbox; one envelope per ticket.
  * ``admin.workspace_at_risk``   — important. Daily aggregation:
                                    workspaces with ≥3 red items
                                    without movement. Dedupe key is
                                    ``workspace:{id}:at_risk:{date}``
                                    so the same risk state never
                                    fires twice in one day.
  * ``admin.cron_health``         — info. Daily summary of cron
                                    successes / failures. In-app
                                    only; never email or WhatsApp.

Admin events fan out to **every** active ``internal_admin`` User —
an alert that one operator misses must reach the others. WhatsApp
is never eligible at the catalog level for this group (internal
staff are not paged on personal WhatsApp by the platform).

Shadow mode (same as N4–N6 + N5): writes ``notification_dispatch``
+ ``audit_log`` only.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.services.notifications.catalog import get_event
from app.services.notifications.dispatcher import (
    DispatchMode,
    DispatchResult,
    dispatch,
)
from app.services.notifications.emitters._helpers import (
    record_shadow_channels,
    resolve_internal_admins,
)
from app.services.notifications.envelope import (
    NotificationEnvelope,
    Recipient,
)


def emit_support_ticket_opened(
    db: Session,
    *,
    ticket_id: str,
    summary: str,
    category: str,
    actor_email: str | None = None,
    mode: DispatchMode = "shadow",
) -> DispatchResult | None:
    """Fire ``support.ticket_opened`` to every active internal_admin.

    ``ticket_id`` is the entire dedupe key — one envelope per
    ticket, idempotent on every retry. The dispatch row's
    ``payload`` carries summary + category for the in-app card.
    """
    return _emit_to_internal_admins(
        db,
        event_type="support.ticket_opened",
        dedupe_key=f"support:ticket:{ticket_id}",
        payload={
            "ticket_id": ticket_id,
            "summary": summary,
            "category": category,
            "actor_email": actor_email or "",
        },
        mode=mode,
    )


def emit_workspace_at_risk(
    db: Session,
    *,
    workspace_id: str,
    workspace_label: str,
    red_count: int,
    on_date: date,
    mode: DispatchMode = "shadow",
) -> DispatchResult | None:
    """Fire ``admin.workspace_at_risk`` for a workspace accumulating reds.

    ``on_date`` makes the dedupe per-day, so the daily risk pass can
    re-emit when state worsens tomorrow but never spams within the
    same day. Callers compute ``red_count`` themselves; this emitter
    does not query workspace state — keeping it pure.
    """
    return _emit_to_internal_admins(
        db,
        event_type="admin.workspace_at_risk",
        dedupe_key=(
            f"workspace:{workspace_id}:at_risk:{on_date.isoformat()}"
        ),
        payload={
            "workspace_id": workspace_id,
            "workspace_label": workspace_label,
            "red_count": red_count,
            "on_date": on_date.isoformat(),
        },
        mode=mode,
    )


def emit_cron_health(
    db: Session,
    *,
    cron_name: str,
    on_date: date,
    dispatched_count: int,
    error_count: int,
    duration_seconds: float | None = None,
    mode: DispatchMode = "shadow",
) -> DispatchResult | None:
    """Fire ``admin.cron_health`` once per cron per day.

    Info-tier — in-app only. The daily summary is best-effort
    operational visibility, not an alert. PagerDuty / Slack pages
    remain the path for actual failures.
    """
    return _emit_to_internal_admins(
        db,
        event_type="admin.cron_health",
        dedupe_key=f"cron:{cron_name}:{on_date.isoformat()}",
        payload={
            "cron_name": cron_name,
            "on_date": on_date.isoformat(),
            "dispatched_count": dispatched_count,
            "error_count": error_count,
            "duration_seconds": duration_seconds,
        },
        mode=mode,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _emit_to_internal_admins(
    db: Session,
    *,
    event_type: str,
    dedupe_key: str,
    payload: dict,
    mode: DispatchMode = "shadow",
) -> DispatchResult | None:
    """Build envelope to every active internal_admin and dispatch.

    Returns ``None`` when there are no resolvable admins — the
    envelope contract requires at least one recipient. In practice
    a CheckWise deployment without an internal_admin is a setup
    bug; this guard just keeps the emitter graceful in dev.
    """
    event = get_event(event_type)
    admins = resolve_internal_admins(db)
    if not admins:
        return None

    envelope = NotificationEnvelope(
        event_type=event_type,
        dedupe_key=dedupe_key,
        recipients=tuple(
            Recipient(user_id=u.id, role="internal_admin") for u in admins
        ),
        payload=payload,
    )
    result = dispatch(db, envelope, mode=mode)
    if mode == "shadow":
        for outcome in result.outcomes:
            if outcome.status == "deduped":
                continue
            record_shadow_channels(db, outcome=outcome, event=event)
    return result
