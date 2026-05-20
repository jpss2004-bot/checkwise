"""Phase 5 — backend-owned enrichment for onboarding + calendar.

The provider portal pages previously stitched in UX copy from
frontend mocks. Phase 5 moves that responsibility to the backend so
the canonical read endpoints are self-sufficient.

These tests pin the new fields:

* Onboarding items expose ``why`` / ``format`` (static catalog copy)
  and state-driven ``next_action`` / ``reviewer_note``.
* Calendar items expose ``required_document``, ``deadline_iso``,
  ``suggested_action``, ``href`` — covering every recurring
  frequency including the January prior-year carryover.
* Replacement lineage still governs which submission is "current",
  so ``reviewer_note`` and the state-driven copy reflect the
  replacement — never the superseded prior.
"""

from __future__ import annotations

import itertools
from collections.abc import Generator
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.statuses import DocumentStatus, ReviewerAction
from app.core.compliance_catalog import recurring_for_year
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Client,
    ProviderWorkspace,
    Submission,
    User,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password, issue_access_token
from app.services.submission_workflow import apply_reviewer_decision


@pytest.fixture
def api_client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    previous = settings.LOCAL_STORAGE_PATH
    settings.LOCAL_STORAGE_PATH = str(tmp_path / "storage")

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.app.state.testing_session = testing_session  # type: ignore[attr-defined]
    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        settings.LOCAL_STORAGE_PATH = previous


def _pdf_bytes() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


_user_seq = itertools.count(1)


def _setup_workspace(
    api_client: TestClient,
    *,
    vendor_name: str = "Servicios Demo SA de CV",
    vendor_rfc: str = "DEM260512AB1",
    client_name: str = "Cliente Piloto CheckWise",
) -> dict:
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        seq = next(_user_seq)
        user = User(
            email=f"canon-{seq}@checkwise.test",
            password_hash=hash_password("CheckWiseTest!2026"),
            full_name=vendor_name,
            status="active",
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        client_row = db.query(Client).filter_by(name=client_name).first()
        if client_row is None:
            client_row = Client(name=client_name)
            db.add(client_row)
            db.flush()
        vendor = Vendor(
            client_id=client_row.id,
            name=vendor_name,
            rfc=vendor_rfc.upper(),
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        workspace = ProviderWorkspace(
            client_id=client_row.id,
            vendor_id=vendor.id,
            owner_user_id=user.id,
            persona_type="moral",
            display_name=vendor_name,
            access_token="placeholder",
        )
        db.add(workspace)
        db.commit()
        ws_id = workspace.id
        user_id, user_email = user.id, user.email
    finally:
        db.close()

    token = issue_access_token(user_id=user_id, email=user_email, roles=[], orgs=[])
    api_client.cookies.clear()
    enter = api_client.post(
        "/api/v1/portal/enter",
        json={"workspace_id": ws_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert enter.status_code == 200, enter.text
    return {"workspace_id": ws_id, "bearer": token, "user_id": user_id}


def _upload_canonical_b1(
    api_client: TestClient, ws_id: str, *, supersedes: str | None = None
) -> str:
    catalog_item = next(
        item
        for item in recurring_for_year(2026)
        if item.institution == "infonavit" and item.period_key == "2026-B1"
    )
    data = {
        "period_code": "2026-B1",
        "period_key": catalog_item.period_key,
        "load_type": "bimestral",
        "institution_code": "infonavit",
        "requirement_name": catalog_item.name,
        "requirement_code": catalog_item.code,
        "initial_status": "pendiente_revision",
    }
    if supersedes:
        data["supersedes_submission_id"] = supersedes
    response = api_client.post(
        f"/api/v1/portal/workspaces/{ws_id}/submissions",
        data=data,
        files={"file": ("inf.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 202, response.text
    return response.json()["submission_id"]


# ---------------------------------------------------------------------------
# Onboarding enrichment
# ---------------------------------------------------------------------------


def test_onboarding_items_carry_why_format_next_action(api_client: TestClient) -> None:
    """Every onboarding item must include the four Phase-5 fields."""
    ws = _setup_workspace(api_client)
    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/onboarding"
    ).json()
    items = [item for section in body["sections"] for item in section["items"]]
    assert items, "expected onboarding catalog to yield items"
    for item in items:
        for key in ("why", "format", "next_action", "reviewer_note"):
            assert key in item, f"missing field {key} on onboarding item {item.get('code')}"
        assert isinstance(item["why"], str) and item["why"], item
        assert isinstance(item["format"], str) and item["format"], item
        assert isinstance(item["next_action"], str) and item["next_action"], item


def test_onboarding_enrichment_present_on_required_and_optional(
    api_client: TestClient,
) -> None:
    """Required + optional items must both have the enriched fields."""
    ws = _setup_workspace(api_client)
    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/onboarding"
    ).json()
    items = [item for section in body["sections"] for item in section["items"]]
    required = [item for item in items if item["required"]]
    optional = [item for item in items if not item["required"]]
    assert required, "expected at least one required onboarding item"
    assert optional, "expected at least one optional onboarding item"
    for item in required + optional:
        assert item["why"]
        assert item["format"]
        assert item["next_action"]


def test_onboarding_reviewer_note_surfaces_reviewer_reason(
    api_client: TestClient,
) -> None:
    """``reviewer_note`` mirrors the latest reviewer-decision message."""
    ws = _setup_workspace(api_client)
    # Upload an onboarding submission for ONB-REPSE-001.
    onb_payload = {
        "period_code": "2026-ONB",
        "period_key": "onb-repse-2026",
        "load_type": "alta_inicial",
        "institution_code": "stps_repse",
        "requirement_name": "Registro REPSE original",
        "requirement_code": "ONB-REPSE-001",
        "initial_status": "pendiente_revision",
    }
    upload = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions",
        data=onb_payload,
        files={"file": ("doc.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert upload.status_code == 202
    sub_id = upload.json()["submission_id"]

    # Reviewer rejects with a reason.
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        sub = db.get(Submission, sub_id)
        assert sub is not None
        apply_reviewer_decision(
            db,
            submission=sub,
            action=ReviewerAction.REJECT,
            reason="El RFC no coincide con la razón social registrada.",
            reviewer_user_id="rev-test-user",
        )
    finally:
        db.close()

    onboarding = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/onboarding"
    ).json()
    items = [item for section in onboarding["sections"] for item in section["items"]]
    repse_item = next(item for item in items if item["code"] == "ONB-REPSE-001")
    assert repse_item["status"] == DocumentStatus.RECHAZADO.value
    assert repse_item["reviewer_note"] == "El RFC no coincide con la razón social registrada."
    # Status-driven next_action signals the rejection.
    assert "rechazad" in repse_item["next_action"].lower()


def test_onboarding_next_action_changes_with_state(api_client: TestClient) -> None:
    """A pending slot has different ``next_action`` text than a slot in review."""
    ws = _setup_workspace(api_client)
    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/onboarding"
    ).json()
    items = [item for section in body["sections"] for item in section["items"]]
    # The fresh workspace has only pending slots (no submissions).
    assert all(item["status"] == "pendiente" for item in items)
    pending_required = next(item for item in items if item["required"])
    assert "destrabar" in pending_required["next_action"].lower()
    # Now upload a canonical INFONAVIT submission for an unrelated slot
    # and look at it (since the canonical onboarding slot we touch must
    # be a recognized ONB-* code; we just use the upload as a control).
    onb_payload = {
        "period_code": "2026-ONB",
        "period_key": "onb-corp-2026",
        "load_type": "alta_inicial",
        "institution_code": "interno_cliente",
        "requirement_name": "Acta constitutiva / reformas (objeto social vigente)",
        "requirement_code": "ONB-CORP-M-001",
        "initial_status": "pendiente_revision",
    }
    upload = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions",
        data=onb_payload,
        files={"file": ("doc.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert upload.status_code == 202

    body2 = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/onboarding"
    ).json()
    items2 = [item for section in body2["sections"] for item in section["items"]]
    corp = next(item for item in items2 if item["code"] == "ONB-CORP-M-001")
    assert corp["status"] == DocumentStatus.PENDIENTE_REVISION.value
    # Different copy than the pending slot.
    assert "revisión" in corp["next_action"].lower()
    assert corp["next_action"] != pending_required["next_action"]


# ---------------------------------------------------------------------------
# Calendar enrichment
# ---------------------------------------------------------------------------


def test_calendar_items_carry_required_document_deadline_action_href(
    api_client: TestClient,
) -> None:
    """Every calendar item must include the four Phase-5 fields."""
    ws = _setup_workspace(api_client)
    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/calendar?year=2026"
    ).json()
    items = [
        item
        for month in body["months"]
        for inst in month["institutions"]
        for item in inst["items"]
    ]
    assert items, "expected calendar catalog to yield items"
    for item in items:
        for key in ("required_document", "deadline_iso", "suggested_action", "href"):
            assert key in item, f"missing field {key} on calendar item {item.get('code')}"
        assert isinstance(item["required_document"], str) and item["required_document"]
        assert item["deadline_iso"].startswith("2026-"), item["deadline_iso"]
        assert isinstance(item["suggested_action"], str) and item["suggested_action"]
        assert item["href"].startswith("/portal/upload?"), item["href"]


def test_calendar_deadlines_cover_every_frequency_and_january_carryover(
    api_client: TestClient,
) -> None:
    """Monthly / bimestral / cuatrimestral / annual / January-prior-year all
    surface deadlines built from the canonical (year, due_month, due_day)."""
    ws = _setup_workspace(api_client)
    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/calendar?year=2026"
    ).json()
    flat = [
        (month["month"], item)
        for month in body["months"]
        for inst in month["institutions"]
        for item in inst["items"]
    ]

    # Monthly IMSS due in February — deadline 2026-02-17.
    monthly = next(
        item for due_month, item in flat
        if due_month == 2 and item["frequency"] == "mensual"
    )
    assert monthly["deadline_iso"] == "2026-02-17"

    # Bimestral INFONAVIT (any one) — deadline day=17.
    bimestral = next(item for _, item in flat if item["frequency"] == "bimestral")
    assert bimestral["deadline_iso"].endswith("-17")

    # Cuatrimestral STPS — deadline day=17.
    cuat = next(item for _, item in flat if item["frequency"] == "cuatrimestral")
    assert cuat["deadline_iso"].endswith("-17")

    # Annual SAT — deadline day=30 (catalog override).
    anual = next(item for _, item in flat if item["frequency"] == "anual")
    assert anual["deadline_iso"] == "2026-04-30"

    # January carryover (prior-year December) — covered by period_key 2025-M12,
    # filed in 2026-01.
    january_items = [item for due_month, item in flat if due_month == 1]
    assert any(item["period_key"].startswith("2025-") for item in january_items), january_items


def test_calendar_suggested_action_reflects_replacement_lineage(
    api_client: TestClient,
) -> None:
    """When a rejection has been replaced, ``suggested_action`` reflects the
    replacement state (in review), not the superseded rejection."""
    ws = _setup_workspace(api_client)

    # First upload, then mark it rejected at the DB level (this test
    # does not exercise the workflow service path).
    prior_id = _upload_canonical_b1(api_client, ws["workspace_id"])
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        sub = db.get(Submission, prior_id)
        assert sub is not None
        sub.status = DocumentStatus.RECHAZADO.value
        db.commit()
    finally:
        db.close()

    # Replace with a fresh upload (lineage explicit).
    new_id = _upload_canonical_b1(api_client, ws["workspace_id"], supersedes=prior_id)
    assert new_id != prior_id

    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/calendar?year=2026"
    ).json()
    flat = [
        item
        for month in body["months"]
        for inst in month["institutions"]
        for item in inst["items"]
    ]
    b1 = next(item for item in flat if item["period_key"] == "2026-B1")
    # Slot reflects the replacement (in review), not the superseded rejection.
    assert b1["submission_id"] == new_id
    assert b1["status"] == DocumentStatus.PENDIENTE_REVISION.value
    assert "revisión" in b1["suggested_action"].lower()


def test_onboarding_lineage_still_drives_current_state_after_phase5(
    api_client: TestClient,
) -> None:
    """Onboarding enrichment runs against the current submission, so a
    superseded rejection never overrides the replacement's state-driven
    copy."""
    ws = _setup_workspace(api_client)
    base = {
        "period_code": "2026-ONB",
        "period_key": "onb-repse-2026",
        "load_type": "alta_inicial",
        "institution_code": "stps_repse",
        "requirement_name": "Registro REPSE original",
        "requirement_code": "ONB-REPSE-001",
        "initial_status": "pendiente_revision",
    }
    first = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions",
        data=base,
        files={"file": ("doc.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert first.status_code == 202
    prior_id = first.json()["submission_id"]
    # Reject the prior.
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        sub = db.get(Submission, prior_id)
        assert sub is not None
        sub.status = DocumentStatus.RECHAZADO.value
        db.commit()
    finally:
        db.close()

    # Replacement upload.
    new = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions",
        data={**base, "supersedes_submission_id": prior_id},
        files={"file": ("doc.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert new.status_code == 202

    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/onboarding"
    ).json()
    items = [item for section in body["sections"] for item in section["items"]]
    repse = next(item for item in items if item["code"] == "ONB-REPSE-001")
    assert repse["submission_id"] == new.json()["submission_id"]
    assert repse["status"] == DocumentStatus.PENDIENTE_REVISION.value
    # ``next_action`` reflects in-review, never the rejection.
    assert "revisión" in repse["next_action"].lower()


# ---------------------------------------------------------------------------
# Stage 2.7 — Recurring requirement first-upload guidance
# ---------------------------------------------------------------------------


def test_calendar_items_carry_anatomy_where_to_obtain_common_errors(
    api_client: TestClient,
) -> None:
    """Every calendar item must include the Stage 2.7 first-upload guidance
    fields with non-empty institution fallbacks at minimum."""
    ws = _setup_workspace(api_client)
    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/calendar?year=2026"
    ).json()
    items = [
        item
        for month in body["months"]
        for inst in month["institutions"]
        for item in inst["items"]
    ]
    assert items, "expected calendar catalog to yield items"
    for item in items:
        for key in ("anatomy", "where_to_obtain", "common_errors"):
            assert key in item, f"missing field {key} on calendar item {item.get('code')}"
        assert isinstance(item["anatomy"], str) and item["anatomy"], item["code"]
        assert (
            isinstance(item["where_to_obtain"], str) and item["where_to_obtain"]
        ), item["code"]
        assert isinstance(item["common_errors"], list) and item["common_errors"], item[
            "code"
        ]
        # Every bullet is a non-empty string.
        for bullet in item["common_errors"]:
            assert isinstance(bullet, str) and bullet, item["code"]


def test_calendar_priority_items_carry_authored_per_doc_overrides(
    api_client: TestClient,
) -> None:
    """The five high-volume recurring items the handoff calls out
    (IMSS opinion / INFONAVIT certificate / ISR mensual / SAT acuse
    anual / STPS cuatrimestral) must carry per-doc overrides — not
    the institution fallback."""
    ws = _setup_workspace(api_client)
    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/calendar?year=2026"
    ).json()
    items = [
        item
        for month in body["months"]
        for inst in month["institutions"]
        for item in inst["items"]
    ]

    expected_overrides = [
        ("imss", "Cuotas obrero patronales", "comprobante de pago bancario"),
        ("infonavit", "Cuotas obrero patronales", "5 %"),
        ("sat", "Declaración ISR por retención sueldos y salarios", "ISR retenido"),
        ("sat", "Acuse declaración anual de impuestos", "ejercicio fiscal anterior"),
        ("stps_repse", "Acuse SISUB", "SISUB"),
        ("stps_repse", "Acuse ICSOE", "ICSOE"),
    ]
    for institution, name, marker in expected_overrides:
        match = next(
            (
                item
                for item in items
                if item["name"] == name
                and any(
                    inst["institution"] == institution
                    and any(i["code"] == item["code"] for i in inst["items"])
                    for month in body["months"]
                    for inst in month["institutions"]
                )
            ),
            None,
        )
        assert match is not None, f"missing {institution}/{name} in calendar items"
        assert marker.lower() in match["anatomy"].lower(), (
            f"{institution}/{name} anatomy missing override marker '{marker}': "
            f"{match['anatomy']}"
        )
        # Per-doc overrides ship 5 bullets; institution fallbacks ship 2-3.
        assert len(match["common_errors"]) >= 5, (
            f"{institution}/{name} expected per-doc common_errors (>=5), "
            f"got {len(match['common_errors'])}"
        )


def test_calendar_guidance_no_engineer_dialect_leaks(
    api_client: TestClient,
) -> None:
    """The first-upload guidance copy must never carry the engineer
    dialect the transcript T9 + Stage 2.6 pass swept out of the
    validation summary."""
    ws = _setup_workspace(api_client)
    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/calendar?year=2026"
    ).json()
    items = [
        item
        for month in body["months"]
        for inst in month["institutions"]
        for item in inst["items"]
    ]
    banned = ("SHA-256", "hash", "OCR", "anomaly", "pipeline", "parser")
    for item in items:
        haystack = " ".join(
            [
                item["anatomy"],
                item["where_to_obtain"],
                " ".join(item["common_errors"]),
            ]
        ).lower()
        for term in banned:
            assert term.lower() not in haystack, (
                f"engineer dialect '{term}' leaked into calendar item {item['code']}"
            )


def test_recurring_catalog_helpers_resolve_in_priority_order() -> None:
    """The accessor functions resolve instance value → per-doc override →
    institution default. The instance value always wins when present."""
    from app.core.compliance_catalog import (
        RecurringRequirement,
        recurring_anatomy,
        recurring_common_errors,
        recurring_where_to_obtain,
    )

    # Instance value beats everything else.
    explicit = RecurringRequirement(
        code="REC-IMSS-TEST",
        name="Cuotas obrero patronales",
        institution="imss",
        frequency="mensual",
        due_month=1,
        period_label="IMSS Test",
        period_key="2026-M01",
        anatomy="Override desde la instancia.",
        where_to_obtain="Súbelo desde la prueba.",
        common_errors=("Solo un bullet de prueba.",),
    )
    assert recurring_anatomy(explicit) == "Override desde la instancia."
    assert recurring_where_to_obtain(explicit) == "Súbelo desde la prueba."
    assert recurring_common_errors(explicit) == ("Solo un bullet de prueba.",)

    # No instance value → per-doc override applies.
    generated = next(
        r
        for r in recurring_for_year(2026)
        if r.institution == "imss" and r.name == "Cuotas obrero patronales"
    )
    assert recurring_anatomy(generated)  # non-empty
    # Per-doc override talks about "comprobante de pago bancario"; the
    # institution default does not.
    assert "comprobante de pago bancario" in recurring_anatomy(generated).lower()
    # The "cédula" wording lives in the override's common_errors.
    assert any(
        "cédula" in bullet.lower() for bullet in recurring_common_errors(generated)
    )
    assert len(recurring_common_errors(generated)) >= 5

    # No instance, no per-doc override → institution default applies.
    generated_fallback = next(
        r
        for r in recurring_for_year(2026)
        if r.institution == "sat" and r.name == "Declaración IVA"
    )
    assert recurring_anatomy(generated_fallback)  # institution default is non-empty
    # Institution defaults are shorter than per-doc overrides.
    assert 2 <= len(recurring_common_errors(generated_fallback)) <= 4
