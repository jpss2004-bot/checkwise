"""CI guard against macOS Finder duplicate files (audit finding CLIENT-007).

macOS Finder, when copying or de-duplicating, leaves artifacts whose
name carries a trailing `` 2`` / `` 3`` / `` copy`` before the extension
(e.g. ``client 2.py``, ``page 2.tsx``, ``tsconfig 2.json``,
``search-bar copy.tsx``). These stale copies are pure noise:

- The space means Python can't import them as modules and Next can't
  route them, so they never run as real code...
- ...yet ``test_*.py`` Finder copies *do* get collected by pytest, where
  the stale (older) assertions fail against current code and inflate the
  failure count with phantom failures (CLIENT-007: ``test_client_portal
  2.py`` alone contributed ~9 phantom failures before removal).

The repo's ``.gitignore`` already declines to track these (rules
``* [2-9].*`` and ``* copy.*`` / ``* copy``). This test is the
belt-and-suspenders CI gate: it fails if any *tracked* file ever slips
past that ignore rule (e.g. via ``git add -f`` or a weakened
``.gitignore``), so Finder duplicates cannot reappear in the source tree.

If this test fails, delete the offending duplicate(s) — the real file is
the same name without the `` 2``/`` copy`` suffix.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

# Mirrors the repo .gitignore Finder-duplicate rules `* [2-9].*` and
# `* copy.*` / `* copy`, applied to a file's basename. A match means the
# name carries a Finder duplicate suffix immediately before its extension.
_FINDER_DUPLICATE = re.compile(r" (?:[2-9]\.| ?copy(?:\.|$))")


def _repo_root() -> Path:
    """Resolve the git toplevel, falling back to the known layout.

    tests/ -> apps/api -> apps -> <repo root>
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parents[3]


def _tracked_files(root: Path) -> list[str] | None:
    """Return git-tracked paths (relative to ``root``), or None if git/repo unavailable."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return [p for p in out.stdout.split("\0") if p]


def test_no_finder_duplicate_files_are_tracked() -> None:
    """No tracked file may carry a Finder duplicate suffix (CLIENT-007)."""
    root = _repo_root()
    tracked = _tracked_files(root)
    if tracked is None:
        pytest.skip("git not available / not a git checkout; guard is a no-op here")

    offenders = sorted(
        path for path in tracked if _FINDER_DUPLICATE.search(Path(path).name)
    )

    assert not offenders, (
        "Tracked macOS Finder duplicate file(s) detected (audit CLIENT-007). "
        "Delete them — the real file is the same name without the "
        "' 2'/' copy' suffix:\n  " + "\n  ".join(offenders)
    )
