"""Phase 7 / Slice N3 — template lookup + ``{{var}}`` substitution.

Looks up the active :class:`NotificationTemplateVersion` row for
``(event_type, channel, locale)`` and renders it against the envelope
payload. The substitution is intentionally simple — a regex-driven
``{{var}}`` replace — so the table can be edited by hand from an
admin UI without invoking a templating engine.

Contract:

  * :func:`render` returns ``None`` when no active row exists. The
    caller falls back to the in-code builder
    (:mod:`app.services.email_templates`,
    :mod:`app.services.whatsapp_templates`) or skips the channel.
    At N3 the dispatcher does not yet call render — the existing
    transactional paths remain authoritative until Slice N4.
  * A missing payload key raises :class:`MissingTemplateVariable`.
    We fail loud rather than silently emit ``{{vendor_name}}`` text
    on the wire.
  * Extra payload keys are ignored — payload is permitted to carry
    audit/dispatch context the template happens not to reference.
  * Locale defaults to ``es-MX``; passing other values is supported
    for future i18n.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NotificationTemplateVersion

Channel = Literal["email", "whatsapp", "inapp"]

# ``{{var}}`` with surrounding whitespace tolerated. Captures the
# bare variable name. Compiled at module load.
_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class MissingTemplateVariable(KeyError):
    """Payload omitted a variable the template references.

    Subclasses ``KeyError`` so callers can write the same
    except-clause they would for a dict lookup, but the dedicated
    type lets the dispatcher (in Slice N4) record a structured
    failure reason without string-matching the message.
    """


@dataclass(frozen=True)
class RenderedTemplate:
    """Output of one render pass."""

    subject: str | None
    body: str
    meta_template_name: str | None
    version: int
    template_id: str


def render(
    db: Session,
    *,
    event_type: str,
    channel: Channel,
    payload: Mapping[str, Any],
    locale: str = "es-MX",
) -> RenderedTemplate | None:
    """Render the active template for ``(event_type, channel, locale)``.

    Returns ``None`` when no active row exists. The caller decides
    whether to fall back to an in-code builder or skip the channel.
    """
    row = db.execute(
        select(NotificationTemplateVersion).where(
            NotificationTemplateVersion.event_type == event_type,
            NotificationTemplateVersion.channel == channel,
            NotificationTemplateVersion.locale == locale,
            NotificationTemplateVersion.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if row is None:
        return None

    return RenderedTemplate(
        subject=_substitute(row.subject, payload) if row.subject else None,
        body=_substitute(row.body, payload),
        meta_template_name=row.meta_template_name,
        version=row.version,
        template_id=row.id,
    )


def _substitute(template: str, payload: Mapping[str, Any]) -> str:
    """Replace every ``{{var}}`` token. Raise on missing key."""

    def _repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in payload:
            raise MissingTemplateVariable(
                f"Template references {{{{{name}}}}} but payload does not "
                f"contain key {name!r}."
            )
        value = payload[name]
        # str() handles dates, ints, None — callers should pre-format
        # locale-sensitive values (dates) before they hit the template.
        return str(value)

    return _VAR_RE.sub(_repl, template)
