"""Unit tests for transactional email outbound.

Junta 2026-05-25 — first paying pilot needs real email delivery on
reviewer decisions and renewal threshold crosses. These tests pin
both the template content (so a copy regression is caught at CI
time) and the dispatch helper's preference gate (so a future
refactor cannot silently start emailing users who picked
WhatsApp).

The SMTP layer itself is monkeypatched per test — we never open a
real socket. The tests are deterministic and run in <1s.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Client,
    Document,
    Institution,
    Membership,
    Organization,
    Period,
    ProviderWorkspace,
    Requirement,
    Submission,
    User,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password
from app.services.email_delivery import EmailDeliveryResult
from app.services.email_templates import (
    build_client_renewal_email,
    build_provider_decision_email,
    build_provider_renewal_email,
)
from app.services.transactional_email import (
    email_provider_of_reviewer_decision,
    email_renewal_threshold_crossed,
)

# ---------------------------------------------------------------------------
# Template tests — pure functions, no DB
# ---------------------------------------------------------------------------


def test_provider_decision_email_approved_includes_full_context() -> None:
    subject, body = build_provider_decision_email(
        provider_name="Jorge",
        vendor_name="Servicios Aurora",
        requirement_name="Constancia de situación fiscal",
        period_label="2026-M05",
        action="approve",
        reason=None,
        observations=None,
        submission_url="https://app.checkwise.mx/portal/submissions/abc",
    )
    assert subject == (
        "Tu documento fue aprobado: Constancia de situación fiscal"
    )
    assert body.startswith("Hola Jorge,")
    assert "Servicios Aurora" in body
    assert "Constancia de situación fiscal" in body
    assert "2026-M05" in body
    assert "https://app.checkwise.mx/portal/submissions/abc" in body
    # Approved decisions don't surface a "Motivo" line.
    assert "Motivo:" not in body
    assert body.rstrip().endswith("CheckWise")


def test_provider_decision_email_rejection_surfaces_reason_and_observations() -> None:
    subject, body = build_provider_decision_email(
        provider_name="Rebeca",
        vendor_name="Constructora Centro",
        requirement_name="Comprobante de pago IMSS",
        period_label="2026-B2",
        action="reject",
        reason="El RFC del documento no coincide con el del proveedor.",
        observations="Vuelve a descargar el comprobante desde el portal IMSS.",
        submission_url="https://app.checkwise.mx/portal/submissions/xyz",
    )
    assert "necesita correcciones" in subject
    assert "Motivo: El RFC del documento no coincide" in body
    assert "Observaciones del revisor: Vuelve a descargar el comprobante" in body


def test_provider_renewal_email_upcoming_vs_overdue() -> None:
    upcoming_subject, upcoming_body = build_provider_renewal_email(
        provider_name="Jorge",
        vendor_name="Servicios Aurora",
        requirement_name="Constancia de situación fiscal",
        due_date=date(2026, 7, 15),
        days_remaining=14,
        severity="yellow",
        portal_url="https://app.checkwise.mx",
    )
    assert upcoming_subject.startswith("Próximo vencimiento")
    assert "Te quedan 14 días" in upcoming_body
    assert "15 de julio de 2026" in upcoming_body

    overdue_subject, overdue_body = build_provider_renewal_email(
        provider_name="Jorge",
        vendor_name="Servicios Aurora",
        requirement_name="Constancia de situación fiscal",
        due_date=date(2026, 4, 15),
        days_remaining=-7,
        severity="red",
        portal_url="https://app.checkwise.mx",
    )
    assert overdue_subject.startswith("Documento vencido por renovar")
    assert "venció el 15 de abril de 2026" in overdue_body
    assert "sigue marcando como pendiente" in overdue_body


def test_client_renewal_email_distinguishes_from_provider() -> None:
    subject, body = build_client_renewal_email(
        client_contact_name="Mariana",
        vendor_name="Servicios Aurora",
        requirement_name="Constancia de situación fiscal",
        due_date=date(2026, 7, 15),
        days_remaining=7,
        severity="yellow",
        client_portal_url="https://app.checkwise.mx/client/vendors/v-1",
    )
    assert "Próximo vencimiento de proveedor: Servicios Aurora" == subject
    assert "Hola Mariana," in body
    assert "Servicios Aurora" in body
    # Client email shouldn't say "Te quedan" (provider-facing copy);
    # it says "Le quedan" to refer to the provider.
    assert "Le quedan 7 días" in body
    assert "https://app.checkwise.mx/client/vendors/v-1" in body


# ---------------------------------------------------------------------------
# Dispatch tests — DB-backed, SMTP monkeypatched
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


@pytest.fixture
def configured_smtp(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Force ``smtp_configured()`` true and capture every send call."""
    from app.services import email_delivery, transactional_email

    sent: list[dict[str, Any]] = []

    def fake_smtp_configured() -> bool:
        return True

    def fake_send(*, to_email: str, subject: str, body: str) -> EmailDeliveryResult:
        sent.append({"to": to_email, "subject": subject, "body": body})
        return EmailDeliveryResult(delivered=True, status="sent")

    monkeypatch.setattr(email_delivery, "smtp_configured", fake_smtp_configured)
    monkeypatch.setattr(
        email_delivery, "send_transactional_email", fake_send
    )
    monkeypatch.setattr(
        transactional_email, "smtp_configured", fake_smtp_configured
    )
    monkeypatch.setattr(
        transactional_email, "send_transactional_email", fake_send
    )
    return sent


def _seed_full_workspace_with_submission(
    db_factory,
    *,
    contact_preference: str = "email",
) -> dict[str, Any]:
    """Seed a minimal client + vendor + workspace + owner-user
    + institution + requirement + submission so the dispatch
    helpers have everything they need to render an email."""
    db: Session = db_factory()
    try:
        client = Client(name="Cliente Demo", rfc="DEM010101AAA")
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id,
            name="Servicios Aurora",
            rfc="SAU010101AB1",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        user = User(
            email="proveedor@example.com",
            password_hash=hash_password("Test!2026"),
            full_name="Jorge Luna",
            status="active",
            contact_preference=contact_preference,
        )
        db.add(user)
        db.flush()
        workspace = ProviderWorkspace(
            client_id=client.id,
            vendor_id=vendor.id,
            persona_type="moral",
            display_name="Servicios Aurora",
            access_token="SECRET-AAA",
            owner_user_id=user.id,
        )
        db.add(workspace)
        db.flush()
        institution = Institution(code="sat", name="SAT")
        db.add(institution)
        db.flush()
        requirement = Requirement(
            code="REC-SAT-CSF",
            name="Constancia de situación fiscal",
            institution_id=institution.id,
            load_type="trimestral",
            frequency="trimestral",
            risk_level="medium",
            current_version=1,
        )
        db.add(requirement)
        db.flush()
        period = Period(code="2026-M05", period_type="mensual", period_key="2026-M05")
        db.add(period)
        db.flush()
        submission = Submission(
            client_id=client.id,
            vendor_id=vendor.id,
            institution_id=institution.id,
            requirement_id=requirement.id,
            period_id=period.id,
            status="aprobado",
            load_type="mensual",
            requirement_code=requirement.code,
            period_key="2026-M05",
        )
        db.add(submission)
        db.flush()
        doc = Document(
            submission_id=submission.id,
            storage_key="local://x.pdf",
            original_filename="csf.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            sha256="a" * 64,
        )
        db.add(doc)
        db.commit()
        return {
            "client_id": client.id,
            "vendor_id": vendor.id,
            "workspace_id": workspace.id,
            "user_id": user.id,
            "submission_id": submission.id,
        }
    finally:
        db.close()


def _seed_client_admin(db_factory, *, client_id: str, contact_preference: str = "email") -> str:
    db: Session = db_factory()
    try:
        user = User(
            email="admin@cliente.example",
            password_hash=hash_password("Test!2026"),
            full_name="Mariana Soto",
            status="active",
            contact_preference=contact_preference,
        )
        db.add(user)
        db.flush()
        org = Organization(
            name="Cliente Demo",
            kind="client",
            client_id=client_id,
        )
        db.add(org)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org.id,
                role="client_admin",
                status="active",
            )
        )
        db.commit()
        return user.id
    finally:
        db.close()


def test_decision_email_sent_when_preference_allows(
    api_client: TestClient, db_factory, configured_smtp
) -> None:
    seeded = _seed_full_workspace_with_submission(db_factory)
    db = db_factory()
    try:
        submission = db.get(Submission, seeded["submission_id"])
        assert submission is not None
        result = email_provider_of_reviewer_decision(
            db,
            submission=submission,
            action="approve",
            reason=None,
            observations=None,
            portal_base_url="https://app.checkwise.mx",
        )
        db.commit()
    finally:
        db.close()
    assert result.status == "sent"
    assert len(configured_smtp) == 1
    sent = configured_smtp[0]
    assert sent["to"] == "proveedor@example.com"
    assert "Tu documento fue aprobado" in sent["subject"]


def test_decision_email_skipped_when_preference_excludes_email(
    api_client: TestClient, db_factory, configured_smtp
) -> None:
    """Junta lock: ``contact_preference="whatsapp"`` users must NOT
    receive email (WhatsApp transport is a separate follow-up)."""
    seeded = _seed_full_workspace_with_submission(
        db_factory, contact_preference="whatsapp"
    )
    db = db_factory()
    try:
        submission = db.get(Submission, seeded["submission_id"])
        assert submission is not None
        result = email_provider_of_reviewer_decision(
            db,
            submission=submission,
            action="approve",
            reason=None,
            observations=None,
            portal_base_url="https://app.checkwise.mx",
        )
        db.commit()
    finally:
        db.close()
    assert result.status == "skipped"
    assert result.error == "preference_excludes_email"
    assert configured_smtp == []


def test_renewal_email_sends_to_both_provider_and_client_admin(
    api_client: TestClient, db_factory, configured_smtp
) -> None:
    """Junta lock: both the provider AND the client_admin get
    emailed on each threshold cross."""
    seeded = _seed_full_workspace_with_submission(db_factory)
    _seed_client_admin(db_factory, client_id=seeded["client_id"])

    db = db_factory()
    try:
        workspace = db.get(ProviderWorkspace, seeded["workspace_id"])
        vendor = db.get(Vendor, seeded["vendor_id"])
        assert workspace is not None and vendor is not None
        provider_result, client_result = email_renewal_threshold_crossed(
            db,
            workspace=workspace,
            vendor=vendor,
            requirement_code="REC-SAT-CSF",
            requirement_name="Constancia de situación fiscal",
            due_date=date(2026, 7, 15),
            days_remaining=14,
            severity="yellow",
            portal_base_url="https://app.checkwise.mx",
            client_portal_base_url="https://app.checkwise.mx",
        )
        db.commit()
    finally:
        db.close()
    assert provider_result.status == "sent"
    assert client_result.status == "sent"
    assert {sent["to"] for sent in configured_smtp} == {
        "proveedor@example.com",
        "admin@cliente.example",
    }


def test_renewal_email_skipped_when_no_client_admin_exists(
    api_client: TestClient, db_factory, configured_smtp
) -> None:
    """Without a client_admin in the org graph the client-side email
    short-circuits cleanly; the provider side still goes out."""
    seeded = _seed_full_workspace_with_submission(db_factory)
    # Note: no _seed_client_admin call.
    db = db_factory()
    try:
        workspace = db.get(ProviderWorkspace, seeded["workspace_id"])
        vendor = db.get(Vendor, seeded["vendor_id"])
        assert workspace is not None and vendor is not None
        provider_result, client_result = email_renewal_threshold_crossed(
            db,
            workspace=workspace,
            vendor=vendor,
            requirement_code="REC-SAT-CSF",
            requirement_name="Constancia de situación fiscal",
            due_date=date(2026, 7, 15),
            days_remaining=14,
            severity="yellow",
            portal_base_url="https://app.checkwise.mx",
            client_portal_base_url="https://app.checkwise.mx",
        )
        db.commit()
    finally:
        db.close()
    assert provider_result.status == "sent"
    assert client_result.status == "skipped"
    assert client_result.error == "no_client_admin"
    assert len(configured_smtp) == 1
    assert configured_smtp[0]["to"] == "proveedor@example.com"


def test_smtp_not_configured_short_circuits_without_raising(
    api_client: TestClient, db_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When SMTP creds are absent the helpers return ``"skipped"``
    so the reviewer flow and the renewal cron commit cleanly."""
    from app.services import email_delivery, transactional_email

    monkeypatch.setattr(email_delivery, "smtp_configured", lambda: False)
    monkeypatch.setattr(transactional_email, "smtp_configured", lambda: False)

    seeded = _seed_full_workspace_with_submission(db_factory)
    db = db_factory()
    try:
        submission = db.get(Submission, seeded["submission_id"])
        assert submission is not None
        result = email_provider_of_reviewer_decision(
            db,
            submission=submission,
            action="approve",
            reason=None,
            observations=None,
            portal_base_url="https://app.checkwise.mx",
        )
    finally:
        db.close()
    assert result.status == "skipped"
    assert result.error == "smtp_not_configured"
