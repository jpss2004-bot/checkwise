"""Phase 7 / Slice N9b — notification_type → category derivation.

Pure function for emit-site convenience: legacy notification types
(``renewal_due_soon``, ``document_approve``, ``provider_uploaded``)
predate the Phase 7 catalog and don't carry a category. This helper
maps the prefixes the codebase actually uses today onto the
canonical Phase 7 vocabulary so emitters that don't yet thread an
explicit category still produce rows the new UX can filter.

Kept in lockstep with the backfill rules in migration
``0028_notification_category``. If you add a new notification_type
to a service, either:

  1. Set ``category=`` explicitly on the row at insert time, or
  2. Add a prefix here so the helper picks it up automatically.

Option 1 is preferred for any new emitter; option 2 is the
fallback for legacy paths the cutover slices will eventually
retire.
"""

from __future__ import annotations

from typing import Literal

NotificationCategory = Literal[
    "renewal",
    "reporting",
    "verification",
    "account",
    "admin",
    "other",
]


def derive_category(notification_type: str) -> NotificationCategory:
    """Map a legacy ``notification_type`` to a Phase 7 category."""
    if not notification_type:
        return "other"
    if notification_type.startswith("renewal"):
        return "renewal"
    if notification_type.startswith("reporting"):
        return "reporting"
    if (
        notification_type.startswith("document_")
        or notification_type.startswith("submission")
        or notification_type == "provider_uploaded"
        or notification_type == "metadata_ready"
    ):
        return "verification"
    if notification_type.startswith("account"):
        return "account"
    if (
        notification_type.startswith("admin")
        or notification_type.startswith("support")
    ):
        return "admin"
    return "other"
