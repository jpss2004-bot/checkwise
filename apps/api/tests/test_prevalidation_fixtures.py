"""Phase 2 — fixture-driven regression suite for the prevalidation pipeline.

Every PDF under ``tests/fixtures/prevalidation/`` is a real-world sample
from the 2026-05-22 "Banco Docs Sample" set (provided by the user;
3 vendors × 4 institution categories × multiple doc types and periods,
40 files total). For each fixture, ``manifest.json`` declares:

- ``input_requirement`` / ``input_institution`` / ``period_key`` — what
  the intake endpoint would have been told the upload is for.
- ``current_status`` — the verdict the pipeline produced when the
  manifest was snapshotted. The test asserts on this; any code change
  that flips a fixture's verdict must update the manifest in the same
  commit.
- ``acceptable_statuses`` — the reviewer-approved set of correct
  outcomes. The test also asserts ``current_status in acceptable_statuses``
  so a regression that flips a fixture to a *forbidden* status (e.g.
  ``posible_mismatch`` — Jorge Luna's 2026-05-21 false positive) fails
  loudly, separately from the pinned-snapshot assertion.

This is the gate every Phase 3-6 change has to pass. Tuning thresholds
or replacing the detector requires landing the manifest update with the
implementation so the verdict shift is visible in the PR diff.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.document_intelligence import analyze_document_text
from app.services.pdf_validation import inspect_pdf
from app.services.submission_service import status_from_inspection

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "prevalidation"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"


def _load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text())


def _fixture_ids(entries: list[dict]) -> list[str]:
    return [entry["file"] for entry in entries]


_MANIFEST = _load_manifest()
_FIXTURES = _MANIFEST["fixtures"]


@pytest.mark.parametrize("entry", _FIXTURES, ids=_fixture_ids(_FIXTURES))
def test_fixture_verdict_matches_manifest(entry: dict[str, Any]) -> None:
    """The pipeline's verdict for the fixture must match the pinned snapshot.

    If a code change deliberately shifts the verdict, update the
    manifest entry in the same commit and the test passes again. The
    intent is to make every behavior shift visible in the diff.
    """
    fixture_path = FIXTURES_DIR / entry["file"]
    assert fixture_path.exists(), f"missing fixture file {entry['file']}"

    inspection = inspect_pdf(fixture_path)
    signals = analyze_document_text(
        inspection.text_sample,
        expected_requirement=entry["input_requirement"],
        expected_institution=entry["input_institution"],
        expected_period=entry["period_key"],
    )
    actual_status = status_from_inspection(inspection, signals).value

    assert actual_status == entry["current_status"], (
        f"{entry['file']}: pipeline now returns {actual_status!r}, "
        f"manifest pins {entry['current_status']!r}. If this change is "
        f"intentional, update manifest.json in the same commit."
    )


@pytest.mark.parametrize("entry", _FIXTURES, ids=_fixture_ids(_FIXTURES))
def test_fixture_status_is_acceptable(entry: dict[str, Any]) -> None:
    """Pinned status must remain inside the reviewer-approved set.

    Catches the case where current_status was *intentionally* updated
    in a commit but to a value the reviewer would never accept (e.g.
    flipping a correct SAT document to ``posible_mismatch``). The
    forbidden set is encoded by absence: ``acceptable_statuses`` lists
    only the values reviewers consider correct.
    """
    assert entry["current_status"] in entry["acceptable_statuses"], (
        f"{entry['file']}: current_status {entry['current_status']!r} "
        f"is not in acceptable_statuses {entry['acceptable_statuses']!r}. "
        f"Either the verdict regressed or acceptable_statuses needs "
        f"expanding — but never silently."
    )


def test_no_fixture_produces_posible_mismatch() -> None:
    """Jorge Luna 2026-05-21 — invariant guard.

    Every fixture is a correctly-filed sample. Any one of them landing
    in ``posible_mismatch`` is the false positive we shipped Phase 1 to
    kill. Asserted at the manifest level so a single offender lights up
    a clear failure independent of the per-fixture parametrization.
    """
    offenders = [
        entry["file"]
        for entry in _FIXTURES
        if entry["current_status"] == "posible_mismatch"
    ]
    assert not offenders, (
        f"{len(offenders)} fixture(s) regressed to posible_mismatch — "
        f"this is the Phase 1 false-positive class: {offenders}"
    )


def test_no_fixture_produces_requiere_aclaracion() -> None:
    """All fixtures are valid PDFs; none should fail PDF inspection."""
    offenders = [
        entry["file"]
        for entry in _FIXTURES
        if entry["current_status"] == "requiere_aclaracion"
    ]
    assert not offenders, (
        f"{len(offenders)} fixture(s) failed PDF inspection: {offenders}"
    )


def test_manifest_covers_every_fixture_file() -> None:
    """No fixture PDF should be sitting in the directory unreferenced.

    Protects against the case where someone drops a new PDF in for
    debugging and forgets to add a manifest entry — the test would
    otherwise silently skip it.
    """
    on_disk = {p.name for p in FIXTURES_DIR.glob("*.pdf")}
    in_manifest = {entry["file"] for entry in _FIXTURES}
    missing_from_manifest = on_disk - in_manifest
    missing_on_disk = in_manifest - on_disk
    assert not missing_from_manifest, (
        f"PDFs on disk but not in manifest: {sorted(missing_from_manifest)}"
    )
    assert not missing_on_disk, (
        f"Manifest entries with no PDF on disk: {sorted(missing_on_disk)}"
    )
