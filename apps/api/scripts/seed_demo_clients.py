"""Seed four NAMED demo client tenants — each with its own 5-provider ladder.

Builds on the machinery in ``seed_demo_sandbox.py`` (real sample PDFs, full
submission graph, deterministic ids, canonical pre-seeded report) but stands
up FOUR independent client tenants, one per demo user:

    Francisco Medina   fmedina@legalshelf.mx      / MedinaDemo!2026
    Hillary Gómez      hgomez@legalshelf.mx       / GomezDemo!2026
    Rubén Martínez     rmartinez@legalshelf.mx    / MartinezDemo!2026
    Rafael Samano      rsamano@samanosc.com.mx    / SamanoDemo!2026

Each tenant gets five REALISTICALLY-NAMED providers that form the same
compliance ladder as the sandbox (recién invitado → cumplimiento total),
backed by real PDFs from ``_reference/sample-docs/`` — so portfolios,
semáforos and generated reports all read as lived-in, never empty.

The script can also WIPE existing demo/test tenants first (explicit
allow-list by client RFC — it never deletes a tenant you didn't name).
Internal organizations (kind='internal') and their users are never touched.

USAGE
-----
  cd apps/api

  # See every client tenant with row counts (read-only).
  .venv/bin/python scripts/seed_demo_clients.py --list

  # Local: wipe ALL client tenants, then seed the four demo clients.
  .venv/bin/python scripts/seed_demo_clients.py --apply --wipe-all-client-tenants

  # Local: wipe only specific tenants by RFC, then seed.
  .venv/bin/python scripts/seed_demo_clients.py --apply --wipe-rfcs TST010101BBB,CUT260601AA1

  # Remove the four demo clients (DB rows + storage blobs).
  .venv/bin/python scripts/seed_demo_clients.py --teardown

  # Promote to prod (take a Neon snapshot FIRST — see reference_neon_snapshots).
  set -a; . ./.env.production; set +a
  .venv/bin/python scripts/seed_demo_clients.py --apply --wipe-rfcs ... --confirm-prod
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func, or_, select

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR.parent))  # apps/api → `app` package
sys.path.insert(0, str(_SCRIPTS_DIR))         # scripts → sibling seeder

import seed_demo_sandbox as sds  # noqa: E402

from app.db.seed import seed_catalog  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Client,
    ClientNotification,
    ComplianceSnapshot,
    Contract,
    Document,
    DocumentInspection,
    DocumentStatusHistory,
    FeedbackReport,
    Membership,
    NotificationDispatch,
    Organization,
    PasswordHistory,
    PasswordResetToken,
    PhoneVerification,
    ProviderNotification,
    ProviderWorkspace,
    RenewalReminder,
    Report,
    ReportConversation,
    ReportExport,
    ReportShare,
    ReportVersion,
    Submission,
    User,
    UserNotificationPreference,
    Validation,
    ValidationEvent,
    Vendor,
    WiseEvent,
)
from app.models.entities import utc_now  # noqa: E402
from app.services.audit_log import add_audit_event  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

# ── Re-point the sandbox machinery at THIS scenario ─────────────────────────
sds.SCENARIO_TAG = "demo_clients"
sds.STORAGE_PREFIX = "demo-clients"
sds.TODAY = date(2026, 6, 10)  # pinned "today" → deterministic renewal math

SCENARIO_TAG = sds.SCENARIO_TAG
LEGAL_CONSENT_VERSION = "v2"


# ============================================================================
# THE FOUR DEMO CLIENTS
# ============================================================================

class DemoClientSpec:
    def __init__(self, *, key, admin_email, admin_password, admin_fullname,
                 client_name, client_rfc, org_name, industry, providers):
        self.key = key
        self.admin_email = admin_email
        self.admin_password = admin_password
        self.admin_fullname = admin_fullname
        self.client_name = client_name
        self.client_rfc = client_rfc
        self.org_name = org_name
        self.industry = industry
        self.providers = providers


def _provider(key, stage, name, rfc, contact, slug, sample_slug, note):
    return sds.ProviderSeed(
        key=key,
        label=name,
        stage=stage,
        vendor_name=name,
        vendor_rfc=rfc,
        contact_name=contact,
        owner_email=f"contacto.{slug}@checkwise.mx",
        real_vendor_slug=sample_slug,
        onboarding_complete=stage not in {"invited", "just_starting"},
        scenario_note=note,
    )


_NOTES = {
    "invited": "Recién invitado; aún no sube documentos.",
    "just_starting": "Apenas empezando; primeros documentos en revisión.",
    "halfway": "A medio camino; mezcla de aprobado, pendiente y rechazos.",
    "almost_done": "Casi completo; CSF próxima a vencer (renovación 90 días).",
    "fully_compliant": "Totalmente en regla; expediente y calendario al día.",
}
_SAMPLES = ["human-medical-humese", "master-clean-plus", "angel-elias-garcia"]
_STAGES = ["invited", "just_starting", "halfway", "almost_done", "fully_compliant"]


def _roster(rows):
    """rows: list of (name, rfc, contact, slug) in ladder order P1..P5."""
    out = []
    for i, (name, rfc, contact, slug) in enumerate(rows):
        out.append(_provider(
            key=f"p{i + 1}",
            stage=_STAGES[i],
            name=name,
            rfc=rfc,
            contact=contact,
            slug=slug,
            sample_slug=_SAMPLES[i % len(_SAMPLES)],
            note=_NOTES[_STAGES[i]],
        ))
    return out


DEMO_CLIENTS = [
    DemoClientSpec(
        key="fmedina",
        admin_email="fmedina@legalshelf.mx",
        admin_password="MedinaDemo!2026",
        admin_fullname="Francisco Medina",
        client_name="Cliente de Francisco Medina",
        client_rfc="FME260610AA1",
        org_name="Cliente de Francisco Medina — Cliente",
        industry="Manufactura",
        providers=_roster([
            ("Transportes Sierra Norte", "TSN260201AA1", "Lucía Fuentes Ramos", "sierranorte"),
            ("Limpieza Industrial Azteca", "LIA260202BB2", "Daniel Quiroz Mena", "azteca"),
            ("Seguridad Privada Coyoacán", "SPC260203CC3", "Ana Sofía Beltrán", "coyoacan"),
            ("Mantenimiento Integral del Bajío", "MIB260204DD4", "Rodrigo Salas Vidal", "bajio"),
            ("Consultoría Laboral Monterrey", "CLM260205EE5", "Mariana Ferreira López", "monterrey"),
        ]),
    ),
    DemoClientSpec(
        key="hgomez",
        admin_email="hgomez@legalshelf.mx",
        admin_password="GomezDemo!2026",
        admin_fullname="Hillary Gómez",
        client_name="Cliente de Hillary Gómez",
        client_rfc="HGO260610BB2",
        org_name="Cliente de Hillary Gómez — Cliente",
        industry="Retail y distribución",
        providers=_roster([
            ("Grupo Logístico Veracruz", "GLV260201AA2", "Héctor Manuel Ríos", "veracruz"),
            ("Comedores Industriales Lumen", "CIL260202BB3", "Paola Estrada Gil", "lumen"),
            ("Vigilancia Táctica del Norte", "VTN260203CC4", "Iván Cervantes Luna", "tacticanorte"),
            ("Instalaciones Eléctricas Rivera", "IER260204DD5", "Claudia Mireles Soto", "rivera"),
            ("Nómina y Talento Querétaro", "NTQ260205EE6", "Sergio Andrade Peña", "queretaro"),
        ]),
    ),
    DemoClientSpec(
        key="rmartinez",
        admin_email="rmartinez@legalshelf.mx",
        admin_password="MartinezDemo!2026",
        admin_fullname="Rubén Martínez",
        client_name="Cliente de Rubén Martínez",
        client_rfc="RMA260610CC3",
        org_name="Cliente de Rubén Martínez — Cliente",
        industry="Construcción",
        providers=_roster([
            ("Construcciones Altiplano", "CAL260201AA3", "Gabriela Núñez Ortiz", "altiplano"),
            ("Fumigaciones Ambientales MX", "FAM260202BB4", "Tomás Aguirre Reyna", "fumigamx"),
            ("Soporte TI Guadalajara", "STG260203CC5", "Renata Villaseñor Cruz", "soportegdl"),
            ("Uniformes Industriales Roma", "UIR260204DD6", "Emilio Bandala Torres", "roma"),
            ("Recursos Humanos del Pacífico", "RHP260205EE7", "Fernanda Casas Marín", "pacifico"),
        ]),
    ),
    DemoClientSpec(
        key="rsamano",
        admin_email="rsamano@samanosc.com.mx",
        admin_password="SamanoDemo!2026",
        admin_fullname="Rafael Samano",
        client_name="Cliente de Rafael Samano",
        client_rfc="RSA260610DD4",
        org_name="Cliente de Rafael Samano — Cliente",
        industry="Servicios financieros",
        providers=_roster([
            ("Grúas y Acarreos Tepeyac", "GAT260201AA4", "Octavio Lemus Prado", "tepeyac"),
            ("Jardinería Corporativa Verde", "JCV260202BB5", "Brenda Anaya Solís", "verde"),
            ("Catering Empresarial San Ángel", "CES260203CC6", "Marcos Tinoco Ávila", "sanangel"),
            ("Climas y Refrigeración Polar", "CRP260204DD7", "Diana Escamilla Bravo", "polar"),
            ("Outsourcing Contable Insurgentes", "OCI260205EE8", "Alonso Gracia Téllez", "insurgentes"),
        ]),
    ),
]
DEMO_CLIENT_RFCS = {c.client_rfc for c in DEMO_CLIENTS}


# ============================================================================
# GENERIC TENANT WIPE (explicit allow-list, internal orgs never touched)
# ============================================================================

def _q_delete(db, model, *criteria):
    db.query(model).filter(*criteria).delete(synchronize_session=False)


def _wipe_client_tenant(db, client) -> tuple[set[str], set[str]]:
    """Cascade-delete one client tenant. Returns (storage_keys, user_ids)
    — blob keys are deleted later (after dedup check), candidate users are
    cleaned up later (only if nothing else references them)."""
    org_ids = list(db.scalars(
        select(Organization.id).where(Organization.client_id == client.id)
    ))
    vendor_ids = list(db.scalars(select(Vendor.id).where(Vendor.client_id == client.id)))
    workspace_ids = list(db.scalars(
        select(ProviderWorkspace.id).where(ProviderWorkspace.client_id == client.id)
    ))
    owner_ids = [
        u for u in db.scalars(
            select(ProviderWorkspace.owner_user_id)
            .where(ProviderWorkspace.client_id == client.id)
        ) if u
    ]
    member_ids = list(db.scalars(
        select(Membership.user_id).where(Membership.organization_id.in_(org_ids))
    )) if org_ids else []
    sub_ids = list(db.scalars(select(Submission.id).where(Submission.client_id == client.id)))
    doc_ids = list(db.scalars(
        select(Document.id).where(Document.submission_id.in_(sub_ids))
    )) if sub_ids else []
    storage_keys = set(db.scalars(
        select(Document.storage_key).where(Document.submission_id.in_(sub_ids))
    )) if sub_ids else set()

    # Reports owned by the tenant's orgs OR scoped to its client/vendors
    # (internal-org reports about this client included).
    report_filters = [Report.client_id == client.id]
    if org_ids:
        report_filters.append(Report.organization_id.in_(org_ids))
    if vendor_ids:
        report_filters.append(Report.vendor_id.in_(vendor_ids))
    report_ids = list(db.scalars(select(Report.id).where(or_(*report_filters))))

    if report_ids:
        db.query(Report).filter(Report.id.in_(report_ids)).update(
            {Report.current_version_id: None}, synchronize_session=False
        )
        db.flush()
        _q_delete(db, ReportConversation, ReportConversation.report_id.in_(report_ids))
        _q_delete(db, ReportExport, ReportExport.report_id.in_(report_ids))
        _q_delete(db, ReportShare, ReportShare.report_id.in_(report_ids))
        _q_delete(db, ReportVersion, ReportVersion.report_id.in_(report_ids))
        _q_delete(db, Report, Report.id.in_(report_ids))

    snap_filters = [ComplianceSnapshot.client_id == client.id]
    if org_ids:
        snap_filters.append(ComplianceSnapshot.organization_id.in_(org_ids))
    if vendor_ids:
        snap_filters.append(ComplianceSnapshot.vendor_id.in_(vendor_ids))
    _q_delete(db, ComplianceSnapshot, or_(*snap_filters))

    if workspace_ids:
        _q_delete(db, WiseEvent, WiseEvent.workspace_id.in_(workspace_ids))
        _q_delete(db, RenewalReminder, RenewalReminder.workspace_id.in_(workspace_ids))
        _q_delete(db, ProviderNotification,
                  ProviderNotification.workspace_id.in_(workspace_ids))
    _q_delete(db, ClientNotification, ClientNotification.client_id == client.id)

    if sub_ids:
        _q_delete(db, ValidationEvent, ValidationEvent.submission_id.in_(sub_ids))
        _q_delete(db, Validation, Validation.submission_id.in_(sub_ids))
    if doc_ids:
        _q_delete(db, DocumentInspection, DocumentInspection.document_id.in_(doc_ids))
        _q_delete(db, DocumentStatusHistory,
                  DocumentStatusHistory.document_id.in_(doc_ids))
    if sub_ids:
        _q_delete(db, Document, Document.submission_id.in_(sub_ids))
        _q_delete(db, Submission, Submission.id.in_(sub_ids))

    if workspace_ids:
        _q_delete(db, ProviderWorkspace, ProviderWorkspace.id.in_(workspace_ids))
    _q_delete(db, Contract, Contract.client_id == client.id)
    if vendor_ids:
        _q_delete(db, Vendor, Vendor.id.in_(vendor_ids))

    if org_ids:
        _q_delete(db, Membership, Membership.organization_id.in_(org_ids))
        _q_delete(db, Organization, Organization.id.in_(org_ids))
        # Organization.client_id is a plain FK column (no ORM relationship);
        # force the org DELETE to emit before the client DELETE.
        db.flush()

    db.delete(client)
    db.flush()
    return storage_keys, set(member_ids) | set(owner_ids)


_USER_REF_CHECKS = [
    ("reports.created_by", Report, Report.created_by_user_id),
    ("report_versions.created_by", ReportVersion, ReportVersion.created_by_user_id),
    ("report_conversations.created_by", ReportConversation,
     ReportConversation.created_by_user_id),
    ("report_shares.created_by", ReportShare, ReportShare.created_by_user_id),
    ("report_exports.requested_by", ReportExport, ReportExport.requested_by_user_id),
]


def _cleanup_orphan_users(db, candidate_ids: set[str]) -> tuple[int, list[str]]:
    """Delete users left dangling by the tenant wipe — but only when nothing
    references them anymore. Internal-org members are never deleted."""
    deleted, skipped = 0, []
    for uid in sorted(candidate_ids):
        user = db.get(User, uid)
        if user is None:
            continue
        still_member = db.scalar(
            select(func.count(Membership.id)).where(Membership.user_id == uid)
        )
        still_owner = db.scalar(
            select(func.count(ProviderWorkspace.id))
            .where(ProviderWorkspace.owner_user_id == uid)
        )
        if still_member or still_owner:
            skipped.append(f"{user.email} (still attached)")
            continue
        hard_refs = [
            label for label, model, col in _USER_REF_CHECKS
            if db.scalar(select(func.count()).select_from(model).where(col == uid))
        ]
        if hard_refs:
            skipped.append(f"{user.email} (referenced by {', '.join(hard_refs)})")
            continue
        db.query(FeedbackReport).filter(FeedbackReport.user_id == uid).update(
            {FeedbackReport.user_id: None}, synchronize_session=False)
        db.query(FeedbackReport).filter(FeedbackReport.triaged_by_user_id == uid).update(
            {FeedbackReport.triaged_by_user_id: None}, synchronize_session=False)
        db.query(WiseEvent).filter(WiseEvent.user_id == uid).update(
            {WiseEvent.user_id: None}, synchronize_session=False)
        _q_delete(db, PasswordResetToken, PasswordResetToken.user_id == uid)
        _q_delete(db, PasswordHistory, PasswordHistory.user_id == uid)
        _q_delete(db, UserNotificationPreference, UserNotificationPreference.user_id == uid)
        _q_delete(db, PhoneVerification, PhoneVerification.user_id == uid)
        _q_delete(db, NotificationDispatch, NotificationDispatch.user_id == uid)
        db.delete(user)
        deleted += 1
    db.flush()
    return deleted, skipped


def _delete_unreferenced_blobs(db, backend, candidate_keys: set[str]) -> int:
    """Blobs are content-addressed and shared across tenants — only delete a
    key once no surviving document row references it."""
    deleted = 0
    for key in sorted(k for k in candidate_keys if k):
        refs = db.scalar(
            select(func.count(Document.id)).where(Document.storage_key == key)
        )
        if refs:
            continue
        try:
            backend.delete(key)
            deleted += 1
        except Exception as exc:  # noqa: BLE001 — blob may already be gone
            print(f"  [!] could not delete blob {key}: {exc}")
    return deleted


# ============================================================================
# SEEDING
# ============================================================================

def _get_or_create_admin(db, spec) -> User:
    user = db.scalar(select(User).where(User.email == spec.admin_email))
    if user is not None:
        owned = db.scalar(
            select(func.count(ProviderWorkspace.id))
            .where(ProviderWorkspace.owner_user_id == user.id)
        )
        if owned:
            print(f"  [!] {spec.admin_email} already exists AND owns {owned} provider "
                  "workspace(s) — workspace ownership shadows org membership in "
                  "report listing (see project_actor_from_precedence_risk).")
        user.password_hash = hash_password(spec.admin_password)
        user.full_name = spec.admin_fullname
        user.status = "active"
        user.must_change_password = False
        db.flush()
        return user
    user = User(
        id=sds._id(f"user:{spec.admin_email}"),
        email=spec.admin_email,
        password_hash=hash_password(spec.admin_password),
        full_name=spec.admin_fullname,
        status="active",
        must_change_password=False,
    )
    db.add(user)
    db.flush()
    return user


def _seed_renewal_signal(db, *, provider, client_id, vendor_id, workspace_id):
    """P4: CSF renewal due ~14 days out → reminders + both notifications."""
    anchor = sds.TODAY - timedelta(days=76)
    due = anchor + timedelta(days=sds.CSF_RENEWAL_DAYS)
    days_to_due = (due - sds.TODAY).days

    for threshold in (30, 14):
        db.add(RenewalReminder(
            id=sds._id(f"renewal:{provider.key}:{sds.CSF_CODE}:{threshold}"),
            workspace_id=workspace_id,
            requirement_code=sds.CSF_CODE,
            cycle_anchor_date=anchor,
            threshold_days=threshold,
            severity="yellow",
            created_at=sds._dt(threshold - days_to_due if threshold > days_to_due else 0),
        ))

    title = f"CSF próxima a vencer · {provider.vendor_name}"
    body = (
        f"La Constancia de Situación Fiscal de {provider.vendor_name} vence el "
        f"{due.isoformat()} (~{days_to_due} días). La CSF debe renovarse cada "
        f"{sds.CSF_RENEWAL_DAYS} días."
    )
    csf_submission_id = sds._id(f"submission:{provider.key}:{sds.CSF_CODE}:onboarding")
    db.add(ClientNotification(
        id=sds._id(f"client-notif:renewal:{provider.key}"),
        client_id=client_id,
        vendor_id=vendor_id,
        submission_id=csf_submission_id,
        notification_type="renewal_due_soon",
        title=title,
        body=body,
        action_url="/client/vendors",
        payload={"scenario": SCENARIO_TAG, "requirement_code": sds.CSF_CODE,
                 "due_on": due.isoformat()},
        severity="yellow",
        category="renewal",
        created_at=sds._dt(1),
    ))
    db.add(ProviderNotification(
        id=sds._id(f"provider-notif:renewal:{provider.key}"),
        workspace_id=workspace_id,
        submission_id=csf_submission_id,
        notification_type="renewal_due_soon",
        severity="warning",
        category="renewal",
        title="Renueva tu Constancia de Situación Fiscal",
        body=body,
        action_url="/portal/dashboard",
        payload={"scenario": SCENARIO_TAG, "requirement_code": sds.CSF_CODE,
                 "due_on": due.isoformat()},
        created_at=sds._dt(1),
    ))


def _seed_one_client(db, *, spec, sample, uploader) -> dict:
    sds._INSTANCE_KEY = f"demo-clients:{spec.key}"
    sds.PROVIDERS = spec.providers
    sds.PROVIDERS_BY_KEY = {p.key: p for p in spec.providers}

    admin = _get_or_create_admin(db, spec)

    client = Client(
        id=sds._id("client"),
        name=spec.client_name,
        rfc=spec.client_rfc,
        email=spec.admin_email,
        responsible_name=spec.admin_fullname,
        industry=spec.industry,
        fiscal_address="Domicilio de demostración (sin validez fiscal)",
        phone="+52 55 1234 5678",
        notes=f"{SCENARIO_TAG}: cliente demo de {spec.admin_fullname} con 5 proveedores escalonados.",
        onboarding_completed_at=utc_now(),
        status="active",
    )
    db.add(client)
    db.flush()

    org = Organization(
        id=sds._id("client-org"),
        name=spec.org_name,
        kind="client",
        client_id=client.id,
        status="active",
    )
    db.add(org)
    db.flush()
    db.add(Membership(
        id=sds._id("membership:admin"),
        user_id=admin.id,
        organization_id=org.id,
        role="client_admin",
        status="active",
    ))
    db.flush()

    vendor_ids = sds._seed_provider_rows(db, client_id=client.id)
    # The shared helper stamps consent v1; the live legal package is v2.
    db.query(ProviderWorkspace).filter(
        ProviderWorkspace.client_id == client.id,
        ProviderWorkspace.legal_consent_version.isnot(None),
    ).update({ProviderWorkspace.legal_consent_version: LEGAL_CONSENT_VERSION},
             synchronize_session=False)
    # Replace the helper's generic "REPSE-DEMO-Pn" with a realistic folio,
    # deterministic per vendor RFC.
    import hashlib as _hashlib
    for provider in spec.providers:
        folio = 100000 + int(_hashlib.sha256(
            provider.vendor_rfc.encode()).hexdigest(), 16) % 800000
        vendor = db.get(Vendor, vendor_ids[provider.key])
        vendor.repse_id = f"AR{folio}/2024"
    db.flush()

    onboarding = recurring = 0
    for provider in spec.providers:
        vid = vendor_ids[provider.key]
        onboarding += sds._seed_onboarding(
            db, sample=sample, uploader=uploader, provider=provider,
            client_id=client.id, vendor_id=vid,
        )
        recurring += sds._seed_recurring(
            db, sample=sample, uploader=uploader, provider=provider,
            client_id=client.id, vendor_id=vid,
        )
        if provider.stage == "almost_done":
            _seed_renewal_signal(
                db, provider=provider, client_id=client.id, vendor_id=vid,
                workspace_id=sds._id(f"workspace:{provider.key}"),
            )

    sds._seed_report(db, org_id=org.id, client_id=client.id,
                     admin_user_id=admin.id, vendor_ids=vendor_ids, stats={})

    return {"client_id": client.id, "org_id": org.id,
            "onboarding": onboarding, "recurring": recurring}


# ============================================================================
# CLI
# ============================================================================

def _list_tenants(db) -> list[dict]:
    rows = []
    for client in db.scalars(select(Client).order_by(Client.created_at)):
        org_ids = list(db.scalars(
            select(Organization.id).where(Organization.client_id == client.id)
        ))
        admins = list(db.scalars(
            select(User.email)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organization_id.in_(org_ids))
        )) if org_ids else []
        rows.append({
            "id": client.id,
            "rfc": client.rfc or "<sin RFC>",
            "name": client.name,
            "vendors": db.scalar(select(func.count(Vendor.id))
                                 .where(Vendor.client_id == client.id)) or 0,
            "workspaces": db.scalar(select(func.count(ProviderWorkspace.id))
                                    .where(ProviderWorkspace.client_id == client.id)) or 0,
            "submissions": db.scalar(select(func.count(Submission.id))
                                     .where(Submission.client_id == client.id)) or 0,
            "users": ", ".join(admins) or "—",
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the four named demo client tenants (5-provider ladder each).")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true",
                      help="List every client tenant with row counts (read-only).")
    mode.add_argument("--apply", action="store_true",
                      help="Wipe requested tenants, then seed the four demo clients.")
    mode.add_argument("--teardown", action="store_true",
                      help="Delete the four demo clients (DB + storage).")
    parser.add_argument("--wipe-rfcs", default=None, metavar="RFC[,RFC...]",
                        help="Client RFCs to wipe before seeding (explicit allow-list).")
    parser.add_argument("--wipe-ids", default=None, metavar="ID[,ID...]",
                        help="Client ids to wipe (for tenants without an RFC).")
    parser.add_argument("--wipe-all-client-tenants", action="store_true",
                        help="Wipe EVERY kind='client' tenant before seeding.")
    parser.add_argument("--skip-blob-delete", action="store_true",
                        help="Leave storage blobs in place (orphaned but recoverable) — "
                             "recommended on prod so a Neon restore stays consistent.")
    parser.add_argument("--confirm-prod", action="store_true",
                        help="Required when CHECKWISE_ENV != 'local'.")
    parser.add_argument("--sample-docs-path", default=None,
                        help="Path to _reference/sample-docs (defaults to repo root).")
    args = parser.parse_args()

    if args.list:
        with SessionLocal() as db:
            rows = _list_tenants(db)
        if not rows:
            print("No client tenants found.")
            return
        for r in rows:
            print(f"  {r['rfc']:<14} {r['name']:<40} vendors={r['vendors']:<3} "
                  f"ws={r['workspaces']:<3} subs={r['submissions']:<4} "
                  f"id={r['id']}  users: {r['users']}")
        return

    sds._assert_env(confirm_prod=args.confirm_prod)
    backend = sds._storage_backend()
    from app.core.config import settings
    print(f"CHECKWISE_ENV={settings.CHECKWISE_ENV}  STORAGE_BUCKET={settings.STORAGE_BUCKET}")

    if args.teardown:
        with SessionLocal() as db:
            blob_keys: set[str] = set()
            user_ids: set[str] = set()
            for rfc in sorted(DEMO_CLIENT_RFCS):
                client = db.scalar(select(Client).where(Client.rfc == rfc))
                if client is None:
                    continue
                print(f"  wiping {client.name} ({rfc})")
                keys, uids = _wipe_client_tenant(db, client)
                blob_keys |= keys
                user_ids |= uids
            deleted_users, skipped = _cleanup_orphan_users(db, user_ids)
            blobs = _delete_unreferenced_blobs(db, backend, blob_keys)
            db.commit()
        print(f"Teardown complete. {deleted_users} user(s) and {blobs} blob(s) removed.")
        for s in skipped:
            print(f"  kept user: {s}")
        return

    # ── apply ──
    wipe_rfcs: set[str] = set(DEMO_CLIENT_RFCS)  # re-runs always replace themselves
    if args.wipe_rfcs:
        wipe_rfcs |= {r.strip().upper() for r in args.wipe_rfcs.split(",") if r.strip()}

    sample_path = (Path(args.sample_docs_path) if args.sample_docs_path
                   else sds._default_sample_docs_path())
    sample = sds.SampleIndex.load(sample_path)
    print(f"Sample docs: {sample_path}")

    with SessionLocal() as db:
        targets = []
        if args.wipe_all_client_tenants:
            targets = list(db.scalars(select(Client)))
        else:
            for rfc in sorted(wipe_rfcs):
                client = db.scalar(select(Client).where(Client.rfc == rfc))
                if client is not None:
                    targets.append(client)
            if args.wipe_ids:
                for cid in (c.strip() for c in args.wipe_ids.split(",") if c.strip()):
                    client = db.get(Client, cid)
                    if client is not None and all(t.id != client.id for t in targets):
                        targets.append(client)

        blob_keys: set[str] = set()
        user_ids: set[str] = set()
        if targets:
            print(f"Wiping {len(targets)} tenant(s):")
            for client in targets:
                print(f"  - {client.name} ({client.rfc})")
                keys, uids = _wipe_client_tenant(db, client)
                blob_keys |= keys
                user_ids |= uids
            deleted_users, skipped = _cleanup_orphan_users(db, user_ids)
            print(f"  removed {deleted_users} orphaned user(s).")
            for s in skipped:
                print(f"  kept user: {s}")

        seed_catalog(db, years=(2026,))
        uploader = sds.BlobUploader(backend)
        results = []
        for spec in DEMO_CLIENTS:
            print(f"Seeding {spec.client_name} …")
            results.append((spec, _seed_one_client(
                db, spec=spec, sample=sample, uploader=uploader)))

        if args.skip_blob_delete:
            blobs_removed = 0
            print(f"  [skip-blob-delete] leaving {len(blob_keys)} candidate blob key(s) in storage.")
        else:
            blobs_removed = _delete_unreferenced_blobs(db, backend, blob_keys)

        add_audit_event(
            db,
            action="demo_clients.scenario_seeded",
            entity_type="client",
            entity_id=results[0][1]["client_id"],
            actor_type="system",
            actor_id=None,
            metadata={
                "scenario": SCENARIO_TAG,
                "clients": [s.client_name for s, _ in results],
                "wiped_tenants": [c.rfc for c in targets],
                "blobs_uploaded": len(uploader._seen),
                "blobs_removed": blobs_removed,
            },
        )
        db.commit()

    print("")
    print("Demo clients ready.")
    for spec, res in results:
        print(f"  {spec.client_name}")
        print(f"    Login   {spec.admin_email} / {spec.admin_password}")
        print(f"    Seeded  {res['onboarding']} onboarding + {res['recurring']} recurring "
              f"submissions across {len(spec.providers)} providers + 1 report")
    print(f"  Unique PDF blobs uploaded: {len(uploader._seen)}")
    print("")
    print("  Each portfolio ladder: P1 recién invitado → P2 en arranque → "
          "P3 media marcha → P4 casi listo (CSF ~14d) → P5 cumplimiento total.")


if __name__ == "__main__":
    main()
