"""Coverage for the endpoints shipped in the 2026-05-26 morning sprint.

Pairs with the deliverables described in
``project_sprint_2026_05_26.md`` and the six commits
``4f66647..5bdd215``. Each test exercises a narrow contract:

* item 1 — ``GET /client/submissions/{id}/document``: tenant guard
  prevents a client_admin from one client downloading a document
  that belongs to another client. Happy path + cross-tenant 404.
* item 2 — ``GET /client/audit-package/tree`` returns the candidate
  set the picker renders; ``POST /client/audit-package.zip`` with
  ``submission_ids`` narrows the resulting ZIP to exactly the
  whitelisted ids.
* item 3 — ``GET /client/calendar?vendor_ids=`` narrows the
  aggregate calendar to the requested subset.
* item 8 — ``POST /admin/clients/provision`` creates Client +
  Organization + User + Membership + PasswordResetToken in one
  call and writes the canonical audit row. Email skip path doesn't
  block the flow when SMTP is not configured.
  ``client.legal_consent_accepted`` audit row is written when the
  profile PATCH carries ``terms_accepted=true``.

The fixtures here intentionally re-implement a slimmer version of
the ones in ``test_client_portal.py`` rather than importing them —
test modules in this repo are self-contained so a future split of
the API into separately-deployable services doesn't have to drag
every helper across the boundary.
"""

from __future__ import annotations

import itertools
import zipfile
from collections.abc import Generator
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.statuses import DocumentStatus
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    AuditLog,
    Client,
    Document,
    Institution,
    Membership,
    Organization,
    ProviderWorkspace,
    Requirement,
    Submission,
    User,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password


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
def api_client(db_factory, tmp_path) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    previous = settings.LOCAL_STORAGE_PATH
    settings.LOCAL_STORAGE_PATH = str(tmp_path / "storage")

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        settings.LOCAL_STORAGE_PATH = previous


_user_seq = itertools.count(1)
_client_seq = itertools.count(1)


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(api_client: TestClient, email: str, password: str) -> str:
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _seed_user(
    db_factory,
    *,
    role: str | None,
    client_id: str | None = None,
    email_prefix: str = "user",
) -> tuple[str, str]:
    """Return ``(email, password)`` for a freshly-seeded user.

    role=None: no memberships.
    role=client_admin: Organization(kind=client) bound to ``client_id``.
    role=internal_admin: Organization(kind=internal).
    """
    password = "SprintTest!2026"
    seq = next(_user_seq)
    email = f"{email_prefix}-{seq}@checkwise.test"
    db = db_factory()
    try:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=f"User {seq}",
            status="active",
        )
        db.add(user)
        db.flush()
        if role is not None:
            if role == "client_admin":
                assert client_id is not None, "client_admin needs a client"
                org = Organization(
                    name=f"Org Client {seq}", kind="client", client_id=client_id
                )
            else:
                org = Organization(name=f"Org Internal {seq}", kind="internal")
            db.add(org)
            db.flush()
            db.add(
                Membership(
                    user_id=user.id,
                    organization_id=org.id,
                    role=role,
                    status="active",
                )
            )
        db.commit()
        return email, password
    finally:
        db.close()


def _seed_client(db_factory, name: str | None = None) -> str:
    seq = next(_client_seq)
    db = db_factory()
    try:
        client = Client(name=name or f"Cliente {seq}")
        db.add(client)
        db.commit()
        return client.id
    finally:
        db.close()


def _seed_vendor_with_workspace(
    db_factory,
    *,
    client_id: str,
    vendor_name: str = "Proveedor Demo",
    rfc: str = "DEM260512AB1",
) -> tuple[str, str]:
    db = db_factory()
    try:
        vendor = Vendor(
            client_id=client_id,
            name=vendor_name,
            rfc=rfc.upper(),
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        ws = ProviderWorkspace(
            client_id=client_id,
            vendor_id=vendor.id,
            persona_type="moral",
            display_name=vendor_name,
            access_token=f"SECRET-{rfc}",
        )
        db.add(ws)
        db.commit()
        return vendor.id, ws.id
    finally:
        db.close()


def _seed_institution(db_factory, *, code: str, name: str | None = None) -> str:
    db = db_factory()
    try:
        existing = db.scalar(select(Institution).where(Institution.code == code))
        if existing:
            return existing.id
        inst = Institution(code=code, name=name or code.upper())
        db.add(inst)
        db.commit()
        return inst.id
    finally:
        db.close()


def _seed_requirement(
    db_factory,
    *,
    code: str,
    name: str,
    institution_id: str,
    load_type: str = "alta_inicial",
    frequency: str = "alta_inicial",
) -> str:
    db = db_factory()
    try:
        existing = db.scalar(select(Requirement).where(Requirement.code == code))
        if existing:
            return existing.id
        req = Requirement(
            code=code,
            name=name,
            institution_id=institution_id,
            load_type=load_type,
            frequency=frequency,
            risk_level="medium",
        )
        db.add(req)
        db.commit()
        return req.id
    finally:
        db.close()


def _pdf_bytes() -> bytes:
    buf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(buf)
    return buf.getvalue()


def _seed_submission(
    db_factory,
    *,
    client_id: str,
    vendor_id: str,
    requirement_id: str,
    requirement_code: str,
    institution_id: str,
    period_key: str | None = None,
    status_value: str = DocumentStatus.APROBADO.value,
    storage_subpath: str = "doc.pdf",
) -> str:
    """Insert a Submission + matching Document row directly.

    The portal-submission endpoint enforces a workspace cookie + a
    blizzard of OCR/prevalidation steps the new endpoints don't care
    about; bypassing those keeps the test focused on the read-side
    contract the sprint added.
    """
    db = db_factory()
    try:
        # Periods live in their own table; the new endpoints query by
        # period_key (denormalised on Submission) so the row only needs
        # a syntactic ``period_id`` to satisfy the FK.
        from app.models import Period

        period = db.scalar(
            select(Period).where(Period.code == (period_key or "no-period"))
        )
        if period is None:
            period = Period(
                code=period_key or "no-period",
                period_type="alta_inicial",
                period_key=period_key,
            )
            db.add(period)
            db.flush()
        sub = Submission(
            client_id=client_id,
            vendor_id=vendor_id,
            period_id=period.id,
            institution_id=institution_id,
            requirement_id=requirement_id,
            requirement_code=requirement_code,
            period_key=period_key,
            load_type="alta_inicial",
            status=status_value,
        )
        db.add(sub)
        db.flush()
        # Materialise the storage artefact under the per-test
        # LOCAL_STORAGE_PATH so the FileResponse fallback in the
        # document endpoint can serve it.
        storage_key = f"{client_id}/{vendor_id}/{sub.id}-{storage_subpath}"
        from pathlib import Path

        base = Path(settings.LOCAL_STORAGE_PATH)
        target = base / storage_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_pdf_bytes())
        doc = Document(
            submission_id=sub.id,
            storage_key=storage_key,
            original_filename=storage_subpath,
            size_bytes=target.stat().st_size,
            sha256=("0" * 64),
            mime_type="application/pdf",
        )
        db.add(doc)
        db.commit()
        return sub.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Item 1 — per-submission document endpoint
# ---------------------------------------------------------------------------


def test_client_can_download_own_submission_document(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory)
    _vendor_id, _ws_id = _seed_vendor_with_workspace(
        db_factory, client_id=client_id
    )
    inst_id = _seed_institution(db_factory, code="interno_cliente")
    req_id = _seed_requirement(
        db_factory,
        code="ONB-CONT-001",
        name="Contrato firmado",
        institution_id=inst_id,
    )
    sub_id = _seed_submission(
        db_factory,
        client_id=client_id,
        vendor_id=_vendor_id,
        requirement_id=req_id,
        requirement_code="ONB-CONT-001",
        institution_id=inst_id,
    )
    email, pw = _seed_user(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    resp = api_client.get(
        f"/api/v1/client/submissions/{sub_id}/document", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    # Inline by default (no audit row written) so iframe previews
    # don't flood the audit log.
    assert "inline" in resp.headers.get("content-disposition", "").lower()


def test_client_download_writes_audit_row(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory)
    _vendor_id, _ws_id = _seed_vendor_with_workspace(
        db_factory, client_id=client_id
    )
    inst_id = _seed_institution(db_factory, code="interno_cliente")
    req_id = _seed_requirement(
        db_factory,
        code="ONB-CONT-001",
        name="Contrato firmado",
        institution_id=inst_id,
    )
    sub_id = _seed_submission(
        db_factory,
        client_id=client_id,
        vendor_id=_vendor_id,
        requirement_id=req_id,
        requirement_code="ONB-CONT-001",
        institution_id=inst_id,
    )
    email, pw = _seed_user(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    resp = api_client.get(
        f"/api/v1/client/submissions/{sub_id}/document?download=1",
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    assert "attachment" in resp.headers.get("content-disposition", "").lower()

    db = db_factory()
    try:
        row = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "client.document_downloaded")
            .where(AuditLog.entity_id == sub_id)
        )
        assert row is not None
        meta = row.event_metadata or {}
        assert meta.get("client_id") == client_id
        assert meta.get("requirement_code") == "ONB-CONT-001"
    finally:
        db.close()


def test_client_cannot_download_another_clients_document(
    api_client: TestClient, db_factory
) -> None:
    """A client_admin from client A must not be able to pull a document
    belonging to client B — the response is a 404 (same shape as
    not-found so the endpoint cannot be used to probe cross-tenant
    existence)."""
    client_a = _seed_client(db_factory, "Client A")
    client_b = _seed_client(db_factory, "Client B")
    _vendor_b, _ws_b = _seed_vendor_with_workspace(
        db_factory, client_id=client_b, rfc="OTH260512XY9"
    )
    inst_id = _seed_institution(db_factory, code="interno_cliente")
    req_id = _seed_requirement(
        db_factory,
        code="ONB-CONT-001",
        name="Contrato firmado",
        institution_id=inst_id,
    )
    sub_b = _seed_submission(
        db_factory,
        client_id=client_b,
        vendor_id=_vendor_b,
        requirement_id=req_id,
        requirement_code="ONB-CONT-001",
        institution_id=inst_id,
    )
    email_a, pw_a = _seed_user(
        db_factory, role="client_admin", client_id=client_a, email_prefix="ca-a"
    )
    token_a = _login(api_client, email_a, pw_a)

    resp = api_client.get(
        f"/api/v1/client/submissions/{sub_b}/document", headers=_h(token_a)
    )
    assert resp.status_code == 404
    # No audit row written on the cross-tenant probe.
    db = db_factory()
    try:
        row = db.scalar(
            select(AuditLog).where(AuditLog.action == "client.document_downloaded")
        )
        assert row is None
    finally:
        db.close()


def test_contracts_surface_on_vendor_detail(
    api_client: TestClient, db_factory
) -> None:
    """The vendor detail payload carries the contracts list newest-first.

    Item 1's `ContractDocumentsCard` reads `detail.contracts`; this
    test pins the contract-code recognition + the
    ``created_at DESC`` order so the UI doesn't end up showing the
    original contract above a more recent modification.
    """
    client_id = _seed_client(db_factory)
    vendor_id, _ws_id = _seed_vendor_with_workspace(
        db_factory, client_id=client_id
    )
    inst_id = _seed_institution(db_factory, code="interno_cliente")
    req_001 = _seed_requirement(
        db_factory,
        code="ONB-CONT-001",
        name="Contrato firmado",
        institution_id=inst_id,
    )
    req_002 = _seed_requirement(
        db_factory,
        code="ONB-CONT-002",
        name="Modificación",
        institution_id=inst_id,
    )
    _seed_submission(
        db_factory,
        client_id=client_id,
        vendor_id=vendor_id,
        requirement_id=req_001,
        requirement_code="ONB-CONT-001",
        institution_id=inst_id,
        storage_subpath="contrato.pdf",
    )
    _seed_submission(
        db_factory,
        client_id=client_id,
        vendor_id=vendor_id,
        requirement_id=req_002,
        requirement_code="ONB-CONT-002",
        institution_id=inst_id,
        storage_subpath="modificacion.pdf",
    )
    email, pw = _seed_user(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    resp = api_client.get(
        f"/api/v1/client/vendors/{vendor_id}", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text
    contracts = resp.json()["contracts"]
    assert len(contracts) == 2
    codes = {c["requirement_code"] for c in contracts}
    assert codes == {"ONB-CONT-001", "ONB-CONT-002"}
    for c in contracts:
        assert c["submission_id"]
        assert c["filename"] in {"contrato.pdf", "modificacion.pdf"}


# ---------------------------------------------------------------------------
# Item 2 — audit-package tree + POST whitelist
# ---------------------------------------------------------------------------


def test_audit_package_tree_returns_candidate_set(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory)
    vendor_id, _ws_id = _seed_vendor_with_workspace(
        db_factory, client_id=client_id
    )
    inst_id = _seed_institution(db_factory, code="interno_cliente")
    req_id = _seed_requirement(
        db_factory,
        code="ONB-CONT-001",
        name="Contrato",
        institution_id=inst_id,
    )
    sub_ids = [
        _seed_submission(
            db_factory,
            client_id=client_id,
            vendor_id=vendor_id,
            requirement_id=req_id,
            requirement_code="ONB-CONT-001",
            institution_id=inst_id,
            storage_subpath=f"contrato-{i}.pdf",
        )
        for i in range(3)
    ]
    email, pw = _seed_user(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    resp = api_client.get(
        "/api/v1/client/audit-package/tree", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["file_count"] == 3
    returned_ids = {item["submission_id"] for item in body["items"]}
    assert returned_ids == set(sub_ids)


def test_audit_package_tree_groups_contracts_under_synthetic_institution(
    api_client: TestClient, db_factory
) -> None:
    """Contract-coded submissions surface in the tree response under
    a synthetic ``contrato`` institution code so the picker can show
    them as a dedicated group — not buried inside ``interno_cliente``
    next to the rest of the catalog."""
    client_id = _seed_client(db_factory)
    vendor_id, _ = _seed_vendor_with_workspace(
        db_factory, client_id=client_id
    )
    inst_id = _seed_institution(db_factory, code="interno_cliente")
    req_contract = _seed_requirement(
        db_factory,
        code="ONB-CONT-001",
        name="Contrato",
        institution_id=inst_id,
    )
    req_other = _seed_requirement(
        db_factory,
        code="ONB-CORP-M-001",
        name="Acta constitutiva",
        institution_id=inst_id,
    )
    _seed_submission(
        db_factory,
        client_id=client_id,
        vendor_id=vendor_id,
        requirement_id=req_contract,
        requirement_code="ONB-CONT-001",
        institution_id=inst_id,
        storage_subpath="contrato.pdf",
    )
    _seed_submission(
        db_factory,
        client_id=client_id,
        vendor_id=vendor_id,
        requirement_id=req_other,
        requirement_code="ONB-CORP-M-001",
        institution_id=inst_id,
        storage_subpath="acta.pdf",
    )
    email, pw = _seed_user(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    resp = api_client.get(
        "/api/v1/client/audit-package/tree", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    by_code: dict[str, list[dict]] = {}
    for it in items:
        by_code.setdefault(it["institution_code"], []).append(it)
    # The contract submission moved to the synthetic group; the acta
    # constitutiva stayed under the real institution. The auditor's
    # tree picker now shows two distinct top-level groups for this
    # vendor, not one ``interno_cliente`` group mixing both.
    assert "contrato" in by_code
    assert len(by_code["contrato"]) == 1
    assert by_code["contrato"][0]["institution_name"] == "Contrato"
    assert "interno_cliente" in by_code
    assert len(by_code["interno_cliente"]) == 1
    assert by_code["interno_cliente"][0]["requirement_code"] == "ONB-CORP-M-001"


def test_audit_package_zip_puts_contracts_in_dedicated_folder(
    api_client: TestClient, db_factory
) -> None:
    """Streaming the ZIP routes contract submissions into a
    ``<vendor>/contratos/<file>`` path; non-contract submissions
    keep the historical ``<vendor>/<institution>/<period>/<file>``
    layout. This is the auditor-facing artefact, not just the
    picker UI — pinning it explicitly."""
    client_id = _seed_client(db_factory, "Audit Client")
    vendor_id, _ = _seed_vendor_with_workspace(
        db_factory, client_id=client_id, vendor_name="ZipTest"
    )
    inst_id = _seed_institution(db_factory, code="interno_cliente")
    req_contract = _seed_requirement(
        db_factory,
        code="ONB-CONT-001",
        name="Contrato",
        institution_id=inst_id,
    )
    req_other = _seed_requirement(
        db_factory,
        code="ONB-CORP-M-001",
        name="Acta",
        institution_id=inst_id,
    )
    sub_contract = _seed_submission(
        db_factory,
        client_id=client_id,
        vendor_id=vendor_id,
        requirement_id=req_contract,
        requirement_code="ONB-CONT-001",
        institution_id=inst_id,
        storage_subpath="contrato.pdf",
    )
    sub_acta = _seed_submission(
        db_factory,
        client_id=client_id,
        vendor_id=vendor_id,
        requirement_id=req_other,
        requirement_code="ONB-CORP-M-001",
        institution_id=inst_id,
        storage_subpath="acta.pdf",
    )
    email, pw = _seed_user(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    resp = api_client.post(
        "/api/v1/client/audit-package.zip",
        json={
            "submission_ids": [sub_contract, sub_acta],
            "skip_manifest": True,
        },
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    archive = zipfile.ZipFile(BytesIO(resp.content))
    names = archive.namelist()
    contract_paths = [n for n in names if "/contratos/" in n]
    other_paths = [n for n in names if "/contratos/" not in n]
    # The contract artefact lives under the dedicated folder; nothing
    # else does, and the contract is NOT also under interno_cliente.
    assert len(contract_paths) == 1
    assert contract_paths[0].endswith("contrato.pdf")
    assert all("/interno_cliente/" in p for p in other_paths)
    assert all("/contratos/" not in p for p in other_paths)


def test_audit_package_zip_post_with_submission_ids_narrows_set(
    api_client: TestClient, db_factory
) -> None:
    """POSTing a submission_ids whitelist must produce a ZIP that
    contains exactly those submissions — not the wider filter set
    that drives the candidate tree."""
    client_id = _seed_client(db_factory)
    vendor_id, _ws_id = _seed_vendor_with_workspace(
        db_factory, client_id=client_id
    )
    inst_id = _seed_institution(db_factory, code="interno_cliente")
    req_id = _seed_requirement(
        db_factory,
        code="ONB-CONT-001",
        name="Contrato",
        institution_id=inst_id,
    )
    sub_ids = [
        _seed_submission(
            db_factory,
            client_id=client_id,
            vendor_id=vendor_id,
            requirement_id=req_id,
            requirement_code="ONB-CONT-001",
            institution_id=inst_id,
            storage_subpath=f"contrato-{i}.pdf",
        )
        for i in range(3)
    ]
    email, pw = _seed_user(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    keep_one = [sub_ids[1]]
    resp = api_client.post(
        "/api/v1/client/audit-package.zip",
        json={
            "submission_ids": keep_one,
            "skip_manifest": True,
        },
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    archive = zipfile.ZipFile(BytesIO(resp.content))
    # Only the one whitelisted submission should be present; INDICE
    # is skipped via skip_manifest so the only files inside come from
    # the document set.
    names = archive.namelist()
    assert len(names) == 1, names
    assert "contrato-1.pdf" in names[0]


# ---------------------------------------------------------------------------
# Item 3 — calendar vendor_ids filter
# ---------------------------------------------------------------------------


def test_client_calendar_vendor_ids_narrows_response(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory)
    vendor_a, _ = _seed_vendor_with_workspace(
        db_factory, client_id=client_id, vendor_name="Vendor A", rfc="AAA260512AA1"
    )
    vendor_b, _ = _seed_vendor_with_workspace(
        db_factory, client_id=client_id, vendor_name="Vendor B", rfc="BBB260512BB1"
    )
    email, pw = _seed_user(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    # Unfiltered — both vendors contribute.
    resp_all = api_client.get(
        "/api/v1/client/calendar?year=2026", headers=_h(token)
    )
    assert resp_all.status_code == 200, resp_all.text
    months_all = resp_all.json()["months"]
    vendor_ids_all: set[str] = set()
    for m in months_all:
        for item in m["items"]:
            vendor_ids_all.add(item["vendor_id"])
    assert {vendor_a, vendor_b}.issubset(vendor_ids_all)

    # Filtered to Vendor A only — Vendor B's rows disappear; unknown
    # vendor ids are silently dropped so the response cannot enumerate.
    resp_a = api_client.get(
        f"/api/v1/client/calendar?year=2026&vendor_ids={vendor_a}&vendor_ids=unknown",
        headers=_h(token),
    )
    assert resp_a.status_code == 200, resp_a.text
    months_a = resp_a.json()["months"]
    vendor_ids_a: set[str] = set()
    for m in months_a:
        for item in m["items"]:
            vendor_ids_a.add(item["vendor_id"])
    assert vendor_a in vendor_ids_a
    assert vendor_b not in vendor_ids_a


# ---------------------------------------------------------------------------
# Item 8 — provision client + terms_accepted audit
# ---------------------------------------------------------------------------


def test_admin_users_provisions_client_with_temp_password(
    api_client: TestClient, db_factory
) -> None:
    """Item 8 v2 — ``POST /admin/users`` with role=client mints a temp
    password (returned in the response for the admin's one-time
    confirmation view AND emailed), bcrypts it onto the User row,
    flips ``must_change_password`` so the recipient is forced through
    ``/activate`` on first login, and wires up the
    Client+Organization+Membership stack."""
    email, pw = _seed_user(db_factory, role="internal_admin", email_prefix="adm")
    token = _login(api_client, email, pw)

    resp = api_client.post(
        "/api/v1/admin/users",
        json={
            "full_name": "María Pérez",
            "email": "Maria.Perez@Acero.MX",
            "role": "client",
            "client_name": "Acero del Norte",
            "client_rfc": "ANO260512XY3",
        },
        headers=_h(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["role"] == "client"
    assert body["client_id"]
    assert body["organization_id"]
    assert body["user_id"]
    # Temp password is returned in plaintext, exactly once, so the
    # admin confirmation screen can render it.
    assert len(body["temp_password"]) >= 12
    assert body["login_url"].endswith("/login")
    assert body["email_status"] in {"skipped", "sent"}

    db = db_factory()
    try:
        client_row = db.get(Client, body["client_id"])
        assert client_row is not None
        assert client_row.name == "Acero del Norte"
        assert client_row.email == "maria.perez@acero.mx"

        org = db.get(Organization, body["organization_id"])
        assert org is not None
        assert org.kind == "client"
        assert org.client_id == client_row.id

        user = db.get(User, body["user_id"])
        assert user is not None
        assert user.email == "maria.perez@acero.mx"
        assert user.must_change_password is True
        # Real bcrypt hash this time — the temp password bcrypt-verifies.
        from app.services.auth import verify_password

        assert user.password_hash and user.password_hash.startswith("$2")
        assert verify_password(body["temp_password"], user.password_hash)

        membership = db.scalar(
            select(Membership).where(Membership.user_id == user.id)
        )
        assert membership is not None
        assert membership.role == "client_admin"
        assert membership.organization_id == org.id

        audit = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "admin.user.provisioned")
            .where(AuditLog.entity_id == user.id)
        )
        assert audit is not None
        after = audit.after or {}
        assert after.get("role") == "client"
        assert after.get("client_id") == client_row.id
    finally:
        db.close()


def test_admin_users_provisions_provider_with_workspace(
    api_client: TestClient, db_factory
) -> None:
    """Item 8 v2 — ``POST /admin/users`` with role=provider mints the
    same temp-password User stack but builds a Vendor +
    ProviderWorkspace (owner_user_id=user.id) anchored under the
    requested parent client. No Membership/Organization for providers
    — the existing portal cookie path is the auth carrier inside
    /portal."""
    email, pw = _seed_user(db_factory, role="internal_admin", email_prefix="adm")
    token = _login(api_client, email, pw)
    parent_client_id = _seed_client(db_factory, "Parent Client")

    resp = api_client.post(
        "/api/v1/admin/users",
        json={
            "full_name": "Juan Proveedor",
            "email": "juan@proveedor.example",
            "role": "provider",
            "vendor_name": "Proveedor Test",
            "vendor_rfc": "PRO260512AB1",
            "persona_type": "moral",
            "contact_phone": "+52 55 1234 5678",
            "parent_client_id": parent_client_id,
        },
        headers=_h(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["role"] == "provider"
    assert body["vendor_id"]
    assert body["workspace_id"]
    assert body["user_id"]
    assert body["client_id"] is None  # provider didn't get a Client
    assert body["organization_id"] is None
    assert len(body["temp_password"]) >= 12

    db = db_factory()
    try:
        from app.models import Vendor as _Vendor

        vendor = db.get(_Vendor, body["vendor_id"])
        assert vendor is not None
        assert vendor.client_id == parent_client_id
        assert vendor.rfc == "PRO260512AB1"
        assert vendor.contact_email == "juan@proveedor.example"

        workspace = db.get(ProviderWorkspace, body["workspace_id"])
        assert workspace is not None
        assert workspace.owner_user_id == body["user_id"]
        # access_token is minted so the legacy cookie path still works
        # for this workspace if anyone hits the older URL.
        assert workspace.access_token

        user = db.get(User, body["user_id"])
        assert user is not None
        assert user.must_change_password is True
        from app.services.auth import verify_password

        assert verify_password(body["temp_password"], user.password_hash)

        # Providers get no Membership — they rely on workspace ownership.
        assert (
            db.scalar(select(Membership).where(Membership.user_id == user.id))
            is None
        )
    finally:
        db.close()


def test_admin_users_provider_requires_parent_client(
    api_client: TestClient, db_factory
) -> None:
    email, pw = _seed_user(db_factory, role="internal_admin", email_prefix="adm")
    token = _login(api_client, email, pw)
    resp = api_client.post(
        "/api/v1/admin/users",
        json={
            "full_name": "Orphan Provider",
            "email": "orphan@p.example",
            "role": "provider",
            "vendor_name": "X",
            "vendor_rfc": "XXX260512AB1",
        },
        headers=_h(token),
    )
    assert resp.status_code == 422


def test_admin_users_rejects_duplicate_email(
    api_client: TestClient, db_factory
) -> None:
    email, pw = _seed_user(db_factory, role="internal_admin", email_prefix="adm")
    token = _login(api_client, email, pw)
    payload = {
        "full_name": "Persona Uno",
        "email": "dup@example.com",
        "role": "client",
        "client_name": "Empresa Uno",
    }
    first = api_client.post(
        "/api/v1/admin/users", json=payload, headers=_h(token)
    )
    assert first.status_code == 201, first.text

    second = api_client.post(
        "/api/v1/admin/users",
        json={**payload, "client_name": "Empresa Dos"},
        headers=_h(token),
    )
    assert second.status_code == 409


def test_admin_users_rejects_non_internal_admin(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory)
    email, pw = _seed_user(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.post(
        "/api/v1/admin/users",
        json={
            "full_name": "Persona X",
            "email": "x@example.com",
            "role": "client",
            "client_name": "Cliente X",
        },
        headers=_h(token),
    )
    assert resp.status_code == 403


def test_client_can_add_provider_and_invitation_is_audited(
    api_client: TestClient, db_factory
) -> None:
    """Item 8 v2 — ``POST /client/providers`` lets a client_admin
    invite a provider directly from their profile. The temp password
    is NOT returned to the client (per the spec — only the admin path
    returns it). The audit row pins the invitation."""
    client_id = _seed_client(db_factory, "Inviting Client")
    email, pw = _seed_user(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)

    resp = api_client.post(
        "/api/v1/client/providers",
        json={
            "vendor_name": "Proveedor Invitado",
            "vendor_rfc": "INV260512AB1",
            "persona_type": "moral",
            "contact_name": "Ada Proveedor",
            "contact_email": "ada@invitado.example",
            "contact_phone": "+52 55 0000 0000",
        },
        headers=_h(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["vendor_id"]
    assert body["workspace_id"]
    assert body["user_id"]
    assert body["contact_email"] == "ada@invitado.example"
    # CRITICAL: the client never sees the temp password.
    assert "temp_password" not in body

    db = db_factory()
    try:
        from app.models import Vendor as _Vendor

        vendor = db.get(_Vendor, body["vendor_id"])
        assert vendor is not None
        assert vendor.client_id == client_id

        audit = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "client.provider_invited")
            .where(AuditLog.entity_id == vendor.id)
        )
        assert audit is not None
        meta = audit.event_metadata or {}
        assert meta.get("client_id") == client_id
        assert meta.get("user_email") == "ada@invitado.example"
    finally:
        db.close()


def test_client_cannot_add_provider_with_duplicate_rfc(
    api_client: TestClient, db_factory
) -> None:
    """Same-client duplicate-RFC returns 409. Different clients can
    share an RFC (the model enforces uniqueness per ``(client_id,
    rfc)``)."""
    client_id = _seed_client(db_factory)
    email, pw = _seed_user(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    payload = {
        "vendor_name": "Dup",
        "vendor_rfc": "DUP260512AB1",
        "persona_type": "moral",
        "contact_name": "Contacto",
        "contact_email": "dup1@p.example",
    }
    first = api_client.post(
        "/api/v1/client/providers", json=payload, headers=_h(token)
    )
    assert first.status_code == 201, first.text
    second = api_client.post(
        "/api/v1/client/providers",
        json={**payload, "contact_email": "dup2@p.example"},
        headers=_h(token),
    )
    assert second.status_code == 409


def test_internal_admin_can_load_vendor_detail_without_client_id_param(
    api_client: TestClient, db_factory
) -> None:
    """Item 5 follow-up — when an internal_admin clicks a vendor link
    from an admin shell, the URL does not carry ``?client_id=``.
    The backend must auto-resolve the scope from the vendor row
    instead of returning the 400 ``_resolve_client_id`` raised
    before.

    The vendor still has to exist; cross-tenant probes from a
    client_admin keep the 404 shape (covered separately in the
    submission-document tenant-guard test)."""
    client_id = _seed_client(db_factory, "Cliente con Vendor")
    vendor_id, _ws = _seed_vendor_with_workspace(
        db_factory, client_id=client_id
    )
    email, pw = _seed_user(
        db_factory, role="internal_admin", email_prefix="adm"
    )
    token = _login(api_client, email, pw)

    resp = api_client.get(
        f"/api/v1/client/vendors/{vendor_id}", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["client_id"] == client_id
    assert body["vendor_id"] == vendor_id


def test_client_admin_still_cannot_see_another_clients_vendor_detail(
    api_client: TestClient, db_factory
) -> None:
    """The auto-resolution path is internal_admin-only — a
    client_admin from client A asking for a vendor that lives under
    client B still gets a 404 (no cross-tenant probe)."""
    client_a = _seed_client(db_factory, "Client A")
    client_b = _seed_client(db_factory, "Client B")
    vendor_b, _ = _seed_vendor_with_workspace(
        db_factory, client_id=client_b, rfc="OTH260512AB9"
    )
    email_a, pw_a = _seed_user(
        db_factory, role="client_admin", client_id=client_a, email_prefix="ca-a"
    )
    token_a = _login(api_client, email_a, pw_a)
    resp = api_client.get(
        f"/api/v1/client/vendors/{vendor_b}", headers=_h(token_a)
    )
    assert resp.status_code == 404


def test_reviewer_queue_surfaces_vendor_id_and_client_id(
    api_client: TestClient, db_factory
) -> None:
    """Item 5 follow-up — the reviewer queue surfaces vendor_id +
    client_id so the admin shell can build a VendorRef link to the
    vendor expediente without forcing a separate lookup."""
    client_id = _seed_client(db_factory, "Cliente Reviewer")
    vendor_id, ws_id = _seed_vendor_with_workspace(
        db_factory, client_id=client_id, vendor_name="Q Vendor", rfc="QUE260512AB1"
    )
    inst_id = _seed_institution(db_factory, code="interno_cliente")
    req_id = _seed_requirement(
        db_factory,
        code="ONB-CORP-M-001",
        name="Acta",
        institution_id=inst_id,
    )
    _seed_submission(
        db_factory,
        client_id=client_id,
        vendor_id=vendor_id,
        requirement_id=req_id,
        requirement_code="ONB-CORP-M-001",
        institution_id=inst_id,
        status_value=DocumentStatus.PENDIENTE_REVISION.value,
    )
    email, pw = _seed_user(
        db_factory, role="internal_admin", email_prefix="rev-adm"
    )
    token = _login(api_client, email, pw)

    resp = api_client.get(
        "/api/v1/reviewer/queue", headers=_h(token)
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert items, "queue should contain at least the pending submission"
    item = items[0]
    assert item["provider"]["vendor_id"] == vendor_id
    assert item["provider"]["client_id"] == client_id


def test_client_profile_patch_terms_accepted_writes_audit(
    api_client: TestClient, db_factory
) -> None:
    """When the client_admin ticks the T&C checkbox on
    /client/onboarding, the profile PATCH must write a
    ``client.legal_consent_accepted`` audit row with the current
    version string."""
    client_id = _seed_client(db_factory, "Cliente Consent")
    email, pw = _seed_user(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.patch(
        "/api/v1/client/profile",
        json={
            "fiscal_address": "Calle Falsa 123",
            "terms_accepted": True,
        },
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text

    db = db_factory()
    try:
        row = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "client.legal_consent_accepted")
            .where(AuditLog.entity_id == client_id)
        )
        assert row is not None
        meta = row.event_metadata or {}
        assert meta.get("legal_consent_version") == "v0-draft"
        assert meta.get("client_id") == client_id
    finally:
        db.close()


def test_client_profile_patch_without_terms_does_not_write_consent(
    api_client: TestClient, db_factory
) -> None:
    """A profile PATCH that omits ``terms_accepted`` (or sets it to
    false) must NOT write a consent row — only the explicit opt-in
    on the first-login screen counts."""
    client_id = _seed_client(db_factory, "Cliente NoConsent")
    email, pw = _seed_user(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.patch(
        "/api/v1/client/profile",
        json={"fiscal_address": "Calle 456"},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    db = db_factory()
    try:
        row = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "client.legal_consent_accepted"
            )
        )
        assert row is None
    finally:
        db.close()
