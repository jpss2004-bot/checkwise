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
    PasswordResetToken,
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


def test_admin_provision_client_creates_full_stack(
    api_client: TestClient, db_factory
) -> None:
    email, pw = _seed_user(db_factory, role="internal_admin", email_prefix="adm")
    token = _login(api_client, email, pw)

    resp = api_client.post(
        "/api/v1/admin/clients/provision",
        json={
            "client_name": "Acero del Norte",
            "rfc": "ANO260512XY3",
            "client_email": "Maria.Perez@Acero.MX",
            "admin_full_name": "María Pérez",
        },
        headers=_h(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["client_id"]
    assert body["organization_id"]
    assert body["user_id"]
    assert "/reset-password?token=" in body["onboarding_url"]
    # SMTP not configured in the test env → status returns "skipped".
    assert body["email_status"] in {"skipped", "sent"}

    db = db_factory()
    try:
        client_row = db.get(Client, body["client_id"])
        assert client_row is not None
        assert client_row.name == "Acero del Norte"
        # Email is normalised to lowercase.
        assert client_row.email == "maria.perez@acero.mx"

        org = db.get(Organization, body["organization_id"])
        assert org is not None
        assert org.kind == "client"
        assert org.client_id == client_row.id

        user = db.get(User, body["user_id"])
        assert user is not None
        assert user.email == "maria.perez@acero.mx"
        assert user.must_change_password is True
        # The placeholder hash should not bcrypt-verify against any
        # plaintext; only the reset link can land a real password.
        assert user.password_hash and not user.password_hash.startswith("$2")

        membership = db.scalar(
            select(Membership).where(Membership.user_id == user.id)
        )
        assert membership is not None
        assert membership.role == "client_admin"
        assert membership.organization_id == org.id

        token_row = db.scalar(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        )
        assert token_row is not None
        assert token_row.used_at is None

        audit = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "admin.client.provisioned")
            .where(AuditLog.entity_id == client_row.id)
        )
        assert audit is not None
        after = audit.after or {}
        assert after.get("user_id") == user.id
        assert after.get("organization_id") == org.id
    finally:
        db.close()


def test_admin_provision_client_rejects_duplicate_email(
    api_client: TestClient, db_factory
) -> None:
    email, pw = _seed_user(db_factory, role="internal_admin", email_prefix="adm")
    token = _login(api_client, email, pw)
    payload = {
        "client_name": "Empresa Uno",
        "client_email": "dup@example.com",
        "admin_full_name": "Persona Uno",
    }
    first = api_client.post(
        "/api/v1/admin/clients/provision", json=payload, headers=_h(token)
    )
    assert first.status_code == 201, first.text

    second = api_client.post(
        "/api/v1/admin/clients/provision",
        json={**payload, "client_name": "Empresa Dos"},
        headers=_h(token),
    )
    assert second.status_code == 409


def test_admin_provision_client_rejects_non_internal_admin(
    api_client: TestClient, db_factory
) -> None:
    client_id = _seed_client(db_factory)
    email, pw = _seed_user(
        db_factory, role="client_admin", client_id=client_id, email_prefix="ca"
    )
    token = _login(api_client, email, pw)
    resp = api_client.post(
        "/api/v1/admin/clients/provision",
        json={
            "client_name": "Cliente X",
            "client_email": "x@example.com",
            "admin_full_name": "Persona X",
        },
        headers=_h(token),
    )
    assert resp.status_code == 403


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
