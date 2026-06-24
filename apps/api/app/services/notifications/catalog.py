"""Phase 7 / Slice N0 — notification event catalog.

Single source of truth for every customer-visible notification event
in CheckWise. Adding a new notification path requires an entry here;
the dispatcher rejects any envelope whose ``event_type`` is not in
the catalog. The catalog is the contract that makes severity mistakes
detectable in tests instead of in production inboxes.

The five groups (A–E) below mirror §1 of the Phase 7 implementation
plan. Mutating any row should be a deliberate review-the-plan moment.

Severity — drives the routing matrix:

    * ``critical`` — actionable today. Fires every preferred channel.
      Email cannot be muted for ``critical`` events; that is the
      compliance audit trail.
    * ``important`` — actionable this week. Fires preferred channels,
      respects per-category mute.
    * ``info`` — informational only. In-app feed only — never email,
      never WhatsApp. This tier exists specifically so the bell badge
      stays trustworthy.

Category — drives the per-user mute matrix and groups events in the
notification center filter chips: ``renewal``, ``reporting``,
``verification``, ``account``, ``admin``.

Recipients — roles eligible to receive an event. The emitter
resolves each role to a concrete ``user_id`` at dispatch time. A
recipient role present on the catalog row but absent from the
envelope is silently skipped (e.g. a client_admin who has not been
assigned to a vendor yet).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

EventSeverity = Literal["critical", "important", "info"]
EventCategory = Literal[
    "renewal",
    "reporting",
    "verification",
    "account",
    "admin",
]
RecipientRole = Literal[
    "provider_owner",
    "client_admin",
    "platform_admin",
    "operations_admin",
    # Deprecated (transition only).
    "internal_admin",
    "invitee",
    "user",
]


@dataclass(frozen=True)
class EventDefinition:
    """One row in the notification catalog."""

    event_type: str
    severity: EventSeverity
    category: EventCategory
    recipients: tuple[RecipientRole, ...]
    description: str
    # ``True`` only when Meta has approved a WhatsApp template for
    # this event. ``info``-tier events are never WhatsApp-eligible
    # regardless of this flag; the dispatcher enforces that.
    whatsapp_eligible: bool = False


# Group A — Renewal lifecycle (REPSE expediente).
# Already shipped on the legacy ``renewal_dispatch`` path. The t-30
# and t-14 thresholds are intentionally demoted to ``info`` so the
# bell shows them but no email or WhatsApp fires — the "de-spam"
# decision documented in §10 of the Phase 7 plan.
_RENEWAL_EVENTS: tuple[EventDefinition, ...] = (
    EventDefinition(
        event_type="renewal.threshold.t-30",
        severity="info",
        category="renewal",
        recipients=("provider_owner", "client_admin"),
        description="30 días antes del vencimiento — bell-only nudge.",
    ),
    EventDefinition(
        event_type="renewal.threshold.t-14",
        severity="info",
        category="renewal",
        recipients=("provider_owner", "client_admin"),
        description="14 días antes del vencimiento — bell-only nudge.",
    ),
    EventDefinition(
        event_type="renewal.threshold.t-7",
        severity="important",
        category="renewal",
        recipients=("provider_owner", "client_admin"),
        description="7 días antes del vencimiento — first cross-channel ping.",
        whatsapp_eligible=True,
    ),
    EventDefinition(
        event_type="renewal.threshold.t-0",
        severity="critical",
        category="renewal",
        recipients=("provider_owner", "client_admin"),
        description="Día del vencimiento — vence hoy.",
        whatsapp_eligible=True,
    ),
    EventDefinition(
        event_type="renewal.threshold.t+7",
        severity="critical",
        category="renewal",
        recipients=("provider_owner", "client_admin"),
        description="7 días vencido.",
        whatsapp_eligible=True,
    ),
    EventDefinition(
        event_type="renewal.threshold.t+14",
        severity="critical",
        category="renewal",
        recipients=("provider_owner", "client_admin"),
        description="14 días vencido.",
        whatsapp_eligible=True,
    ),
    EventDefinition(
        event_type="renewal.threshold.t+21",
        severity="critical",
        category="renewal",
        recipients=("provider_owner", "client_admin"),
        description="21 días vencido.",
        whatsapp_eligible=True,
    ),
    EventDefinition(
        event_type="renewal.threshold.t+28",
        severity="critical",
        category="renewal",
        recipients=("provider_owner", "client_admin"),
        description="28 días vencido — terminal threshold; row stays red until reupload.",
        whatsapp_eligible=True,
    ),
)

# Group B — Periodic institutional reporting (NEW in Phase 7).
# Recipients differ from renewal: client_admin only joins on the
# red tier (t-0 onward) so they are not nagged for every provider's
# monthly IMSS upload window.
_REPORTING_EVENTS: tuple[EventDefinition, ...] = (
    EventDefinition(
        event_type="reporting.window.opened",
        severity="important",
        category="reporting",
        recipients=("provider_owner",),
        description="Ventana de reporte abierta para el periodo.",
        whatsapp_eligible=True,
    ),
    EventDefinition(
        event_type="reporting.due.t-7",
        severity="important",
        category="reporting",
        recipients=("provider_owner",),
        description="7 días antes del cierre de la ventana de reporte.",
        whatsapp_eligible=True,
    ),
    EventDefinition(
        event_type="reporting.due.t-1",
        severity="critical",
        category="reporting",
        recipients=("provider_owner",),
        description="1 día antes del cierre — última oportunidad limpia.",
        whatsapp_eligible=True,
    ),
    EventDefinition(
        event_type="reporting.due.t-0",
        severity="critical",
        category="reporting",
        recipients=("provider_owner", "client_admin"),
        description="Día de cierre de la ventana de reporte.",
        whatsapp_eligible=True,
    ),
    EventDefinition(
        event_type="reporting.overdue.t+3",
        severity="critical",
        category="reporting",
        recipients=("provider_owner", "client_admin"),
        description="3 días vencido el reporte periódico — terminal threshold.",
        whatsapp_eligible=True,
    ),
)

# Group C — Verification lifecycle.
# ``submission.received`` is intentionally ``info`` — the provider
# already saw the UI confirmation; we don't need to email them about
# their own upload. Approved is ``important`` so it closes the loop
# without burning a critical-slot. Rejected/clarification are red
# because action is required.
_VERIFICATION_EVENTS: tuple[EventDefinition, ...] = (
    EventDefinition(
        event_type="submission.received",
        severity="info",
        category="verification",
        recipients=("provider_owner",),
        description="Documento recibido y encolado para revisión.",
    ),
    EventDefinition(
        event_type="submission.in_review",
        severity="info",
        category="verification",
        recipients=("provider_owner",),
        description="Un revisor de Legal Shelf tomó el documento.",
    ),
    EventDefinition(
        event_type="submission.approved",
        severity="important",
        category="verification",
        recipients=("provider_owner", "client_admin"),
        description="Documento aprobado por Legal Shelf.",
        whatsapp_eligible=True,
    ),
    EventDefinition(
        event_type="submission.rejected",
        severity="critical",
        category="verification",
        recipients=("provider_owner",),
        description="Documento rechazado — se requiere reenvío.",
        whatsapp_eligible=True,
    ),
    EventDefinition(
        event_type="submission.clarification_requested",
        severity="critical",
        category="verification",
        recipients=("provider_owner",),
        description="El revisor necesita información adicional.",
        whatsapp_eligible=True,
    ),
)

# Group D — Account & onboarding.
# Invitations and password resets are critical: the user literally
# cannot proceed without the email/WhatsApp landing. Welcome is
# important so the user notices the channel preference confirmation.
_ACCOUNT_EVENTS: tuple[EventDefinition, ...] = (
    EventDefinition(
        event_type="account.invitation_sent",
        severity="critical",
        category="account",
        recipients=("invitee",),
        description="Invitación inicial a la plataforma (single-use link).",
        whatsapp_eligible=True,
    ),
    EventDefinition(
        event_type="account.welcome",
        severity="important",
        category="account",
        recipients=("user",),
        description="Bienvenida tras el primer login post-invitación.",
    ),
    EventDefinition(
        event_type="account.password_reset_requested",
        severity="critical",
        category="account",
        recipients=("user",),
        description="Token de restablecimiento de contraseña (single-use).",
    ),
    EventDefinition(
        event_type="account.channel_preference_changed",
        severity="info",
        category="account",
        recipients=("user",),
        description="Confirmación de cambio de preferencia de canal.",
    ),
    EventDefinition(
        event_type="account.whatsapp_verified",
        severity="info",
        category="account",
        recipients=("user",),
        description="Número de WhatsApp verificado vía OTP.",
    ),
)

# Group E — Admin & support. WhatsApp is never eligible for this
# group: internal staff should not be paged on personal WhatsApp by
# the platform.
_ADMIN_EVENTS: tuple[EventDefinition, ...] = (
    EventDefinition(
        event_type="support.ticket_opened",
        severity="important",
        category="admin",
        recipients=("platform_admin",),
        description="Nuevo ticket de soporte/feedback con severidad ≥ media.",
    ),
    EventDefinition(
        event_type="admin.workspace_at_risk",
        severity="important",
        category="admin",
        recipients=("platform_admin",),
        description="Un workspace acumula ≥3 items rojos sin movimiento reciente.",
    ),
    EventDefinition(
        event_type="admin.cron_health",
        severity="info",
        category="admin",
        recipients=("platform_admin",),
        description="Resumen diario de salud de los crons de notificación.",
    ),
)


def _build_catalog() -> Mapping[str, EventDefinition]:
    rows: list[EventDefinition] = [
        *_RENEWAL_EVENTS,
        *_REPORTING_EVENTS,
        *_VERIFICATION_EVENTS,
        *_ACCOUNT_EVENTS,
        *_ADMIN_EVENTS,
    ]
    seen: dict[str, EventDefinition] = {}
    for row in rows:
        if row.event_type in seen:
            raise RuntimeError(
                f"Duplicate event_type in catalog: {row.event_type!r}"
            )
        # ``info`` events are never eligible for outbound channels;
        # an info-tier row with whatsapp_eligible=True is almost
        # certainly a copy-paste mistake. Fail loud at import time.
        if row.severity == "info" and row.whatsapp_eligible:
            raise RuntimeError(
                f"Catalog row {row.event_type!r} is info-tier but "
                "whatsapp_eligible=True; info events are in-app only."
            )
        if not row.recipients:
            raise RuntimeError(
                f"Catalog row {row.event_type!r} has no recipients."
            )
        seen[row.event_type] = row
    return MappingProxyType(seen)


CATALOG: Mapping[str, EventDefinition] = _build_catalog()
EVENT_TYPES: frozenset[str] = frozenset(CATALOG.keys())


def get_event(event_type: str) -> EventDefinition:
    """Return the catalog row for ``event_type`` or raise ``KeyError``.

    Use this — never index ``CATALOG`` directly — so the error path
    is consistent everywhere a dispatch attempt fails validation.
    """
    try:
        return CATALOG[event_type]
    except KeyError as exc:
        raise KeyError(
            f"Unknown notification event_type: {event_type!r}. "
            "Add it to app.services.notifications.catalog before dispatching."
        ) from exc
