"""Seed the compliance catalog into ``institutions``, ``requirements`` and
``requirement_versions``.

Revision ID: 0005_seed_catalog
Revises: 0004_canonical_keys
Create Date: 2026-05-13

Data-only migration introduced by Patch 2 of the Reconciliation series.
After this migration runs, every canonical catalog code emitted by
``compliance_catalog.py`` exists as a row in ``requirements`` with a
matching ``version=1`` row in ``requirement_versions``. Subsequent
submissions resolve canonical codes directly against the DB instead of
relying on the on-the-fly fallback in ``endpoints.py``.

The seed is idempotent: ``downgrade`` is intentionally a no-op because
the rows it inserts are referenced by ``submissions`` and deleting them
would cascade-fail on a populated database. Catalog evolution is handled
through *new versions* (``current_version += 1``), not destructive edits.
"""

from __future__ import annotations

from alembic import op

revision = "0005_seed_catalog"
down_revision = "0004_canonical_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Defer imports so the rest of the codebase can still load this module
    # without requiring the full app context (e.g., ``alembic history``).
    from sqlalchemy.orm import Session

    from app.db.seed import seed_catalog

    session = Session(bind=op.get_bind())
    result = seed_catalog(session)
    session.flush()
    # The migration runs inside Alembic's transaction; do not commit here.
    print(
        f"[0005_seed_catalog] inserted institutions={result.institutions_inserted}, "
        f"requirements={result.requirements_inserted}, "
        f"requirement_versions={result.requirement_versions_inserted}"
    )


def downgrade() -> None:
    """Intentional no-op. See module docstring for rationale."""
    pass
