"""Catalog v2 — slot resolver + calendar endpoint integration (Session 2).

Pins the load-bearing v2 wiring that lets the recurring catalog
collapse from ~139 rows/year to ~34 without breaking historical
submissions:

* ``build_workspace_calendar_slots`` branches on
  ``settings.RECURRING_CATALOG_V2``. With the flag on it iterates the
  v2 generator and matches submissions via a compatibility join keyed
  by ``(institution_code, period_key)`` instead of
  ``(requirement_code, period_key)`` — so a legacy v1-coded submission
  like ``REC-IMSS-2026-01-comprobante-de-pago-bancario`` still counts
  toward the collapsed ``REC-IMSS-2026-01`` slot.

* ``GET /api/v1/portal/workspaces/{id}/calendar`` keeps its v1 shape
  when the flag is off (~50 items per month) and emits the v2 shape
  (~3 items per month, each carrying ``accepts_documents`` and
  ``minimum_documents``) when the flag is on.

* ``db.seed`` populates Requirement rows for BOTH catalog shapes so
  the submission write path can resolve either code namespace at any
  point — flag flip becomes a config change, not a DB migration.
"""

from __future__ import annotations

import itertools
from collections.abc import Generator
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.seed import seed_catalog
from app.db.session import get_db
from app.main import app
from app.models import (
    Client,
    ProviderWorkspace,
    Requirement,
    User,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password, issue_access_token


@pytest.fixture
def api_client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    previous_storage = settings.LOCAL_STORAGE_PATH
    settings.LOCAL_STORAGE_PATH = str(tmp_path / "storage")
    previous_flag = settings.RECURRING_CATALOG_V2

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.app.state.testing_session = testing_session  # type: ignore[attr-defined]

    # Seed the catalog so Requirement rows exist for both v1 and v2.
    bootstrap = testing_session()
    try:
        seed_catalog(bootstrap, years=(2026,))
        bootstrap.commit()
    finally:
        bootstrap.close()

    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        settings.LOCAL_STORAGE_PATH = previous_storage
        settings.RECURRING_CATALOG_V2 = previous_flag


def _pdf_bytes() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


_user_seq = itertools.count(1)


def _setup_workspace(api_client: TestClient) -> dict:
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        seq = next(_user_seq)
        user = User(
            email=f"v2slots-{seq}@checkwise.test",
            password_hash=hash_password("CheckWiseTest!2026"),
            full_name=f"Slot Tester {seq}",
            status="active",
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        client_row = db.query(Client).filter_by(name="Cliente V2 Slots").first()
        if client_row is None:
            client_row = Client(name="Cliente V2 Slots")
            db.add(client_row)
            db.flush()
        vendor = Vendor(
            client_id=client_row.id,
            name=f"Slot Vendor {seq}",
            rfc=f"SLT2605{seq:02d}AB1",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        workspace = ProviderWorkspace(
            client_id=client_row.id,
            vendor_id=vendor.id,
            owner_user_id=user.id,
            persona_type="moral",
            display_name=vendor.name,
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
    return {"workspace_id": ws_id, "bearer": token}


def _upload_v1_iemss_january(api_client: TestClient, ws_id: str) -> str:
    """Submit a legacy v1-coded IMSS January upload (covers Dec 2025)."""
    data = {
        "period_code": "2025-12",
        "period_key": "2025-M12",
        "load_type": "mensual",
        "institution_code": "imss",
        "requirement_name": "Comprobante de pago bancario",
        "requirement_code": "REC-IMSS-2026-01-comprobante-de-pago-bancario",
        "initial_status": "pendiente_revision",
    }
    response = api_client.post(
        f"/api/v1/portal/workspaces/{ws_id}/submissions",
        data=data,
        files={"file": ("comprobante.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 202, response.text
    return response.json()["submission_id"]


# ---------------------------------------------------------------------------
# Seeding both catalogs
# ---------------------------------------------------------------------------


def test_seed_populates_both_v1_and_v2_requirement_codes(
    api_client: TestClient,
) -> None:
    """After the seed runs, the Requirement table contains both
    code namespaces. Either path (v1 or v2 submission) can resolve."""
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        codes = set(db.scalars(select(Requirement.code)).all())
    finally:
        db.close()

    v1_imss_jan = "REC-IMSS-2026-01-cuotas-obrero-patronales"
    v2_imss_jan = "REC-IMSS-2026-01"
    assert v1_imss_jan in codes
    assert v2_imss_jan in codes


# ---------------------------------------------------------------------------
# v1 behavior unchanged with flag off
# ---------------------------------------------------------------------------


def test_calendar_returns_v1_shape_when_flag_off(api_client: TestClient) -> None:
    settings.RECURRING_CATALOG_V2 = False
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
    # v1 ships ~139 items/year. Confirm we still emit per-doc rows.
    assert len(items) == 139
    # Per-doc codes carry a slug suffix.
    assert any(
        item["code"] == "REC-IMSS-2026-01-cuotas-obrero-patronales"
        for item in items
    )
    # accepts_documents stays an empty list on v1 rows.
    for item in items:
        assert item["accepts_documents"] == []
        assert item["minimum_documents"] == "one"


# ---------------------------------------------------------------------------
# v2 shape when flag on
# ---------------------------------------------------------------------------


def test_calendar_returns_v2_shape_when_flag_on(api_client: TestClient) -> None:
    settings.RECURRING_CATALOG_V2 = True
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
    # v2 collapses to 34 rows/year.
    assert len(items) == 34
    # IMSS January row uses the v2 code shape (no per-doc suffix).
    imss_jan = next(
        item
        for item in items
        if item["code"] == "REC-IMSS-2026-01"
    )
    # Carries the four alternative doc types.
    assert len(imss_jan["accepts_documents"]) == 4
    accepted_names = {entry["name"] for entry in imss_jan["accepts_documents"]}
    assert "Comprobante de pago bancario" in accepted_names
    assert "CFDI de pago de cuotas" in accepted_names
    assert imss_jan["minimum_documents"] == "one"
    # Per-doc anatomy / where_to_obtain / common_errors come through.
    for entry in imss_jan["accepts_documents"]:
        assert entry["anatomy"]
        assert entry["where_to_obtain"]
        assert entry["common_errors"]


def test_v2_calendar_includes_stps_either_or_both_row(
    api_client: TestClient,
) -> None:
    """The classic 'either / or / both' obligation — STPS SISUB +
    ICSOE. Provider can submit one, the other, or both; the v2 row
    must list both in accepts_documents."""
    settings.RECURRING_CATALOG_V2 = True
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
    stps_rows = [item for item in items if item["code"].startswith("REC-STPS-")]
    assert len(stps_rows) == 3  # 3 cuatrimestres
    sample = stps_rows[0]
    accepted_names = {entry["name"] for entry in sample["accepts_documents"]}
    assert accepted_names == {"Acuse SISUB", "Acuse ICSOE"}


# ---------------------------------------------------------------------------
# Compatibility join — legacy v1 submission satisfies v2 slot
# ---------------------------------------------------------------------------


def test_legacy_v1_submission_satisfies_v2_slot_after_flag_flip(
    api_client: TestClient,
) -> None:
    """The load-bearing compatibility guarantee. A provider submitted
    an IMSS January upload under the legacy v1 code
    ``REC-IMSS-2026-01-comprobante-de-pago-bancario`` (period_key
    ``2025-M12``). After the flag flips and the calendar shows the
    collapsed ``REC-IMSS-2026-01`` row, that submission must still
    count toward the v2 slot — otherwise months of provider work
    suddenly appears unsubmitted."""
    # Submit under v1 first (flag off → wizard targets legacy codes).
    settings.RECURRING_CATALOG_V2 = False
    ws = _setup_workspace(api_client)
    submission_id = _upload_v1_iemss_january(api_client, ws["workspace_id"])
    assert submission_id

    # Now flip the flag and reload the calendar.
    settings.RECURRING_CATALOG_V2 = True
    body = api_client.get(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/calendar?year=2026"
    ).json()
    items = [
        item
        for month in body["months"]
        for inst in month["institutions"]
        for item in inst["items"]
    ]
    imss_jan_v2 = next(
        item
        for item in items
        if item["code"] == "REC-IMSS-2026-01"
    )
    # The collapsed v2 row picked up the legacy v1 submission.
    assert imss_jan_v2["submission_id"] == submission_id, (
        "v2 compatibility join failed: legacy v1 submission "
        f"{submission_id} did not surface on the v2 IMSS January slot"
    )
    # Status reflects the underlying submission, not 'pendiente'.
    assert imss_jan_v2["status"] != "pendiente"


# ---------------------------------------------------------------------------
# Persona filter still works
# ---------------------------------------------------------------------------


def test_v2_calendar_respects_persona_type(api_client: TestClient) -> None:
    """A persona moral and a persona fisica workspace should both see
    the same v2 row set (recurring obligations apply to both per v2's
    persona_types=("moral", "fisica") defaults)."""
    settings.RECURRING_CATALOG_V2 = True
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
    assert len(items) == 34
