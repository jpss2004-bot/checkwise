"""Unit tests for the accent-insensitive search helpers."""

from sqlalchemy.dialects import postgresql, sqlite

from app.core.text_search import accent_ci_contains, normalize_for_search
from app.models import Client


def test_normalize_strips_accents_and_folds_case() -> None:
    assert normalize_for_search("González") == "gonzalez"
    assert normalize_for_search("ANÁHUAC") == "anahuac"
    assert normalize_for_search("  Peña  ") == "pena"
    assert normalize_for_search("") == ""


def test_accent_ci_contains_uses_unaccent_on_postgres() -> None:
    expr = accent_ci_contains("postgresql", Client.name, "anahuac")
    compiled = str(expr.compile(dialect=postgresql.dialect()))
    # The column is wrapped in the IMMUTABLE f_unaccent wrapper (migration 0052)
    # and matched with ILIKE against an unaccented pattern.
    assert "f_unaccent(clients.name)" in compiled
    assert "ILIKE" in compiled.upper()


def test_accent_ci_contains_falls_back_to_plain_ilike_on_sqlite() -> None:
    expr = accent_ci_contains("sqlite", Client.name, "anahuac")
    compiled = str(expr.compile(dialect=sqlite.dialect()))
    # No f_unaccent on SQLite (the test backend has no unaccent extension).
    assert "f_unaccent" not in compiled
    assert "LIKE" in compiled.upper()
