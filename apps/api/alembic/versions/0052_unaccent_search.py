"""Enable accent-insensitive search: unaccent extension + IMMUTABLE wrapper.

Revision ID: 0052_unaccent_search
Revises: 0051_perf_indexes_admin_lists_and_queue
Create Date: 2026-06-18

Search across the product was accent-SENSITIVE — a Mexican REPSE product where
"Gonzalez" should find "González", "Anahuac" should find "Anáhuac". This adds
the ``unaccent`` extension and an IMMUTABLE ``f_unaccent`` wrapper so the admin
clients/vendors/users searches can do ``f_unaccent(col) ILIKE f_unaccent(:q)``.

Why the wrapper: ``unaccent(text)`` (1-arg) is only STABLE, so it can't be used
in an expression index or assumed immutable by the planner. Pinning the
dictionary — ``unaccent('unaccent', text)`` — is IMMUTABLE, so wrapping it lets
us index it later (deferred for now, like the pg_trgm indexes in 0051) and lets
the planner treat it as a constant for literal arguments.

Fast metadata-only DDL — no CONCURRENTLY / autocommit block needed. Idempotent
(IF NOT EXISTS / OR REPLACE). SQLite test fixtures never run this; the search
helper falls back to plain ILIKE there.

DEPLOY: snapshot Neon before pushing (auto-runs via Render preDeploy). The
``unaccent`` extension is on Neon's allowlist.
"""

from __future__ import annotations

from alembic import op

revision = "0052_unaccent_search"
down_revision = "0051_perf_indexes_admin_lists_and_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION f_unaccent(text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE
        PARALLEL SAFE
        STRICT
        AS $func$ SELECT unaccent('unaccent', $1) $func$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS f_unaccent(text)")
    # Leave the unaccent extension in place — other objects may rely on it and
    # dropping an extension is rarely what a rollback wants.
