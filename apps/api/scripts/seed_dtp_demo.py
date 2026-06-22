"""Seed the DTP Consultores LIVE-DEMO scenario (prod Neon · main) — FAST path.

Reuses the stage logic in ``seed_demo_sandbox`` (``_seed_onboarding`` /
``_seed_recurring`` / ``_seed_renewal_signal`` / ``_seed_report``) but swaps in a
cached, flush-deferred ``_insert_submission`` so the whole thing commits in ~1
minute instead of ~30 (no per-row SELECT/flush round-trips to Neon).

CLIENT SIDE — DTP as the client, three orgs (same 10 subcontractors, improving):
    DTP · Mes 1   →  ~25%   login: dtp.m1@checkwise.demo
    DTP · Mes 3   →  ~65%   login: dtp.m3@checkwise.demo
    DTP · Mes 6   →  ~95%   login: dtp.m6@checkwise.demo
    (all share DEMO_PW; all display as "DTP Consultores, S.A. de C.V.")

Storage: seeded documents REUSE existing prod blob keys (no S3 creds).
Clock: TODAY pinned to 2026-06-09. Tagged with MARKER, re-runnable, tearable down.

USAGE (from apps/api):
  DATABASE_URL=... CHECKWISE_ENV=local STORAGE_BACKEND=local \
    .venv/bin/python scripts/seed_dtp_demo.py --apply
  ... --teardown
"""

from __future__ import annotations

import argparse
from datetime import date

import seed_demo_sandbox as S  # reuse all primitives
from sqlalchemy import select

from app.models import (  # noqa: E402
    Client,
    ClientNotification,
    ComplianceSnapshot,
    Document,
    DocumentInspection,
    DocumentStatusHistory,
    Membership,
    Organization,
    ProviderNotification,
    ProviderWorkspace,
    RenewalReminder,
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

# ── Pin the scenario clock to the real demo day ──────────────────────────────
S.TODAY = date(2026, 6, 9)

MARKER = "DTP_DEMO_2026_06_09"
DEMO_PW = "DemoDTP!2026"
CLIENT_DISPLAY_NAME = "DTP Consultores, S.A. de C.V."
DEMO_EMAIL_DOMAIN = "checkwise.demo"

REUSE_BLOBS = [
    ("demo-sandbox/_blobs/92034d726fb52fdd9ec619e4978815748bf58566c19ae654e0af7340a9072362.pdf",
     "92034d726fb52fdd9ec619e4978815748bf58566c19ae654e0af7340a9072362", 266284),
    ("demo-sandbox/_blobs/6ae3447c5b0534020ccaa8aa5a4c87cf5d504da23326a97401aa7fe8fdc73cc4.pdf",
     "6ae3447c5b0534020ccaa8aa5a4c87cf5d504da23326a97401aa7fe8fdc73cc4", 43927),
    ("demo-sandbox/_blobs/bab1e150b82f59679d6496b559bccb2b361e2fd79a9163d2236681e08e8ea181.pdf",
     "bab1e150b82f59679d6496b559bccb2b361e2fd79a9163d2236681e08e8ea181", 36419),
]


class ReuseUploader:
    def __init__(self) -> None:
        self._i = 0
        self._seen: dict = {}

    def put(self, data: bytes) -> tuple[str, str, int]:
        key, sha, size = REUSE_BLOBS[self._i % len(REUSE_BLOBS)]
        self._i += 1
        return key, sha, size


# ── Caches populated once, before seeding (eliminate per-row SELECTs) ─────────
_REQ_CACHE: dict[str, dict] = {}     # requirement_code -> {req_id, inst_id, freq, ver_id}
_PERIOD_CACHE: dict[str | None, str] = {}  # period_key -> period_id


def _build_caches(db) -> None:
    ver_by_req: dict[str, tuple[str, int]] = {}
    for rid, vid, vnum in db.execute(
        select(RequirementVersion.requirement_id, RequirementVersion.id, RequirementVersion.version)
    ):
        cur = ver_by_req.get(rid)
        if cur is None or vnum < cur[1]:
            ver_by_req[rid] = (vid, vnum)
    for req in db.scalars(select(Requirement)):
        v = ver_by_req.get(req.id)
        _REQ_CACHE[req.code] = {
            "req_id": req.id, "inst_id": req.institution_id,
            "freq": req.frequency, "ver_id": (v[0] if v else None),
        }
    # Pre-create every period we'll reference (onboarding + full recurring year)
    S._INSTANCE_KEY = "dtp-shared"
    keys = {None} | {it.period_key for it in S.recurring_for_year(2026, "moral")}
    for pk in keys:
        _PERIOD_CACHE[pk] = S._get_or_create_period(db, period_key=pk)
    db.flush()


def _lean_insert(
    db, *, sample, uploader, provider, client_id, vendor_id, requirement_code,
    status_value, days_ago, period_key=None, reviewer_note=None,
    supersedes_submission_id=None, chain_suffix="",
) -> str:
    """Drop-in for S._insert_submission: submission + document only, cached
    lookups, no SELECT, no flush. Status is set directly (drives compliance)."""
    if supersedes_submission_id is not None:
        db.flush()  # the superseded (v1) row must exist before this self-referential insert
    rc = _REQ_CACHE[requirement_code]
    period_id = _PERIOD_CACHE.get(period_key) or S._get_or_create_period(db, period_key=period_key)
    submitted_at = S._dt(days_ago)
    slot_salt = f"{provider.key}:{requirement_code}:{period_key or 'onboarding'}{chain_suffix}"
    key, sha, size = uploader.put(b"")
    sub_id = S._id(f"submission:{slot_salt}")
    db.add(Submission(
        id=sub_id, client_id=client_id, vendor_id=vendor_id, institution_id=rc["inst_id"],
        requirement_id=rc["req_id"], requirement_version_id=rc["ver_id"], period_id=period_id,
        status=status_value, load_type=rc["freq"], requirement_code=requirement_code,
        period_key=period_key, comments=f"{S.SCENARIO_TAG}: {provider.label}",
        submitted_by=provider.contact_name, supersedes_submission_id=supersedes_submission_id,
        created_at=submitted_at, updated_at=submitted_at,
    ))
    db.add(Document(
        id=S._id(f"document:{slot_salt}"), submission_id=sub_id, storage_key=key,
        original_filename="documento-demo.pdf", mime_type="application/pdf",
        size_bytes=size, sha256=sha, status=status_value, ocr_status="not_started",
        created_at=submitted_at, updated_at=submitted_at,
    ))
    return sub_id


# ── DTP's 10 subcontractors (same set across all three orgs) ─────────────────
_SLUGS = ["human-medical-humese", "master-clean-plus", "angel-elias-garcia"]
VENDORS = [
    ("Geotecnia y Laboratorio de Materiales del Bajío, S.A. de C.V.", "GLM180312AB1", "Ing. Raúl Medina Cortés"),
    ("Topografía y Geodesia Aplicada, S.C.",                          "TGA170518CD2", "Ing. Laura Vázquez Pineda"),
    ("Estudios Ambientales y Sociales Terranova, S.A. de C.V.",       "EAS190722EF3", "Biól. Marcela Ríos Lara"),
    ("Ingeniería Estructural Robles y Asociados, S.C.",               "IER160203GH4", "Ing. Arturo Robles Díaz"),
    ("Supervisión y Control de Obra Vértice, S.A. de C.V.",           "SCO181109IJ5", "Ing. Pablo Hinojosa Vega"),
    ("Maquinaria y Equipo Pesado del Centro, S.A. de C.V.",           "MEP150815KL6", "Lic. Sandra Núñez Olvera"),
    ("Personal Técnico Especializado en Obra (PETEO), S.A. de C.V.",  "PTE200127MN7", "Lic. Hugo Maldonado Cruz"),
    ("Seguridad y Señalización Vial del Norte, S.A. de C.V.",         "SSV170630OP8", "Ing. Daniela Acosta Fierro"),
    ("Instrumentación y Control Eléctrico Industrial, S.A. de C.V.",  "ICE190411QR9", "Ing. Emilio Tapia Serrano"),
    ("Laboratorio de Control de Calidad GeoControl, S.A. de C.V.",    "LCC160924ST0", "Q.F.B. Norma Salgado Reyes"),
]

I, J, H, A, F = "invited", "just_starting", "halfway", "almost_done", "fully_compliant"  # noqa: E741
ORGS = [
    {"key": "dtp-mes0", "rfc": "DTP0240115M0", "email": f"dtp.m0@{DEMO_EMAIL_DOMAIN}",
     "label": "Mes 0", "admin_name": "Coordinación de Cumplimiento · DTP",
     "stages": [I, I, I, I, I, I, I, I, I, I], "onboarding_done": False, "make_report": False},  # 0% · alta nueva
    {"key": "dtp-mes1", "rfc": "DTP1240115M1", "email": f"dtp.m1@{DEMO_EMAIL_DOMAIN}",
     "label": "Mes 1", "admin_name": "Coordinación de Cumplimiento · DTP",
     "stages": [H, I, H, H, H, J, H, I, H, F]},   # ~26% (6 halfway + 3 zero + 1 full)
    {"key": "dtp-mes3", "rfc": "DTP2240115M3", "email": f"dtp.m3@{DEMO_EMAIL_DOMAIN}",
     "label": "Mes 3", "admin_name": "Coordinación de Cumplimiento · DTP",
     "stages": [F, A, F, H, A, H, F, H, J, F]},   # ~68% yellow (6 full + 3 halfway + 1 zero)
    {"key": "dtp-mes6", "rfc": "DTP3240115M6", "email": f"dtp.m6@{DEMO_EMAIL_DOMAIN}",
     "label": "Mes 6", "admin_name": "Coordinación de Cumplimiento · DTP",
     "stages": [F, A, F, F, F, H, F, A, F, F]},   # ~94%
]


def _provider_for(org_key: str, idx: int, stage: str) -> S.ProviderSeed:
    name, rfc, contact = VENDORS[idx]
    return S.ProviderSeed(
        key=f"{org_key}-v{idx}", label=name, stage=stage, vendor_name=name, vendor_rfc=rfc,
        contact_name=contact, owner_email=f"prov.{org_key}.v{idx}@{DEMO_EMAIL_DOMAIN}",
        real_vendor_slug=_SLUGS[idx % len(_SLUGS)],
        onboarding_complete=stage not in {"invited", "just_starting"},
        scenario_note=f"{MARKER} {org_key} v{idx} ({stage})",
    )


def _seed_client(db, org: dict) -> tuple[str, str, str]:
    S._INSTANCE_KEY = org["key"]
    admin = User(
        id=S._id(f"user:{org['email']}"), email=org["email"],
        password_hash=S.hash_password(DEMO_PW), full_name=org["admin_name"],
        status="active", must_change_password=False,
    )
    db.add(admin)
    client = Client(
        id=S._id("client"), name=CLIENT_DISPLAY_NAME, rfc=org["rfc"], email=org["email"],
        responsible_name="Coordinación de Cumplimiento",
        industry="Ingeniería y consultoría en infraestructura",
        fiscal_address="Av. Insurgentes Sur, Ciudad de México (demostración)",
        phone="+52 55 5000 0000", notes=f"{MARKER} · {org['label']} · escenario de demostración DTP.",
        onboarding_completed_at=(S.utc_now() if org.get("onboarding_done", True) else None),
        status="active",
    )
    db.add(client)
    org_row = Organization(
        id=S._id("client-org"), name=f"DTP Consultores — {org['label']}",
        kind="client", client_id=client.id, status="active",
    )
    db.add(org_row)
    db.add(Membership(
        id=S._id("membership:admin"), user_id=admin.id, organization_id=org_row.id,
        role="client_admin", status="active",
    ))
    db.flush()
    return client.id, org_row.id, admin.id


def _seed_vendors(db, *, org: dict, client_id: str, sample, uploader) -> dict[str, str]:
    vendor_ids: dict[str, str] = {}
    for idx, stage in enumerate(org["stages"]):
        provider = _provider_for(org["key"], idx, stage)
        complete_at = S._dt(115) if provider.onboarding_complete else None
        db.add(Vendor(
            id=S._id(f"vendor:{provider.key}"), client_id=client_id, name=provider.vendor_name,
            rfc=provider.vendor_rfc, contact_name=provider.contact_name,
            contact_email=provider.owner_email, contact_phone="+52 55 1111 2222",
            repse_id=f"REPSE-{provider.vendor_rfc[:6]}", persona_type="moral", status="active",
        ))
        db.add(ProviderWorkspace(
            id=S._id(f"workspace:{provider.key}"), client_id=client_id,
            vendor_id=S._id(f"vendor:{provider.key}"), owner_user_id=None, filial_name="Matriz",
            persona_type="moral", display_name=provider.vendor_name,
            access_token=S._id(f"token:{provider.key}"), onboarding_completed_at=complete_at,
            profile_confirmed_at=complete_at, legal_consent_accepted_at=complete_at,
            legal_consent_version="v2" if provider.onboarding_complete else None, status="active",
        ))
        vid = S._id(f"vendor:{provider.key}")
        S._seed_onboarding(db, sample=sample, uploader=uploader, provider=provider,
                           client_id=client_id, vendor_id=vid)
        S._seed_recurring(db, sample=sample, uploader=uploader, provider=provider,
                          client_id=client_id, vendor_id=vid)
        db.flush()  # persist vendor+workspace+submissions (executemany) before renewal FKs
        if stage == "almost_done":
            S._seed_renewal_signal(db, provider=provider, client_id=client_id, vendor_id=vid,
                                   workspace_id=S._id(f"workspace:{provider.key}"))
        vendor_ids[provider.key] = vid
    return vendor_ids


# ── PART 2: DTP as a PROVIDER (its own expediente toward its clients) ─────────
def _degrade_provider(db, *, vendor_id, frac, to_status) -> None:
    """Flip the most-recent `frac` of approved submissions to `to_status`
    so a fully-compliant provider reads at a target % (status-driven)."""
    approved = list(db.scalars(
        select(Submission).where(Submission.vendor_id == vendor_id, Submission.status == "aprobado")
        .order_by(Submission.created_at.desc())
    ))
    n = max(1, round(len(approved) * frac))
    flip_ids = [s.id for s in approved[:n]]
    for s in approved[:n]:
        s.status = to_status
    if flip_ids:
        db.query(Document).filter(Document.submission_id.in_(flip_ids)).update(
            {Document.status: to_status}, synchronize_session=False)


def _seed_vendor_report(db, *, org_id, client_id, vendor_id, created_by_user_id, vendor_name) -> None:
    from app.constants.reports import ReportAudience
    from app.services.reports.context import ReportScope
    from app.services.reports.deterministic_layouts import build_deterministic_blocks
    scope = ReportScope(organization_id=org_id, audience=ReportAudience.VENDOR_FACING,
                        client_id=client_id, vendor_id=vendor_id, period=None)
    blocks = build_deterministic_blocks(db, preset_id="provider-current-state", scope=scope)
    report = Report(
        id=S._id("report:provider"), organization_id=org_id, client_id=client_id, vendor_id=vendor_id,
        title=f"Estado de cumplimiento del proveedor · {vendor_name} · Jun 2026",
        description="Reporte del proveedor: cumplimiento global, hallazgos, pendientes y próximos pasos.",
        audience="vendor_facing", status="active", created_by_user_id=created_by_user_id,
    )
    db.add(report)
    db.flush()
    ver_id = S._id("report-version:provider")
    db.add(ReportVersion(
        id=ver_id, report_id=report.id, version_number=1, parent_version_id=None,
        label="Versión inicial · demo", content_json={"blocks": blocks, "audience": "vendor_facing"},
        plan_json={"blocks": [{"id": b["id"], "type": b["type"], "config": b["config"]} for b in blocks],
                   "rationale": "Reporte demo del proveedor.", "scope_hint": "Expediente del proveedor."},
        generated_by="ai", source_snapshot_id=None, llm_metadata=None, created_by_user_id=created_by_user_id,
    ))
    db.flush()
    report.current_version_id = ver_id
    db.flush()


PROVIDER_SCENARIOS = [
    {"key": "dtp-prov-cfe", "contratante": "Comisión Federal de Electricidad · Contratante (Demo)",
     "crfc": "CFE110101AA1", "email": f"dtp.cfe@{DEMO_EMAIL_DOMAIN}", "label": "DTP -> CFE (~95%)",
     "flip_frac": 0.06, "flip_to": "vencido"},
    {"key": "dtp-prov-sict", "contratante": "Sec. de Infraestructura (SICT) · Contratante (Demo)",
     "crfc": "SCT110101BB2", "email": f"dtp.sict@{DEMO_EMAIL_DOMAIN}", "label": "DTP -> SICT (~50%)",
     "flip_frac": 0.52, "flip_to": "pendiente_revision"},
    {"key": "dtp-prov-nuevo", "contratante": "Gobierno del Estado · Nuevo Contrato (Demo)",
     "crfc": "GEN110101CC3", "email": f"dtp.nuevo@{DEMO_EMAIL_DOMAIN}", "label": "DTP -> Nuevo (0%, onboarding)",
     "stage": "invited", "onboarding_done": False},
]


def _seed_provider_side(db, *, sample, uploader) -> list[tuple[str, str]]:
    """DTP as a provider toward two contratante clients. Each provider login is
    a real user that owns the DTP workspace (so /portal/enter works). Seeded at
    100%; a follow-up SQL pass degrades SICT->~50% and CFE->~95%."""
    out: list[tuple[str, str]] = []
    for sc in PROVIDER_SCENARIOS:
        S._INSTANCE_KEY = sc["key"]
        contratante = Client(
            id=S._id("client"), name=sc["contratante"], rfc=sc["crfc"], email=sc["email"],
            responsible_name="Área de Contratistas", industry="Sector público / contratante",
            notes=f"{MARKER} · contratante de DTP como proveedor.",
            onboarding_completed_at=S.utc_now(), status="active",
        )
        db.add(contratante)
        org = Organization(
            id=S._id("client-org"), name=sc["contratante"], kind="client",
            client_id=contratante.id, status="active",
        )
        db.add(org)
        user = User(
            id=S._id("user"), email=sc["email"], password_hash=S.hash_password(DEMO_PW),
            full_name="DTP Consultores · Cumplimiento", status="active", must_change_password=False,
        )
        db.add(user)
        onboarding_done = sc.get("onboarding_done", True)
        provider = S.ProviderSeed(
            key=sc["key"], label="DTP Consultores, S.A. de C.V.", stage=sc.get("stage", "fully_compliant"),
            vendor_name="DTP Consultores, S.A. de C.V.", vendor_rfc="DTP160101XX0",
            contact_name="DTP Consultores · Cumplimiento", owner_email=sc["email"],
            real_vendor_slug=_SLUGS[0], onboarding_complete=onboarding_done, scenario_note=f"{MARKER} {sc['key']}",
        )
        vid = S._id(f"vendor:{sc['key']}")
        db.add(Vendor(
            id=vid, client_id=contratante.id, name=provider.vendor_name, rfc=provider.vendor_rfc,
            contact_name=provider.contact_name, contact_email=sc["email"], contact_phone="+52 55 5555 5555",
            repse_id="REPSE-DTP-0001", persona_type="moral", status="active",
        ))
        complete_at = S._dt(110) if onboarding_done else None
        db.add(ProviderWorkspace(
            id=S._id(f"workspace:{sc['key']}"), client_id=contratante.id, vendor_id=vid,
            owner_user_id=user.id, filial_name="Matriz", persona_type="moral",
            display_name=provider.vendor_name, access_token=S._id(f"token:{sc['key']}"),
            onboarding_completed_at=complete_at, profile_confirmed_at=complete_at,
            legal_consent_accepted_at=complete_at,
            legal_consent_version="v2" if onboarding_done else None, status="active",
        ))
        db.flush()
        S._seed_onboarding(db, sample=sample, uploader=uploader, provider=provider,
                           client_id=contratante.id, vendor_id=vid)
        S._seed_recurring(db, sample=sample, uploader=uploader, provider=provider,
                          client_id=contratante.id, vendor_id=vid)
        db.flush()
        if sc.get("flip_frac"):
            _degrade_provider(db, vendor_id=vid, frac=sc["flip_frac"], to_status=sc["flip_to"])
            db.flush()
        if onboarding_done:
            _seed_vendor_report(db, org_id=org.id, client_id=contratante.id, vendor_id=vid,
                                created_by_user_id=user.id, vendor_name=provider.vendor_name)
        out.append((sc["label"], sc["email"]))
    return out


def _teardown(db) -> int:
    client_rows = list(db.scalars(select(Client).where(Client.notes.like(f"{MARKER}%"))))
    n = 0
    for client in client_rows:
        cid = client.id
        vendor_ids = set(db.scalars(select(Vendor.id).where(Vendor.client_id == cid)))
        ws_ids = set(db.scalars(select(ProviderWorkspace.id).where(ProviderWorkspace.client_id == cid)))
        sub_ids = set(db.scalars(select(Submission.id).where(Submission.client_id == cid)))
        doc_ids = set(db.scalars(select(Document.id).where(Document.submission_id.in_(sub_ids)))) if sub_ids else set()
        org_rows = list(db.scalars(select(Organization).where(Organization.client_id == cid)))
        org_ids = {o.id for o in org_rows}
        report_ids = set(db.scalars(select(Report.id).where(Report.organization_id.in_(org_ids)))) if org_ids else set()
        if report_ids:
            for tbl in (ReportConversation, ReportExport, ReportShare, ReportVersion):
                db.query(tbl).filter(tbl.report_id.in_(report_ids)).delete(synchronize_session=False)
            db.query(Report).filter(Report.id.in_(report_ids)).delete(synchronize_session=False)
        if ws_ids:
            for tbl in (WiseEvent, RenewalReminder, ProviderNotification):
                db.query(tbl).filter(tbl.workspace_id.in_(ws_ids)).delete(synchronize_session=False)
        db.query(ClientNotification).filter(ClientNotification.client_id == cid).delete(synchronize_session=False)
        if sub_ids:
            db.query(ValidationEvent).filter(ValidationEvent.submission_id.in_(sub_ids)).delete(synchronize_session=False)
            db.query(Validation).filter(Validation.submission_id.in_(sub_ids)).delete(synchronize_session=False)
        if doc_ids:
            db.query(DocumentInspection).filter(DocumentInspection.document_id.in_(doc_ids)).delete(synchronize_session=False)
            db.query(DocumentStatusHistory).filter(DocumentStatusHistory.document_id.in_(doc_ids)).delete(synchronize_session=False)
        if sub_ids:
            db.query(Document).filter(Document.submission_id.in_(sub_ids)).delete(synchronize_session=False)
            db.query(Submission).filter(Submission.id.in_(sub_ids)).delete(synchronize_session=False)
        db.query(ComplianceSnapshot).filter(ComplianceSnapshot.client_id == cid).delete(synchronize_session=False)
        if ws_ids:
            db.query(ProviderWorkspace).filter(ProviderWorkspace.id.in_(ws_ids)).delete(synchronize_session=False)
        if vendor_ids:
            db.query(Vendor).filter(Vendor.id.in_(vendor_ids)).delete(synchronize_session=False)
        db.flush()
        for org_row in org_rows:
            db.query(Membership).filter(Membership.organization_id == org_row.id).delete(synchronize_session=False)
            db.query(ComplianceSnapshot).filter(ComplianceSnapshot.organization_id == org_row.id).delete(synchronize_session=False)
            db.delete(org_row)
        db.flush()
        admin = db.scalar(select(User).where(User.email == client.email))
        if admin is not None and client.email and client.email.endswith(DEMO_EMAIL_DOMAIN):
            db.query(Membership).filter(Membership.user_id == admin.id).delete(synchronize_session=False)
            db.delete(admin)
        db.delete(client)
        db.flush()
        n += 1
    return n


def _freshen(db) -> None:
    """Set each DTP client's 3 most-recent submissions to 'yesterday' so
    'última actividad' and the 14-day activity chart read current."""
    yesterday = S._dt(1)
    for cid in list(db.scalars(select(Client.id).where(Client.notes.like(f"{MARKER}%")))):
        recent = list(db.scalars(
            select(Submission.id).where(Submission.client_id == cid)
            .order_by(Submission.created_at.desc()).limit(3)
        ))
        if recent:
            db.query(Submission).filter(Submission.id.in_(recent)).update(
                {Submission.created_at: yesterday, Submission.updated_at: yesterday},
                synchronize_session=False)


def _apply(db) -> None:
    db.autoflush = False
    S.seed_catalog(db, years=(2026,))
    _build_caches(db)
    S._insert_submission = _lean_insert  # swap in the fast path
    sample = S.SampleIndex.load(S._default_sample_docs_path())
    uploader = ReuseUploader()

    removed = _teardown(db)
    if removed:
        print(f"  (re-run) removed {removed} existing DTP demo client(s) first")

    for org in ORGS:
        client_id, org_id, admin_id = _seed_client(db, org)
        vendor_ids = _seed_vendors(db, org=org, client_id=client_id, sample=sample, uploader=uploader)
        db.flush()  # ensure all submissions visible to the report's SELECTs
        if org.get("make_report", True):
            S._seed_report(db, org_id=org_id, client_id=client_id, admin_user_id=admin_id,
                           vendor_ids=vendor_ids, stats={})
        print(f"  seeded {CLIENT_DISPLAY_NAME} · {org['label']:<6} client_id={client_id} login={org['email']}")
    for label, email in _seed_provider_side(db, sample=sample, uploader=uploader):
        print(f"  seeded provider {label}  login={email}")
    _freshen(db)
    db.commit()


def main() -> None:
    p = argparse.ArgumentParser(description="Seed/teardown the DTP live-demo scenario (fast).")
    m = p.add_mutually_exclusive_group(required=True)
    m.add_argument("--apply", action="store_true")
    m.add_argument("--teardown", action="store_true")
    p.add_argument("--confirm-prod", action="store_true")
    args = p.parse_args()

    from urllib.parse import urlparse
    print(f"DB host: {urlparse(S.settings.sqlalchemy_url).hostname}")
    with S.SessionLocal() as db:
        if args.teardown:
            n = _teardown(db)
            db.commit()
            print(f"Teardown complete · removed {n} DTP demo client(s).")
            return
        _apply(db)

    print(f"\nDTP demo ready. Password for all client logins: {DEMO_PW}")
    for org in ORGS:
        print(f"  {org['label']:<6} {org['email']}")


if __name__ == "__main__":
    main()
