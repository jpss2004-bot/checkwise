"""Phone-verification OTP storage.

Phase 7 / Slice N8 — short-lived OTP records for the WhatsApp
verification flow. The User can have multiple historical rows (a
re-issue after the prior code expires), but at any moment at most
one is "active": ``consumed_at IS NULL AND expires_at > now()``.

Why hash the code rather than store it plaintext:

    OTPs are sent out-of-band via WhatsApp. The plaintext value
    only lives in the user's phone screen and in the request body
    when they confirm — it never goes back to disk. A database
    dump must not give an attacker usable OTPs.

The ``code_hash`` column stores ``HMAC-SHA256(AUTH_JWT_SECRET,
plaintext_code)`` — see ``app.services.phone_verification.hash_otp_code``.
Key-stretching via a server secret (rather than a per-row salt)
keeps the column fixed-width and constant-time to verify; the
attempts counter is the real brute-force guard.

Revision ID: 0027_phone_verifications
Revises: 0026_notification_template_versions
Create Date: 2026-05-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0027_phone_verifications"
down_revision = "0026_notification_template_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "phone_verifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # E.164 without the leading ``+`` — matches the format
        # ``whatsapp_delivery.normalize_phone_e164`` returns and the
        # value ``User.phone_e164`` stores on confirmation.
        sa.Column("phone_e164", sa.String(length=20), nullable=False),
        # HMAC-SHA256 of the plaintext code under AUTH_JWT_SECRET.
        # Fixed 64 hex chars; never the plaintext.
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        # Non-null after a successful confirm. ``consumed_at`` +
        # ``expires_at`` together encode whether the row is active.
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        # Failed-code counter for brute-force defense. Capped at 5
        # at the application layer; reaching the cap auto-invalidates
        # the row (callers see the same 400 as an expired code).
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_phone_verifications_user_created",
        "phone_verifications",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_phone_verifications_user_created",
        table_name="phone_verifications",
    )
    op.drop_table("phone_verifications")
