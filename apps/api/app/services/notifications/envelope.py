"""Phase 7 / Slice N0 — dispatch envelope.

A :class:`NotificationEnvelope` is the unit the dispatcher operates
on. It ties one catalog event to a concrete dedupe key, a recipient
set, and the payload values the template will render.

Construction validates against the catalog: an unknown
``event_type`` or an empty recipient set raises immediately, so
broken emitters fail in tests rather than producing silent gaps in
the audit log.

Dedupe key conventions (informational — the dispatcher only cares
that two envelopes with the same key collide):

    * renewal events       — ``"workspace:{id}:req:{code}:cycle:{anchor}:t:{threshold}"``
    * reporting events     — ``"workspace:{id}:req:{id}:period:{key}:t:{threshold}"``
    * verification events  — ``"submission:{id}:{event_suffix}"``
    * account events       — ``"user:{id}:{event_suffix}"`` (one-shot per cause)
    * admin events         — ``"{cause_specific}"``
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.services.notifications.catalog import (
    EventDefinition,
    RecipientRole,
    get_event,
)


@dataclass(frozen=True)
class Recipient:
    """One concrete addressee for a dispatch attempt.

    ``user_id`` is the canonical identity. ``role`` matches the
    catalog row's recipient list and lets the dispatcher honor any
    role-specific behavior (e.g. internal_admin never gets WhatsApp
    regardless of the user's contact_preference).
    """

    user_id: str
    role: RecipientRole


@dataclass(frozen=True)
class NotificationEnvelope:
    """Immutable description of one dispatch attempt.

    The envelope is what an emitter hands to the dispatcher. It is
    self-contained: anything the dispatcher, renderer, or audit log
    needs lives on this object so the emitter does not need to be
    re-invoked.
    """

    event_type: str
    dedupe_key: str
    recipients: tuple[Recipient, ...]
    payload: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def __post_init__(self) -> None:
        # ``get_event`` raises a domain-specific KeyError; we want a
        # ValueError surface for envelope-construction failures so
        # callers can distinguish "unknown event" (their bug) from
        # "user not found" (their input).
        try:
            definition = get_event(self.event_type)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc

        if not self.recipients:
            raise ValueError(
                f"NotificationEnvelope for {self.event_type!r} has no recipients."
            )

        if not self.dedupe_key:
            raise ValueError(
                f"NotificationEnvelope for {self.event_type!r} has empty dedupe_key."
            )

        allowed_roles = set(definition.recipients)
        for recipient in self.recipients:
            if recipient.role not in allowed_roles:
                raise ValueError(
                    f"Recipient role {recipient.role!r} is not allowed for "
                    f"event {self.event_type!r}. Catalog allows: "
                    f"{sorted(allowed_roles)}."
                )

        seen: set[str] = set()
        for recipient in self.recipients:
            if recipient.user_id in seen:
                raise ValueError(
                    f"NotificationEnvelope for {self.event_type!r} lists "
                    f"user_id {recipient.user_id!r} more than once."
                )
            seen.add(recipient.user_id)

    @property
    def definition(self) -> EventDefinition:
        """Catalog row for this envelope's event_type."""
        return get_event(self.event_type)
