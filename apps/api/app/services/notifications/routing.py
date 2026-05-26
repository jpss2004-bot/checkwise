"""Phase 7 / Slice N2 — channel routing decision.

Pure function from (event severity × WhatsApp eligibility × user
preference × per-category mute × phone-verification state) to a
:class:`ChannelDecision`. No I/O, no DB reads — the dispatcher
gathers inputs once per recipient and asks routing for the answer.

Routing matrix (this is the canonical contract; the table in §2
of the Phase 7 plan is generated from this code):

    severity == "info"
        → in-app only. Email + WhatsApp always skipped with reason
          ``"info_tier"``. The info tier exists specifically so the
          notification bell stays trustworthy.

    severity == "important"
        → email fires iff ``contact_preference ∈ {"email", "both"}``
          AND the category is not email-muted.
        → WhatsApp fires iff the event is whatsapp-eligible AND
          ``contact_preference ∈ {"whatsapp", "both"}`` AND the user
          has a verified phone AND the category is not
          whatsapp-muted.

    severity == "critical"
        → email **always** fires. Preference is ignored; category
          mute is ignored. This is the compliance audit trail and
          cannot be turned off. Every user has an email address by
          virtue of being able to log in.
        → WhatsApp fires under the same rules as ``important`` —
          the user can mute critical WhatsApp via the category
          mute matrix, because WhatsApp is opt-in by Meta policy.

The in-app channel is always on for every severity. The catalog
guarantees ``info`` events are never marked ``whatsapp_eligible``
at import time, so the WhatsApp path is double-guarded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.notifications.catalog import EventDefinition

ContactPreference = Literal["email", "whatsapp", "both"]


# Canonical skip reasons — these are the strings the dispatcher
# writes into ``notification_dispatch.email_reason`` /
# ``whatsapp_reason`` at N4. Pinning them here means a UI surfacing
# "why didn't I get the email?" can localize off a stable enum
# rather than a free-form message.
SKIP_INFO_TIER = "info_tier"
SKIP_EVENT_NOT_ELIGIBLE = "event_not_eligible"
SKIP_PREFERENCE_EXCLUDES = "preference_excludes_channel"
SKIP_CATEGORY_MUTED = "category_muted"
SKIP_PHONE_NOT_VERIFIED = "phone_not_verified"


@dataclass(frozen=True)
class ChannelDecision:
    """Per-(envelope, recipient) channel selection.

    ``in_app`` is always ``True`` — the routing layer does not
    decide whether to write the in-app row; that is the
    dispatcher's invariant. The field exists on this dataclass for
    symmetry with the audit trail.
    """

    in_app: bool
    email: bool
    email_skip_reason: str | None
    whatsapp: bool
    whatsapp_skip_reason: str | None

    @property
    def any_outbound(self) -> bool:
        return self.email or self.whatsapp


def decide(
    *,
    event: EventDefinition,
    contact_preference: ContactPreference,
    has_verified_phone: bool,
    category_email_muted: bool,
    category_whatsapp_muted: bool,
) -> ChannelDecision:
    """Decide channels for one (event, recipient) pair.

    Caller is responsible for resolving ``contact_preference``,
    ``has_verified_phone``, and the two mute flags from the user
    row + ``user_notification_preferences``. This function is
    intentionally pure so the matrix can be exhaustively
    parametrized in tests.
    """
    # ---- info tier — bell only ---------------------------------
    if event.severity == "info":
        return ChannelDecision(
            in_app=True,
            email=False,
            email_skip_reason=SKIP_INFO_TIER,
            whatsapp=False,
            whatsapp_skip_reason=SKIP_INFO_TIER,
        )

    # ---- email decision ----------------------------------------
    if event.severity == "critical":
        # Compliance audit trail. Email is unmuteable; preference
        # is ignored. Every user has an email address by virtue of
        # being able to authenticate.
        email = True
        email_skip_reason: str | None = None
    else:
        # important
        if contact_preference == "whatsapp":
            email = False
            email_skip_reason = SKIP_PREFERENCE_EXCLUDES
        elif category_email_muted:
            email = False
            email_skip_reason = SKIP_CATEGORY_MUTED
        else:
            email = True
            email_skip_reason = None

    # ---- whatsapp decision -------------------------------------
    if not event.whatsapp_eligible:
        whatsapp = False
        whatsapp_skip_reason: str | None = SKIP_EVENT_NOT_ELIGIBLE
    elif contact_preference == "email":
        whatsapp = False
        whatsapp_skip_reason = SKIP_PREFERENCE_EXCLUDES
    elif not has_verified_phone:
        whatsapp = False
        whatsapp_skip_reason = SKIP_PHONE_NOT_VERIFIED
    elif category_whatsapp_muted:
        # WhatsApp mute applies to both critical and important —
        # Meta requires opt-in, so the user can always disable
        # their WhatsApp channel for a category.
        whatsapp = False
        whatsapp_skip_reason = SKIP_CATEGORY_MUTED
    else:
        whatsapp = True
        whatsapp_skip_reason = None

    return ChannelDecision(
        in_app=True,
        email=email,
        email_skip_reason=email_skip_reason,
        whatsapp=whatsapp,
        whatsapp_skip_reason=whatsapp_skip_reason,
    )
