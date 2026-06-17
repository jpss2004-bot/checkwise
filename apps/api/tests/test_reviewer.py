from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Client,
    Document,
    DocumentInspection,
    DocumentStatusHistory,
    Institution,
    Membership,
    Organization,
    Period,
    Requirement,
    RequirementVersion,
    Submission,
    User,
    ValidationEvent,
    Vendor,
    entities,  # noqa: F401
)
from app.models.entities import utc_now
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def api_client(db_factory) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_user(
    db_factory,
    *,
    email: str,
    role: str | None,
    full_name: str = "Test User",
    password: str = "Hunter2 Correct horse",
) -> tuple[str, str | None, str]:
    """Returns (user_id, org_id_or_None, password)."""
    db = db_factory()
    try:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            status="active",
        )
        db.add(user)
        db.flush()
        org_id: str | None = None
        if role is not None:
            org = Organization(name="LegalShelf", kind="internal")
            db.add(org)
            db.flush()
            org_id = org.id
            db.add(
                Membership(
                    user_id=user.id,
                    organization_id=org.id,
                    role=role,
                    status="active",
                )
            )
        db.commit()
        return user.id, org_id, password
    finally:
        db.close()


_SEED_COUNTER = 0


def _seed_submission(
    db_factory,
    *,
    status_: str = "pendiente_revision",
    requirement_code: str = "sat:declaracion_iva:mensual",
    institution_code: str = "sat",
    period_key: str = "2026-M03",
    requirement_name: str = "Declaración mensual de IVA",
    age_hours: int = 6,
    authenticity_risk: str | None = None,
    risk_reasons: list | None = None,
    forensics: dict | None = None,
    verification: dict | None = None,
    rfc_alignment: str | None = None,
) -> str:
    """Inserts the minimum row graph needed for a reviewer queue item.

    Each call mints unique RFC / requirement code suffixes so the same
    test can seed multiple submissions without unique-constraint
    clashes. Passing ``authenticity_risk`` also creates the
    ``DocumentInspection`` row carrying the Phase-A forensics verdict;
    by default no inspection row exists (legacy / pre-forensics shape).
    """
    global _SEED_COUNTER
    _SEED_COUNTER += 1
    suffix = _SEED_COUNTER
    rfc_suffix = f"{suffix:03d}"

    db = db_factory()
    try:
        client_rfc = f"CL{rfc_suffix}260101AB"[:13]
        client = Client(name=f"Cliente Reviewer Test {suffix}", rfc=client_rfc)
        db.add(client)
        db.flush()
        vendor_rfc = f"VD{rfc_suffix}260101XY"[:13]
        vendor = Vendor(client_id=client.id, name=f"Servicios Reviewer {suffix}", rfc=vendor_rfc)
        db.add(vendor)
        db.flush()
        institution = db.scalar(
            select(Institution).where(Institution.code == institution_code)
        )
        if institution is None:
            institution = Institution(code=institution_code, name=institution_code.upper())
            db.add(institution)
            db.flush()
        requirement = db.scalar(
            select(Requirement).where(Requirement.code == requirement_code)
        )
        if requirement is None:
            requirement = Requirement(
                code=requirement_code,
                name=requirement_name,
                institution_id=institution.id,
                load_type="mensual",
                frequency="mensual",
                risk_level="medium",
                current_version=1,
            )
            db.add(requirement)
            db.flush()
            req_version = RequirementVersion(
                requirement_id=requirement.id,
                version=1,
            )
            db.add(req_version)
            db.flush()
        else:
            req_version = db.scalar(
                select(RequirementVersion).where(
                    RequirementVersion.requirement_id == requirement.id
                )
            )
            assert req_version is not None
        # Period uniqueness is on (code, period_type). Derive code from the
        # canonical key to keep multiple seeded periods distinct in one test.
        period = db.scalar(
            select(Period).where(
                Period.code == period_key, Period.period_type == "mensual"
            )
        )
        if period is None:
            period = Period(
                code=period_key,
                year=2026,
                month=int(period_key.split("-M")[-1]) if "-M" in period_key else None,
                period_type="mensual",
                period_key=period_key,
            )
            db.add(period)
            db.flush()
        # Pin submitted_at to a known age for queue-age assertions.
        submitted_at = utc_now() - timedelta(hours=age_hours)
        submission = Submission(
            client_id=client.id,
            vendor_id=vendor.id,
            institution_id=institution.id,
            requirement_id=requirement.id,
            requirement_version_id=req_version.id,
            period_id=period.id,
            status=status_,
            load_type="mensual",
            requirement_code=requirement_code,
            period_key=period_key,
            created_at=submitted_at,
            updated_at=submitted_at,
        )
        db.add(submission)
        db.flush()
        document = Document(
            submission_id=submission.id,
            storage_key=f"local://qa/{submission.id}.pdf",
            original_filename="qa.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            sha256="a" * 64,
        )
        db.add(document)
        if (
            authenticity_risk is not None
            or verification is not None
            or rfc_alignment is not None
        ):
            db.flush()
            db.add(
                DocumentInspection(
                    document_id=document.id,
                    is_pdf=True,
                    authenticity_risk=authenticity_risk,
                    risk_reasons=risk_reasons,
                    forensics=forensics,
                    verification=verification,
                    expected_rfc=vendor.rfc,
                    rfc_alignment=rfc_alignment,
                )
            )
        db.commit()
        return submission.id
    finally:
        db.close()


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


def test_queue_requires_authentication(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/reviewer/queue")
    assert response.status_code == 401


def test_queue_denies_user_without_reviewer_or_admin(
    api_client: TestClient, db_factory
) -> None:
    # User exists but has no role memberships.
    _seed_user(db_factory, email="nobody@x.mx", role=None)
    token = _login(api_client, "nobody@x.mx", "Hunter2 Correct horse")
    response = api_client.get(
        "/api/v1/reviewer/queue", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


def test_queue_accepts_reviewer_role(api_client: TestClient, db_factory) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    response = api_client.get(
        "/api/v1/reviewer/queue", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200


def test_queue_accepts_internal_admin_role(api_client: TestClient, db_factory) -> None:
    _seed_user(db_factory, email="adm@x.mx", role="internal_admin")
    token = _login(api_client, "adm@x.mx", "Hunter2 Correct horse")
    response = api_client.get(
        "/api/v1/reviewer/queue", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Queue behaviour
# ---------------------------------------------------------------------------


def test_queue_returns_only_review_states(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")

    in_queue_id = _seed_submission(db_factory, status_="pendiente_revision")
    _seed_submission(
        db_factory,
        status_="aprobado",
        requirement_code="sat:other:mensual",
        period_key="2026-M02",
    )
    _seed_submission(
        db_factory,
        status_="requiere_aclaracion",
        requirement_code="sat:other:mensual",
        period_key="2026-M01",
    )

    response = api_client.get(
        "/api/v1/reviewer/queue", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    ids = [item["submission_id"] for item in payload["items"]]
    assert ids == [in_queue_id]
    assert payload["total"] == 1


def test_queue_orders_oldest_first(api_client: TestClient, db_factory) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    newer = _seed_submission(db_factory, age_hours=1, period_key="2026-M01")
    older = _seed_submission(db_factory, age_hours=48, period_key="2026-M02")
    response = api_client.get(
        "/api/v1/reviewer/queue", headers={"Authorization": f"Bearer {token}"}
    )
    payload = response.json()
    ids = [item["submission_id"] for item in payload["items"]]
    assert ids == [older, newer]
    # age_hours rounding (// 3600) — be lenient on the boundary.
    older_item = payload["items"][0]
    assert older_item["age_hours"] >= 47


def test_queue_filter_by_status(api_client: TestClient, db_factory) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    _seed_submission(db_factory, status_="pendiente_revision", period_key="2026-M01")
    mismatch_id = _seed_submission(
        db_factory, status_="posible_mismatch", period_key="2026-M02"
    )

    response = api_client.get(
        "/api/v1/reviewer/queue",
        params={"status": "posible_mismatch"},
        headers={"Authorization": f"Bearer {token}"},
    )
    payload = response.json()
    assert {item["submission_id"] for item in payload["items"]} == {mismatch_id}


def test_queue_filter_by_institution(api_client: TestClient, db_factory) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    sat_id = _seed_submission(
        db_factory, institution_code="sat", period_key="2026-M01"
    )
    _seed_submission(
        db_factory, institution_code="imss", period_key="2026-M02"
    )

    response = api_client.get(
        "/api/v1/reviewer/queue",
        params={"institution": "sat"},
        headers={"Authorization": f"Bearer {token}"},
    )
    payload = response.json()
    assert {item["submission_id"] for item in payload["items"]} == {sat_id}


def test_queue_filters_by_client_and_vendor(api_client: TestClient, db_factory) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    first_id = _seed_submission(db_factory, period_key="2026-M01")
    second_id = _seed_submission(db_factory, period_key="2026-M02")
    db = db_factory()
    try:
        first = db.get(Submission, first_id)
        second = db.get(Submission, second_id)
        assert first is not None and second is not None
        client_id = first.client_id
        vendor_id = first.vendor_id
    finally:
        db.close()

    by_client = api_client.get(
        "/api/v1/reviewer/queue",
        params={"client_id": client_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    by_vendor = api_client.get(
        "/api/v1/reviewer/queue",
        params={"vendor_id": vendor_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert by_client.status_code == 200, by_client.text
    assert by_vendor.status_code == 200, by_vendor.text
    assert {item["submission_id"] for item in by_client.json()["items"]} == {first_id}
    assert {item["submission_id"] for item in by_vendor.json()["items"]} == {first_id}


def test_queue_facets_are_scoped_to_actionable_rows(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    actionable_id = _seed_submission(db_factory, period_key="2026-M01")
    terminal_id = _seed_submission(
        db_factory,
        period_key="2026-M02",
        status_="aprobado",
    )
    db = db_factory()
    try:
        actionable = db.get(Submission, actionable_id)
        terminal = db.get(Submission, terminal_id)
        assert actionable is not None and terminal is not None
        actionable_client_id = actionable.client_id
        actionable_vendor_id = actionable.vendor_id
        terminal_client_id = terminal.client_id
        terminal_vendor_id = terminal.vendor_id
    finally:
        db.close()

    response = api_client.get(
        "/api/v1/reviewer/queue/facets",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert {client["id"] for client in payload["clients"]} == {actionable_client_id}
    assert {vendor["id"] for vendor in payload["vendors"]} == {actionable_vendor_id}
    assert terminal_client_id not in {client["id"] for client in payload["clients"]}
    assert terminal_vendor_id not in {vendor["id"] for vendor in payload["vendors"]}


def test_queue_facets_client_scoped_includes_idle_providers(
    api_client: TestClient, db_factory
) -> None:
    """P0-02: selecting a client must surface ALL of its active providers —
    including one with no queue item — sourced from the Vendor↔Client link,
    not just providers that happen to have an actionable submission. Without a
    client selected the list stays actionable-scoped (bounded)."""
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    actionable_id = _seed_submission(db_factory, period_key="2026-M01")

    db = db_factory()
    try:
        actionable = db.get(Submission, actionable_id)
        assert actionable is not None
        client_id = actionable.client_id
        busy_vendor_id = actionable.vendor_id
        # An idle provider under the SAME client — no submission at all.
        idle_vendor = Vendor(
            client_id=client_id,
            name="Proveedor sin movimientos",
            rfc="IDLE010101AAA",
        )
        db.add(idle_vendor)
        db.commit()
        idle_vendor_id = idle_vendor.id
    finally:
        db.close()

    # Unscoped: only the provider with an actionable row appears.
    unscoped = api_client.get(
        "/api/v1/reviewer/queue/facets",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    unscoped_vendor_ids = {v["id"] for v in unscoped["vendors"]}
    assert busy_vendor_id in unscoped_vendor_ids
    assert idle_vendor_id not in unscoped_vendor_ids

    # Client-scoped: BOTH providers appear — the link table, not queue activity.
    scoped = api_client.get(
        "/api/v1/reviewer/queue/facets",
        params={"client_id": client_id},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    scoped_vendor_ids = {v["id"] for v in scoped["vendors"]}
    assert busy_vendor_id in scoped_vendor_ids
    assert idle_vendor_id in scoped_vendor_ids


# ---------------------------------------------------------------------------
# Authenticity verdict (document-revalidation Phase A)
# ---------------------------------------------------------------------------


_SAMPLE_REASONS = [
    {
        "code": "suspicious_generator",
        "severity": "medium",
        "detail_es": (
            "Generado con Canva — los documentos oficiales no se "
            "producen con editores de diseño."
        ),
    }
]
_SAMPLE_FORENSICS = {"producer": "Canva", "eof_count": 1, "has_javascript": False}


def test_queue_exposes_authenticity_risk(api_client: TestClient, db_factory) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    flagged_id = _seed_submission(
        db_factory, period_key="2026-M01", authenticity_risk="high_risk"
    )
    legacy_id = _seed_submission(db_factory, period_key="2026-M02")

    response = api_client.get(
        "/api/v1/reviewer/queue", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    by_id = {item["submission_id"]: item for item in response.json()["items"]}
    assert by_id[flagged_id]["authenticity_risk"] == "high_risk"
    # Legacy row without inspection → not analyzed → null, not "clean".
    assert by_id[legacy_id]["authenticity_risk"] is None


def test_queue_filters_by_risk(api_client: TestClient, db_factory) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    _seed_submission(db_factory, period_key="2026-M01", authenticity_risk="clean")
    risky_id = _seed_submission(
        db_factory, period_key="2026-M02", authenticity_risk="high_risk"
    )
    _seed_submission(db_factory, period_key="2026-M03")  # not analyzed

    response = api_client.get(
        "/api/v1/reviewer/queue",
        params={"risk": "high_risk"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert {item["submission_id"] for item in payload["items"]} == {risky_id}
    assert payload["total"] == 1


def test_queue_exposes_and_filters_by_rfc_alignment(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    _seed_submission(db_factory, period_key="2026-M01", rfc_alignment="match")
    mismatch_id = _seed_submission(
        db_factory,
        period_key="2026-M02",
        rfc_alignment="mismatch",
    )

    response = api_client.get(
        "/api/v1/reviewer/queue",
        params={"rfc": "mismatch"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert {item["submission_id"] for item in payload["items"]} == {mismatch_id}
    assert payload["items"][0]["rfc_alignment"] == "mismatch"
    assert payload["total"] == 1


def test_queue_rejects_unknown_risk_value(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    response = api_client.get(
        "/api/v1/reviewer/queue",
        params={"risk": "muy_sospechoso"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_detail_includes_authenticity_block(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    submission_id = _seed_submission(
        db_factory,
        authenticity_risk="suspicious",
        risk_reasons=_SAMPLE_REASONS,
        forensics=_SAMPLE_FORENSICS,
    )
    response = api_client.get(
        f"/api/v1/reviewer/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    authenticity = response.json()["authenticity"]
    assert authenticity == {
        "risk": "suspicious",
        "reasons": _SAMPLE_REASONS,
        "forensics": _SAMPLE_FORENSICS,
        "analyzed": True,
    }


def test_detail_authenticity_unanalyzed_for_legacy_rows(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    submission_id = _seed_submission(db_factory)  # no inspection row at all
    response = api_client.get(
        f"/api/v1/reviewer/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    authenticity = response.json()["authenticity"]
    assert authenticity == {
        "risk": None,
        "reasons": [],
        "forensics": None,
        "analyzed": False,
    }


_SAMPLE_VERIFICATION = {
    "qr_codes": [
        {
            "page": 1,
            "content": "https://verificacfdi.facturaelectronica.sat.gob.mx/x?id=1",
            "is_url": True,
            "host": "verificacfdi.facturaelectronica.sat.gob.mx",
            "official": True,
            "institution_guess": "sat",
        }
    ],
    "folios": [{"kind": "cfdi_uuid", "value": "AD662D33-6934-459C-A128-BDF0393E0F44"}],
    "pages_scanned": 1,
    "images_scanned": 2,
    "error": None,
}


def test_detail_includes_verification_block(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    submission_id = _seed_submission(
        db_factory,
        authenticity_risk="clean",
        risk_reasons=[],
        verification=_SAMPLE_VERIFICATION,
    )
    response = api_client.get(
        f"/api/v1/reviewer/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    verification = response.json()["verification"]
    assert verification == {
        "qr_codes": _SAMPLE_VERIFICATION["qr_codes"],
        "folios": _SAMPLE_VERIFICATION["folios"],
        "analyzed": True,
    }


def test_detail_verification_empty_for_legacy_rows(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    # Inspection row predating Phase B: authenticity present, NULL
    # verification column.
    submission_id = _seed_submission(db_factory, authenticity_risk="clean")
    response = api_client.get(
        f"/api/v1/reviewer/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["verification"] == {
        "qr_codes": [],
        "folios": [],
        "analyzed": False,
    }


def test_detail_verification_absent_inspection_row(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    submission_id = _seed_submission(db_factory)  # no inspection row at all
    response = api_client.get(
        f"/api/v1/reviewer/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["verification"] == {
        "qr_codes": [],
        "folios": [],
        "analyzed": False,
    }


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


def test_detail_returns_submission(api_client: TestClient, db_factory) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    submission_id = _seed_submission(db_factory)
    response = api_client.get(
        f"/api/v1/reviewer/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["submission_id"] == submission_id
    assert payload["status"] == "pendiente_revision"
    assert payload["requirement"]["name"] == "Declaración mensual de IVA"


def test_detail_404_for_unknown_submission(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    response = api_client.get(
        "/api/v1/reviewer/submissions/does-not-exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action,expected_status",
    [
        ("approve", "aprobado"),
        ("reject", "rechazado"),
        ("request_clarification", "requiere_aclaracion"),
        ("mark_exception", "excepcion_legal"),
    ],
)
def test_decision_transitions_status(
    api_client: TestClient, db_factory, action: str, expected_status: str
) -> None:
    user_id, _, password = _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", password)
    submission_id = _seed_submission(db_factory)
    body = {"action": action}
    if action != "approve":
        body["reason"] = "Documento ilegible en la página 2"

    response = api_client.post(
        f"/api/v1/reviewer/submissions/{submission_id}/decision",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["new_status"] == expected_status
    assert payload["previous_status"] == "pendiente_revision"
    assert payload["action"] == action
    assert payload["reviewer_user_id"] == user_id

    # Database state.
    db = db_factory()
    try:
        sub = db.get(Submission, submission_id)
        assert sub is not None and sub.status == expected_status

        # History row written.
        history = db.scalars(
            select(DocumentStatusHistory).where(
                DocumentStatusHistory.submission_id == submission_id
            )
        ).all()
        assert any(
            h.to_status == expected_status and h.actor == f"reviewer:{user_id}"
            for h in history
        )

        # ValidationEvent row written.
        events = db.scalars(
            select(ValidationEvent).where(
                ValidationEvent.submission_id == submission_id,
                ValidationEvent.event_type == "reviewer_decision",
            )
        ).all()
        assert any(e.result == action and e.actor_type == "reviewer" for e in events)
    finally:
        db.close()


@pytest.mark.parametrize(
    "action",
    ["reject", "request_clarification", "mark_exception"],
)
def test_decision_requires_reason_for_non_approve(
    api_client: TestClient, db_factory, action: str
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    submission_id = _seed_submission(db_factory)
    response = api_client.post(
        f"/api/v1/reviewer/submissions/{submission_id}/decision",
        json={"action": action},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    # Whitespace-only reason is also rejected.
    response = api_client.post(
        f"/api/v1/reviewer/submissions/{submission_id}/decision",
        json={"action": action, "reason": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_decision_approve_does_not_require_reason(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    submission_id = _seed_submission(db_factory)
    response = api_client.post(
        f"/api/v1/reviewer/submissions/{submission_id}/decision",
        json={"action": "approve"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_decision_409_when_already_resolved(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    submission_id = _seed_submission(db_factory, status_="aprobado")
    response = api_client.post(
        f"/api/v1/reviewer/submissions/{submission_id}/decision",
        json={"action": "approve"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409


def test_decision_404_for_unknown_submission(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    response = api_client.post(
        "/api/v1/reviewer/submissions/does-not-exist/decision",
        json={"action": "approve"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_decision_requires_reviewer_role(api_client: TestClient, db_factory) -> None:
    _seed_user(db_factory, email="nobody@x.mx", role=None)
    token = _login(api_client, "nobody@x.mx", "Hunter2 Correct horse")
    submission_id = _seed_submission(db_factory)
    response = api_client.post(
        f"/api/v1/reviewer/submissions/{submission_id}/decision",
        json={"action": "approve"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Document preview / download (Junta 2026-05-23 — admin debe poder ver el PDF)
# ---------------------------------------------------------------------------


def test_document_endpoint_requires_reviewer_role(
    api_client: TestClient, db_factory
) -> None:
    """Without reviewer/admin membership the endpoint returns 403."""
    _seed_user(db_factory, email="outsider@x.mx", role=None)
    token = _login(api_client, "outsider@x.mx", "Hunter2 Correct horse")
    submission_id = _seed_submission(db_factory)
    response = api_client.get(
        f"/api/v1/reviewer/submissions/{submission_id}/document",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_document_endpoint_404_for_unknown_submission(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    response = api_client.get(
        "/api/v1/reviewer/submissions/no-such-thing/document",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_document_endpoint_404_when_storage_missing(
    api_client: TestClient, db_factory
) -> None:
    """The seed fixture writes a local:// storage key with no backing
    file; the endpoint should degrade to 404 instead of crashing."""
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    submission_id = _seed_submission(db_factory)
    response = api_client.get(
        f"/api/v1/reviewer/submissions/{submission_id}/document",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_document_endpoint_streams_non_ascii_filename(
    api_client: TestClient, db_factory, monkeypatch, tmp_path
) -> None:
    """Accented PDF names must not break preview/download headers."""
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    submission_id = _seed_submission(db_factory)
    storage_key = "documents/demo/liquidacion.pdf"
    filename = "ÁNGEL ELÍAS GARCÍA Liquidación.pdf"
    file_path = tmp_path / storage_key
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n")

    db = db_factory()
    try:
        document = db.scalar(
            select(Document).where(Document.submission_id == submission_id).limit(1)
        )
        assert document is not None
        document.storage_key = storage_key
        document.original_filename = filename
        db.commit()
    finally:
        db.close()

    response = api_client.get(
        f"/api/v1/reviewer/submissions/{submission_id}/document",
        params={"proxy": "1"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert "filename*=utf-8''" in response.headers["content-disposition"].lower()
    assert response.content.startswith(b"%PDF-")


# ---------------------------------------------------------------------------
# Queue pagination (keyset cursor)
# ---------------------------------------------------------------------------


def test_queue_total_reflects_all_matching_rows_and_sets_cursor(
    api_client: TestClient, db_factory
) -> None:
    """``total`` is the real filtered count (not len(items)) and
    ``next_cursor`` is populated when more rows remain past ``limit``."""
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    oldest = _seed_submission(db_factory, age_hours=30, period_key="2026-M01")
    middle = _seed_submission(db_factory, age_hours=20, period_key="2026-M02")
    _seed_submission(db_factory, age_hours=10, period_key="2026-M03")

    response = api_client.get(
        "/api/v1/reviewer/queue",
        params={"limit": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 3
    assert len(payload["items"]) == 2
    assert payload["total"] > len(payload["items"])
    assert [i["submission_id"] for i in payload["items"]] == [oldest, middle]
    assert payload["next_cursor"] is not None


def test_queue_cursor_walks_disjoint_pages_in_fifo_order(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    expected_fifo = [
        _seed_submission(db_factory, age_hours=50, period_key="2026-M01"),
        _seed_submission(db_factory, age_hours=40, period_key="2026-M02"),
        _seed_submission(db_factory, age_hours=30, period_key="2026-M03"),
        _seed_submission(db_factory, age_hours=20, period_key="2026-M04"),
        _seed_submission(db_factory, age_hours=10, period_key="2026-M05"),
    ]

    headers = {"Authorization": f"Bearer {token}"}
    collected: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        params: dict = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        response = api_client.get(
            "/api/v1/reviewer/queue", params=params, headers=headers
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["total"] == 5
        page_ids = [i["submission_id"] for i in payload["items"]]
        # Pages are disjoint.
        assert not set(page_ids) & set(collected)
        collected.extend(page_ids)
        cursor = payload["next_cursor"]
        pages += 1
        if cursor is None:
            break
        assert pages < 10, "cursor never terminated"

    assert pages == 3
    assert collected == expected_fifo


def test_queue_rejects_garbage_cursor(api_client: TestClient, db_factory) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    response = api_client.get(
        "/api/v1/reviewer/queue",
        params={"cursor": "no-es-un-cursor"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Detail — vendor identity block
# ---------------------------------------------------------------------------


def test_detail_includes_vendor_block_with_expected_rfc(
    api_client: TestClient, db_factory
) -> None:
    from app.models import ProviderWorkspace

    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    submission_id = _seed_submission(db_factory)

    # Look up the seeded vendor/client and tie them to a workspace.
    db = db_factory()
    try:
        sub = db.get(Submission, submission_id)
        assert sub is not None
        vendor = db.get(Vendor, sub.vendor_id)
        client_row = db.get(Client, sub.client_id)
        assert vendor is not None and client_row is not None
        vendor.persona_type = "moral"
        workspace = ProviderWorkspace(
            client_id=client_row.id,
            vendor_id=vendor.id,
            persona_type="moral",
            access_token=f"tok-{submission_id[:24]}",
        )
        db.add(workspace)
        db.commit()
        expected = {
            "vendor_id": vendor.id,
            "vendor_name": vendor.name,
            "vendor_rfc": vendor.rfc,
            "persona_type": "moral",
            "client_id": client_row.id,
            "client_name": client_row.name,
            "workspace_id": workspace.id,
        }
    finally:
        db.close()

    response = api_client.get(
        f"/api/v1/reviewer/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["vendor"] == expected


def test_detail_includes_prevalidation_evidence(
    api_client: TestClient, db_factory
) -> None:
    from app.services.submission_service import PREVALIDATION_EVIDENCE_METADATA_KEY

    _seed_user(db_factory, email="rev-evidence@x.mx", role="reviewer")
    token = _login(api_client, "rev-evidence@x.mx", "Hunter2 Correct horse")
    submission_id = _seed_submission(db_factory, rfc_alignment="match")

    evidence = {
        "version": "prevalidation_evidence.v1",
        "expected": {
            "provider": {"name": "Servicios Reviewer", "rfc": "ABC010203XY1"},
            "requirement": {
                "name": "Resumen de liquidación IMSS",
                "institution": "imss",
                "document_type": "imss_liquidacion",
                "period": "2026-01",
            },
        },
        "extracted": {
            "institution": "imss",
            "document_type": "imss_liquidacion",
            "identifiers": {"rfcs": ["ABC010203XY1"]},
        },
        "alignment": {"provider_identity": "match", "period": "match"},
        "scores": {"requirement_match_confidence": 0.97},
        "findings": [],
    }
    db = db_factory()
    try:
        document = db.scalar(
            select(Document).where(Document.submission_id == submission_id).limit(1)
        )
        assert document is not None
        inspection = db.scalar(
            select(DocumentInspection)
            .where(DocumentInspection.document_id == document.id)
            .limit(1)
        )
        assert inspection is not None
        inspection.raw_metadata = {PREVALIDATION_EVIDENCE_METADATA_KEY: evidence}
        db.commit()
    finally:
        db.close()

    response = api_client.get(
        f"/api/v1/reviewer/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["prevalidation_evidence"]["version"] == "prevalidation_evidence.v1"
    assert (
        payload["prevalidation_evidence"]["alignment"]["provider_identity"]
        == "match"
    )


# ---------------------------------------------------------------------------
# Decision — next-pending pointer
# ---------------------------------------------------------------------------


def test_decision_returns_next_pending_submission_id(
    api_client: TestClient, db_factory
) -> None:
    _seed_user(db_factory, email="rev@x.mx", role="reviewer")
    token = _login(api_client, "rev@x.mx", "Hunter2 Correct horse")
    older = _seed_submission(db_factory, age_hours=48, period_key="2026-M01")
    newer = _seed_submission(db_factory, age_hours=2, period_key="2026-M02")
    headers = {"Authorization": f"Bearer {token}"}

    # Deciding the older one points at the remaining (newer) item.
    response = api_client.post(
        f"/api/v1/reviewer/submissions/{older}/decision",
        json={"action": "approve"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["next_pending_submission_id"] == newer

    # Deciding the last one drains the queue -> None.
    response = api_client.post(
        f"/api/v1/reviewer/submissions/{newer}/decision",
        json={"action": "reject", "reason": "Documento ilegible"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["next_pending_submission_id"] is None
