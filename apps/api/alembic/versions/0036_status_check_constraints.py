"""CHECK constraints on submission + document status.

Audit 2026-06-09 (finding D5). ``submissions.status`` and
``documents.status`` are free ``String(40)`` columns — the app validates
against the ``DocumentStatus`` enum at the Pydantic/intake layer, but a
bug or a manual DB poke could write an out-of-enum value that the
read-side ``classify_slot_state`` would then silently bucket as
``MISSING``. These CHECK constraints make the DB reject such writes.

Added ``NOT VALID``: the constraint is enforced on every **new** write
immediately, but Postgres does *not* scan the existing table on ``ADD``,
so the deploy can't fail on a legacy row that pre-dates the enum. (Run a
later ``VALIDATE CONSTRAINT`` by hand once you've confirmed/cleaned any
stragglers — see the helper query in the audit doc.) Postgres-only; the
SQLite test schema omits it (the focused migration test exercises the
predicate directly).

Revision ID: 0036_status_check_constraints
Revises: 0035_unique_active_slot
Create Date: 2026-06-09
"""

from __future__ import annotations

from alembic import op

revision = "0036_status_check_constraints"
down_revision = "0035_unique_active_slot"
branch_labels = None
depends_on = None

# Point-in-time snapshot of DocumentStatus (app/constants/statuses.py).
# Kept literal so re-running this historical migration never depends on
# the live enum drifting.
_STATUSES: tuple[str, ...] = (
    "pendiente",
    "recibido",
    "pendiente_revision",
    "prevalidado",
    "posible_mismatch",
    "aprobado",
    "rechazado",
    "vencido",
    "no_aplica",
    "requiere_aclaracion",
    "excepcion_legal",
)

_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("ck_submissions_status", "submissions"),
    ("ck_documents_status", "documents"),
)


def _in_list() -> str:
    return ", ".join(f"'{s}'" for s in _STATUSES)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    in_list = _in_list()
    for name, table in _CONSTRAINTS:
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            f"CHECK (status IN ({in_list})) NOT VALID"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for name, table in _CONSTRAINTS:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
