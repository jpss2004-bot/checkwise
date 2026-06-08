"""Seed the approved local-only user-testing scenario.

Creates one synthetic client portfolio with three providers:

* Provider A: high compliance / mostly complete.
* Provider B: partial compliance / action required. Mina Olaez is the
  provider-side tester for this workspace.
* Provider C: problematic compliance / review required.

The script writes only synthetic PDFs. It refuses non-local
environments and does not read or upload any real customer documents.

Usage:
  cd apps/api
  .venv/bin/python scripts/seed_user_testing_scenario.py
"""

from __future__ import annotations

import hashlib
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from sqlalchemy import select

# Make ``app`` importable when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.constants.statuses import DocumentStatus  # noqa: E402
from app.core.compliance_catalog import recurring_for_year  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.seed import seed_catalog  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Client,
    ClientNotification,
    ComplianceSnapshot,
    Document,
    DocumentInspection,
    DocumentStatusHistory,
    Institution,
    Membership,
    Organization,
    Period,
    ProviderWorkspace,
    Report,
    ReportConversation,
    ReportExport,
    ReportShare,
    ReportVersion,
    Requirement,
    RequirementVersion,
    Submission,
    User,
    Validation,
    ValidationEvent,
    Vendor,
    WiseEvent,
)
from app.models.entities import utc_now  # noqa: E402
from app.services.audit_log import add_audit_event  # noqa: E402
from app.services.auth import hash_password  # noqa: E402
from app.services.storage import LocalStorageService  # noqa: E402

SCENARIO_TAG = "user_testing_2026_06_01"
CLIENT_NAME = "Cliente Piloto User Testing · Local"
CLIENT_RFC = "CUT260601AA1"
CLIENT_ORG_NAME = "Cliente Piloto User Testing — Local"
INTERNAL_ORG_NAME = "LegalShelf User Testing — Local"

MAYELA_EMAIL = "mayela.user-test@checkwise.local"
MAYELA_PASSWORD = "MayelaLocal!2026"
ANWAR_EMAIL = "anuar.user-test@checkwise.local"
ANWAR_PASSWORD = "AnuarLocal!2026"
MINA_EMAIL = "mina.olaez.user-test@checkwise.local"
MINA_PASSWORD = "MinaLocal!2026"

SCENARIO_NAMESPACE = uuid.UUID("03b62ad7-b7f2-4f9f-bc04-260601000001")


@dataclass(frozen=True)
class ProviderSeed:
    key: str
    label: str
    vendor_name: str
    vendor_rfc: str
    owner_name: str
    owner_email: str
    owner_password: str
    workspace_id: str
    workspace_token: str
    onboarding_complete: bool
    scenario_note: str


PROVIDERS = [
    ProviderSeed(
        key="provider-a",
        label="Provider A — high compliance",
        vendor_name="Servicios Alfa Sintéticos · Local",
        vendor_rfc="SAS260601AA1",
        owner_name="Operaciones Alfa",
        owner_email="provider.alfa.user-test@checkwise.local",
        owner_password="ProviderAlfa!2026",
        workspace_id="ut-20260601-provider-a",
        workspace_token="ut-local-token-provider-a",
        onboarding_complete=True,
        scenario_note="Mostly complete and healthy portfolio state.",
    ),
    ProviderSeed(
        key="provider-b",
        label="Provider B — partial compliance",
        vendor_name="Servicios Beta Sintéticos · Local",
        vendor_rfc="SBS260601BB2",
        owner_name="Mina Olaez",
        owner_email=MINA_EMAIL,
        owner_password=MINA_PASSWORD,
        workspace_id="ut-20260601-provider-b",
        workspace_token="ut-local-token-provider-b",
        onboarding_complete=True,
        scenario_note="Partial compliance with pending and mismatch cases.",
    ),
    ProviderSeed(
        key="provider-c",
        label="Provider C — problematic compliance",
        vendor_name="Servicios Cobre Sintéticos · Local",
        vendor_rfc="SCS260601CC3",
        owner_name="Operaciones Cobre",
        owner_email="provider.cobre.user-test@checkwise.local",
        owner_password="ProviderCobre!2026",
        workspace_id="ut-20260601-provider-c",
        workspace_token="ut-local-token-provider-c",
        onboarding_complete=False,
        scenario_note="Problematic provider with rejected, expired, and clarification states.",
    ),
]


def _id(value: str) -> str:
    return str(uuid.uuid5(SCENARIO_NAMESPACE, value))


def _assert_local_only() -> None:
    if not settings.is_local_env:
        raise SystemExit(
            "Refusing to seed user-testing scenario outside CHECKWISE_ENV=local."
        )
    parsed = urlparse(settings.sqlalchemy_url)
    if parsed.scheme.startswith("sqlite"):
        return
    host = (parsed.hostname or "").lower()
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit(
            f"Refusing to seed user-testing scenario against non-local DB host: {host!r}."
        )


def _render_synthetic_pdf(
    *,
    title: str,
    provider: ProviderSeed,
    requirement_code: str,
    period_key: str | None,
    status: str,
    reviewer_note: str | None,
) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER

    c.setFillColor(HexColor("#ECFEFF"))
    c.rect(0, height - 66, width, 66, fill=1, stroke=0)
    c.setFillColor(HexColor("#013557"))
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, height - 38, "DOCUMENTO SINTETICO · CHECKWISE USER TEST")

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 21)
    c.drawString(72, height - 120, title)
    c.setFont("Helvetica", 10)
    c.drawString(72, height - 146, "Uso: escenario local de pruebas de usuario. Sin validez fiscal, laboral ni legal.")

    rows = [
        ("Proveedor", provider.vendor_name),
        ("RFC sintetico", provider.vendor_rfc),
        ("Requisito", requirement_code),
        ("Periodo", period_key or "alta-inicial"),
        ("Estado esperado", status),
        ("Escenario", provider.scenario_note),
    ]
    y = height - 190
    for key, value in rows:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(72, y, f"{key}:")
        c.setFont("Helvetica", 10)
        c.drawString(180, y, value)
        y -= 18

    body = [
        "Este PDF fue generado automaticamente para probar CheckWise sin exponer",
        "documentos reales, datos personales, informacion fiscal, nomina o folios",
        "de proveedores reales.",
        "",
        "Cualquier parecido con una constancia, acuse, pago, declaracion o",
        "liquidacion real es intencional solo a nivel de categoria documental.",
        "Los datos, importes, identificadores y fechas son ficticios.",
    ]
    if reviewer_note:
        body.extend(["", f"Nota de revisor sintetica: {reviewer_note}"])

    text = c.beginText(72, y - 18)
    text.setFont("Helvetica", 10)
    text.setLeading(15)
    for line in body:
        text.textLine(line)
    c.drawText(text)

    c.setFillColor(HexColor("#B91C1C"))
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(width / 2, 52, "NO SUBIR A PRODUCCION · NO USAR COMO EVIDENCIA REAL")
    c.showPage()
    c.save()
    return buffer.getvalue()


def _storage_key(provider: ProviderSeed, requirement_code: str, period_key: str | None) -> str:
    safe_period = (period_key or "alta-inicial").replace("/", "-")
    safe_req = requirement_code.lower().replace("_", "-")
    return f"user-testing/2026-06-01/{provider.key}/{safe_period}/{safe_req}.pdf"


def _period_type(period_key: str | None) -> str:
    if not period_key:
        return "alta_inicial"
    if "-B" in period_key:
        return "bimestral"
    if "-Q" in period_key:
        return "cuatrimestral"
    if "-A" in period_key:
        return "anual"
    return "mensual"


def _get_or_create_period(db, *, period_key: str | None) -> str:
    code = f"{SCENARIO_TAG}-{period_key or 'alta-inicial'}"
    ptype = _period_type(period_key)
    row = db.scalar(select(Period).where(Period.code == code, Period.period_type == ptype))
    if row is not None:
        return row.id
    year = None
    month = None
    if period_key and period_key[:4].isdigit():
        year = int(period_key[:4])
    if period_key and "-M" in period_key:
        month = int(period_key.split("-M", 1)[1])
    row = Period(
        code=code,
        period_key=period_key,
        year=year,
        month=month,
        period_type=ptype,
    )
    db.add(row)
    db.flush()
    return row.id


def _catalog_lookup() -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for item in recurring_for_year(2026, "moral"):
        out[item.code] = (item.period_key, item.frequency)
    return out


def _reviewer_note_for(status: str, explicit: str | None) -> tuple[str | None, str | None]:
    if explicit:
        if status == DocumentStatus.RECHAZADO.value:
            return "reject", explicit
        if status == DocumentStatus.REQUIERE_ACLARACION.value:
            return "request_clarification", explicit
        if status == DocumentStatus.EXCEPCION_LEGAL.value:
            return "mark_exception", explicit
        if status == DocumentStatus.APROBADO.value:
            return "approve", explicit
    return None, explicit


def _insert_submission(
    db,
    *,
    provider: ProviderSeed,
    client_id: str,
    vendor_id: str,
    requirement_code: str,
    status_value: str,
    submitted_at: datetime,
    period_key: str | None = None,
    filename: str | None = None,
    reviewer_note: str | None = None,
) -> None:
    requirement = db.scalar(select(Requirement).where(Requirement.code == requirement_code))
    if requirement is None:
        raise RuntimeError(f"Missing seeded requirement: {requirement_code}")
    version = db.scalar(
        select(RequirementVersion)
        .where(RequirementVersion.requirement_id == requirement.id)
        .order_by(RequirementVersion.version.asc())
        .limit(1)
    )
    institution = db.get(Institution, requirement.institution_id)
    period_id = _get_or_create_period(db, period_key=period_key)

    submission = Submission(
        id=_id(f"{provider.key}:{requirement_code}:{period_key or 'onboarding'}"),
        client_id=client_id,
        vendor_id=vendor_id,
        institution_id=requirement.institution_id,
        requirement_id=requirement.id,
        requirement_version_id=version.id if version else None,
        period_id=period_id,
        status=status_value,
        load_type=requirement.frequency,
        requirement_code=requirement_code,
        period_key=period_key,
        comments=f"{SCENARIO_TAG}: {provider.label}",
        submitted_by=provider.owner_name,
        created_at=submitted_at,
        updated_at=submitted_at,
    )
    db.add(submission)
    db.flush()

    display_title = requirement.name
    pdf_bytes = _render_synthetic_pdf(
        title=display_title,
        provider=provider,
        requirement_code=requirement_code,
        period_key=period_key,
        status=status_value,
        reviewer_note=reviewer_note,
    )
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    storage_key = _storage_key(provider, requirement_code, period_key)
    LocalStorageService().save_bytes(
        storage_key=storage_key,
        data=pdf_bytes,
        content_type="application/pdf",
    )
    document = Document(
        id=_id(f"document:{provider.key}:{requirement_code}:{period_key or 'onboarding'}"),
        submission_id=submission.id,
        storage_key=storage_key,
        original_filename=filename
        or f"{provider.key}-{requirement_code.lower()}-{period_key or 'alta'}.pdf",
        mime_type="application/pdf",
        size_bytes=len(pdf_bytes),
        sha256=digest,
        status=status_value,
        ocr_status="not_started",
        created_at=submitted_at,
        updated_at=submitted_at,
    )
    db.add(document)
    db.flush()

    db.add(
        DocumentInspection(
            id=_id(f"inspection:{provider.key}:{requirement_code}:{period_key or 'onboarding'}"),
            document_id=document.id,
            is_pdf=True,
            is_corrupt=False,
            is_encrypted=False,
            page_count=1,
            text_char_count=1200,
            has_text=True,
            is_probably_scanned=False,
            detected_institution=institution.code if institution else None,
            detected_document_type=requirement.name,
            detected_rfcs=[provider.vendor_rfc],
            detected_dates=[submitted_at.date().isoformat()],
            period_mentions=[period_key] if period_key else [],
            requirement_match_confidence=0.92
            if status_value in {DocumentStatus.APROBADO.value, DocumentStatus.PREVALIDADO.value}
            else 0.61,
            mismatch_reason=(
                "RFC sintetico no coincide con el proveedor esperado."
                if status_value == DocumentStatus.POSIBLE_MISMATCH.value
                else None
            ),
            raw_metadata={"scenario": SCENARIO_TAG, "synthetic": True},
            created_at=submitted_at,
            updated_at=submitted_at,
        )
    )
    db.add(
        DocumentStatusHistory(
            id=_id(f"history:received:{provider.key}:{requirement_code}:{period_key or 'onboarding'}"),
            submission_id=submission.id,
            document_id=document.id,
            from_status=None,
            to_status=DocumentStatus.RECIBIDO.value,
            reason="Documento sintetico recibido para prueba local.",
            actor=f"provider:{provider.owner_name}",
            created_at=submitted_at,
        )
    )
    if status_value != DocumentStatus.RECIBIDO.value:
        db.add(
            DocumentStatusHistory(
                id=_id(f"history:state:{provider.key}:{requirement_code}:{period_key or 'onboarding'}"),
                submission_id=submission.id,
                document_id=document.id,
                from_status=DocumentStatus.RECIBIDO.value,
                to_status=status_value,
                reason=reviewer_note,
                actor="system:user_testing_seed",
                created_at=submitted_at + timedelta(minutes=5),
            )
        )

    db.add(
        Validation(
            id=_id(f"validation:{provider.key}:{requirement_code}:{period_key or 'onboarding'}"),
            submission_id=submission.id,
            document_id=document.id,
            rule_code="synthetic_fixture",
            rule_type="user_testing_seed",
            result="pass" if status_value != DocumentStatus.POSIBLE_MISMATCH.value else "warning",
            severity="info" if status_value != DocumentStatus.POSIBLE_MISMATCH.value else "warning",
            message="Fixture sintetico generado localmente; no contiene datos reales.",
            requires_human_review=status_value
            in {
                DocumentStatus.PENDIENTE_REVISION.value,
                DocumentStatus.POSIBLE_MISMATCH.value,
                DocumentStatus.REQUIERE_ACLARACION.value,
                DocumentStatus.RECHAZADO.value,
            },
            created_at=submitted_at,
            updated_at=submitted_at,
        )
    )

    action, note = _reviewer_note_for(status_value, reviewer_note)
    if action and note:
        db.add(
            ValidationEvent(
                id=_id(f"review:{provider.key}:{requirement_code}:{period_key or 'onboarding'}"),
                submission_id=submission.id,
                document_id=document.id,
                event_type="reviewer_decision",
                rule_code="reviewer_decision",
                result=action,
                severity="info" if action == "approve" else "warning",
                message=note,
                confidence=None,
                payload={
                    "scenario": SCENARIO_TAG,
                    "synthetic": True,
                    "from_status": DocumentStatus.PENDIENTE_REVISION.value,
                    "to_status": status_value,
                },
                actor_type="reviewer",
                created_at=submitted_at + timedelta(hours=2),
            )
        )
    elif status_value == DocumentStatus.POSIBLE_MISMATCH.value:
        db.add(
            ValidationEvent(
                id=_id(f"mismatch:{provider.key}:{requirement_code}:{period_key or 'onboarding'}"),
                submission_id=submission.id,
                document_id=document.id,
                event_type="prevalidation",
                rule_code="synthetic_mismatch",
                result="warning",
                severity="warning",
                message=note or "Posible mismatch sintetico: revisar RFC y periodo.",
                confidence=0.61,
                payload={"scenario": SCENARIO_TAG, "synthetic": True},
                actor_type="system",
                created_at=submitted_at + timedelta(minutes=6),
            )
        )


def _wipe_existing(db) -> None:
    provider_workspace_ids = [p.workspace_id for p in PROVIDERS]
    provider_emails = [p.owner_email for p in PROVIDERS]
    user_emails = [MAYELA_EMAIL, ANWAR_EMAIL, "anwar.user-test@checkwise.local", *provider_emails]

    vendor_ids = set(
        db.scalars(
            select(ProviderWorkspace.vendor_id).where(
                ProviderWorkspace.id.in_(provider_workspace_ids)
            )
        ).all()
    )
    client = db.scalar(select(Client).where(Client.name == CLIENT_NAME))
    if client is not None:
        vendor_ids.update(
            db.scalars(select(Vendor.id).where(Vendor.client_id == client.id)).all()
        )
        db.query(ClientNotification).filter(ClientNotification.client_id == client.id).delete(
            synchronize_session=False
        )

    if vendor_ids:
        db.query(WiseEvent).filter(WiseEvent.workspace_id.in_(provider_workspace_ids)).delete(
            synchronize_session=False
        )
        sub_ids = set(
            db.scalars(select(Submission.id).where(Submission.vendor_id.in_(vendor_ids))).all()
        )
        if sub_ids:
            db.query(ValidationEvent).filter(ValidationEvent.submission_id.in_(sub_ids)).delete(
                synchronize_session=False
            )
            db.query(Validation).filter(Validation.submission_id.in_(sub_ids)).delete(
                synchronize_session=False
            )
            doc_ids = set(
                db.scalars(select(Document.id).where(Document.submission_id.in_(sub_ids))).all()
            )
            if doc_ids:
                db.query(DocumentInspection).filter(DocumentInspection.document_id.in_(doc_ids)).delete(
                    synchronize_session=False
                )
                db.query(DocumentStatusHistory).filter(
                    DocumentStatusHistory.document_id.in_(doc_ids)
                ).delete(synchronize_session=False)
            db.query(Document).filter(Document.submission_id.in_(sub_ids)).delete(
                synchronize_session=False
            )
            db.query(Submission).filter(Submission.id.in_(sub_ids)).delete(
                synchronize_session=False
            )
        db.query(ProviderWorkspace).filter(ProviderWorkspace.vendor_id.in_(vendor_ids)).delete(
            synchronize_session=False
        )
        db.query(Vendor).filter(Vendor.id.in_(vendor_ids)).delete(synchronize_session=False)

    orgs = list(
        db.scalars(
            select(Organization).where(
                Organization.name.in_([CLIENT_ORG_NAME, INTERNAL_ORG_NAME])
            )
        )
    )
    if orgs:
        org_ids = [o.id for o in orgs]
        report_ids = set(
            db.scalars(select(Report.id).where(Report.organization_id.in_(org_ids))).all()
        )
        if report_ids:
            db.query(ReportConversation).filter(
                ReportConversation.report_id.in_(report_ids)
            ).delete(synchronize_session=False)
            db.query(ReportExport).filter(ReportExport.report_id.in_(report_ids)).delete(
                synchronize_session=False
            )
            db.query(ReportShare).filter(ReportShare.report_id.in_(report_ids)).delete(
                synchronize_session=False
            )
            db.query(ReportVersion).filter(ReportVersion.report_id.in_(report_ids)).delete(
                synchronize_session=False
            )
            db.query(Report).filter(Report.id.in_(report_ids)).delete(
                synchronize_session=False
            )
        db.query(ComplianceSnapshot).filter(
            ComplianceSnapshot.organization_id.in_(org_ids)
        ).delete(synchronize_session=False)
        db.query(Membership).filter(Membership.organization_id.in_(org_ids)).delete(
            synchronize_session=False
        )
        db.query(Organization).filter(Organization.id.in_(org_ids)).delete(
            synchronize_session=False
        )

    users = list(db.scalars(select(User).where(User.email.in_(user_emails))))
    if users:
        user_ids = [u.id for u in users]
        db.query(Membership).filter(Membership.user_id.in_(user_ids)).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)

    if client is not None:
        db.delete(client)
    db.flush()


def _user(email: str, password: str, full_name: str) -> User:
    return User(
        id=_id(f"user:{email}"),
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        status="active",
        must_change_password=False,
    )


def _seed_users_and_orgs(db) -> tuple[str, str, str, dict[str, str]]:
    mayela = _user(MAYELA_EMAIL, MAYELA_PASSWORD, "Mayela")
    anwar = _user(ANWAR_EMAIL, ANWAR_PASSWORD, "Anuar")
    db.add_all([mayela, anwar])
    provider_user_ids: dict[str, str] = {}
    for provider in PROVIDERS:
        user = _user(provider.owner_email, provider.owner_password, provider.owner_name)
        db.add(user)
        provider_user_ids[provider.key] = user.id
    db.flush()

    client = Client(
        id=_id("client"),
        name=CLIENT_NAME,
        rfc=CLIENT_RFC,
        email=MAYELA_EMAIL,
        responsible_name="Mayela",
        industry="Servicios corporativos",
        fiscal_address="Direccion sintetica de pruebas locales",
        phone="+52 55 0000 0000",
        notes=f"{SCENARIO_TAG}: cliente sintetico local para pruebas de usuario.",
        onboarding_completed_at=utc_now(),
        status="active",
    )
    db.add(client)
    db.flush()

    client_org = Organization(
        id=_id("client-org"),
        name=CLIENT_ORG_NAME,
        kind="client",
        client_id=client.id,
        status="active",
    )
    internal_org = Organization(
        id=_id("internal-org"),
        name=INTERNAL_ORG_NAME,
        kind="internal",
        status="active",
    )
    db.add_all([client_org, internal_org])
    db.flush()
    db.add(
        Membership(
            id=_id("membership:mayela"),
            user_id=mayela.id,
            organization_id=client_org.id,
            role="client_admin",
            status="active",
        )
    )
    for role in ("internal_admin", "reviewer"):
        db.add(
            Membership(
                id=_id(f"membership:anwar:{role}"),
                user_id=anwar.id,
                organization_id=internal_org.id,
                role=role,
                status="active",
            )
        )
    db.flush()
    return client.id, client_org.id, anwar.id, provider_user_ids


def _seed_provider_rows(db, *, client_id: str, provider_user_ids: dict[str, str]) -> dict[str, str]:
    vendor_ids: dict[str, str] = {}
    now = utc_now()
    for provider in PROVIDERS:
        vendor = Vendor(
            id=_id(f"vendor:{provider.key}"),
            client_id=client_id,
            name=provider.vendor_name,
            rfc=provider.vendor_rfc,
            contact_name=provider.owner_name,
            contact_email=provider.owner_email,
            contact_phone="+52 55 0000 0000",
            repse_id=f"REPSE-SYN-{provider.key.upper()}",
            persona_type="moral",
            status="active",
        )
        db.add(vendor)
        db.flush()
        workspace = ProviderWorkspace(
            id=provider.workspace_id,
            client_id=client_id,
            vendor_id=vendor.id,
            owner_user_id=provider_user_ids[provider.key],
            filial_name="Filial sintetica local",
            persona_type="moral",
            display_name=provider.vendor_name,
            access_token=provider.workspace_token,
            onboarding_completed_at=now - timedelta(days=20)
            if provider.onboarding_complete
            else None,
            profile_confirmed_at=now - timedelta(days=20),
            legal_consent_accepted_at=now - timedelta(days=20),
            legal_consent_version="v1",
            status="active",
        )
        db.add(workspace)
        db.flush()
        vendor_ids[provider.key] = vendor.id
    return vendor_ids


def _seed_submissions(db, *, client_id: str, vendor_ids: dict[str, str]) -> int:
    catalog = _catalog_lookup()
    now = utc_now()

    def rec(provider_key: str, code: str, status_value: str, days: int, note: str | None = None) -> None:
        provider = next(p for p in PROVIDERS if p.key == provider_key)
        period_key, _freq = catalog[code]
        _insert_submission(
            db,
            provider=provider,
            client_id=client_id,
            vendor_id=vendor_ids[provider_key],
            requirement_code=code,
            period_key=period_key,
            status_value=status_value,
            submitted_at=now - timedelta(days=days),
            reviewer_note=note,
        )

    def onb(provider_key: str, code: str, status_value: str, days: int, note: str | None = None) -> None:
        provider = next(p for p in PROVIDERS if p.key == provider_key)
        _insert_submission(
            db,
            provider=provider,
            client_id=client_id,
            vendor_id=vendor_ids[provider_key],
            requirement_code=code,
            period_key=None,
            status_value=status_value,
            submitted_at=now - timedelta(days=days),
            reviewer_note=note,
        )

    count = 0
    onboarding_codes = [
        "ONB-CONT-001",
        "ONB-CORP-M-001",
        "ONB-CORP-M-002",
        "ONB-REPSE-001",
        "ONB-PATR-001",
    ]

    for code in onboarding_codes:
        onb("provider-a", code, DocumentStatus.APROBADO.value, 22, "Validado en escenario sintetico.")
        onb("provider-b", code, DocumentStatus.APROBADO.value, 18, "Validado en escenario sintetico.")
        count += 2

    onb("provider-c", "ONB-CONT-001", DocumentStatus.APROBADO.value, 25, "Contrato sintetico validado.")
    onb(
        "provider-c",
        "ONB-REPSE-001",
        DocumentStatus.RECHAZADO.value,
        12,
        "El folio REPSE sintetico no corresponde al periodo indicado. Solicitar nuevo documento.",
    )
    onb(
        "provider-c",
        "ONB-PATR-001",
        DocumentStatus.REQUIERE_ACLARACION.value,
        10,
        "Falta constancia sintetica de registro patronal. El proveedor debe aclarar.",
    )
    count += 3

    # Provider A should read as genuinely green in the client portfolio.
    # The semaphore considers the full 2026 recurring catalog, so seed
    # every recurring moral-persona requirement as approved.
    for item in recurring_for_year(2026, "moral"):
        rec("provider-a", item.code, DocumentStatus.APROBADO.value, 8, "Documento sintetico aprobado.")
        count += 1

    rec("provider-b", "REC-SAT-2026-04-declaracion-iva", DocumentStatus.APROBADO.value, 9, "Documento sintetico aprobado.")
    rec("provider-b", "REC-IMSS-2026-04-comprobante-de-pago-bancario", DocumentStatus.PENDIENTE_REVISION.value, 5)
    rec("provider-b", "REC-INFONAVIT-2026-03-comprobante-de-pago-bancario", DocumentStatus.PENDIENTE_REVISION.value, 3)
    rec("provider-b", "REC-ACUSES-2026-05-acuse-sisub", DocumentStatus.PENDIENTE_REVISION.value, 2)
    count += 4

    rec(
        "provider-c",
        "REC-SAT-2026-03-declaracion-iva",
        DocumentStatus.RECHAZADO.value,
        20,
        "La declaracion sintetica trae periodo incorrecto. Requiere sustitucion.",
    )
    rec(
        "provider-c",
        "REC-SAT-2026-04-comprobantes-de-nomina-de-los-trabajadores",
        DocumentStatus.REQUIERE_ACLARACION.value,
        14,
        "Falta un comprobante de nomina sintetico en el paquete.",
    )
    rec("provider-c", "REC-IMSS-2026-03-comprobante-de-pago-bancario", DocumentStatus.VENCIDO.value, 45)
    rec("provider-c", "REC-INFONAVIT-2026-03-comprobante-de-pago-bancario", DocumentStatus.POSIBLE_MISMATCH.value, 13)
    rec(
        "provider-c",
        "REC-ACUSES-2026-05-acuse-icsoe",
        DocumentStatus.RECHAZADO.value,
        11,
        "El acuse ICSOE sintetico esta incompleto; falta pagina de confirmacion.",
    )
    count += 5
    return count


def main() -> None:
    _assert_local_only()
    with SessionLocal() as db:
        _wipe_existing(db)
        seed_catalog(db, years=(2026,))
        client_id, _client_org_id, anwar_user_id, provider_user_ids = _seed_users_and_orgs(db)
        vendor_ids = _seed_provider_rows(
            db, client_id=client_id, provider_user_ids=provider_user_ids
        )
        submissions = _seed_submissions(db, client_id=client_id, vendor_ids=vendor_ids)
        add_audit_event(
            db,
            action="user_testing.scenario_seeded",
            entity_type="client",
            entity_id=client_id,
            actor_type="system",
            actor_id=anwar_user_id,
            metadata={
                "scenario": SCENARIO_TAG,
                "local_only": True,
                "synthetic_documents": True,
                "providers": [p.vendor_name for p in PROVIDERS],
                "submissions": submissions,
            },
        )
        db.commit()

    print("Seeded local-only CheckWise user-testing scenario.")
    print("")
    print("Environment:")
    print("  Frontend: http://localhost:3000")
    print("")
    print("Synthetic test accounts:")
    print(f"  Mayela client_admin: {MAYELA_EMAIL} / {MAYELA_PASSWORD}")
    print(f"  Anuar internal_admin+reviewer: {ANWAR_EMAIL} / {ANWAR_PASSWORD}")
    print(f"  Mina provider_admin: {MINA_EMAIL} / {MINA_PASSWORD}")
    print("")
    print("Provider portfolio:")
    for provider in PROVIDERS:
        print(f"  {provider.label}: {provider.vendor_name} ({provider.workspace_id})")
    print("")
    print("All seeded PDFs are synthetic and stored under:")
    print(f"  {settings.LOCAL_STORAGE_PATH}/user-testing/2026-06-01/")


if __name__ == "__main__":
    main()
