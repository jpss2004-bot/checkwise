"""Catalog v2 — collapsed recurring obligations (Session 1, 2026-05-20).

Pins the v2 generator's shape so Session 2 (slot resolver) and
Session 3 (endpoints + frontend) can land on a stable contract. v2 is
authored alongside v1 — until ``settings.RECURRING_CATALOG_V2`` flips,
nothing in production consumes these rows; these tests are the only
caller.

Coverage:

* Row counts match the design (12 IMSS + 12 SAT + 6 INFONAVIT + 3
  STPS + 1 SAT anual = 34 rows/year, persona moral).
* Code shape is ``REC-<INSTITUTION>-<YEAR>-<DUE_MONTH:02d>`` with the
  SAT annual exception ``REC-SAT-<YEAR>-04-anual``. Distinct from v1
  codes so the catalogs can cohabit in the DB.
* ``accepts_documents`` enumerates the v1 doc templates for that
  (institution, frequency) — IMSS keeps the 4 docs, SAT keeps the 5,
  INFONAVIT 4, STPS 2, SAT anual 1.
* ``minimum_documents`` defaults to ``"one"`` (Jose Pablo's
  "either / or / both" rule).
* ``recurring_accepted_documents`` returns one entry per accepted doc
  with override-or-institution-fallback for anatomy / where_to_obtain
  / common_errors. v1 rows still return ``[]`` so legacy callers see
  no behavior change.
"""

from __future__ import annotations

from app.core.compliance_catalog import (
    RecurringRequirement,
    recurring_accepted_documents,
    recurring_for_year,
    recurring_for_year_v2,
)

# ---------------------------------------------------------------------------
# Row counts + structure
# ---------------------------------------------------------------------------


def test_v2_collapses_one_thirty_nine_rows_to_thirty_four() -> None:
    """v1 emits ~139 rows/year (4 IMSS + 5 SAT per month + 4 INFONAVIT
    per bimester + 2 STPS per cuatrimestre + 1 SAT anual). v2 collapses
    to one row per (institution, period)."""
    v1 = recurring_for_year(2026, "moral")
    v2 = recurring_for_year_v2(2026, "moral")
    assert len(v1) == 139, f"v1 row count drifted from 139 → {len(v1)}"
    assert len(v2) == 34, f"v2 row count expected 34, got {len(v2)}"


def test_v2_row_distribution_by_institution_and_frequency() -> None:
    rows = recurring_for_year_v2(2026, "moral")
    by_inst: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row.institution, row.frequency)
        by_inst[key] = by_inst.get(key, 0) + 1
    assert by_inst == {
        ("imss", "mensual"): 12,
        ("sat", "mensual"): 12,
        ("infonavit", "bimestral"): 6,
        ("stps_repse", "cuatrimestral"): 3,
        ("sat", "anual"): 1,
    }


def test_v2_codes_use_collapsed_shape_not_per_doc_suffix() -> None:
    rows = recurring_for_year_v2(2026, "moral")
    # IMSS January 2026 — single code, no doc suffix.
    imss_jan = next(r for r in rows if r.institution == "imss" and r.due_month == 1)
    assert imss_jan.code == "REC-IMSS-2026-01"
    # SAT February 2026.
    sat_feb = next(
        r for r in rows
        if r.institution == "sat" and r.frequency == "mensual" and r.due_month == 2
    )
    assert sat_feb.code == "REC-SAT-2026-02"
    # INFONAVIT B1 (due March).
    inf_b1 = next(
        r for r in rows if r.institution == "infonavit" and r.due_month == 3
    )
    assert inf_b1.code == "REC-INFONAVIT-2026-03"
    # STPS Q1 (due May).
    stps_q1 = next(
        r for r in rows if r.institution == "stps_repse" and r.due_month == 5
    )
    assert stps_q1.code == "REC-STPS-2026-05"
    # SAT annual — uses the ``-anual`` suffix.
    sat_anual = next(r for r in rows if r.frequency == "anual")
    assert sat_anual.code == "REC-SAT-2026-04-anual"


def test_v2_and_v1_codes_never_collide() -> None:
    """Both catalogs must coexist in production. Their code namespaces
    cannot overlap or a submission written under one shape would
    resolve under the other."""
    v1_codes = {r.code for r in recurring_for_year(2026, "moral")}
    v2_codes = {r.code for r in recurring_for_year_v2(2026, "moral")}
    overlap = v1_codes & v2_codes
    assert not overlap, f"v1 / v2 code overlap: {sorted(overlap)}"


# ---------------------------------------------------------------------------
# Accepted-documents contract
# ---------------------------------------------------------------------------


def test_v2_imss_row_accepts_four_doc_types() -> None:
    rows = recurring_for_year_v2(2026, "moral")
    imss = next(r for r in rows if r.institution == "imss" and r.due_month == 1)
    assert set(imss.accepts_documents) == {
        "Comprobante de pago bancario",
        "CFDI de pago de cuotas",
        "Cuotas obrero patronales",
        "Resumen de liquidación",
    }


def test_v2_sat_monthly_row_accepts_five_doc_types() -> None:
    rows = recurring_for_year_v2(2026, "moral")
    sat = next(
        r for r in rows
        if r.institution == "sat" and r.frequency == "mensual" and r.due_month == 1
    )
    assert set(sat.accepts_documents) == {
        "Declaración ISR por retención sueldos y salarios",
        "Declaración IVA",
        "Comprobante entero pago ISR",
        "Comprobante entero pago IVA",
        "Comprobantes de nómina de los trabajadores",
    }


def test_v2_stps_row_accepts_sisub_and_icsoe() -> None:
    """The classic 'either / or / both' obligation. Confirm both
    accuses are listed."""
    rows = recurring_for_year_v2(2026, "moral")
    stps = next(r for r in rows if r.institution == "stps_repse")
    assert set(stps.accepts_documents) == {"Acuse SISUB", "Acuse ICSOE"}


def test_v2_sat_annual_row_accepts_only_acuse() -> None:
    rows = recurring_for_year_v2(2026, "moral")
    sat_anual = next(r for r in rows if r.frequency == "anual")
    assert sat_anual.accepts_documents == (
        "Acuse declaración anual de impuestos",
    )


# ---------------------------------------------------------------------------
# minimum_documents default + override
# ---------------------------------------------------------------------------


def test_v2_minimum_documents_defaults_to_one() -> None:
    """Matches Jose Pablo's 'either / or / both' rule: any one of the
    accepted docs satisfies the obligation."""
    rows = recurring_for_year_v2(2026, "moral")
    for row in rows:
        assert row.minimum_documents == "one", (
            f"row {row.code} defaulted to {row.minimum_documents}, expected 'one'"
        )


def test_v2_minimum_documents_can_be_overridden_per_row() -> None:
    """When a future obligation needs 'all-of-N' semantics (e.g. a
    complete payment-evidence package), the field accepts ``"all"`` on
    the instance. We don't author any such rows yet; this just pins
    the contract."""
    row = RecurringRequirement(
        code="REC-TEST-ALL",
        name="Paquete completo",
        institution="imss",
        frequency="mensual",
        due_month=1,
        period_label="Test",
        period_key="2026-M01",
        accepts_documents=("A", "B", "C"),
        minimum_documents="all",
    )
    assert row.minimum_documents == "all"


# ---------------------------------------------------------------------------
# recurring_accepted_documents accessor
# ---------------------------------------------------------------------------


def test_v2_accepted_documents_accessor_returns_one_entry_per_accepted_doc() -> None:
    rows = recurring_for_year_v2(2026, "moral")
    imss = next(r for r in rows if r.institution == "imss" and r.due_month == 1)
    entries = recurring_accepted_documents(imss)
    assert len(entries) == 4
    names = {entry["name"] for entry in entries}
    assert names == set(imss.accepts_documents)
    for entry in entries:
        assert isinstance(entry["anatomy"], str) and entry["anatomy"], entry
        assert (
            isinstance(entry["where_to_obtain"], str) and entry["where_to_obtain"]
        ), entry
        assert (
            isinstance(entry["common_errors"], list) and entry["common_errors"]
        ), entry


def test_v2_accepted_documents_uses_per_doc_overrides_when_present() -> None:
    """The Stage 2.7 override map authored content for the IMSS
    ``Cuotas obrero patronales`` doc; the accessor must surface that
    override (not the institution default) for that specific entry."""
    rows = recurring_for_year_v2(2026, "moral")
    imss = next(r for r in rows if r.institution == "imss" and r.due_month == 1)
    entries = recurring_accepted_documents(imss)
    cuotas = next(e for e in entries if e["name"] == "Cuotas obrero patronales")
    # The override anatomy mentions the bank-payment cross-check.
    assert "comprobante de pago bancario" in str(cuotas["anatomy"]).lower(), cuotas
    # Per-doc override ships ≥ 5 common-error bullets; institution
    # default ships 3. Discriminator pinned in Stage 2.7 tests.
    assert isinstance(cuotas["common_errors"], list)
    assert len(cuotas["common_errors"]) >= 5


def test_v2_accepted_documents_falls_back_to_institution_defaults() -> None:
    """SAT monthly docs that don't have per-doc overrides (e.g.
    'Declaración IVA') must still get a non-empty institution-default
    paragraph so the disclosure isn't blank."""
    rows = recurring_for_year_v2(2026, "moral")
    sat = next(
        r for r in rows
        if r.institution == "sat" and r.frequency == "mensual" and r.due_month == 1
    )
    entries = recurring_accepted_documents(sat)
    iva = next(e for e in entries if e["name"] == "Declaración IVA")
    assert iva["anatomy"]  # non-empty institution default
    assert iva["where_to_obtain"]
    assert iva["common_errors"]


def test_v2_accessor_returns_empty_list_for_v1_rows() -> None:
    """Legacy v1 rows have ``accepts_documents=()``. The accessor must
    return ``[]`` so callers can branch on length without checking the
    flag."""
    v1_rows = recurring_for_year(2026, "moral")
    sample = v1_rows[0]
    assert sample.accepts_documents == ()
    assert recurring_accepted_documents(sample) == []


# ---------------------------------------------------------------------------
# Persona filtering still works
# ---------------------------------------------------------------------------


def test_v2_persona_fisica_returns_same_obligations_as_persona_moral() -> None:
    """Recurring obligations apply equally to both persona types in
    v1; v2 must preserve that."""
    moral = recurring_for_year_v2(2026, "moral")
    fisica = recurring_for_year_v2(2026, "fisica")
    assert len(moral) == len(fisica)
    assert {r.code for r in moral} == {r.code for r in fisica}
