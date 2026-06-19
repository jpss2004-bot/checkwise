#!/usr/bin/env python3
"""seed_flagship_demo.py — the flagship prospect demo tenant.

ONE polished client whose FIVE providers occupy a curated A–E compliance
distribution tuned to a ~90-95% portfolio with EXACTLY ONE red "problem"
provider — plus a real provider login (Provider D) so a prospect can experience
BOTH sides of the ecosystem and watch compliance rise live during the demo.

    A · Modelo            Grupo Industrial Vallejo            100%  · verde
    B · Sólido            Servicios Logísticos Anáhuac        ~97%  · verde/amarillo (CSF por renovar)
    C · Promedio          Mantenimiento y Limpieza Tlalpan    ~88%  · amarillo (faltantes/en revisión)
    D · En mejora ★login  Constructora y Edificaciones Bajío  ~91%  · amarillo (sube docs en vivo)
    E · En riesgo         Transportes y Distribución del Golfo ~82% · ROJO (vencidos, rechazos, faltantes)

Why this differs from seed_demo_sandbox / seed_demo_clients: those seed a
lifecycle ladder that *starts at 0%* (invited → fully compliant), so the
portfolio mean lands ~50%. This seeder targets a mature, mostly-green portfolio
with one clearly-flagged problem provider — the shape a prospect should see.

Reuses the seed_demo_sandbox primitives (real-PDF uploader, the full
submission/inspection/history/validation graph, the deterministic report
builder) and layers branded synthetic PDFs (flagship_demo_assets) over the
high-touch onboarding expediente so a document a prospect opens shows the SAME
company they're looking at in the portal.

USAGE
-----
  cd apps/api

  # Local build (CHECKWISE_ENV=local). Wipes its own client then reseeds.
  .venv/bin/python scripts/seed_flagship_demo.py --apply

  # Remove everything this seeder created (DB rows + storage blobs).
  .venv/bin/python scripts/seed_flagship_demo.py --teardown

  # Show the seeded tenant's per-provider compliance (read-only).
  .venv/bin/python scripts/seed_flagship_demo.py --measure

  # Promote to prod. Take a Neon snapshot FIRST. Uploads branded + real PDFs
  # to the configured object store (R2/S3).
  CHECKWISE_ENV=production DATABASE_URL=... STORAGE_BUCKET=... \
    .venv/bin/python scripts/seed_flagship_demo.py --apply --confirm-prod
"""
from __future__ import annotations

import argparse
import calendar
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import flagship_demo_assets as fa  # noqa: E402
import seed_demo_clients as sdc  # noqa: E402  (battle-tested wipe helpers)
import seed_demo_sandbox as sds  # noqa: E402  (submission graph + report builder)

from app.constants.statuses import DocumentStatus  # noqa: E402
from app.core.compliance_catalog import recurring_for_year  # noqa: E402
from app.db.seed import seed_catalog  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Client,
    ClientNotification,
    Membership,
    Organization,
    ProviderWorkspace,
    Report,
    ReportVersion,
    User,
    Vendor,
)
from app.models.entities import utc_now  # noqa: E402
from app.services.audit_log import add_audit_event  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

# ============================================================================
# IDENTITY / CREDENTIALS
# ============================================================================

SCENARIO_TAG = "flagship_demo"
STORAGE_PREFIX = "flagship-demo"
INSTANCE_KEY = "flagship-demo:v1"
# "Today" for the scenario — pinned so re-runs are deterministic. Two days
# before the real date so seeded activity reads as "just now".
TODAY = date(2026, 6, 15)

CLIENT_NAME = "Corporativo Industrial Anáhuac, S.A. de C.V."
CLIENT_RFC = "CIA180115R30"
CLIENT_ORG_NAME = "Corporativo Industrial Anáhuac — Cliente"
CLIENT_INDUSTRY = "Manufactura e infraestructura industrial"

ADMIN_EMAIL = "demo.cliente@checkwise.mx"
ADMIN_PASSWORD = "Cliente2026Demo!"
ADMIN_FULLNAME = "Daniela Robles Cárdenas"

PROVIDER_LOGIN_EMAIL = "demo.proveedor@checkwise.mx"
PROVIDER_LOGIN_PASSWORD = "Proveedor2026Demo!"
PROVIDER_LOGIN_FULLNAME = "Daniel Quiroz Mena"

LEGAL_CONSENT_VERSION = "v2"

ONB = {
    "contrato": "ONB-CONT-001",
    "acta": "ONB-CORP-M-001",
    "csf": "ONB-CORP-M-002",
    "repse": "ONB-REPSE-001",
    "patronal": "ONB-PATR-001",
}

A = DocumentStatus.APROBADO.value
PR = DocumentStatus.PENDIENTE_REVISION.value
REJ = DocumentStatus.RECHAZADO.value
ACL = DocumentStatus.REQUIERE_ACLARACION.value
MM = DocumentStatus.POSIBLE_MISMATCH.value
VEN = DocumentStatus.VENCIDO.value


# ============================================================================
# PROVIDER ROSTER + COMPLIANCE PROFILES
# ============================================================================

@dataclass(frozen=True)
class Profile:
    """The per-provider 'imperfection plan' applied to the recurring calendar.

    Counts are applied to the most-recent PAST-DUE recurring slots; everything
    else is approved. Onboarding overrides replace the default APPROVED status
    for specific expediente docs. Tunable — see _measure() to recalibrate.
    """

    rec_in_review: int = 0
    rec_missing: int = 0
    rec_rejected: int = 0
    rec_aclaracion: int = 0
    rec_mismatch: int = 0
    # code -> (status, reviewer_note, days_ago)
    onb_overrides: dict = field(default_factory=dict)
    renewal: bool = False
    onboarding_days_ago: int = 150  # how long ago this provider onboarded


@dataclass(frozen=True)
class FlagshipProvider:
    key: str
    demo_label: str
    legal_name: str
    rfc: str
    sector: str
    contact_name: str
    contact_email: str
    real_vendor_slug: str
    ciudad: str
    notaria: int
    founded: date
    repse_folio: str
    scenario_note: str
    profile: Profile
    is_login: bool = False


_REJ_NOTE = "Documento ilegible / folio no corresponde al periodo. Volver a subir versión corregida."
_ACL_NOTE = "Falta el CFDI de respaldo del pago. Aclarar y adjuntar comprobante."
_MM_NOTE = "El RFC del comprobante no coincide con el del proveedor registrado."

FLAGSHIP_PROVIDERS = [
    FlagshipProvider(
        key="a-modelo",
        demo_label="A · Proveedor modelo",
        legal_name="Grupo Industrial Vallejo, S.A. de C.V.",
        rfc="GIV150218AB3",
        sector="Mantenimiento industrial especializado",
        contact_name="Mariana Ferreira López",
        contact_email="mariana.ferreira@giv-demo.mx",
        real_vendor_slug="master-clean-plus",
        ciudad="Monterrey, N.L.",
        notaria=42,
        founded=date(2015, 2, 18),
        repse_folio="AR128340/2024",
        scenario_note="Expediente y calendario 2026 completos; 100% aprobado.",
        profile=Profile(onboarding_days_ago=165),
    ),
    FlagshipProvider(
        key="b-solido",
        demo_label="B · Proveedor sólido",
        legal_name="Servicios Logísticos Anáhuac, S.A. de C.V.",
        rfc="SLA160712CD4",
        sector="Logística y transporte de carga",
        contact_name="Rodrigo Salas Vidal",
        contact_email="rodrigo.salas@sla-demo.mx",
        real_vendor_slug="human-medical-humese",
        ciudad="Guadalajara, Jal.",
        notaria=18,
        founded=date(2016, 7, 12),
        repse_folio="AR203991/2024",
        scenario_note="Cumplimiento alto; 2 entregas recientes en revisión; CSF por renovar (~14 días).",
        profile=Profile(rec_in_review=3, renewal=True, onboarding_days_ago=158),
    ),
    FlagshipProvider(
        key="c-promedio",
        demo_label="C · Proveedor promedio",
        legal_name="Mantenimiento y Limpieza Corporativa Tlalpan, S. de R.L. de C.V.",
        rfc="MLC190503EF5",
        sector="Limpieza y servicios de facilities",
        contact_name="Ana Sofía Beltrán",
        contact_email="ana.beltran@mlc-demo.mx",
        real_vendor_slug="angel-elias-garcia",
        ciudad="Ciudad de México",
        notaria=9,
        founded=date(2019, 5, 3),
        repse_folio="AR455120/2024",
        scenario_note="Al corriente en lo esencial; varias obligaciones recientes faltantes o en revisión.",
        profile=Profile(rec_in_review=10, rec_missing=7, onboarding_days_ago=150),
    ),
    FlagshipProvider(
        key="d-mejora",
        demo_label="D · Proveedor en mejora (login)",
        legal_name="Constructora y Edificaciones del Bajío, S.A. de C.V.",
        rfc="CEB200911GH6",
        sector="Construcción y obra civil",
        contact_name="Daniel Quiroz Mena",
        contact_email=PROVIDER_LOGIN_EMAIL,
        real_vendor_slug="master-clean-plus",
        ciudad="Querétaro, Qro.",
        notaria=27,
        founded=date(2020, 9, 11),
        repse_folio="AR612077/2024",
        scenario_note="Subió mucho en las últimas semanas; quedan algunas obligaciones por cargar (las sube el prospecto en vivo).",
        profile=Profile(rec_in_review=8, rec_missing=5, onboarding_days_ago=42),
        is_login=True,
    ),
    FlagshipProvider(
        key="e-riesgo",
        demo_label="E · Proveedor en riesgo",
        legal_name="Transportes y Distribución del Golfo, S.A. de C.V.",
        rfc="TDG170820KK9",
        sector="Transporte y distribución",
        contact_name="Lucía Fuentes Ramos",
        contact_email="lucia.fuentes@tdg-demo.mx",
        real_vendor_slug="human-medical-humese",
        ciudad="Veracruz, Ver.",
        notaria=5,
        founded=date(2017, 8, 20),
        repse_folio="AR789453/2023",
        scenario_note="Riesgo crítico: CSF vencida, REPSE rechazado, declaraciones faltantes, rechazos y aclaraciones abiertas.",
        profile=Profile(
            rec_in_review=4, rec_missing=8, rec_rejected=6, rec_aclaracion=3, rec_mismatch=2,
            onb_overrides={
                ONB["csf"]: (VEN, "Constancia de Situación Fiscal vencida; debe renovarse.", 210),
                ONB["repse"]: (REJ, "El folio REPSE no corresponde a la razón social vigente. Subir constancia actualizada.", 55),
            },
            onboarding_days_ago=175,
        ),
    ),
]
PROVIDERS_BY_KEY = {p.key: p for p in FLAGSHIP_PROVIDERS}


def _as_seed(fp: FlagshipProvider) -> sds.ProviderSeed:
    return sds.ProviderSeed(
        key=fp.key,
        label=fp.demo_label,
        stage="flagship",
        vendor_name=fp.legal_name,
        vendor_rfc=fp.rfc,
        contact_name=fp.contact_name,
        owner_email=fp.contact_email,
        real_vendor_slug=fp.real_vendor_slug,
        onboarding_complete=True,
        scenario_note=fp.scenario_note,
    )


# ============================================================================
# PERIOD RECENCY (drives which slots get the imperfections + timestamps)
# ============================================================================

def _period_end(period_key: str) -> date:
    year = int(period_key[:4])
    if "-M" in period_key:
        m = int(period_key.split("-M")[1])
        return date(year, m, calendar.monthrange(year, m)[1])
    if "-B" in period_key:
        b = int(period_key.split("-B")[1])
        m = min(b * 2, 12)
        return date(year, m, calendar.monthrange(year, m)[1])
    if "-Q" in period_key:
        q = int(period_key.split("-Q")[1])
        m = min(q * 4, 12)
        return date(year, m, calendar.monthrange(year, m)[1])
    if "-A" in period_key:
        return date(year, 12, 31)
    return date(year, 6, 30)


def _recency_days(period_key: str) -> int:
    """Days since the period closed. Positive = past-due, negative = future."""
    return (TODAY - _period_end(period_key)).days


def _days_ago_for(period_key: str) -> int:
    r = _recency_days(period_key)
    return max(3, r + 12) if r >= 0 else max(3, 12 + r)


# ============================================================================
# BRANDED ONBOARDING EXPEDIENTE (high-touch synthetic PDFs)
# ============================================================================

def _branded_onboarding_doc(fp: FlagshipProvider, code: str, *, expired: bool = False) -> tuple[bytes, str]:
    name, rfc = fp.legal_name, fp.rfc
    if code == ONB["contrato"]:
        return (
            fa.contrato_servicios(legal_name=name, rfc=rfc, issued_on=date(2025, 1, 15), client_name=CLIENT_NAME),
            "contrato-servicios-especializados.pdf",
        )
    if code == ONB["acta"]:
        return (
            fa.acta_constitutiva(legal_name=name, rfc=rfc, issued_on=fp.founded, notaria=fp.notaria, ciudad=fp.ciudad),
            "acta-constitutiva.pdf",
        )
    if code == ONB["csf"]:
        issued = TODAY - timedelta(days=210 if expired else 45)
        return (
            fa.constancia_situacion_fiscal(legal_name=name, rfc=rfc, issued_on=issued, ciudad=fp.ciudad, expired=expired),
            "constancia-situacion-fiscal-vencida.pdf" if expired else "constancia-situacion-fiscal.pdf",
        )
    if code == ONB["repse"]:
        return (
            fa.registro_repse(legal_name=name, rfc=rfc, issued_on=date(2024, 3, 1), repse_folio=fp.repse_folio),
            "constancia-registro-repse.pdf",
        )
    # patronal
    return (
        fa.registro_patronal(legal_name=name, rfc=rfc, issued_on=fp.founded + timedelta(days=30)),
        "tarjeta-identificacion-patronal-imss.pdf",
    )


# ============================================================================
# DOCUMENT SEEDING (the A–E distribution)
# ============================================================================

def _seed_provider_documents(db, *, sample, uploader, fp: FlagshipProvider, client_id, vendor_id) -> dict:
    """Seed the onboarding expediente + full recurring calendar for one provider.

    Returns notable submission ids (for E's notifications). Statuses are set
    directly per the provider profile; no OCR runs.
    """
    seed = _as_seed(fp)
    p = fp.profile
    notable: dict[str, str] = {}

    base_onb_days = p.onboarding_days_ago
    onb_default_days = {
        ONB["contrato"]: base_onb_days,
        ONB["acta"]: base_onb_days + 4,
        ONB["csf"]: min(base_onb_days, 45),   # CSF renews — recent
        ONB["repse"]: base_onb_days - 2,
        ONB["patronal"]: base_onb_days + 2,
    }

    for code in ONB.values():
        override = p.onb_overrides.get(code)
        status = override[0] if override else A
        note = override[1] if override else None
        days = override[2] if override else onb_default_days[code]
        expired = status == VEN
        sub_id = sds._insert_submission(
            db, sample=sample, uploader=uploader, provider=seed,
            client_id=client_id, vendor_id=vendor_id, requirement_code=code,
            status_value=status, days_ago=days, period_key=None, reviewer_note=note,
            override_doc=_branded_onboarding_doc(fp, code, expired=expired),
        )
        if code == ONB["repse"] and status == REJ:
            notable["repse_rejected"] = sub_id
        if code == ONB["csf"] and status == VEN:
            notable["csf_vencido"] = sub_id

    # --- recurring calendar: file the whole annual catalog, then degrade the
    # most-recent past-due slots per the profile (matches the product's
    # full-annual-catalog scoring used by the sandbox green providers).
    items = recurring_for_year(2026, "moral")
    past_due = sorted(
        (it for it in items if _recency_days(it.period_key) >= 0),
        key=lambda it: _recency_days(it.period_key),
    )
    future = [it for it in items if _recency_days(it.period_key) < 0]

    treatments: list[tuple[str, str | None]] = (
        [("skip", None)] * p.rec_missing
        + [(REJ, _REJ_NOTE)] * p.rec_rejected
        + [(ACL, _ACL_NOTE)] * p.rec_aclaracion
        + [(MM, _MM_NOTE)] * p.rec_mismatch
        + [(PR, None)] * p.rec_in_review
    )
    plan: dict[str, tuple[str, str | None]] = {}
    for it, treat in zip(past_due, treatments, strict=False):
        plan[it.code] = treat

    for it in past_due + future:
        decision = plan.get(it.code)
        if decision is not None and decision[0] == "skip":
            continue
        status, note = decision if decision is not None else (A, "Documento aprobado.")
        sub_id = sds._insert_submission(
            db, sample=sample, uploader=uploader, provider=seed,
            client_id=client_id, vendor_id=vendor_id, requirement_code=it.code,
            status_value=status, days_ago=_days_ago_for(it.period_key),
            period_key=it.period_key, reviewer_note=note,
        )
        if status == ACL and "aclaracion" not in notable:
            notable["aclaracion"] = sub_id
        if status == REJ and "rec_rejected" not in notable:
            notable["rec_rejected"] = sub_id

    return notable


# ============================================================================
# NOTIFICATIONS (rich client feed for the problem provider)
# ============================================================================

def _notif(db, *, key, client_id, vendor_id, submission_id, ntype, title, body, severity, category, days_ago, action="/client/vendors"):
    db.add(ClientNotification(
        id=sds._id(f"client-notif:{key}"),
        client_id=client_id,
        vendor_id=vendor_id,
        submission_id=submission_id,
        notification_type=ntype,
        title=title,
        body=body,
        action_url=action,
        payload={"scenario": SCENARIO_TAG},
        severity=severity,
        category=category,
        created_at=sds._dt(days_ago),
    ))


def _seed_problem_notifications(db, *, fp: FlagshipProvider, client_id, vendor_id, notable: dict) -> None:
    name = fp.legal_name
    if notable.get("csf_vencido"):
        _notif(db, key=f"{fp.key}:csf", client_id=client_id, vendor_id=vendor_id,
               submission_id=notable["csf_vencido"], ntype="document_expired",
               title=f"Constancia de Situación Fiscal vencida · {name}",
               body="La CSF del proveedor está vencida. Solicita la constancia actualizada para mantener el expediente vigente.",
               severity="red", category="risk", days_ago=9)
    if notable.get("repse_rejected"):
        _notif(db, key=f"{fp.key}:repse", client_id=client_id, vendor_id=vendor_id,
               submission_id=notable["repse_rejected"], ntype="document_rejected",
               title=f"Registro REPSE rechazado · {name}",
               body="El registro REPSE fue rechazado por inconsistencia de folio. El proveedor debe volver a subir la constancia corregida.",
               severity="red", category="risk", days_ago=6)
    if notable.get("aclaracion"):
        _notif(db, key=f"{fp.key}:acl", client_id=client_id, vendor_id=vendor_id,
               submission_id=notable["aclaracion"], ntype="correction_open",
               title=f"Acción correctiva abierta · {name}",
               body="Hay obligaciones que requieren aclaración del proveedor. Da seguimiento para cerrarlas.",
               severity="yellow", category="action", days_ago=4)


# ============================================================================
# REPORTS (multiple client-facing presets)
# ============================================================================

_REPORTS = [
    ("client-monthly-executive", "exec", "Resumen ejecutivo mensual · Junio 2026",
     "Panorama del portafolio: cumplimiento global, por institución, radar, matriz de riesgo y recomendaciones."),
    ("client-vendor-risk-matrix", "risk", "Matriz de riesgo de proveedores · 2.º trimestre 2026",
     "Clasificación de los proveedores por nivel de riesgo y obligaciones pendientes."),
    ("client-missing-evidence", "missing", "Evidencia faltante del portafolio · Junio 2026",
     "Documentos y obligaciones faltantes por proveedor, priorizados por criticidad."),
]


def _seed_reports(db, *, org_id, client_id, admin_user_id) -> int:
    from app.constants.reports import ReportAudience
    from app.services.reports.context import ReportScope
    from app.services.reports.deterministic_layouts import build_deterministic_blocks

    scope = ReportScope(
        organization_id=org_id, audience=ReportAudience.CLIENT_FACING,
        client_id=client_id, vendor_id=None, period=None,
    )
    count = 0
    for preset_id, rkey, title, description in _REPORTS:
        blocks = build_deterministic_blocks(db, preset_id=preset_id, scope=scope)
        report = Report(
            id=sds._id(f"report:{rkey}"),
            organization_id=org_id, client_id=client_id, vendor_id=None,
            title=title, description=description,
            audience="client_facing", status="active",
            created_by_user_id=admin_user_id,
        )
        db.add(report)
        db.flush()
        version_id = sds._id(f"report-version:{rkey}")
        db.add(ReportVersion(
            id=version_id, report_id=report.id, version_number=1,
            parent_version_id=None, label="Versión inicial · demo",
            content_json={"blocks": blocks, "audience": "client_facing"},
            plan_json={
                "blocks": [{"id": b["id"], "type": b["type"], "config": b["config"]} for b in blocks],
                "rationale": f"Reporte demo ({preset_id}) para el portafolio insignia.",
                "scope_hint": "Portafolio de 5 proveedores (distribución A–E).",
            },
            generated_by="ai", source_snapshot_id=None, llm_metadata=None,
            created_by_user_id=admin_user_id,
        ))
        db.flush()
        report.current_version_id = version_id
        db.flush()
        count += 1
    return count


# ============================================================================
# CLIENT / USERS / VENDORS
# ============================================================================

def _seed_client_and_users(db) -> tuple[str, str, str, str]:
    admin = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
    if admin is None:
        admin = User(id=sds._id(f"user:{ADMIN_EMAIL}"), email=ADMIN_EMAIL)
        db.add(admin)
    admin.password_hash = hash_password(ADMIN_PASSWORD)
    admin.full_name = ADMIN_FULLNAME
    admin.status = "active"
    admin.must_change_password = False
    # Pre-accept the legal-consent gate so the prospect lands directly on the
    # dashboard instead of the consent wall.
    admin.legal_consent_accepted_at = sds._dt(160)
    admin.legal_consent_version = LEGAL_CONSENT_VERSION
    db.flush()

    prov = db.scalar(select(User).where(User.email == PROVIDER_LOGIN_EMAIL))
    if prov is None:
        prov = User(id=sds._id(f"user:{PROVIDER_LOGIN_EMAIL}"), email=PROVIDER_LOGIN_EMAIL)
        db.add(prov)
    prov.password_hash = hash_password(PROVIDER_LOGIN_PASSWORD)
    prov.full_name = PROVIDER_LOGIN_FULLNAME
    prov.status = "active"
    prov.must_change_password = False
    prov.legal_consent_accepted_at = sds._dt(42)
    prov.legal_consent_version = LEGAL_CONSENT_VERSION
    db.flush()

    client = Client(
        id=sds._id("client"), name=CLIENT_NAME, rfc=CLIENT_RFC, email=ADMIN_EMAIL,
        responsible_name=ADMIN_FULLNAME, industry=CLIENT_INDUSTRY,
        fiscal_address="Av. Insurgentes Sur 1234, Ciudad de México (domicilio de demostración)",
        phone="+52 55 8000 1234",
        notes=f"{SCENARIO_TAG}: portafolio insignia con 5 proveedores (distribución A–E).",
        onboarding_completed_at=utc_now(), status="active",
    )
    db.add(client)
    db.flush()

    org = Organization(id=sds._id("client-org"), name=CLIENT_ORG_NAME, kind="client",
                       client_id=client.id, status="active")
    db.add(org)
    db.flush()
    db.add(Membership(id=sds._id("membership:admin"), user_id=admin.id,
                      organization_id=org.id, role="client_admin", status="active"))
    db.flush()
    return client.id, org.id, admin.id, prov.id


# ============================================================================
# APPLY / TEARDOWN / MEASURE
# ============================================================================

def _configure_sds() -> None:
    """Point the reused sds primitives at the flagship namespace."""
    sds._INSTANCE_KEY = INSTANCE_KEY
    sds.SCENARIO_TAG = SCENARIO_TAG
    sds.STORAGE_PREFIX = STORAGE_PREFIX
    sds.TODAY = TODAY
    sds.PROVIDERS = [_as_seed(fp) for fp in FLAGSHIP_PROVIDERS]
    sds.PROVIDERS_BY_KEY = {s.key: s for s in sds.PROVIDERS}
    sdc.SCENARIO_TAG = SCENARIO_TAG


def _apply(db, *, sample, uploader) -> dict:
    _configure_sds()
    seed_catalog(db, years=(2025, 2026))

    client_id, org_id, admin_id, prov_id = _seed_client_and_users(db)

    vendor_ids = sds._seed_provider_rows(db, client_id=client_id)

    # Patch the helper's placeholders: real REPSE folios, legal consent v2, and
    # the provider login owner on Provider D's workspace.
    db.query(ProviderWorkspace).filter(
        ProviderWorkspace.client_id == client_id,
        ProviderWorkspace.legal_consent_version.isnot(None),
    ).update({ProviderWorkspace.legal_consent_version: LEGAL_CONSENT_VERSION},
             synchronize_session=False)
    for fp in FLAGSHIP_PROVIDERS:
        vendor = db.get(Vendor, vendor_ids[fp.key])
        vendor.repse_id = fp.repse_folio
        ws = db.get(ProviderWorkspace, sds._id(f"workspace:{fp.key}"))
        ws.onboarding_completed_at = sds._dt(fp.profile.onboarding_days_ago)
        ws.profile_confirmed_at = sds._dt(fp.profile.onboarding_days_ago)
        if fp.is_login:
            ws.owner_user_id = prov_id
    db.flush()

    for fp in FLAGSHIP_PROVIDERS:
        vid = vendor_ids[fp.key]
        notable = _seed_provider_documents(
            db, sample=sample, uploader=uploader, fp=fp, client_id=client_id, vendor_id=vid,
        )
        if fp.profile.renewal:
            sdc._seed_renewal_signal(
                db, provider=_as_seed(fp), client_id=client_id, vendor_id=vid,
                workspace_id=sds._id(f"workspace:{fp.key}"),
            )
        if notable:
            _seed_problem_notifications(db, fp=fp, client_id=client_id, vendor_id=vid, notable=notable)
    db.flush()

    reports = _seed_reports(db, org_id=org_id, client_id=client_id, admin_user_id=admin_id)

    add_audit_event(
        db, action="flagship_demo.scenario_seeded", entity_type="client", entity_id=client_id,
        metadata={"scenario": SCENARIO_TAG, "providers": [fp.legal_name for fp in FLAGSHIP_PROVIDERS],
                  "reports": reports, "blobs_uploaded": len(uploader._seen)},
    )
    db.commit()
    return {"client_id": client_id, "org_id": org_id, "reports": reports,
            "vendor_ids": vendor_ids, "blobs": len(uploader._seen)}


def _teardown(db, *, backend) -> None:
    _configure_sds()
    client = db.scalar(select(Client).where(Client.rfc == CLIENT_RFC))
    if client is None:
        print("  Nothing to tear down (flagship client not found).")
        return
    storage_keys, user_ids = sdc._wipe_client_tenant(db, client)
    for email in (ADMIN_EMAIL, PROVIDER_LOGIN_EMAIL):
        u = db.scalar(select(User).where(User.email == email))
        if u is not None:
            user_ids.add(u.id)
    removed_users, _ = sdc._cleanup_orphan_users(db, user_ids)
    db.flush()
    removed_blobs = sdc._delete_unreferenced_blobs(db, backend, storage_keys)
    db.commit()
    print(f"  Removed flagship client, {removed_users} user(s), {removed_blobs} blob(s).")


def _measure(db) -> None:
    """Read back each provider's computed compliance via the live engine."""
    _configure_sds()
    from app.services.dashboard_compute import compute_semaphore
    from app.services.evidence_slots import (
        build_workspace_calendar_slots,
        build_workspace_onboarding_slots,
    )

    client = db.scalar(select(Client).where(Client.rfc == CLIENT_RFC))
    if client is None:
        print("  Flagship client not seeded.")
        return
    print(f"\n  Portfolio · {client.name}")
    print("  " + "-" * 72)
    pcts: list[int] = []
    levels: list[str] = []
    for fp in FLAGSHIP_PROVIDERS:
        ws = db.get(ProviderWorkspace, sds._id(f"workspace:{fp.key}"))
        onb = build_workspace_onboarding_slots(db, ws)
        cal = build_workspace_calendar_slots(db, ws, 2026)
        sem = compute_semaphore(onb, cal)
        pct = sem["compliance_pct"]
        level = sem.get("level", "?")
        pcts.append(pct)
        levels.append(level)
        print(f"  {fp.demo_label:34s} {pct:3d}%  {level:6s}  {fp.legal_name}")
    mean = round(sum(pcts) / len(pcts)) if pcts else 0
    reds = sum(1 for lv in levels if lv in ("red", "rojo"))
    print("  " + "-" * 72)
    print(f"  Portfolio mean (simple): {mean}%   ·   red providers: {reds}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the CheckWise flagship demo tenant.")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--apply", action="store_true", help="Wipe + reseed the flagship tenant.")
    g.add_argument("--teardown", action="store_true", help="Remove the flagship tenant.")
    g.add_argument("--measure", action="store_true", help="Print per-provider compliance (read-only).")
    parser.add_argument("--confirm-prod", action="store_true", help="Required outside local.")
    parser.add_argument("--sample-docs-path", default=None, help="Path to _reference/sample-docs.")
    args = parser.parse_args()

    if not args.measure:
        sds._assert_env(confirm_prod=args.confirm_prod)

    _configure_sds()
    backend = sds._storage_backend()
    db = SessionLocal()
    try:
        if args.measure:
            _measure(db)
            return
        if args.teardown:
            _teardown(db, backend=backend)
            return
        # --apply: wipe self first (idempotent), then seed.
        _teardown(db, backend=backend)
        sample_path = Path(args.sample_docs_path) if args.sample_docs_path else sds._default_sample_docs_path()
        sample = sds.SampleIndex.load(sample_path)
        uploader = sds.BlobUploader(backend)
        result = _apply(db, sample=sample, uploader=uploader)
        print(f"\n  Seeded flagship tenant: client_id={result['client_id']}")
        print(f"  Reports: {result['reports']}   Blobs uploaded: {result['blobs']}")
        print(f"  Client login:   {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        print(f"  Provider login: {PROVIDER_LOGIN_EMAIL} / {PROVIDER_LOGIN_PASSWORD}  (Provider D)")
        _measure(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
