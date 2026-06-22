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

    @field_validator("name", "message")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        # Required fields: trim, and reject whitespace-only with a 422
        # (returning None here would null a NOT NULL column → 500 on the
        # public form). field_validator runs AFTER min_length, so the
        # trimmed-empty case must be re-checked here.
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank")
        return trimmed

    @field_validator("company", "role")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        # Optional fields: whitespace-only collapses to None (column is
        # nullable), the original intent.
        if value is None:
            return value
        return value.strip() or None

    @field_validator("source")
    @classmethod
    def _strip_source(cls, value: str) -> str:
        # Required-with-default: fall back to the default rather than null.
        return value.strip() or "landing"

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
