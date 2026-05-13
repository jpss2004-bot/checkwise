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
