"""
Local dev seed — gives you something to click on.

Idempotent: re-running deletes the demo rows it created and re-inserts
them with deterministic ids / tokens / passwords. Safe to run as many
times as you want; will not touch the canonical catalog seed.

Creates:
- 1 internal LegalShelf org + 1 user "ada@legalshelf.mx" with roles
  ``internal_admin`` + ``reviewer``. Password: "demo1234".
- 1 client + 1 vendor + 1 provider workspace with a deterministic
  ``access_token`` = "demo-token" so you can paste it into the portal.
- 4 sample submissions in different review states so the reviewer
  queue and the provider calendar both have content.

Usage:
  cd backend
  .venv/bin/python scripts/dev_seed.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Make ``app`` importable when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Client,
    Document,
    DocumentStatusHistory,
    Institution,
    Membership,
    Organization,
    Period,
    ProviderWorkspace,
    Report,
    ReportConversation,
    ReportVersion,
    Requirement,
    RequirementVersion,
    Submission,
    User,
    Vendor,
)
from app.services.auth import hash_password  # noqa: E402

DEMO_USER_EMAIL = "ada@legalshelf.mx"
DEMO_USER_PASSWORD = "demo1234"
DEMO_USER_FULLNAME = "Ada Reyes"
DEMO_ORG_NAME = "LegalShelf — Demo"

DEMO_PROVIDER_EMAIL = "proveedor.demo@checkwise.mx"
DEMO_PROVIDER_TEMP_PASSWORD = "CheckWiseDemo!2026"
DEMO_PROVIDER_FULLNAME = "Distribuidora Nogal"

DEMO_CLIENT_NAME = "Acerogrupo Industrial · Demo"
DEMO_CLIENT_RFC = "AID010101AB1"
DEMO_VENDOR_NAME = "Distribuidora Nogal · Demo"
DEMO_VENDOR_RFC = "DNG890101AB1"
DEMO_CONTRACT_REF = "C-DEMO-001"

DEMO_WORKSPACE_TOKEN = "demo-token"
DEMO_WORKSPACE_ID = "ws-demo-0001"

# ── Boss demo account (CheckWise 1.7.1) ────────────────────────────
# Account B in the demo guide: a returning provider whose initial
# expediente is already complete, so login lands directly on the
# dashboard. Independent client + vendor + workspace from the
# first-login provider above so the two scenarios never collide.
BOSS_DEMO_EMAIL = "boss.demo@checkwise.mx"
BOSS_DEMO_PASSWORD = "BossDemo!2026"
BOSS_DEMO_FULLNAME = "Servicios Especializados Aurora"

BOSS_DEMO_CLIENT_NAME = "Constructora Aurora · Demo"
BOSS_DEMO_CLIENT_RFC = "AUR010101CD2"
BOSS_DEMO_VENDOR_NAME = "Servicios Especializados Aurora · Demo"
BOSS_DEMO_VENDOR_RFC = "SEA050101EF3"

BOSS_DEMO_WORKSPACE_ID = "ws-demo-0002"
BOSS_DEMO_WORKSPACE_TOKEN = "boss-demo-token"

# ── Client-admin demo account (CheckWise 2.1) ──────────────────────
# Read-only view across a portfolio of vendors. /client/* is gated by
# ``client_admin`` membership; we seed one Client + Organization with
# 3 vendors at varied compliance states so the client surfaces have
# real signal during demo + browser verify.
CLIENT_DEMO_EMAIL = "cliente.demo@checkwise.mx"
CLIENT_DEMO_PASSWORD = "ClienteDemo!2026"
CLIENT_DEMO_FULLNAME = "Mariana Soto"

CLIENT_PORTFOLIO_CLIENT_NAME = "Operadora Multinacional · Demo"
CLIENT_PORTFOLIO_CLIENT_RFC = "OMN010101GH4"
CLIENT_PORTFOLIO_ORG_NAME = "Operadora Multinacional — Cliente"

CLIENT_PORTFOLIO_VENDORS = [
    {
        "name": "Logística Andina · Demo",
        "rfc": "LAN020202IJ5",
        "workspace_id": "ws-demo-cli-01",
        "complete": True,
    },
    {
        "name": "Servicios Hidalgo · Demo",
        "rfc": "SHI030303KL6",
        "workspace_id": "ws-demo-cli-02",
        "complete": True,
    },
    {
        "name": "Constructora Pacífico · Demo",
        "rfc": "CPA040404MN7",
        "workspace_id": "ws-demo-cli-03",
        "complete": False,
    },
]


def _utc(year: int, month: int, day: int = 1) -> datetime:
    return datetime(year, month, day, 12, 0, 0, tzinfo=UTC)


def _wipe_demo(db) -> None:
    """Remove anything tagged with the demo identifiers so the seed
    is idempotent. Order matters because of FKs."""
    # Phase 5 (V2.1) — wipe seeded reports first so their cascades
    # release the user FK and the org row before we touch users/orgs.
    demo_org_names = (DEMO_ORG_NAME, CLIENT_PORTFOLIO_ORG_NAME)
    for org in db.scalars(select(Organization).where(Organization.name.in_(demo_org_names))):
        for rep in list(db.scalars(select(Report).where(Report.organization_id == org.id))):
            db.query(ReportConversation).filter(ReportConversation.report_id == rep.id).delete(
                synchronize_session=False
            )
            db.query(ReportVersion).filter(ReportVersion.report_id == rep.id).delete(
                synchronize_session=False
            )
            db.delete(rep)
        db.flush()

    client_portfolio_ws_ids = tuple(v["workspace_id"] for v in CLIENT_PORTFOLIO_VENDORS)
    demo_client_names = (
        DEMO_CLIENT_NAME,
        BOSS_DEMO_CLIENT_NAME,
        CLIENT_PORTFOLIO_CLIENT_NAME,
    )

    vendor_ids_to_drop: set[str] = set()
    client_ids_to_drop: set[str] = set()

    # First pass: collect vendor + client ids, then strip submissions
    # and workspaces. We defer vendor/client deletion until every
    # workspace has been cleared so multi-workspace clients (e.g. the
    # portfolio with 3 vendors) drop cleanly.
    for ws_id in (DEMO_WORKSPACE_ID, BOSS_DEMO_WORKSPACE_ID, *client_portfolio_ws_ids):
        workspace = db.scalar(select(ProviderWorkspace).where(ProviderWorkspace.id == ws_id))
        if workspace is None:
            continue
        vendor_ids_to_drop.add(workspace.vendor_id)
        client_ids_to_drop.add(workspace.client_id)

        for sub in list(
            db.scalars(select(Submission).where(Submission.vendor_id == workspace.vendor_id))
        ):
            db.query(DocumentStatusHistory).filter(
                DocumentStatusHistory.submission_id == sub.id
            ).delete(synchronize_session=False)
            db.query(Document).filter(Document.submission_id == sub.id).delete(
                synchronize_session=False
            )
            db.delete(sub)
        db.flush()

        db.delete(workspace)
        db.flush()

    # Also collect any client_id that matches a demo client by name —
    # covers vendors created outside the workspace iteration above.
    for client_row in db.scalars(select(Client).where(Client.name.in_(demo_client_names))):
        client_ids_to_drop.add(client_row.id)
        for v in db.scalars(select(Vendor).where(Vendor.client_id == client_row.id)):
            vendor_ids_to_drop.add(v.id)

    if vendor_ids_to_drop:
        db.query(Vendor).filter(Vendor.id.in_(vendor_ids_to_drop)).delete(synchronize_session=False)
        db.flush()

    # Drop demo orgs (they hold the Client FK on kind='client' rows) and
    # their memberships BEFORE we drop the clients themselves.
    for org_name in (DEMO_ORG_NAME, CLIENT_PORTFOLIO_ORG_NAME):
        org = db.scalar(select(Organization).where(Organization.name == org_name))
        if org is not None:
            db.query(Membership).filter(Membership.organization_id == org.id).delete(
                synchronize_session=False
            )
            db.delete(org)
            db.flush()

    if client_ids_to_drop:
        db.query(Client).filter(Client.id.in_(client_ids_to_drop)).delete(synchronize_session=False)
        db.flush()

    for demo_email in (
        DEMO_USER_EMAIL,
        DEMO_PROVIDER_EMAIL,
        BOSS_DEMO_EMAIL,
        CLIENT_DEMO_EMAIL,
    ):
        user = db.scalar(select(User).where(User.email == demo_email))
        if user is not None:
            db.query(Membership).filter(Membership.user_id == user.id).delete(
                synchronize_session=False
            )
            db.delete(user)
            db.flush()


def _seed_admin(db) -> tuple[str, str]:
    org = Organization(name=DEMO_ORG_NAME, kind="internal")
    db.add(org)
    db.flush()

    user = User(
        email=DEMO_USER_EMAIL,
        password_hash=hash_password(DEMO_USER_PASSWORD),
        full_name=DEMO_USER_FULLNAME,
        status="active",
    )
    db.add(user)
    db.flush()

    for role in ("internal_admin", "reviewer"):
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org.id,
                role=role,
                status="active",
            )
        )

    return user.id, org.id


def _seed_provider_user(db) -> str:
    """Create the provider demo user and return its id.

    Marked ``must_change_password=True`` so the first login forces the
    user through ``/activate`` to set a permanent password before
    reaching the workspace.
    """
    user = User(
        email=DEMO_PROVIDER_EMAIL,
        password_hash=hash_password(DEMO_PROVIDER_TEMP_PASSWORD),
        full_name=DEMO_PROVIDER_FULLNAME,
        status="active",
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    return user.id


def _seed_boss_demo_user(db) -> str:
    """Create the boss-demo user and return its id.

    Marked ``must_change_password=False`` so login lands directly on
    the workspace entry, then on the dashboard once the user clicks
    "Entrar a mi espacio".
    """
    user = User(
        email=BOSS_DEMO_EMAIL,
        password_hash=hash_password(BOSS_DEMO_PASSWORD),
        full_name=BOSS_DEMO_FULLNAME,
        status="active",
        must_change_password=False,
    )
    db.add(user)
    db.flush()
    return user.id


def _seed_boss_demo_workspace(db, *, owner_user_id: str) -> tuple[str, str, str]:
    """Boss demo workspace: provider whose initial expediente is
    already complete, so the dashboard is unlocked from first login.
    """
    client = Client(name=BOSS_DEMO_CLIENT_NAME, rfc=BOSS_DEMO_CLIENT_RFC)
    db.add(client)
    db.flush()

    vendor = Vendor(
        client_id=client.id,
        name=BOSS_DEMO_VENDOR_NAME,
        rfc=BOSS_DEMO_VENDOR_RFC,
        persona_type="moral",
    )
    db.add(vendor)
    db.flush()

    workspace = ProviderWorkspace(
        id=BOSS_DEMO_WORKSPACE_ID,
        client_id=client.id,
        vendor_id=vendor.id,
        contract_id=None,
        owner_user_id=owner_user_id,
        filial_name="Filial Centro",
        persona_type="moral",
        display_name=BOSS_DEMO_VENDOR_NAME,
        access_token=BOSS_DEMO_WORKSPACE_TOKEN,
        # Already-completed expediente. This is the field the
        # withOnboardingGate HOC reads to allow /portal/dashboard.
        onboarding_completed_at=datetime.now(UTC) - timedelta(days=14),
        status="active",
    )
    db.add(workspace)
    db.flush()

    return client.id, vendor.id, workspace.id


def _seed_workspace(db, *, owner_user_id: str) -> tuple[str, str, str]:
    client = Client(name=DEMO_CLIENT_NAME, rfc=DEMO_CLIENT_RFC)
    db.add(client)
    db.flush()

    vendor = Vendor(
        client_id=client.id,
        name=DEMO_VENDOR_NAME,
        rfc=DEMO_VENDOR_RFC,
        persona_type="moral",
    )
    db.add(vendor)
    db.flush()

    workspace = ProviderWorkspace(
        id=DEMO_WORKSPACE_ID,
        client_id=client.id,
        vendor_id=vendor.id,
        contract_id=None,
        owner_user_id=owner_user_id,
        filial_name="Filial Norte",
        persona_type="moral",
        display_name="Distribuidora Nogal · Demo",
        access_token=DEMO_WORKSPACE_TOKEN,
        onboarding_completed_at=None,
        status="active",
    )
    db.add(workspace)
    db.flush()

    return client.id, vendor.id, workspace.id


def _get_or_create_period(db, *, period_key: str, code: str, period_type: str) -> str:
    existing = db.scalar(
        select(Period).where(Period.code == code, Period.period_type == period_type)
    )
    if existing is not None:
        return existing.id
    year, month = 2026, None
    if "-M" in period_key:
        month = int(period_key.split("-M", 1)[1])
    period = Period(
        code=code,
        period_key=period_key,
        year=year,
        month=month,
        period_type=period_type,
    )
    db.add(period)
    db.flush()
    return period.id


def _seed_submissions(db, *, client_id: str, vendor_id: str) -> int:
    """Insert 4 submissions hitting the canonical SAT / IMSS catalog so
    the reviewer queue + provider calendar both have content."""

    demo_specs = [
        {
            "code": "REC-SAT-2026-03-declaracion-iva",
            "period_key": "2026-M03",
            "period_code": "2026-03-sat-iva",
            "status": "pendiente_revision",
            "filename": "iva_marzo.pdf",
            "age_hours": 4,
        },
        {
            "code": "REC-IMSS-2026-03-comprobante-de-pago-bancario",
            "period_key": "2026-M03",
            "period_code": "2026-03-imss-pago",
            "status": "posible_mismatch",
            "filename": "imss_marzo.pdf",
            "age_hours": 36,
        },
        {
            "code": "REC-SAT-2026-02-declaracion-iva",
            "period_key": "2026-M02",
            "period_code": "2026-02-sat-iva",
            "status": "aprobado",
            "filename": "iva_febrero.pdf",
            "age_hours": 24 * 35,
        },
        {
            "code": "REC-SAT-2026-01-declaracion-iva",
            "period_key": "2026-M01",
            "period_code": "2026-01-sat-iva",
            "status": "rechazado",
            "filename": "iva_enero.pdf",
            "age_hours": 24 * 60,
        },
    ]

    inserted = 0
    for spec in demo_specs:
        requirement = db.scalar(select(Requirement).where(Requirement.code == spec["code"]))
        if requirement is None:
            # If the catalog seed hasn't run, skip — but normally it has.
            continue
        version = db.scalar(
            select(RequirementVersion)
            .where(RequirementVersion.requirement_id == requirement.id)
            .order_by(RequirementVersion.version.asc())
        )
        if version is None:
            continue
        institution = db.get(Institution, requirement.institution_id)
        period_id = _get_or_create_period(
            db,
            period_key=spec["period_key"],
            code=spec["period_code"],
            period_type="mensual",
        )

        submitted_at = datetime.now(UTC) - timedelta(hours=spec["age_hours"])
        submission = Submission(
            client_id=client_id,
            vendor_id=vendor_id,
            institution_id=institution.id if institution else requirement.institution_id,
            requirement_id=requirement.id,
            requirement_version_id=version.id,
            period_id=period_id,
            status=spec["status"],
            load_type="mensual",
            requirement_code=spec["code"],
            period_key=spec["period_key"],
            created_at=submitted_at,
            updated_at=submitted_at,
        )
        db.add(submission)
        db.flush()

        doc = Document(
            submission_id=submission.id,
            storage_key=f"local://demo/{submission.id}.pdf",
            original_filename=spec["filename"],
            mime_type="application/pdf",
            size_bytes=128_000,
            sha256=("d" + spec["code"]).ljust(64, "0")[:64].replace(":", "_"),
        )
        db.add(doc)
        db.flush()
        db.add(
            DocumentStatusHistory(
                submission_id=submission.id,
                document_id=doc.id,
                from_status=None,
                to_status="recibido",
                reason=None,
                actor="system:dev_seed",
            )
        )
        if spec["status"] != "recibido":
            db.add(
                DocumentStatusHistory(
                    submission_id=submission.id,
                    document_id=doc.id,
                    from_status="recibido",
                    to_status=spec["status"],
                    reason=(
                        "RFC del PDF no coincide con el del proveedor."
                        if spec["status"] == "posible_mismatch"
                        else None
                    ),
                    actor="system:dev_seed",
                )
            )
        db.flush()
        inserted += 1

    return inserted


def _seed_client_portfolio(db) -> tuple[str, str, int, int]:
    """Phase 5 (V2.1): seed a Client + Organization + 3 vendors + sample
    submissions so /client/* is reachable and shows real signal.

    Returns (org_id, client_id, vendors_inserted, submissions_inserted).
    """
    user = User(
        email=CLIENT_DEMO_EMAIL,
        password_hash=hash_password(CLIENT_DEMO_PASSWORD),
        full_name=CLIENT_DEMO_FULLNAME,
        status="active",
        must_change_password=False,
    )
    db.add(user)
    db.flush()

    client = Client(
        name=CLIENT_PORTFOLIO_CLIENT_NAME,
        rfc=CLIENT_PORTFOLIO_CLIENT_RFC,
    )
    db.add(client)
    db.flush()

    org = Organization(
        name=CLIENT_PORTFOLIO_ORG_NAME,
        kind="client",
        client_id=client.id,
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
    db.flush()

    submissions_total = 0
    for spec in CLIENT_PORTFOLIO_VENDORS:
        vendor = Vendor(
            client_id=client.id,
            name=spec["name"],
            rfc=spec["rfc"],
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()

        workspace = ProviderWorkspace(
            id=spec["workspace_id"],
            client_id=client.id,
            vendor_id=vendor.id,
            contract_id=None,
            owner_user_id=user.id,
            filial_name="Filial principal",
            persona_type="moral",
            display_name=spec["name"],
            access_token=f"cli-portfolio-{spec['workspace_id']}",
            onboarding_completed_at=(
                datetime.now(UTC) - timedelta(days=21) if spec["complete"] else None
            ),
            status="active",
        )
        db.add(workspace)
        db.flush()

        submissions_total += _seed_submissions(db, client_id=client.id, vendor_id=vendor.id)

    return org.id, client.id, len(CLIENT_PORTFOLIO_VENDORS), submissions_total


def _seed_reports(
    db,
    *,
    legalshelf_org_id: str,
    legalshelf_user_id: str,
    client_org_id: str,
    client_user_id: str,
    client_id: str,
    boss_vendor_id: str,
) -> int:
    """Seed 3 reports with realistic block content so /portal/reports
    has populated entries for the executive demo.

    Reports cover the three canonical demo narratives:
      1. Internal executive view (LegalShelf operations)
      2. Client-facing portfolio risk view (cliente.demo)
      3. Vendor-specific missing-documents narrative
    """

    # Block specs use the exact shapes the frontend renderers expect:
    #   text     → {heading?, body}
    #   divider  → {label?}
    #   kpi_strip → config.metrics: [{label, metric_key, format}],
    #              data.resolved: [{metric_key, value, trend_pct_vs_prior}]
    # Data-driven blocks (executive_summary, vendor_risk_matrix,
    # ai_recommendation) require the AI execution pipeline to populate
    # data and are intentionally omitted from seeds — they would render
    # in their "no data" placeholder state otherwise.
    specs = [
        {
            "id": str(uuid.uuid4()),
            "organization_id": legalshelf_org_id,
            "client_id": None,
            "vendor_id": None,
            "title": "Resumen ejecutivo · Mayo 2026",
            "description": (
                "Vista panorámica del control plane: clientes, proveedores, "
                "workspaces activos, bandeja de revisión y eventos audit log."
            ),
            "audience": "internal_only",
            "status": "active",
            "created_by_user_id": legalshelf_user_id,
            "blocks": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "text",
                    "config": {
                        "heading": "Contexto",
                        "body": (
                            "Durante mayo 2026, CheckWise procesó 87 entregas "
                            "REPSE distribuidas entre SAT, IMSS e INFONAVIT. La "
                            "bandeja humana mantuvo un tiempo medio de decisión "
                            "de 9.4 horas, dentro del SLA interno de 24 horas."
                        ),
                    },
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "kpi_strip",
                    "config": {
                        "metrics": [
                            {
                                "label": "Cumplimiento",
                                "metric_key": "completion_pct",
                                "format": "percent",
                            },
                            {
                                "label": "Proveedores",
                                "metric_key": "vendors_total",
                                "format": "number",
                            },
                            {
                                "label": "En revisión",
                                "metric_key": "in_review_count",
                                "format": "number",
                            },
                            {
                                "label": "Revisión prom.",
                                "metric_key": "avg_review_hours",
                                "format": "duration_hours",
                            },
                        ],
                    },
                    "data": {
                        "resolved": [
                            {"metric_key": "completion_pct", "value": 86, "trend_pct_vs_prior": 4},
                            {"metric_key": "vendors_total", "value": 5, "trend_pct_vs_prior": 0},
                            {
                                "metric_key": "in_review_count",
                                "value": 10,
                                "trend_pct_vs_prior": -12,
                            },
                            {
                                "metric_key": "avg_review_hours",
                                "value": 9,
                                "trend_pct_vs_prior": -25,
                            },
                        ],
                    },
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "divider",
                    "config": {"label": "Bandeja humana"},
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "text",
                    "config": {
                        "heading": "Estado operativo",
                        "body": (
                            "El portafolio se mantiene saludable. Tres "
                            "proveedores presentan obligaciones vencidas "
                            "concentradas en IMSS marzo, y un proveedor "
                            "cliente está en aclaración por RFC inconsistente. "
                            "La automatización capturó 4 de cada 5 mismatches "
                            "antes de llegar al revisor humano."
                        ),
                    },
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "text",
                    "config": {
                        "heading": "Recomendación",
                        "body": (
                            "Priorizar el seguimiento con Constructora "
                            "Pacífico — su expediente lleva 21 días incompleto "
                            "y bloquea la vista de cumplimiento del cliente."
                        ),
                    },
                },
            ],
        },
        {
            "id": str(uuid.uuid4()),
            "organization_id": client_org_id,
            "client_id": client_id,
            "vendor_id": None,
            "title": "Riesgo del portafolio · Q2 2026",
            "description": (
                "Distribución del semáforo de cumplimiento por proveedor, con "
                "foco en obligaciones críticas próximas a vencer."
            ),
            "audience": "client_facing",
            "status": "active",
            "created_by_user_id": client_user_id,
            "blocks": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "text",
                    "config": {
                        "heading": "Resumen para dirección",
                        "body": (
                            "Tu portafolio de 3 proveedores REPSE presenta un "
                            "cumplimiento del 78% al cierre del Q2. Dos "
                            "proveedores están en verde, uno en amarillo por "
                            "un faltante de IMSS de marzo. No hay proveedores "
                            "en rojo este trimestre."
                        ),
                    },
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "kpi_strip",
                    "config": {
                        "metrics": [
                            {
                                "label": "Cumplimiento",
                                "metric_key": "completion_pct",
                                "format": "percent",
                            },
                            {
                                "label": "En riesgo",
                                "metric_key": "vendors_at_risk",
                                "format": "number",
                            },
                            {
                                "label": "Vencidos",
                                "metric_key": "overdue_count",
                                "format": "number",
                            },
                            {
                                "label": "Próximo en",
                                "metric_key": "days_to_next_deadline",
                                "format": "duration_days",
                            },
                        ],
                    },
                    "data": {
                        "resolved": [
                            {"metric_key": "completion_pct", "value": 78, "trend_pct_vs_prior": 3},
                            {
                                "metric_key": "vendors_at_risk",
                                "value": 1,
                                "trend_pct_vs_prior": -50,
                            },
                            {"metric_key": "overdue_count", "value": 0, "trend_pct_vs_prior": -100},
                            {
                                "metric_key": "days_to_next_deadline",
                                "value": 12,
                                "trend_pct_vs_prior": 0,
                            },
                        ],
                    },
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "divider",
                    "config": {"label": "Detalle por proveedor"},
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "text",
                    "config": {
                        "heading": "Logística Andina",
                        "body": (
                            "Cumplimiento al 96%. 0 faltantes obligatorios, "
                            "0 rechazos en el trimestre. Categoría: Verde."
                        ),
                    },
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "text",
                    "config": {
                        "heading": "Servicios Hidalgo",
                        "body": (
                            "Cumplimiento al 92%. 0 faltantes, 1 rechazo "
                            "resuelto durante el trimestre (acuse INFONAVIT "
                            "reemitido). Categoría: Verde."
                        ),
                    },
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "text",
                    "config": {
                        "heading": "Constructora Pacífico",
                        "body": (
                            "Cumplimiento al 71%. 1 faltante obligatorio "
                            "(IMSS marzo 2026). 0 rechazos. Categoría: "
                            "Amarillo. Dentro del periodo de gracia."
                        ),
                    },
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "text",
                    "config": {
                        "heading": "Notas legales",
                        "body": (
                            "El semáforo amarillo de Constructora Pacífico "
                            "no constituye incumplimiento contractual al "
                            "cierre del Q2. CheckWise está coordinando el "
                            "reenvío del acuse IMSS."
                        ),
                    },
                },
            ],
        },
        {
            "id": str(uuid.uuid4()),
            "organization_id": client_org_id,
            "client_id": client_id,
            "vendor_id": boss_vendor_id,
            "title": "Documentos faltantes · Servicios Especializados Aurora",
            "description": (
                "Análisis detallado de documentos pendientes y rechazados para "
                "un proveedor específico del portafolio."
            ),
            "audience": "client_facing",
            "status": "draft",
            "created_by_user_id": client_user_id,
            "blocks": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "text",
                    "config": {
                        "heading": "Alcance",
                        "body": (
                            "Reporte específico para Servicios Especializados "
                            "Aurora durante los últimos 90 días. Foco en las "
                            "entregas que requirieron intervención del "
                            "proveedor."
                        ),
                    },
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "kpi_strip",
                    "config": {
                        "metrics": [
                            {
                                "label": "Envíos",
                                "metric_key": "submissions_period",
                                "format": "number",
                            },
                            {
                                "label": "Aprobados",
                                "metric_key": "approved_pct",
                                "format": "percent",
                            },
                            {
                                "label": "Vencidos",
                                "metric_key": "overdue_count",
                                "format": "number",
                            },
                            {
                                "label": "Revisión prom.",
                                "metric_key": "avg_review_hours",
                                "format": "duration_hours",
                            },
                        ],
                    },
                    "data": {
                        "resolved": [
                            {
                                "metric_key": "submissions_period",
                                "value": 4,
                                "trend_pct_vs_prior": 0,
                            },
                            {"metric_key": "approved_pct", "value": 25, "trend_pct_vs_prior": -10},
                            {"metric_key": "overdue_count", "value": 0, "trend_pct_vs_prior": 0},
                            {
                                "metric_key": "avg_review_hours",
                                "value": 14,
                                "trend_pct_vs_prior": 5,
                            },
                        ],
                    },
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "divider",
                    "config": {"label": "Hallazgos"},
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "text",
                    "config": {
                        "heading": "Recomendación de CheckWise",
                        "body": (
                            "Sugerimos solicitar al proveedor el reenvío "
                            "del acuse IMSS marzo 2026 con el RFC corregido. "
                            "El documento previo presentó inconsistencia "
                            "entre el RFC del PDF y el del proveedor "
                            "registrado."
                        ),
                    },
                },
            ],
        },
    ]

    for spec in specs:
        report = Report(
            id=spec["id"],
            organization_id=spec["organization_id"],
            client_id=spec["client_id"],
            vendor_id=spec["vendor_id"],
            title=spec["title"],
            description=spec["description"],
            audience=spec["audience"],
            status=spec["status"],
            created_by_user_id=spec["created_by_user_id"],
        )
        db.add(report)
        db.flush()

        # Pass through each block's optional `data` field so the
        # renderers have pre-resolved values to display (without
        # having to run the AI executor on demo data).
        version_blocks = []
        for b in spec["blocks"]:
            entry = {"id": b["id"], "type": b["type"], "config": b["config"]}
            if "data" in b:
                entry["data"] = b["data"]
            version_blocks.append(entry)

        version_id = str(uuid.uuid4())
        version = ReportVersion(
            id=version_id,
            report_id=report.id,
            version_number=1,
            parent_version_id=None,
            label="Versión inicial · seed demo",
            content_json={
                "blocks": version_blocks,
                "audience": spec["audience"],
            },
            plan_json={
                "blocks": [
                    {"id": b["id"], "type": b["type"], "config": b["config"]}
                    for b in spec["blocks"]
                ],
                "rationale": "Seeded executive demo content (V2.1 evidence pack).",
                "scope_hint": spec.get("description", ""),
            },
            generated_by="user",
            source_snapshot_id=None,
            llm_metadata=None,
            created_by_user_id=spec["created_by_user_id"],
        )
        db.add(version)
        db.flush()

        report.current_version_id = version_id
        db.flush()

    return len(specs)


def main() -> None:
    db = SessionLocal()
    try:
        _wipe_demo(db)
        user_id, org_id = _seed_admin(db)
        provider_user_id = _seed_provider_user(db)
        client_id, vendor_id, workspace_id = _seed_workspace(db, owner_user_id=provider_user_id)
        submissions = _seed_submissions(db, client_id=client_id, vendor_id=vendor_id)
        boss_user_id = _seed_boss_demo_user(db)
        boss_client_id, boss_vendor_id, boss_workspace_id = _seed_boss_demo_workspace(
            db, owner_user_id=boss_user_id
        )
        boss_submissions = _seed_submissions(db, client_id=boss_client_id, vendor_id=boss_vendor_id)
        client_org_id, client_portfolio_id, cli_vendors, cli_submissions = _seed_client_portfolio(
            db
        )
        # V2.1 evidence pack — seed 3 reports for the executive demo.
        client_user = db.scalar(select(User).where(User.email == CLIENT_DEMO_EMAIL))
        # V2.1 evidence — give boss.demo memberships so the Reports
        # surface is populated when she visits /portal/reports (the
        # listing endpoint scopes by org membership). Without this,
        # boss.demo can pass the portal gate but sees an empty list.
        boss_user_for_member = db.scalar(select(User).where(User.email == BOSS_DEMO_EMAIL))
        if boss_user_for_member:
            for target_org_id in (org_id, client_org_id):
                exists = db.scalar(
                    select(Membership).where(
                        Membership.user_id == boss_user_for_member.id,
                        Membership.organization_id == target_org_id,
                    )
                )
                if not exists:
                    db.add(
                        Membership(
                            user_id=boss_user_for_member.id,
                            organization_id=target_org_id,
                            role="client_admin",
                            status="active",
                        )
                    )
            db.flush()
        reports_seeded = _seed_reports(
            db,
            legalshelf_org_id=org_id,
            legalshelf_user_id=user_id,
            client_org_id=client_org_id,
            client_user_id=client_user.id if client_user else user_id,
            client_id=client_portfolio_id,
            boss_vendor_id=boss_vendor_id,
        )
        db.commit()
    finally:
        db.close()

    print("CheckWise 2.1 demo data ready.")
    print()
    print("  Reviewer / admin login:")
    print("    URL       http://localhost:3000/login")
    print(f"    Email     {DEMO_USER_EMAIL}")
    print(f"    Password  {DEMO_USER_PASSWORD}")
    print("    Roles     internal_admin, reviewer")
    print()
    print("  Account A — first-login provider (incomplete expediente):")
    print("    URL       http://localhost:3000/login")
    print(f"    Email     {DEMO_PROVIDER_EMAIL}")
    print(f"    Password  {DEMO_PROVIDER_TEMP_PASSWORD}  (temporary)")
    print("    Flow      forced /activate → /portal/onboarding (gate active)")
    print(f"    workspace {workspace_id}  ({DEMO_VENDOR_NAME})")
    print(f"    seeded    {submissions} sample submission(s)")
    print()
    print("  Account B — boss demo (completed expediente, dashboard unlocked):")
    print("    URL       http://localhost:3000/login")
    print(f"    Email     {BOSS_DEMO_EMAIL}")
    print(f"    Password  {BOSS_DEMO_PASSWORD}")
    print("    Flow      login → /portal/entra-a-tu-espacio → /portal/dashboard")
    print(f"    workspace {boss_workspace_id}  ({BOSS_DEMO_VENDOR_NAME})")
    print(f"    seeded    {boss_submissions} sample submission(s)")
    print()
    print("  Account C — client-admin (V2.1, /client/* portfolio view):")
    print("    URL       http://localhost:3000/login")
    print(f"    Email     {CLIENT_DEMO_EMAIL}")
    print(f"    Password  {CLIENT_DEMO_PASSWORD}")
    print("    Flow      login → /client/dashboard (top-nav console)")
    print(f"    org       {client_org_id}  ({CLIENT_PORTFOLIO_ORG_NAME})")
    print(f"    client    {client_portfolio_id}  ({CLIENT_PORTFOLIO_CLIENT_NAME})")
    print(f"    seeded    {cli_vendors} vendor(s) · {cli_submissions} submission(s)")
    print()
    print(f"  Reports seeded for the executive demo: {reports_seeded}")
    print("    · Resumen ejecutivo (internal_only · LegalShelf)")
    print("    · Riesgo del portafolio (client_facing · Operadora Multinacional)")
    print("    · Documentos faltantes (vendor-scoped · draft)")


if __name__ == "__main__":
    main()
