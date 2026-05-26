"""Phase 7 — unified notification fabric.

This package is the single dispatch path for every customer-visible
notification event in CheckWise. It is introduced in additive slices:

  * N0 (this slice) — catalog + envelope + dispatcher skeleton that
    only writes audit rows; no in-app, no email, no WhatsApp.
  * N1 — ``notification_dispatch`` idempotency anchor.
  * N2 — severity × preference × mute routing matrix.
  * N3 — versioned templates.
  * N4–N7 — emitters migrate onto the fabric one class at a time.

Nothing in production calls into this package at N0. The existing
``renewal_dispatch`` + ``transactional_email`` + ``transactional_whatsapp``
paths stay authoritative until N4 flips the renewal emitter over.
"""

from __future__ import annotations

from app.services.notifications.catalog import (
    CATALOG,
    EVENT_TYPES,
    EventCategory,
    EventDefinition,
    EventSeverity,
    RecipientRole,
    get_event,
)
from app.services.notifications.dispatcher import (
    DispatchResult,
    PerRecipientOutcome,
    dispatch,
)
from app.services.notifications.emitters.account import (
    emit_channel_preference_changed,
    emit_invitation_sent,
    emit_password_reset_requested,
    emit_welcome,
    emit_whatsapp_verified,
)
from app.services.notifications.emitters.admin import (
    emit_cron_health,
    emit_support_ticket_opened,
    emit_workspace_at_risk,
)
from app.services.notifications.emitters.renewal import (
    THRESHOLD_TO_EVENT_TYPE,
    EmitOutcome,
    emit_renewals_for_workspace,
)
from app.services.notifications.emitters.reporting import (
    REPORTING_THRESHOLD_TO_EVENT,
    ReportingEmitOutcome,
    emit_reporting_for_workspace,
    reporting_thresholds_crossed,
)
from app.services.notifications.emitters.verification import (
    REVIEWER_ACTION_EVENT_TYPE,
    emit_reviewer_decision,
    emit_submission_in_review,
    emit_submission_received,
)
from app.services.notifications.envelope import (
    NotificationEnvelope,
    Recipient,
)
from app.services.notifications.idempotency import claim
from app.services.notifications.rendering import (
    Channel,
    MissingTemplateVariable,
    RenderedTemplate,
    render,
)
from app.services.notifications.routing import (
    SKIP_CATEGORY_MUTED,
    SKIP_EVENT_NOT_ELIGIBLE,
    SKIP_INFO_TIER,
    SKIP_PHONE_NOT_VERIFIED,
    SKIP_PREFERENCE_EXCLUDES,
    ChannelDecision,
    ContactPreference,
    decide,
)

__all__ = [
    "CATALOG",
    "EVENT_TYPES",
    "EventCategory",
    "EventDefinition",
    "EventSeverity",
    "RecipientRole",
    "get_event",
    "DispatchResult",
    "PerRecipientOutcome",
    "dispatch",
    "NotificationEnvelope",
    "Recipient",
    "claim",
    "ChannelDecision",
    "ContactPreference",
    "decide",
    "SKIP_CATEGORY_MUTED",
    "SKIP_EVENT_NOT_ELIGIBLE",
    "SKIP_INFO_TIER",
    "SKIP_PHONE_NOT_VERIFIED",
    "SKIP_PREFERENCE_EXCLUDES",
    "Channel",
    "MissingTemplateVariable",
    "RenderedTemplate",
    "render",
    "EmitOutcome",
    "THRESHOLD_TO_EVENT_TYPE",
    "emit_renewals_for_workspace",
    "REVIEWER_ACTION_EVENT_TYPE",
    "emit_reviewer_decision",
    "emit_submission_in_review",
    "emit_submission_received",
    "REPORTING_THRESHOLD_TO_EVENT",
    "ReportingEmitOutcome",
    "emit_reporting_for_workspace",
    "reporting_thresholds_crossed",
    "emit_channel_preference_changed",
    "emit_invitation_sent",
    "emit_password_reset_requested",
    "emit_welcome",
    "emit_whatsapp_verified",
    "emit_cron_health",
    "emit_support_ticket_opened",
    "emit_workspace_at_risk",
]
