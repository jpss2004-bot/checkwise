from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_compliance_catalog_returns_metadata_and_both_persona_types() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/compliance/catalog")
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["source"].startswith("C.Árbol")
    assert payload["metadata"]["version"]
    assert "moral" in payload["onboarding"]
    assert "fisica" in payload["onboarding"]
    assert "moral" in payload["recurring"]
    assert payload["year"] == 2026


def test_onboarding_endpoint_filters_by_persona() -> None:
    client = TestClient(app)
    moral = client.get("/api/v1/compliance/onboarding?persona_type=moral").json()
    fisica = client.get("/api/v1/compliance/onboarding?persona_type=fisica").json()

    moral_codes = {r["code"] for r in moral["requirements"]}
    fisica_codes = {r["code"] for r in fisica["requirements"]}

    # Persona moral has the constitutiva, fisica has identificacion oficial.
    assert "ONB-CORP-M-001" in moral_codes
    assert "ONB-CORP-M-001" not in fisica_codes
    assert "ONB-CORP-F-001" in fisica_codes
    assert "ONB-CORP-F-001" not in moral_codes


def test_calendar_has_infonavit_bimonthly_due_months() -> None:
    client = TestClient(app)
    payload = client.get("/api/v1/compliance/calendar?year=2026&persona_type=moral").json()
    inf_months = sorted(
        m["month"]
        for m in payload["months"]
        for inst in m["institutions"]
        if inst["institution"] == "infonavit"
    )
    # Per the Árbol: B6 due Ene, B1 due Mar, B2 due May, B3 due Jul,
    # B4 due Sep, B5 due Nov.
    assert inf_months == [1, 3, 5, 7, 9, 11]


def test_calendar_has_acuses_cuatrimestrales_and_annual_in_abril() -> None:
    client = TestClient(app)
    payload = client.get("/api/v1/compliance/calendar?year=2026").json()
    acuses_months = sorted(
        m["month"]
        for m in payload["months"]
        for inst in m["institutions"]
        if inst["institution"] == "stps_repse"
    )
    assert acuses_months == [1, 5, 9]
    # Annual declaration sits in April with frequency=anual.
    april = next(m for m in payload["months"] if m["month"] == 4)
    has_annual = any(
        item["frequency"] == "anual"
        for inst in april["institutions"]
        for item in inst["items"]
    )
    assert has_annual


def test_calendar_every_item_carries_canonical_period_key() -> None:
    """Patch 3 (Reconciliation): every recurring item must expose ``period_key``."""
    import re

    client = TestClient(app)
    payload = client.get("/api/v1/compliance/calendar?year=2026&persona_type=moral").json()
    pattern = re.compile(r"^20\d{2}-(M(0[1-9]|1[0-2])|B[1-6]|Q[1-3]|A)$")
    items = [
        item
        for month in payload["months"]
        for inst in month["institutions"]
        for item in inst["items"]
    ]
    assert items, "calendar must produce at least one recurring item"
    for item in items:
        assert "period_key" in item, item
        assert item["period_key"], item
        assert pattern.match(item["period_key"]), item["period_key"]


def test_calendar_period_keys_match_known_anchors() -> None:
    """Spot-check that key catalog anchors produce the expected canonical keys."""
    client = TestClient(app)
    payload = client.get("/api/v1/compliance/calendar?year=2026&persona_type=moral").json()
    by_month = {month["month"]: month for month in payload["months"]}

    # IMSS February covers January 2026 → 2026-M01.
    feb_imss = next(
        item
        for inst in by_month[2]["institutions"]
        if inst["institution"] == "imss"
        for item in inst["items"]
    )
    assert feb_imss["period_key"] == "2026-M01"

    # IMSS January covers December previous year → 2025-M12.
    jan_imss = next(
        item
        for inst in by_month[1]["institutions"]
        if inst["institution"] == "imss"
        for item in inst["items"]
    )
    assert jan_imss["period_key"] == "2025-M12"

    # INFONAVIT March covers B1 2026.
    mar_infonavit = next(
        item
        for inst in by_month[3]["institutions"]
        if inst["institution"] == "infonavit"
        for item in inst["items"]
    )
    assert mar_infonavit["period_key"] == "2026-B1"

    # INFONAVIT January covers B6 previous year.
    jan_infonavit = next(
        item
        for inst in by_month[1]["institutions"]
        if inst["institution"] == "infonavit"
        for item in inst["items"]
    )
    assert jan_infonavit["period_key"] == "2025-B6"

    # Acuses May covers Q1 2026.
    may_acuses = next(
        item
        for inst in by_month[5]["institutions"]
        if inst["institution"] == "stps_repse"
        for item in inst["items"]
    )
    assert may_acuses["period_key"] == "2026-Q1"

    # Acuses January covers Q3 previous year.
    jan_acuses = next(
        item
        for inst in by_month[1]["institutions"]
        if inst["institution"] == "stps_repse"
        for item in inst["items"]
    )
    assert jan_acuses["period_key"] == "2025-Q3"

    # Annual April covers previous fiscal year.
    annual = next(
        item
        for inst in by_month[4]["institutions"]
        if inst["institution"] == "sat"
        for item in inst["items"]
        if item["frequency"] == "anual"
    )
    assert annual["period_key"] == "2025-A"


def test_catalog_lookup_recurring_by_code_returns_known_item() -> None:
    """The catalog must expose a code-lookup helper used by /submissions."""
    from app.core.compliance_catalog import lookup_recurring_by_code

    sample = next(
        item
        for item in __import__(
            "app.core.compliance_catalog", fromlist=["recurring_for_year"]
        ).recurring_for_year(2026)
    )
    found = lookup_recurring_by_code(sample.code)
    assert found is not None
    assert found.code == sample.code

    assert lookup_recurring_by_code("REC-NOT-A-REAL-CODE") is None
    assert lookup_recurring_by_code("not even REC shaped") is None


# ---------------------------------------------------------------------------
# Bugfix (2026-05-21) — Jay Luna empty-calendar bug
# ---------------------------------------------------------------------------
#
# Workspaces created via legacy / CLI paths sometimes stored
# ``persona_type`` as ``"persona_moral"`` / ``"persona_fisica"``
# (full label) instead of the canonical ``"moral"`` / ``"fisica"``
# tokens. The catalog filter does strict membership on
# ``r.persona_types`` so any non-canonical value returned 0 items and
# the provider calendar rendered as "Sin obligaciones". The
# ``normalize_persona_type`` helper maps the variants to the
# canonical form and the read endpoints call it at the boundary.


def test_normalize_persona_type_handles_canonical_tokens() -> None:
    from app.core.compliance_catalog import normalize_persona_type

    assert normalize_persona_type("moral") == "moral"
    assert normalize_persona_type("fisica") == "fisica"


def test_normalize_persona_type_handles_full_label_variants() -> None:
    """Maps every full-label variant a legacy path might have stored
    back to the canonical token."""
    from app.core.compliance_catalog import normalize_persona_type

    # Full-label variants.
    assert normalize_persona_type("persona_moral") == "moral"
    assert normalize_persona_type("persona_fisica") == "fisica"
    assert normalize_persona_type("persona moral") == "moral"
    assert normalize_persona_type("persona fisica") == "fisica"
    # Accented + diacritic variants.
    assert normalize_persona_type("persona_física") == "fisica"
    assert normalize_persona_type("física") == "fisica"
    # Case variants.
    assert normalize_persona_type("MORAL") == "moral"
    assert normalize_persona_type("Fisica") == "fisica"
    assert normalize_persona_type("FISICA") == "fisica"
    # Short codes.
    assert normalize_persona_type("PM") == "moral"
    assert normalize_persona_type("pf") == "fisica"


def test_normalize_persona_type_falls_back_to_moral_for_unknown() -> None:
    """Unknown / empty / None values fall back to 'moral' so the
    calendar never silently empties. Empty is the worst outcome —
    a wrong-but-visible default at least lets the provider see
    SOMETHING and lets ops notice via the WARNING log."""
    from app.core.compliance_catalog import normalize_persona_type

    assert normalize_persona_type("") == "moral"
    assert normalize_persona_type(None) == "moral"
    assert normalize_persona_type("not_a_real_value") == "moral"
    # Whitespace handling.
    assert normalize_persona_type("  moral  ") == "moral"


def test_recurring_for_year_with_normalize_bridges_legacy_workspaces() -> None:
    """End-to-end: passing a normalized legacy value through the
    catalog returns the same 139 items as the canonical token. Pins
    the property that the bugfix actually closes the empty-calendar
    hole at the catalog boundary."""
    from app.core.compliance_catalog import (
        normalize_persona_type,
        recurring_for_year,
    )

    canonical = recurring_for_year(2026, "fisica")
    # Legacy workspace stored "persona_fisica" — the bug. Normalize
    # at the boundary then call the catalog; the row count must match
    # the canonical-input count exactly.
    legacy_value = "persona_fisica"
    via_normalizer = recurring_for_year(
        2026, normalize_persona_type(legacy_value)
    )
    assert len(via_normalizer) == len(canonical) > 0

    # Sanity: the raw legacy value DOES return zero. This is the bug
    # that motivated normalize_persona_type — if this assertion ever
    # starts failing, the catalog filter changed and the
    # normalization layer may no longer be necessary.
    raw = recurring_for_year(2026, legacy_value)  # type: ignore[arg-type]
    assert len(raw) == 0
