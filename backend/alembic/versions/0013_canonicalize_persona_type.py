"""Canonicalize persona_type values + add CHECK constraint.

Revision ID: 0013_canonicalize_persona_type
Revises: 0012_password_reset_tokens
Create Date: 2026-05-21

Closes the durable side of the Jay Luna empty-calendar bug
(commit f28ae44). The read-time ``normalize_persona_type`` helper
maps legacy values like ``"persona_moral"`` / ``"persona_fisica"``
to the canonical ``"moral"`` / ``"fisica"`` tokens at every catalog
boundary, but the bad values still live in
``provider_workspaces.persona_type`` and ``vendors.persona_type``.
Any caller that bypasses the normalizer — analytics, audit reports,
a future endpoint that's not been updated yet — would still trip.

This migration:

1. Canonicalizes every existing row using the same alias table the
   runtime normalizer uses. Idempotent — running it twice produces
   the same state. Anything truly unrecognized maps to ``"moral"``
   so the data matches the normalizer's fallback policy (wrong-but-
   visible beats silent zero on the calendar). The WARNING log the
   normalizer emits for unknown values is the ops signal for those
   cases; this migration consolidates the cleanup.

2. Adds a CHECK constraint to both tables so no future provisioning
   path can write a non-canonical value. The constraint allows NULL
   on ``vendors.persona_type`` (the column is nullable) and rejects
   any non-NULL value outside ``('moral', 'fisica')``.

Downgrade drops the constraints but does NOT try to reverse the
canonicalization. The mapping is lossy — there's no record of which
``"moral"`` rows used to be ``"persona_moral"`` vs ``"PM"`` vs
canonical-from-day-one — and reversing it would require restoring
from backup. Operators rolling back can safely leave the canonical
values in place; the runtime normalizer keeps working alongside the
old code.
"""

from __future__ import annotations

from alembic import op

revision = "0013_canonicalize_persona_type"
down_revision = "0012_password_reset_tokens"
branch_labels = None
depends_on = None


# Mirror of ``app.core.compliance_catalog._PERSONA_TYPE_ALIASES``.
# Kept inline so the migration doesn't import application code (a
# common pitfall: app-time normalization helpers can drift faster
# than migrations are re-run, and importing them at migration time
# couples the durable schema to a moving target).
_MORAL_ALIASES = ("moral", "persona_moral", "persona moral", "pm")
_FISICA_ALIASES = (
    "fisica",
    "física",
    "persona_fisica",
    "persona_física",
    "persona fisica",
    "persona física",
    "pf",
)


def _canonicalize_sql(table: str, *, nullable: bool) -> str:
    """Build the canonicalizing UPDATE for a given table.

    ``nullable`` controls whether NULL rows are left alone (for the
    ``vendors`` table, where the column is nullable) or coerced to
    ``"moral"`` (for ``provider_workspaces``, where the column is
    NOT NULL and a NULL value would itself be illegal).
    """
    moral_lits = ", ".join(f"'{a}'" for a in _MORAL_ALIASES)
    fisica_lits = ", ".join(f"'{a}'" for a in _FISICA_ALIASES)
    null_clause = "" if nullable else " OR persona_type IS NULL"
    return f"""
        UPDATE {table}
        SET persona_type = CASE
            WHEN LOWER(TRIM(persona_type)) IN ({moral_lits}) THEN 'moral'
            WHEN LOWER(TRIM(persona_type)) IN ({fisica_lits}) THEN 'fisica'
            ELSE 'moral'
        END
        WHERE
            (persona_type IS NOT NULL AND persona_type NOT IN ('moral', 'fisica'))
            {null_clause};
    """


def upgrade() -> None:
    # 1. Canonicalize every existing row.
    op.execute(_canonicalize_sql("provider_workspaces", nullable=False))
    op.execute(_canonicalize_sql("vendors", nullable=True))

    # 2. Add CHECK constraints so no future write can drop bad data.
    # ``persona_type IN ('moral', 'fisica')`` evaluates to UNKNOWN
    # for NULL, which a CHECK treats as satisfied — so the same
    # condition works on both the nullable vendors column and the
    # NOT NULL provider_workspaces column.
    op.create_check_constraint(
        "ck_provider_workspaces_persona_type",
        "provider_workspaces",
        "persona_type IN ('moral', 'fisica')",
    )
    op.create_check_constraint(
        "ck_vendors_persona_type",
        "vendors",
        "persona_type IN ('moral', 'fisica')",
    )


def downgrade() -> None:
    # Drop the constraints. We deliberately do NOT reverse the
    # canonicalization — the mapping is lossy, and restoring the
    # pre-migration values would require a backup. The runtime
    # normalizer in the application code handles legacy values fine
    # regardless of whether they're present in the DB.
    op.drop_constraint(
        "ck_vendors_persona_type", "vendors", type_="check"
    )
    op.drop_constraint(
        "ck_provider_workspaces_persona_type",
        "provider_workspaces",
        type_="check",
    )
