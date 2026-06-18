"""Accent-insensitive text search helpers.

CheckWise is a Mexican product: vendor/client/user names are full of Spanish
diacritics (á é í ó ú ñ ü). Plain ``ILIKE`` is case-insensitive but accent-
SENSITIVE, so a search for "Gonzalez" misses "González" and vice versa. These
helpers make name search accent-insensitive on both the SQL side (Postgres
``unaccent`` via the IMMUTABLE ``f_unaccent`` wrapper, migration 0052) and the
Python side (for the few in-memory filters), so search behaves the same way
everywhere — and the same way as the frontend's ``normalizeForSearch``.
"""

from __future__ import annotations

import unicodedata

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement


def normalize_for_search(value: str) -> str:
    """Fold case and strip combining diacritics (Python-side, for in-memory
    filters). ``"González"`` -> ``"gonzalez"``."""
    decomposed = unicodedata.normalize("NFD", value)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return stripped.casefold().strip()


def accent_ci_contains(
    dialect_name: str, column: ColumnElement[str], term: str
) -> ColumnElement[bool]:
    """An accent- and case-insensitive substring predicate for a SQL column.

    Postgres (prod): ``f_unaccent(column) ILIKE f_unaccent('%term%')`` — relies
    on the ``unaccent`` extension + the IMMUTABLE ``f_unaccent`` wrapper added by
    migration 0052. SQLite (tests): falls back to a plain case-insensitive
    ``ILIKE`` — accent-insensitivity is a prod refinement and the test fixtures
    don't assert on accents, so this keeps the suite green without the extension.
    """
    pattern = f"%{term}%"
    if dialect_name == "postgresql":
        return func.f_unaccent(column).ilike(func.f_unaccent(pattern))
    return column.ilike(pattern)
