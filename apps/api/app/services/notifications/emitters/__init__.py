"""Phase 7 — emitter modules.

Each emitter walks a domain-specific source (the renewal-bearing
expediente requirements, the periodic-reporting calendar, the
reviewer decision endpoints, ...) and translates state changes
into :class:`NotificationEnvelope` instances that flow through the
unified dispatcher.

Emitters never write notifications, emails, or WhatsApp messages
directly. They build envelopes; the dispatcher claims idempotency,
records audit, and (post-N4b) drives channel fan-out.
"""

from __future__ import annotations
