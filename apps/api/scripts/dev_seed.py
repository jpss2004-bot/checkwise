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

import os
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
    demo_org_names = (
        DEMO_ORG_NAME,
        CLIENT_PORTFOLIO_ORG_NAME,
        f"{BOSS_DEMO_CLIENT_NAME} — Cliente",  # P1
    )
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
        # P1.4 (2026-05-20): ComplianceSnapshot rows FK back to
        # Vendor. Re-running the seed after a /generate or report
        # refresh leaves snapshots pinned to the demo vendors;
        # deleting the vendors raises a FK violation. Wipe the
        # snapshots first so the seed stays idempotent.
        from app.models import ComplianceSnapshot

        db.query(ComplianceSnapshot).filter(
            ComplianceSnapshot.vendor_id.in_(vendor_ids_to_drop)
        ).delete(synchronize_session=False)
        db.query(Vendor).filter(Vendor.id.in_(vendor_ids_to_drop)).delete(synchronize_session=False)
        db.flush()

    # Drop demo orgs (they hold the Client FK on kind='client' rows) and
    # their memberships BEFORE we drop the clients themselves.
    for org_name in (
        DEMO_ORG_NAME,
        CLIENT_PORTFOLIO_ORG_NAME,
        f"{BOSS_DEMO_CLIENT_NAME} — Cliente",  # P1
    ):
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

    P1: also creates an Organization tied to the workspace's client so
    ``_actor_from`` can resolve an owning-org for provider-authored
    reports. Without this org, boss.demo can read vendor_facing reports
    but ``create_report`` would fail with "User has no organization
    memberships."
    """
    client = Client(name=BOSS_DEMO_CLIENT_NAME, rfc=BOSS_DEMO_CLIENT_RFC)
    db.add(client)
    db.flush()

    # P1: client-kind org so create_report can pick an owning_org for
    # vendor_facing reports authored by the boss provider.
    db.add(
        Organization(
            name=f"{BOSS_DEMO_CLIENT_NAME} — Cliente",
            kind="client",
            client_id=client.id,
        )
    )
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
    """Seed an active provider expediente that exercises every status
    the Reports surface can display.

    Scenario (boss.demo workspace, today = 2026-05-20):

    SAT (mensual IVA, ISR, nómina, entero):
      - IVA upload Ene: rechazado with reviewer reason (PDF ilegible).
      - IVA upload Feb: aprobado.
      - IVA upload Mar: pendiente_revision.
      - IVA upload Abr: aprobado (closes April obligation).
      - IVA upload May: pendiente_revision (current).
      - ISR retención upload Abr: aprobado (different requirement).
      - Nómina upload Abr: requiere_aclaracion (reviewer asked for a
        missing receipt on one employee).
      - Comprobante entero ISR upload Abr: excepcion_legal (legal
        team marked it as not applicable for this period under a
        special ruling).
      - SAT IVA upload Oct 2025: vencido (the obligation passed
        without being filed on time).

    IMSS (mensual pago bancario):
      - Pago Mar: posible_mismatch (RFC drift).
      - Pago Abr: aprobado.

    IMSS — supersession chain on Feb:
      - Initial pago Feb: rechazado (wrong period range).
      - Replacement pago Feb: aprobado (supersedes_submission_id
        points at the rejected row above).

    INFONAVIT (bimestral):
      - Comprobante de pago B1: pendiente_revision (just uploaded).

    STPS/REPSE (cuatrimestral acuses):
      - Acuse SISUB Q1 2026: aprobado.
      - Acuse ICSOE Q1 2026: pendiente_revision.

    P1.4 (2026-05-20): ``period_key`` is derived from the canonical
    :data:`RecurringRequirement.period_key` for each code, NOT from
    the code's MM suffix. The catalog distinguishes the upload month
    (encoded in the code) from the obligation period it covers; the
    slot resolver matches on the latter. Hard-coding period_key was
    the root cause of the "0/144 on track" pulse finding fixed
    yesterday — we keep the look-up so the seed can't drift again.
    """
    from app.core.compliance_catalog import recurring_for_year

    catalog_period_keys = {
        r.code: r.period_key for r in recurring_for_year(2026, "moral")
    }
    catalog_freq = {
        r.code: r.frequency for r in recurring_for_year(2026, "moral")
    }
    catalog_period_keys_2025 = {
        r.code: r.period_key for r in recurring_for_year(2025, "moral")
    }

    def canonical_period_key(code: str, fallback: str) -> str:
        return (
            catalog_period_keys.get(code)
            or catalog_period_keys_2025.get(code)
            or fallback
        )

    def canonical_frequency(code: str, fallback: str = "mensual") -> str:
        return catalog_freq.get(code, fallback)

    demo_specs = [
        # ── SAT IVA — five upload months ────────────────────────
        {
            "code": "REC-SAT-2026-01-declaracion-iva",
            "period_code": "2026-01-sat-iva",
            "status": "rechazado",
            "filename": "iva_enero.pdf",
            "age_hours": 24 * 60,
            "rejection_reason": (
                "PDF ilegible: la última página del acuse está cortada. "
                "Vuelve a generar la declaración desde el portal del SAT y "
                "carga el acuse completo."
            ),
        },
        {
            "code": "REC-SAT-2026-02-declaracion-iva",
            "period_code": "2026-02-sat-iva",
            "status": "aprobado",
            "filename": "iva_febrero.pdf",
            "age_hours": 24 * 35,
            "rejection_reason": None,
        },
        {
            "code": "REC-SAT-2026-03-declaracion-iva",
            "period_code": "2026-03-sat-iva",
            "status": "pendiente_revision",
            "filename": "iva_marzo.pdf",
            "age_hours": 4,
            "rejection_reason": None,
        },
        {
            "code": "REC-SAT-2026-04-declaracion-iva",
            "period_code": "2026-04-sat-iva",
            "status": "aprobado",
            "filename": "iva_abril.pdf",
            "age_hours": 24 * 12,
            "rejection_reason": None,
        },
        {
            "code": "REC-SAT-2026-05-declaracion-iva",
            "period_code": "2026-05-sat-iva",
            "status": "pendiente_revision",
            "filename": "iva_mayo.pdf",
            "age_hours": 2,
            "rejection_reason": None,
        },
        # ── SAT ISR retención sueldos y salarios ────────────────
        {
            "code": "REC-SAT-2026-04-declaracion-isr-por-retencion-sueldos-y-salarios",
            "period_code": "2026-04-sat-isr-ret",
            "status": "aprobado",
            "filename": "isr_retencion_abril.pdf",
            "age_hours": 24 * 10,
            "rejection_reason": None,
        },
        # ── SAT nómina — requiere_aclaracion ────────────────────
        {
            "code": "REC-SAT-2026-04-comprobantes-de-nomina-de-los-trabajadores",
            "period_code": "2026-04-sat-nomina",
            "status": "requiere_aclaracion",
            "filename": "nomina_abril.pdf",
            "age_hours": 24 * 6,
            "rejection_reason": (
                "Falta el CFDI de nómina de Juan Pérez (empleado #04). "
                "Adjunta el comprobante individual o márcalo como baja."
            ),
        },
        # ── SAT entero ISR — excepcion_legal ────────────────────
        {
            "code": "REC-SAT-2026-04-comprobante-entero-pago-isr",
            "period_code": "2026-04-sat-entero-isr",
            "status": "excepcion_legal",
            "filename": "entero_isr_abril.pdf",
            "age_hours": 24 * 9,
            "rejection_reason": (
                "Periodo exento conforme al criterio normativo SAT 2025/02 — "
                "marcado como excepción legal por el equipo de LegalShelf."
            ),
        },
        # ── SAT comprobante entero IVA Ene 2026 — vencido ───────
        # Demonstrates the EXPIRED slot state. The catalog seed only
        # carries 2026 codes locally, so we re-use a different SAT
        # requirement (entero IVA, not declaracion) on a stale
        # period_key so the slot resolver classifies it as expired
        # without colliding with the IVA Ene row above.
        {
            "code": "REC-SAT-2026-01-comprobante-entero-pago-iva",
            "period_code": "2026-01-sat-entero-iva",
            "status": "vencido",
            "filename": "entero_iva_enero.pdf",
            "age_hours": 24 * 120,
            "rejection_reason": (
                "El plazo SAT para entero del IVA del periodo de diciembre "
                "2025 venció sin que se cargara el acuse. Solicita asesoría "
                "con tu contador para regularizar."
            ),
        },
        # ── IMSS pago bancario — multi-period ───────────────────
        {
            "code": "REC-IMSS-2026-03-comprobante-de-pago-bancario",
            "period_code": "2026-03-imss-pago",
            "status": "posible_mismatch",
            "filename": "imss_marzo.pdf",
            "age_hours": 36,
            "rejection_reason": "RFC del PDF no coincide con el del proveedor.",
        },
        {
            "code": "REC-IMSS-2026-04-comprobante-de-pago-bancario",
            "period_code": "2026-04-imss-pago",
            "status": "aprobado",
            "filename": "imss_abril.pdf",
            "age_hours": 24 * 8,
            "rejection_reason": None,
        },
        # ── INFONAVIT B1 — bimestral ────────────────────────────
        {
            "code": "REC-INFONAVIT-2026-03-comprobante-de-pago-bancario",
            "period_code": "2026-B1-infonavit-pago",
            "status": "pendiente_revision",
            "filename": "infonavit_b1.pdf",
            "age_hours": 24 * 5,
            "rejection_reason": None,
            "period_type": "bimestral",
        },
        # ── STPS/REPSE acuses — cuatrimestral ───────────────────
        {
            "code": "REC-ACUSES-2026-05-acuse-sisub",
            "period_code": "2026-Q1-stps-sisub",
            "status": "aprobado",
            "filename": "acuse_sisub_q1.pdf",
            "age_hours": 24 * 17,
            "rejection_reason": None,
            "period_type": "cuatrimestral",
        },
        {
            "code": "REC-ACUSES-2026-05-acuse-icsoe",
            "period_code": "2026-Q1-stps-icsoe",
            "status": "pendiente_revision",
            "filename": "acuse_icsoe_q1.pdf",
            "age_hours": 24 * 1,
            "rejection_reason": None,
            "period_type": "cuatrimestral",
        },
    ]

    # Build the simple-case submissions first so they're flushed and
    # we can reference one of them from the supersession chain below.
    inserted_submissions: dict[str, str] = {}
    inserted = 0
    for spec in demo_specs:
        sub_id = _insert_demo_submission(
            db,
            client_id=client_id,
            vendor_id=vendor_id,
            spec=spec,
            canonical_period_key=canonical_period_key,
            canonical_frequency=canonical_frequency,
        )
        if sub_id is not None:
            inserted_submissions[spec["code"]] = sub_id
            inserted += 1

    # ── Supersession chain on IMSS Feb ────────────────────────────
    # First attempt was rejected (wrong period range); provider then
    # re-uploaded a corrected file three days later, which got
    # approved. The replacement carries supersedes_submission_id so
    # the slot resolver walks the lineage and the corrected row is
    # the "current" submission for that obligation.
    supersession_first = {
        "code": "REC-IMSS-2026-02-comprobante-de-pago-bancario",
        "period_code": "2026-02-imss-pago",
        "status": "rechazado",
        "filename": "imss_febrero_v1.pdf",
        "age_hours": 24 * 28,
        "rejection_reason": (
            "Rango de periodo en el PDF corresponde a enero, no a "
            "febrero. Genera el comprobante con el rango correcto."
        ),
    }
    first_id = _insert_demo_submission(
        db,
        client_id=client_id,
        vendor_id=vendor_id,
        spec=supersession_first,
        canonical_period_key=canonical_period_key,
        canonical_frequency=canonical_frequency,
    )
    if first_id is not None:
        inserted += 1
        supersession_second = {
            "code": "REC-IMSS-2026-02-comprobante-de-pago-bancario",
            "period_code": "2026-02-imss-pago",
            "status": "aprobado",
            "filename": "imss_febrero_v2.pdf",
            "age_hours": 24 * 25,
            "rejection_reason": None,
            "supersedes_submission_id": first_id,
        }
        second_id = _insert_demo_submission(
            db,
            client_id=client_id,
            vendor_id=vendor_id,
            spec=supersession_second,
            canonical_period_key=canonical_period_key,
            canonical_frequency=canonical_frequency,
        )
        if second_id is not None:
            inserted += 1

    return inserted


def _insert_demo_submission(
    db,
    *,
    client_id: str,
    vendor_id: str,
    spec: dict,
    canonical_period_key,
    canonical_frequency,
) -> str | None:
    """Insert one demo submission + document + status history.

    Returns the submission id on success, ``None`` if the requirement
    isn't in the catalog yet (the canonical seed must run first). The
    helper keeps ``_seed_submissions`` readable and lets us reuse the
    body for supersession chains where the second insert references
    the first.
    """
    code = spec["code"]
    requirement = db.scalar(select(Requirement).where(Requirement.code == code))
    if requirement is None:
        return None
    version = db.scalar(
        select(RequirementVersion)
        .where(RequirementVersion.requirement_id == requirement.id)
        .order_by(RequirementVersion.version.asc())
    )
    if version is None:
        return None
    institution = db.get(Institution, requirement.institution_id)
    period_type = spec.get("period_type") or "mensual"
    fallback_pk = "2026-M04"
    period_id = _get_or_create_period(
        db,
        period_key=canonical_period_key(code, fallback_pk),
        code=spec["period_code"],
        period_type=period_type,
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
        load_type=canonical_frequency(code, period_type),
        requirement_code=code,
        period_key=canonical_period_key(code, fallback_pk),
        supersedes_submission_id=spec.get("supersedes_submission_id"),
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
        sha256=("d" + code + (spec.get("filename") or "")).ljust(64, "0")[:64].replace(":", "_"),
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
                reason=spec.get("rejection_reason"),
                actor="system:dev_seed",
            )
        )
    db.flush()
    return submission.id


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
    boss_client_id: str,
    boss_org_id: str,
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
            # P1: this report is the boss provider's own vendor-facing
            # view. organization_id + client_id now point at boss's
            # client (consistent tenant scope) and audience flipped to
            # vendor_facing so /portal/reports populates for boss.demo.
            "id": str(uuid.uuid4()),
            "organization_id": boss_org_id,
            "client_id": boss_client_id,
            "vendor_id": boss_vendor_id,
            "title": "Documentos faltantes · Servicios Especializados Aurora",
            "description": (
                "Análisis detallado de documentos pendientes y rechazados "
                "para este proveedor."
            ),
            "audience": "vendor_facing",
            "status": "draft",
            "created_by_user_id": legalshelf_user_id,
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
    # P0 guard (added 2026-05-18): this script seeds a documented-password
    # admin user. If it ever runs against a production database, the
    # documented password becomes a public backdoor. Refuse to run unless
    # DATABASE_URL points at a local-development host.
    #
    # We allow localhost / 127.0.0.1 / *.local. Anything else (e.g. a
    # *.neon.tech, *.render.com, RDS endpoint) is rejected. To explicitly
    # bypass the guard for a recovery scenario, set
    # CHECKWISE_ALLOW_SEED_AGAINST=<host substring> in the environment.
    from app.core.config import get_settings  # local import

    settings = get_settings()
    raw_url = settings.DATABASE_URL
    # Strip query string and credentials, keep only the host fragment.
    try:
        host = raw_url.split("@", 1)[1].split("/", 1)[0].split(":")[0].lower()
    except IndexError:
        host = ""

    local_hosts = ("localhost", "127.0.0.1")
    is_local = host in local_hosts or host.endswith(".local")
    override = os.environ.get("CHECKWISE_ALLOW_SEED_AGAINST", "").strip().lower()
    if not is_local and (not override or override not in host):
        sys.stderr.write(
            "ERROR: dev_seed.py refuses to run against a non-local host.\n"
            f"  Detected DATABASE_URL host: {host or '<unknown>'}\n"
            "  Allowed: localhost, 127.0.0.1, *.local\n"
            "  This script seeds the documented demo admin password\n"
            "  (see README and docs/CREDENTIALS.md). Running it against a\n"
            "  shared / production database is a security incident.\n"
            "  If you genuinely need to bypass this guard, set\n"
            "    CHECKWISE_ALLOW_SEED_AGAINST=<substring of the host>\n"
            "  and re-run. Use with extreme caution.\n"
        )
        sys.exit(2)

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
        # R-bug-2026-05-18: Earlier versions of this seed gave
        # boss.demo a ``client_admin`` membership so /portal/reports
        # would not look empty. Side effect: the login router saw
        # the client_admin role and routed her to /client/dashboard
        # instead of the provider workspace at /portal/*.
        #
        # boss.demo is documented (README, docs/DEMO_1.7.1.md) as the
        # *provider* B account. Leave her membership-free so the login
        # router falls through to /portal/entra-a-tu-espacio. P1 adds
        # a vendor_facing seeded report so /portal/reports has signal
        # for boss.demo via the workspace-derived visibility branch.
        boss_org_id = db.scalar(
            select(Organization.id).where(Organization.client_id == boss_client_id)
        )
        if boss_org_id is None:
            raise RuntimeError(
                "Seed invariant broken: no Organization for boss client"
            )
        reports_seeded = _seed_reports(
            db,
            legalshelf_org_id=org_id,
            legalshelf_user_id=user_id,
            client_org_id=client_org_id,
            client_user_id=client_user.id if client_user else user_id,
            client_id=client_portfolio_id,
            boss_vendor_id=boss_vendor_id,
            boss_client_id=boss_client_id,
            boss_org_id=boss_org_id,
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
