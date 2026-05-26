"""Phase 7 / Slice N1 — dispatcher with idempotency claim.

Single entry point future slices fill in. At N1 the dispatcher:

    1. Validates the envelope against the catalog (defense-in-depth
       re-check; envelope construction also validates).
    2. For each recipient: attempts to claim a row in
       ``notification_dispatch`` via the insert-first dedupe pattern
       (:mod:`app.services.notifications.idempotency`). A claim
       collision short-circuits with status ``deduped`` — no audit
       row, no fan-out — so cron replays and concurrent emitters
       converge on a single send.
    3. On successful claim, writes one ``audit_log`` row with action
       ``notification.dispatch_attempted`` so the trazabilidad
       contract holds from day one.
    4. Returns a :class:`DispatchResult` summarising per-recipient
       decisions.

Channel fan-out (in-app row + email + WhatsApp) lands in Slice N4.
Until then, no production call site invokes this module — the
existing renewal/email/WhatsApp paths remain authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.orm import Session

from app.models import NotificationDispatch
from app.services.audit_log import add_audit_event
from app.services.notifications.envelope import NotificationEnvelope, Recipient
from app.services.notifications.idempotency import claim

DispatchStatus = Literal["queued", "deduped"]
DispatchMode = Literal["shadow", "active"]


@dataclass(frozen=True)
class PerRecipientOutcome:
    """Result for one (envelope, recipient) pair.

    ``dispatch_row`` is ``None`` only when ``status == "deduped"`` —
    a duplicate claim never materializes a row. Emitters use the
    row reference to write channel-attempt status (email_status,
    whatsapp_status, reasons) after running their fan-out without
    a second SELECT.
    """

    user_id: str
    role: str
    status: DispatchStatus
    dispatch_row: NotificationDispatch | None = None


@dataclass(frozen=True)
class DispatchResult:
    """Aggregate result returned to the emitter."""

    event_type: str
    dedupe_key: str
    outcomes: tuple[PerRecipientOutcome, ...] = field(default_factory=tuple)

    @property
    def queued(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "queued")

    @property
    def deduped(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "deduped")


def dispatch(
    db: Session,
    envelope: NotificationEnvelope,
    *,
    mode: DispatchMode = "shadow",
) -> DispatchResult:
    """Claim + record one dispatch attempt per recipient.

    ``mode="shadow"`` (default) — the historic behavior preserved
    for backward compatibility with all existing emitter tests.
    The dispatch row is written but no in-app, email, or messaging
    side effects occur. The caller (or a downstream shadow helper)
    stamps the ``would_send`` / ``would_skip`` status separately.

    ``mode="active"`` — the cutover mode. The dispatcher writes the
    in-app notification row (via
    :mod:`app.services.notifications.fanout`), sends email via
    ``send_transactional_email``, and sends SMS / WhatsApp via
    ``send_message``. Canonical statuses (``sent`` / ``skipped`` /
    ``failed``) land on the dispatch row.

    Caller owns the outer transaction commit. Each recipient's claim
    runs inside its own SAVEPOINT — a collision rolls back only that
    recipient's INSERT, not the entire envelope. This mirrors the
    Slice 6B renewal dispatcher.
    """
    definition = envelope.definition

    outcomes: list[PerRecipientOutcome] = []
    for recipient in envelope.recipients:
        claimed = claim(
            db,
            user_id=recipient.user_id,
            recipient_role=recipient.role,
            event_type=envelope.event_type,
            dedupe_key=envelope.dedupe_key,
            severity=definition.severity,
            payload=envelope.payload,
        )
        if claimed is None:
            outcomes.append(
                PerRecipientOutcome(
                    user_id=recipient.user_id,
                    role=recipient.role,
                    status="deduped",
                    dispatch_row=None,
                )
            )
            continue

        _record_attempt(
            db, envelope=envelope, recipient=recipient, mode=mode
        )

        if mode == "active":
            # Local import to keep the shadow path free of any
            # email / SMS / in-app coupling. Importing at call time
            # also keeps the test surface for shadow-only tests
            # stable — they never trigger the fanout module's deps.
            from app.services.notifications.fanout import fanout_channels

            fanout_channels(
                db,
                envelope=envelope,
                recipient=recipient,
                dispatch_row=claimed,
            )

        outcomes.append(
            PerRecipientOutcome(
                user_id=recipient.user_id,
                role=recipient.role,
                status="queued",
                dispatch_row=claimed,
            )
        )

    return DispatchResult(
        event_type=envelope.event_type,
        dedupe_key=envelope.dedupe_key,
        outcomes=tuple(outcomes),
    )


def _record_attempt(
    db: Session,
    *,
    envelope: NotificationEnvelope,
    recipient: Recipient,
    mode: DispatchMode = "shadow",
):
    definition = envelope.definition
    metadata = {
        "event_type": envelope.event_type,
        "dedupe_key": envelope.dedupe_key,
        "severity": definition.severity,
        "category": definition.category,
        "recipient_role": recipient.role,
        # ``phase`` carries the dispatcher mode so the audit trail
        # distinguishes shadow-era runs from cutover runs without
        # needing a join to a deploy log.
        "phase": (
            "cutover_active" if mode == "active" else "n1_idempotency"
        ),
        # ``payload`` is opaque to the dispatcher; we log the keys
        # only so PII does not land in audit_log by accident.
        "payload_keys": sorted(envelope.payload.keys()),
    }
    return add_audit_event(
        db,
        action="notification.dispatch_attempted",
        entity_type="user",
        entity_id=recipient.user_id,
        actor_type="system",
        metadata=metadata,
    )
