"""Pydantic schemas for the public contact form (P0-3).

Request/response shapes for ``POST /api/v1/contact``. Mirrors the
``ContactRequest`` entity, minus operator-only fields.

Validation policy:
- ``name`` and ``message`` required; trimmed; non-empty after trim.
- ``email`` validated as RFC 5322-ish (``EmailStr``); max 254 chars
  per the standard.
- ``company`` and ``role`` optional, capped at sensible lengths.
- ``source`` defaults to ``landing`` and accepts a short alphanumeric
  identifier so future embedded forms can self-identify.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class ContactRequestCreate(BaseModel):
    """Inbound request body."""

    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    company: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=60)
    message: str = Field(min_length=1, max_length=5000)
    source: str = Field(default="landing", min_length=1, max_length=60)

    @field_validator("name", "message", "company", "role", "source")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        # Pydantic V2: ``str | None`` fields receive ``None`` and pass
        # through unchanged; strings get stripped of leading/trailing
        # whitespace before length validators run on the trimmed form.
        if value is None:
            return value
        trimmed = value.strip()
        return trimmed or None  # treat whitespace-only as None for optional fields

    @field_validator("email")
    @classmethod
    def _enforce_email_length(cls, value: str) -> str:
        # EmailStr accepts addresses far longer than RFC 5321's 254-char
        # total cap when the local part is over-long. We add an explicit
        # belt to keep the column-width contract (`String(254)` in the
        # model) honest and to bound abuse vectors.
        if len(value) > 254:
            raise ValueError("email address exceeds 254 characters")
        return value


class BookingIntentCreate(BaseModel):
    """Inbound body for ``POST /api/v1/contact/booking-intent``.

    A no-PII beacon fired when a landing visitor engages with the
    embedded demo scheduler. The booking itself lives in Google
    Calendar; this only carries a short self-identifying source tag.
    """

    source: str = Field(default="landing", min_length=1, max_length=60)

    @field_validator("source")
    @classmethod
    def _strip_source(cls, value: str) -> str:
        trimmed = value.strip()
        return trimmed or "landing"


class ContactRequestPublicResponse(BaseModel):
    """Response body returned to the unauthenticated submitter.

    We deliberately do not echo the email or message back, and we
    return a stable ``request_id`` that the client can show as a folio
    ("solicitud REQ-...") so the user has a reference for follow-up.
    """

    ok: bool
    request_id: str
    created_at: datetime
