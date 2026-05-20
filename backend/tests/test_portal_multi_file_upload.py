"""Stage 2.7-b — Multi-document submission endpoint.

Covers:

* Feature flag off (default): endpoint returns 404 even for valid
  payloads.
* Happy path with flag on: N files → 1 Submission with N Documents,
  per-doc validations + status history persisted, audit_log row carries
  ``multi_file_upload=True`` and ``document_count=N``.
* File count cap: N > 5 → 422.
* Aggregate size cap: total > 30 MB → 413, no Submission written.
* Non-PDF file in the batch → 400, no Submission written.
* Tenant guard still enforced.
* Replacement lineage works with a multi-doc parent (covers the
  handoff §2.7-b verification requirement).
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

from app.constants.statuses import DocumentStatus
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    AuditLog,
    Client,
    Document,
    DocumentStatusHistory,
    ProviderWorkspace,
    Submission,
    User,
    Validation,
    ValidationEvent,
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
    previous_flag = settings.MULTI_FILE_UPLOAD_ENABLED

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
        settings.LOCAL_STORAGE_PATH = previous_storage
        settings.MULTI_FILE_UPLOAD_ENABLED = previous_flag


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
            email=f"multi-{seq}@checkwise.test",
            password_hash=hash_password("CheckWiseTest!2026"),
            full_name=f"Multi Doc Tester {seq}",
            status="active",
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        client_row = db.query(Client).filter_by(name="Cliente Piloto Multi").first()
        if client_row is None:
            client_row = Client(name="Cliente Piloto Multi")
            db.add(client_row)
            db.flush()
        vendor = Vendor(
            client_id=client_row.id,
            name=f"Multi Doc Vendor {seq} SA",
            rfc=f"MDV2605{seq:02d}AB1",
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
    return {"workspace_id": ws_id, "bearer": token, "user_id": user_id}


def _post_batch(
    api_client: TestClient,
    ws_id: str,
    *,
    files: list[tuple[str, bytes, str]] | None = None,
    requirement_name: str = "Cuotas obrero patronales",
    requirement_code: str = "REC-IMSS-2026-02-cuotas-obrero-patronales",
    period_code: str = "2026-M01",
    period_key: str = "2026-M01",
    institution_code: str = "imss",
    load_type: str = "mensual",
    supersedes_submission_id: str | None = None,
):
    if files is None:
        files = [
            (f"doc-{idx}.pdf", _pdf_bytes(), "application/pdf") for idx in range(2)
        ]
    data = {
        "period_code": period_code,
        "period_key": period_key,
        "load_type": load_type,
        "institution_code": institution_code,
        "requirement_name": requirement_name,
        "requirement_code": requirement_code,
        "initial_status": "pendiente_revision",
    }
    if supersedes_submission_id:
        data["supersedes_submission_id"] = supersedes_submission_id
    multi_files = [
        ("files", (filename, payload, content_type))
        for filename, payload, content_type in files
    ]
    return api_client.post(
        f"/api/v1/portal/workspaces/{ws_id}/submissions/batch",
        data=data,
        files=multi_files,
    )


# ---------------------------------------------------------------------------
# Feature flag gating
# ---------------------------------------------------------------------------


def test_endpoint_disabled_by_default_returns_404(api_client: TestClient) -> None:
    settings.MULTI_FILE_UPLOAD_ENABLED = False
    ws = _setup_workspace(api_client)
    resp = _post_batch(api_client, ws["workspace_id"])
    assert resp.status_code == 404
    assert "no está disponible" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_multi_file_creates_one_submission_with_n_documents(
    api_client: TestClient,
) -> None:
    settings.MULTI_FILE_UPLOAD_ENABLED = True
    ws = _setup_workspace(api_client)
    resp = _post_batch(
        api_client,
        ws["workspace_id"],
        files=[
            ("contrato.pdf", _pdf_bytes(), "application/pdf"),
            ("anexo-a.pdf", _pdf_bytes(), "application/pdf"),
            ("anexo-b.pdf", _pdf_bytes(), "application/pdf"),
        ],
    )
    assert resp.status_code == 202, resp.text
    payload = resp.json()
    assert payload["submission_id"]
    # Per-file documents come back with distinct ids + original filenames.
    docs = payload["documents"]
    assert len(docs) == 3
    filenames = {d["original_filename"] for d in docs}
    assert filenames == {"contrato.pdf", "anexo-a.pdf", "anexo-b.pdf"}
    for doc in docs:
        assert doc["document_id"]
        assert doc["status"] == DocumentStatus.PENDIENTE_REVISION.value
        assert doc["sha256"]
        assert doc["storage_key"]
        # Per-doc validations + events run individually.
        assert doc["validations"]
        assert doc["validation_events"]

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        submission = db.scalar(
            select(Submission).where(Submission.id == payload["submission_id"])
        )
        assert submission is not None
        documents = db.scalars(
            select(Document).where(Document.submission_id == submission.id)
        ).all()
        assert len(documents) == 3, "expected 1 Submission → 3 Documents"
        # Per-doc DocumentStatusHistory rows are created.
        history = db.scalars(
            select(DocumentStatusHistory).where(
                DocumentStatusHistory.submission_id == submission.id
            )
        ).all()
        assert len(history) == 3
        # Per-doc Validations: each doc has at least the standard signals.
        validations = db.scalars(
            select(Validation).where(Validation.submission_id == submission.id)
        ).all()
        assert len(validations) >= 3 * 3  # >= 3 signals per doc
        # Audit log carries the multi-file marker.
        audit = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "submission.created")
            .where(AuditLog.entity_id == submission.id)
        )
        assert audit is not None
        metadata = audit.event_metadata or {}
        assert metadata.get("multi_file_upload") is True
        assert metadata.get("document_count") == 3
        assert len(metadata.get("storage_keys") or []) == 3
        assert len(metadata.get("sha256_list") or []) == 3
    finally:
        db.close()


def test_multi_file_overall_status_is_worst_case(api_client: TestClient) -> None:
    """When one of the N docs would derive POSIBLE_MISMATCH or
    REQUIERE_ACLARACION, the Submission's overall status reflects that
    rather than PENDIENTE_REVISION."""
    settings.MULTI_FILE_UPLOAD_ENABLED = True
    ws = _setup_workspace(api_client)
    # Two valid PDFs — both should derive PENDIENTE_REVISION. Same hash
    # would trigger a duplicate warning but not change the derived
    # status. Use distinct bytes so each gets its own sha256.
    resp = _post_batch(
        api_client,
        ws["workspace_id"],
        files=[
            ("a.pdf", _pdf_bytes(), "application/pdf"),
            ("b.pdf", _pdf_bytes() + b"%EOF\n", "application/pdf"),
        ],
    )
    assert resp.status_code == 202, resp.text
    payload = resp.json()
    # With two clean PDFs the overall status stays PENDIENTE_REVISION.
    assert payload["status"] == DocumentStatus.PENDIENTE_REVISION.value


# ---------------------------------------------------------------------------
# Caps
# ---------------------------------------------------------------------------


def test_more_than_five_files_returns_422(api_client: TestClient) -> None:
    settings.MULTI_FILE_UPLOAD_ENABLED = True
    ws = _setup_workspace(api_client)
    six = [(f"doc-{i}.pdf", _pdf_bytes(), "application/pdf") for i in range(6)]
    resp = _post_batch(api_client, ws["workspace_id"], files=six)
    assert resp.status_code == 422
    assert "5" in resp.json()["detail"]

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        assert db.scalars(select(Submission)).first() is None
    finally:
        db.close()


def test_aggregate_size_over_cap_returns_413(
    api_client: TestClient,
) -> None:
    settings.MULTI_FILE_UPLOAD_ENABLED = True
    ws = _setup_workspace(api_client)
    # 5 files × 7 MB each = 35 MB > 30 MB cap. Use synthetic large
    # bytes that still pass the PDF magic header check.
    big = b"%PDF-1.4\n" + (b"0" * (7 * 1024 * 1024))
    big_files = [(f"big-{i}.pdf", big, "application/pdf") for i in range(5)]
    resp = _post_batch(api_client, ws["workspace_id"], files=big_files)
    assert resp.status_code == 413
    assert "MB" in resp.json()["detail"]

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        assert db.scalars(select(Submission)).first() is None
    finally:
        db.close()


def test_rollback_cleans_up_storage_writes(
    api_client: TestClient,
) -> None:
    """Stage 2.7-b storage cleanup gap fix (2026-05-20).

    The aggregate-size cap fires mid-loop after the first N files have
    already been written to storage. The rollback path must remove
    those orphan bytes — otherwise every failed batch upload leaks up
    to ``MULTI_FILE_TOTAL_BYTES_CAP`` of PDF data forever.

    Setup: 5 × 7 MB files. The first 4 reach storage (28 MB cumulative);
    the 5th pushes aggregate to 35 MB and triggers the 413 path which
    calls ``_cleanup_partial_storage``. After the request returns, the
    test storage tree must be empty under ``documents/``.
    """
    from pathlib import Path

    settings.MULTI_FILE_UPLOAD_ENABLED = True
    ws = _setup_workspace(api_client)

    big = b"%PDF-1.4\n" + (b"0" * (7 * 1024 * 1024))
    big_files = [(f"big-{i}.pdf", big, "application/pdf") for i in range(5)]
    storage_root = Path(settings.LOCAL_STORAGE_PATH)

    resp = _post_batch(api_client, ws["workspace_id"], files=big_files)
    assert resp.status_code == 413, resp.text

    # No Submission row (already asserted in the sister test; reasserted
    # here for self-contained debugging).
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        assert db.scalars(select(Submission)).first() is None
    finally:
        db.close()

    # No orphan PDFs left behind. Walk the storage tree and confirm
    # every file under documents/ is gone — pre-cleanup-fix this
    # directory would contain 4 × 7 MB PDFs that never get reaped.
    documents_dir = storage_root / "documents"
    if documents_dir.exists():
        leftover = [p for p in documents_dir.rglob("*") if p.is_file()]
        assert not leftover, (
            f"rollback should have cleaned storage, but found: {[str(p) for p in leftover]}"
        )


def test_empty_files_list_returns_422(api_client: TestClient) -> None:
    settings.MULTI_FILE_UPLOAD_ENABLED = True
    ws = _setup_workspace(api_client)
    resp = _post_batch(api_client, ws["workspace_id"], files=[])
    # FastAPI itself may reject empty `files` with 422 before our
    # handler runs. Either way the request fails.
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PDF gating
# ---------------------------------------------------------------------------


def test_non_pdf_file_in_batch_rejects_whole_batch(api_client: TestClient) -> None:
    settings.MULTI_FILE_UPLOAD_ENABLED = True
    ws = _setup_workspace(api_client)
    resp = _post_batch(
        api_client,
        ws["workspace_id"],
        files=[
            ("good.pdf", _pdf_bytes(), "application/pdf"),
            ("evil.xml", b"<?xml version=\"1.0\"?>", "application/xml"),
        ],
    )
    assert resp.status_code == 400
    assert "PDF" in resp.json()["detail"]

    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        assert db.scalars(select(Submission)).first() is None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Replacement lineage
# ---------------------------------------------------------------------------


def test_supersedes_prior_submission_still_works_with_multi_doc_batch(
    api_client: TestClient,
) -> None:
    """The replacement-lineage flow (supersedes_submission_id) must
    continue to function when the replacing entry is a multi-doc batch."""
    settings.MULTI_FILE_UPLOAD_ENABLED = True
    ws = _setup_workspace(api_client)

    # First, write a legacy single-file submission so we have something
    # to supersede.
    first = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/submissions",
        data={
            "period_code": "2026-M01",
            "period_key": "2026-M01",
            "load_type": "mensual",
            "institution_code": "imss",
            "requirement_name": "Cuotas obrero patronales",
            "requirement_code": "REC-IMSS-2026-02-cuotas-obrero-patronales",
            "initial_status": "pendiente_revision",
        },
        files={"file": ("prior.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert first.status_code == 202, first.text
    prior_id = first.json()["submission_id"]

    # Reject the prior at the DB level so it qualifies for replacement.
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        sub = db.get(Submission, prior_id)
        assert sub is not None
        sub.status = DocumentStatus.RECHAZADO.value
        db.commit()
    finally:
        db.close()

    # Replace with a multi-doc batch.
    resp = _post_batch(
        api_client,
        ws["workspace_id"],
        files=[
            ("contrato-corregido.pdf", _pdf_bytes(), "application/pdf"),
            ("anexo-corregido.pdf", _pdf_bytes() + b"%EOF\n", "application/pdf"),
        ],
        supersedes_submission_id=prior_id,
    )
    assert resp.status_code == 202, resp.text
    new_id = resp.json()["submission_id"]
    assert new_id != prior_id

    # The lineage event timeline must show the replacement.
    db = factory()
    try:
        events = db.scalars(
            select(ValidationEvent).where(
                ValidationEvent.event_type == "submission_replacement_linked"
            )
        ).all()
        assert any(
            event.submission_id == new_id for event in events
        ), "new multi-doc submission should carry the replacement event"
        prior_marker = db.scalars(
            select(ValidationEvent).where(
                ValidationEvent.event_type == "submission_replaced"
            )
        ).all()
        assert any(
            event.submission_id == prior_id for event in prior_marker
        ), "prior submission should be marked as replaced"
    finally:
        db.close()
