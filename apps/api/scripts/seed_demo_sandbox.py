"""Seed the CheckWise "Demo Sandbox" — a 5-provider realism ladder.

Stands up ONE dedicated sandbox client whose five providers each occupy a
different point on the REPSE-compliance journey, so that a report generated
for this client looks like a real, lived-in portfolio instead of an empty
shell:

    P1  Proveedor Recién Invitado     just invited        → everything MISSING
    P2  Servicios en Arranque         just starting       → a couple docs in review
    P3  Operadora Media Marcha        halfway             → mixed: approved / pending /
                                                            rejected→approved (supersession) /
                                                            posible_mismatch  (the at-risk one)
    P4  Corporativo Casi Listo        almost done         → all approved, CSF renewal due ~14d
                                                            (RenewalReminder + notifications seeded)
    P5  Cumplimiento Total            fully compliant      → all approved, current

Each provider exercises the full lifecycle (onboarding expediente + ~6 months
of recurring SAT/IMSS/INFONAVIT/STPS obligations) and is backed by REAL sample
PDFs from ``_reference/sample-docs/`` (statuses are set directly; no OCR runs).

This is a NEW, self-contained seeder. It deliberately does NOT touch the
``user_testing_2026_06_01`` scenario (Mayela/Anuar/Mina), which backs a live
program. Everything it creates is namespaced under ``SCENARIO_TAG`` and is
fully re-runnable (wipe-then-reseed) and tearable-down.

USAGE
-----
  cd apps/api

  # Local build (CHECKWISE_ENV=local). Wipes + reseeds.
  .venv/bin/python scripts/seed_demo_sandbox.py --apply

  # Remove everything this seeder created (DB rows + storage blobs).
  .venv/bin/python scripts/seed_demo_sandbox.py --teardown

  # Promote to the prod test client. Reads real PDFs locally and uploads
  # them to the configured object store (R2/S3). Take a Neon snapshot FIRST.
  CHECKWISE_ENV=production DATABASE_URL=... STORAGE_BUCKET=... \
    .venv/bin/python scripts/seed_demo_sandbox.py --apply --confirm-prod

NOTES
-----
  * The sample sandbox has no onboarding doc types (no real CSF / REPSE
    constancia / contrato). For those slots the closest available real PDF is
    attached as the stored blob — cosmetic only, since statuses are set
    directly and OCR is skipped.
  * Sample PDFs are 2025-period files reused for 2026 obligations; the file
    contents will mention 2025 even when the obligation is a 2026 month.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

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
from app.models.entities import utc_now  # noqa: E402
from app.services.audit_log import add_audit_event  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

# ============================================================================
# CONSTANTS
# ============================================================================

SCENARIO_TAG = "demo_sandbox"
SCENARIO_NAMESPACE = uuid.UUID("5a9db0c0-0000-5e30-9000-000000000001")

# "Today" for the scenario. Hard-pinned so re-runs are deterministic and the
# renewal math (P4) lands the same way every time.
TODAY = date(2026, 6, 3)

CLIENT_NAME = "Demo Sandbox · CheckWise"
CLIENT_RFC = "DSC260603AA1"
CLIENT_ORG_NAME = "Demo Sandbox — Cliente"

ADMIN_EMAIL = "sandbox.admin@checkwise.local"
ADMIN_PASSWORD = "SandboxAdmin!2026"
ADMIN_FULLNAME = "Admin Sandbox"

# Storage layout for the (de-duplicated) document blobs this seeder uploads.
STORAGE_PREFIX = "demo-sandbox"

# Recurring obligations we materialise — roughly the last ~6 months of 2026
# plus the bimonthly / cuatrimestral periods that overlap them. Keeping the
# window bounded (vs the whole year) keeps the dataset realistic for a tenant
# that's been live a few months — and keeps PDF copying sane.
TARGET_PERIOD_KEYS = {
    "2026-M01",
    "2026-M02",
    "2026-M03",
    "2026-M04",
    "2026-M05",
    "2026-B1",
    "2026-B2",
    "2026-Q1",
}

# Months → days-ago so submission timestamps fall just after each period.
_MONTH_DAYS_AGO = {
    "2026-M01": 118,
    "2026-M02": 92,
    "2026-M03": 66,
    "2026-M04": 38,
    "2026-M05": 12,
    "2026-B1": 80,
    "2026-B2": 28,
    "2026-Q1": 52,
}

ONBOARDING_CODES = [
    "ONB-CONT-001",   # Contrato firmado (interno_cliente)
    "ONB-CORP-M-001", # Documentación corporativa (interno_cliente)
    "ONB-CORP-M-002", # Constancia de Situación Fiscal — CSF (sat, renueva 90d)
    "ONB-REPSE-001",  # Registro REPSE original (stps_repse)
    "ONB-PATR-001",   # Registro patronal (imss)
]
CSF_CODE = "ONB-CORP-M-002"
CSF_RENEWAL_DAYS = 90


@dataclass(frozen=True)
class ProviderSeed:
    key: str
    label: str
    stage: str
    vendor_name: str
    vendor_rfc: str
    contact_name: str
    owner_email: str
    real_vendor_slug: str  # which sample-docs vendor backs this provider's PDFs
    onboarding_complete: bool
    scenario_note: str


# Each provider is backed by one real sample-docs vendor (cycled across the 3
# available sets) for visual consistency within a provider.
PROVIDERS = [
    ProviderSeed(
        key="p1-invitado",
        label="P1 · Proveedor Recién Invitado",
        stage="invited",
        vendor_name="Proveedor Recién Invitado · Sandbox",
        vendor_rfc="PRI260101AA1",
        contact_name="Lucía Fuentes Ramos",
        owner_email="p1.sandbox@checkwise.local",
        real_vendor_slug="human-medical-humese",
        onboarding_complete=False,
        scenario_note="Recién invitado; aún no sube documentos.",
    ),
    ProviderSeed(
        key="p2-arranque",
        label="P2 · Servicios en Arranque",
        stage="just_starting",
        vendor_name="Servicios en Arranque · Sandbox",
        vendor_rfc="SEA260102BB2",
        contact_name="Daniel Quiroz Mena",
        owner_email="p2.sandbox@checkwise.local",
        real_vendor_slug="master-clean-plus",
        onboarding_complete=False,
        scenario_note="Apenas empezando; primeros documentos en revisión.",
    ),
    ProviderSeed(
        key="p3-media-marcha",
        label="P3 · Operadora Media Marcha",
        stage="halfway",
        vendor_name="Operadora Media Marcha · Sandbox",
        vendor_rfc="OMM260103CC3",
        contact_name="Ana Sofía Beltrán",
        owner_email="p3.sandbox@checkwise.local",
        real_vendor_slug="angel-elias-garcia",
        onboarding_complete=True,
        scenario_note="A medio camino; mezcla de aprobado, pendiente y rechazos.",
    ),
    ProviderSeed(
        key="p4-casi-listo",
        label="P4 · Corporativo Casi Listo",
        stage="almost_done",
        vendor_name="Corporativo Casi Listo · Sandbox",
        vendor_rfc="CCL260104DD4",
        contact_name="Rodrigo Salas Vidal",
        owner_email="p4.sandbox@checkwise.local",
        real_vendor_slug="human-medical-humese",
        onboarding_complete=True,
        scenario_note="Casi completo; CSF próxima a vencer (renovación 90 días).",
    ),
    ProviderSeed(
        key="p5-total",
        label="P5 · Cumplimiento Total",
        stage="fully_compliant",
        vendor_name="Cumplimiento Total · Sandbox",
        vendor_rfc="CTO260105EE5",
        contact_name="Mariana Ferreira López",
        owner_email="p5.sandbox@checkwise.local",
        real_vendor_slug="master-clean-plus",
        onboarding_complete=True,
        scenario_note="Totalmente en regla; expediente y calendario al día.",
    ),
]
PROVIDERS_BY_KEY = {p.key: p for p in PROVIDERS}


# Instance key namespaces all deterministic ids. Empty string = the
# standalone Demo Sandbox client; in --attach-client-admin mode it's set to
# the target client_id so the seeded rows (vendors, workspaces, report, etc.)
# get their own id space and never collide with another tenant's sandbox.
_INSTANCE_KEY = ""


def _id(value: str) -> str:
    key = f"{_INSTANCE_KEY}:{value}" if _INSTANCE_KEY else value
    return str(uuid.uuid5(SCENARIO_NAMESPACE, key))


def _dt(days_ago: int) -> datetime:
    """A timezone-aware timestamp ``days_ago`` before the pinned TODAY noon."""
    base = datetime(TODAY.year, TODAY.month, TODAY.day, 12, 0, 0, tzinfo=utc_now().tzinfo)
    return base - timedelta(days=days_ago)


# ============================================================================
# ENVIRONMENT SAFETY
# ============================================================================

def _assert_env(*, confirm_prod: bool) -> None:
    if settings.is_local_env:
        return
    if not confirm_prod:
        raise SystemExit(
            f"CHECKWISE_ENV={settings.CHECKWISE_ENV!r}. Refusing to seed/teardown the "
            "demo sandbox outside local without --confirm-prod.\n"
            "  Before promoting to the prod test client, take a Neon snapshot first\n"
            "  (named pre-deploy sibling branch) so you have a clean rollback anchor."
        )
    parsed = urlparse(settings.sqlalchemy_url)
    host = (parsed.hostname or "").lower()
    print(f"  [!] Non-local seed authorised via --confirm-prod (db host: {host or '<unknown>'}).")
    print("  [!] Confirm you have a fresh Neon snapshot before continuing.")


# ============================================================================
# REAL-PDF SAMPLE SANDBOX
# ============================================================================

def _default_sample_docs_path() -> Path:
    # script: .../checkwise/CheckWise/apps/api/scripts/seed_demo_sandbox.py
    # sample-docs lives at the OUTER repo root: .../checkwise/_reference/sample-docs
    return Path(__file__).resolve().parents[4] / "_reference" / "sample-docs"


@dataclass
class SampleIndex:
    base: Path
    # (vendor_slug, institution_code) -> list of file entries
    by_vendor_institution: dict[tuple[str, str], list[dict]] = field(default_factory=dict)
    by_vendor: dict[str, list[dict]] = field(default_factory=dict)

    @classmethod
    def load(cls, base: Path) -> "SampleIndex":
        manifest_path = base / "manifest.json"
        if not manifest_path.is_file():
            raise SystemExit(
                f"Sample-docs manifest not found at {manifest_path}.\n"
                "  Pass --sample-docs-path /path/to/_reference/sample-docs, or build the\n"
                "  sandbox with scripts/reports/build_sample_sandbox.py first."
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        idx = cls(base=base)
        for entry in manifest.get("files", []):
            vslug = entry["vendor_slug"]
            inst = entry["institution_code"]
            idx.by_vendor_institution.setdefault((vslug, inst), []).append(entry)
            idx.by_vendor.setdefault(vslug, []).append(entry)
        return idx

    def pick(self, *, vendor_slug: str, institution_code: str, salt: str) -> dict:
        """Deterministically pick a real file for a vendor + institution.

        Falls back to any file for that vendor when the institution has no
        sample coverage (e.g. interno_cliente onboarding docs)."""
        candidates = self.by_vendor_institution.get((vendor_slug, institution_code))
        if not candidates:
            candidates = self.by_vendor.get(vendor_slug, [])
        if not candidates:
            raise SystemExit(f"No sample documents available for vendor {vendor_slug!r}.")
        digest = int(hashlib.sha256(salt.encode("utf-8")).hexdigest(), 16)
        return candidates[digest % len(candidates)]

    def read_bytes(self, entry: dict) -> bytes:
        return (self.base / entry["by_vendor_path"]).read_bytes()


# ============================================================================
# STORAGE
# ============================================================================

def _storage_backend():
    if settings.is_local_env:
        from app.services.storage import LocalStorageService

        return LocalStorageService()
    from app.services.storage import S3StorageService

    return S3StorageService()


class BlobUploader:
    """Uploads real PDF bytes once per content hash and hands back the key."""

    def __init__(self, backend) -> None:
        self._backend = backend
        self._seen: dict[str, str] = {}  # sha256 -> storage_key

    def put(self, data: bytes) -> tuple[str, str, int]:
        digest = hashlib.sha256(data).hexdigest()
        size = len(data)
        key = self._seen.get(digest)
        if key is None:
            key = f"{STORAGE_PREFIX}/_blobs/{digest}.pdf"
            self._backend.save_bytes(storage_key=key, data=data, content_type="application/pdf")
            self._seen[digest] = key
        return key, digest, size


# ============================================================================
# PERIODS
# ============================================================================

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
    year = int(period_key[:4]) if (period_key and period_key[:4].isdigit()) else None
    month = int(period_key.split("-M", 1)[1]) if (period_key and "-M" in period_key) else None
    row = Period(
        id=_id(f"period:{period_key or 'alta-inicial'}"),
        code=code,
        period_key=period_key,
        year=year,
        month=month,
        period_type=ptype,
    )
    db.add(row)
    db.flush()
    return row.id


# ============================================================================
# SUBMISSION GRAPH
# ============================================================================

_REVIEW_STATES = {
    DocumentStatus.PENDIENTE_REVISION.value,
    DocumentStatus.POSIBLE_MISMATCH.value,
    DocumentStatus.REQUIERE_ACLARACION.value,
    DocumentStatus.RECHAZADO.value,
}

_REVIEWER_ACTION = {
    DocumentStatus.APROBADO.value: "approve",
    DocumentStatus.RECHAZADO.value: "reject",
    DocumentStatus.REQUIERE_ACLARACION.value: "request_clarification",
    DocumentStatus.EXCEPCION_LEGAL.value: "mark_exception",
}


def _insert_submission(
    db,
    *,
    sample: SampleIndex,
    uploader: BlobUploader,
    provider: ProviderSeed,
    client_id: str,
    vendor_id: str,
    requirement_code: str,
    status_value: str,
    days_ago: int,
    period_key: str | None,
    reviewer_note: str | None = None,
    supersedes_submission_id: str | None = None,
    chain_suffix: str = "",
) -> str:
    """Insert one submission + its document/inspection/history/validation graph.

    Returns the submission id. Attaches a REAL sample PDF (by institution) as
    the stored blob. Status is written directly — no OCR/prevalidation runs.
    """
    requirement = db.scalar(select(Requirement).where(Requirement.code == requirement_code))
    if requirement is None:
        raise RuntimeError(f"Missing seeded requirement: {requirement_code} (run seed_catalog).")
    version = db.scalar(
        select(RequirementVersion)
        .where(RequirementVersion.requirement_id == requirement.id)
        .order_by(RequirementVersion.version.asc())
        .limit(1)
    )
    institution = db.get(Institution, requirement.institution_id)
    inst_code = institution.code if institution else "interno_cliente"
    period_id = _get_or_create_period(db, period_key=period_key)
    submitted_at = _dt(days_ago)

    slot_salt = f"{provider.key}:{requirement_code}:{period_key or 'onboarding'}{chain_suffix}"
    entry = sample.pick(vendor_slug=provider.real_vendor_slug, institution_code=inst_code, salt=slot_salt)
    storage_key, digest, size = uploader.put(sample.read_bytes(entry))

    submission = Submission(
        id=_id(f"submission:{slot_salt}"),
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
        submitted_by=provider.contact_name,
        supersedes_submission_id=supersedes_submission_id,
        created_at=submitted_at,
        updated_at=submitted_at,
    )
    db.add(submission)
    db.flush()

    document = Document(
        id=_id(f"document:{slot_salt}"),
        submission_id=submission.id,
        storage_key=storage_key,
        original_filename=entry["filename"],
        mime_type="application/pdf",
        size_bytes=size,
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
            id=_id(f"inspection:{slot_salt}"),
            document_id=document.id,
            is_pdf=True,
            is_corrupt=False,
            is_encrypted=False,
            page_count=1,
            text_char_count=1200,
            has_text=True,
            is_probably_scanned=False,
            detected_institution=inst_code,
            detected_document_type=requirement.name,
            detected_rfcs=[provider.vendor_rfc],
            detected_dates=[submitted_at.date().isoformat()],
            period_mentions=[period_key] if period_key else [],
            requirement_match_confidence=(
                0.93 if status_value == DocumentStatus.APROBADO.value else 0.62
            ),
            mismatch_reason=(
                "RFC del documento no coincide con el proveedor registrado."
                if status_value == DocumentStatus.POSIBLE_MISMATCH.value
                else None
            ),
            raw_metadata={"scenario": SCENARIO_TAG, "sample_source": entry["filename"]},
            created_at=submitted_at,
            updated_at=submitted_at,
        )
    )
    db.add(
        DocumentStatusHistory(
            id=_id(f"history:received:{slot_salt}"),
            submission_id=submission.id,
            document_id=document.id,
            from_status=None,
            to_status=DocumentStatus.RECIBIDO.value,
            reason="Documento recibido (escenario demo sandbox).",
            actor=f"provider:{provider.contact_name}",
            created_at=submitted_at,
        )
    )
    if status_value != DocumentStatus.RECIBIDO.value:
        db.add(
            DocumentStatusHistory(
                id=_id(f"history:state:{slot_salt}"),
                submission_id=submission.id,
                document_id=document.id,
                from_status=DocumentStatus.RECIBIDO.value,
                to_status=status_value,
                reason=reviewer_note,
                actor="system:demo_sandbox_seed",
                created_at=submitted_at + timedelta(minutes=5),
            )
        )

    is_mismatch = status_value == DocumentStatus.POSIBLE_MISMATCH.value
    db.add(
        Validation(
            id=_id(f"validation:{slot_salt}"),
            submission_id=submission.id,
            document_id=document.id,
            rule_code="demo_sandbox_fixture",
            rule_type="demo_seed",
            result="warning" if is_mismatch else "pass",
            severity="warning" if is_mismatch else "info",
            message="Fixture de demo sandbox; estatus asignado directamente.",
            requires_human_review=status_value in _REVIEW_STATES,
            created_at=submitted_at,
            updated_at=submitted_at,
        )
    )

    action = _REVIEWER_ACTION.get(status_value)
    if action and reviewer_note:
        db.add(
            ValidationEvent(
                id=_id(f"review:{slot_salt}"),
                submission_id=submission.id,
                document_id=document.id,
                event_type="reviewer_decision",
                rule_code="reviewer_decision",
                result=action,
                severity="info" if action == "approve" else "warning",
                message=reviewer_note,
                confidence=None,
                payload={
                    "scenario": SCENARIO_TAG,
                    "from_status": DocumentStatus.PENDIENTE_REVISION.value,
                    "to_status": status_value,
                },
                actor_type="reviewer",
                created_at=submitted_at + timedelta(hours=3),
            )
        )
    elif is_mismatch:
        db.add(
            ValidationEvent(
                id=_id(f"mismatch:{slot_salt}"),
                submission_id=submission.id,
                document_id=document.id,
                event_type="prevalidation",
                rule_code="demo_mismatch",
                result="warning",
                severity="warning",
                message=reviewer_note or "Posible mismatch: revisar RFC y periodo.",
                confidence=0.62,
                payload={"scenario": SCENARIO_TAG},
                actor_type="system",
                created_at=submitted_at + timedelta(minutes=6),
            )
        )

    return submission.id


# ============================================================================
# PER-STAGE PLANS
# ============================================================================

def _recurring_targets() -> list:
    """Recurring catalog items (moral) limited to the target period window."""
    return [
        item
        for item in recurring_for_year(2026, "moral")
        if item.period_key in TARGET_PERIOD_KEYS
    ]


def _days_ago_for_period(period_key: str | None) -> int:
    if not period_key:
        return 60
    # Periods outside the explicit window (e.g. later-2026 months a fully
    # compliant provider files ahead, or carryover) get a recent default so
    # their timestamps stay in the past.
    return _MONTH_DAYS_AGO.get(period_key, 7)


def _seed_onboarding(db, *, sample, uploader, provider, client_id, vendor_id) -> int:
    """Stage-specific onboarding expediente. Returns submissions inserted."""
    A = DocumentStatus.APROBADO.value
    PR = DocumentStatus.PENDIENTE_REVISION.value
    REJ = DocumentStatus.RECHAZADO.value

    def ins(code, status, days, note=None, **kw) -> str:
        return _insert_submission(
            db, sample=sample, uploader=uploader, provider=provider,
            client_id=client_id, vendor_id=vendor_id, requirement_code=code,
            status_value=status, days_ago=days, period_key=None, reviewer_note=note, **kw,
        )

    stage = provider.stage
    if stage == "invited":
        return 0

    if stage == "just_starting":
        ins("ONB-CONT-001", PR, 5)
        ins(CSF_CODE, PR, 3)
        return 2

    if stage == "halfway":
        ins("ONB-CONT-001", A, 58, "Contrato validado.")
        ins("ONB-CORP-M-001", A, 56, "Documentación corporativa validada.")
        ins(CSF_CODE, A, 50, "CSF vigente.")
        ins("ONB-PATR-001", A, 54, "Registro patronal validado.")
        # REPSE: rejected first, then a corrected re-upload that supersedes it.
        first = ins(
            "ONB-REPSE-001", REJ, 40,
            "El folio REPSE no corresponde a la razón social. Solicitar documento corregido.",
            chain_suffix=":v1",
        )
        ins(
            "ONB-REPSE-001", A, 35, "Registro REPSE corregido y validado.",
            supersedes_submission_id=first, chain_suffix=":v2",
        )
        return 6

    if stage == "almost_done":
        ins("ONB-CONT-001", A, 116, "Contrato validado.")
        ins("ONB-CORP-M-001", A, 114, "Documentación corporativa validada.")
        # CSF approved 76 days ago → next renewal (90d) due in ~14 days.
        ins(CSF_CODE, A, 76, "CSF vigente (renovación próxima).")
        ins("ONB-REPSE-001", A, 112, "Registro REPSE vigente.")
        ins("ONB-PATR-001", A, 110, "Registro patronal validado.")
        return 5

    # fully_compliant
    ins("ONB-CONT-001", A, 146, "Contrato validado.")
    ins("ONB-CORP-M-001", A, 144, "Documentación corporativa validada.")
    ins(CSF_CODE, A, 20, "CSF reciente y vigente.")
    ins("ONB-REPSE-001", A, 142, "Registro REPSE vigente.")
    ins("ONB-PATR-001", A, 140, "Registro patronal validado.")
    return 5


def _seed_recurring(db, *, sample, uploader, provider, client_id, vendor_id) -> int:
    A = DocumentStatus.APROBADO.value
    PR = DocumentStatus.PENDIENTE_REVISION.value
    MM = DocumentStatus.POSIBLE_MISMATCH.value

    stage = provider.stage
    if stage in {"invited", "just_starting"}:
        return 0

    # "Almost done" and "fully compliant" file the WHOLE 2026 calendar so the
    # portfolio semáforo (which scores the full annual catalog) reads green —
    # matches the precedent set by the user-testing green provider. "Halfway"
    # only covers the recent ~6-month window so it stays visibly mid-journey.
    items = recurring_for_year(2026, "moral") if stage in {"almost_done", "fully_compliant"} else _recurring_targets()

    count = 0
    for item in items:
        period = item.period_key
        days = _days_ago_for_period(period)

        if stage == "halfway":
            # Older months approved; recent months still in review; one IMSS
            # March item flagged as a possible mismatch (this is the at-risk one).
            if period in {"2026-M04", "2026-M05"}:
                status, note = PR, None
            else:
                status, note = A, "Documento aprobado."
            if item.institution == "imss" and period == "2026-M03":
                status, note = MM, "RFC del comprobante no coincide con el proveedor."
        else:
            # almost_done + fully_compliant → everything approved & current.
            status, note = A, "Documento aprobado."

        _insert_submission(
            db, sample=sample, uploader=uploader, provider=provider,
            client_id=client_id, vendor_id=vendor_id, requirement_code=item.code,
            status_value=status, days_ago=days, period_key=period, reviewer_note=note,
        )
        count += 1
    return count


def _seed_renewal_signal(db, *, provider, client_id, vendor_id, workspace_id) -> None:
    """P4 only: CSF renewal due ~14 days out → reminders + notifications."""
    anchor = TODAY - timedelta(days=76)          # CSF approval day
    due = anchor + timedelta(days=CSF_RENEWAL_DAYS)  # ~2026-06-17 → ~14 days out
    days_to_due = (due - TODAY).days

    # Thresholds already crossed for a due date ~14 days away: 30 and 14.
    for threshold in (30, 14):
        db.add(
            RenewalReminder(
                id=_id(f"renewal:{provider.key}:{CSF_CODE}:{threshold}"),
                workspace_id=workspace_id,
                requirement_code=CSF_CODE,
                cycle_anchor_date=anchor,
                threshold_days=threshold,
                severity="yellow",
                created_at=_dt(threshold - days_to_due if threshold > days_to_due else 0),
            )
        )

    title = "CSF próxima a vencer · Corporativo Casi Listo"
    body = (
        f"La Constancia de Situación Fiscal vence el {due.isoformat()} "
        f"(~{days_to_due} días). La CSF debe renovarse cada {CSF_RENEWAL_DAYS} días."
    )
    db.add(
        ClientNotification(
            id=_id(f"client-notif:renewal:{provider.key}"),
            client_id=client_id,
            vendor_id=vendor_id,
            submission_id=_id(f"submission:{provider.key}:{CSF_CODE}:onboarding"),
            notification_type="renewal_due_soon",
            title=title,
            body=body,
            # Renewals deep-link to the calendar (the future obligation lives
            # there), matching the live emitter routing (2nd-review note 5.x).
            action_url=f"/client/calendar?vendor_id={vendor_id}",
            payload={"scenario": SCENARIO_TAG, "requirement_code": CSF_CODE, "due_on": due.isoformat()},
            severity="yellow",
            category="renewal",
            created_at=_dt(1),
        )
    )
    db.add(
        ProviderNotification(
            id=_id(f"provider-notif:renewal:{provider.key}"),
            workspace_id=workspace_id,
            submission_id=_id(f"submission:{provider.key}:{CSF_CODE}:onboarding"),
            notification_type="renewal_due_soon",
            severity="warning",
            category="renewal",
            title="Renueva tu Constancia de Situación Fiscal",
            body=body,
            action_url="/portal/dashboard",
            payload={"scenario": SCENARIO_TAG, "requirement_code": CSF_CODE, "due_on": due.isoformat()},
            created_at=_dt(1),
        )
    )


# ============================================================================
# USERS / ORG / CLIENT / VENDORS
# ============================================================================

def _seed_client_and_admin(db) -> tuple[str, str]:
    admin = User(
        id=_id(f"user:{ADMIN_EMAIL}"),
        email=ADMIN_EMAIL,
        password_hash=hash_password(ADMIN_PASSWORD),
        full_name=ADMIN_FULLNAME,
        status="active",
        must_change_password=False,
    )
    db.add(admin)
    db.flush()

    client = Client(
        id=_id("client"),
        name=CLIENT_NAME,
        rfc=CLIENT_RFC,
        email=ADMIN_EMAIL,
        responsible_name=ADMIN_FULLNAME,
        industry="Servicios corporativos",
        fiscal_address="Domicilio de demostración (sin validez fiscal)",
        phone="+52 55 1234 5678",
        notes=f"{SCENARIO_TAG}: cliente de demostración con 5 proveedores escalonados.",
        onboarding_completed_at=utc_now(),
        status="active",
    )
    db.add(client)
    db.flush()

    org = Organization(
        id=_id("client-org"),
        name=CLIENT_ORG_NAME,
        kind="client",
        client_id=client.id,
        status="active",
    )
    db.add(org)
    db.flush()
    db.add(
        Membership(
            id=_id("membership:admin"),
            user_id=admin.id,
            organization_id=org.id,
            role="client_admin",
            status="active",
        )
    )
    db.flush()
    return client.id, org.id


def _seed_provider_rows(db, *, client_id: str) -> dict[str, str]:
    """Vendor + ProviderWorkspace per provider. Returns {key: vendor_id}.

    ``owner_user_id`` is left NULL on purpose: these workspaces have no portal
    user, and workspace ownership shadows org membership in report listing —
    leaving them unowned keeps the client_admin's reports visible.
    """
    vendor_ids: dict[str, str] = {}
    for provider in PROVIDERS:
        vendor = Vendor(
            id=_id(f"vendor:{provider.key}"),
            client_id=client_id,
            name=provider.vendor_name,
            rfc=provider.vendor_rfc,
            contact_name=provider.contact_name,
            contact_email=provider.owner_email,
            contact_phone="+52 55 0000 0000",
            repse_id=f"REPSE-DEMO-{provider.key.upper()}",
            persona_type="moral",
            status="active",
        )
        db.add(vendor)
        db.flush()

        complete_at = _dt(120) if provider.onboarding_complete else None
        db.add(
            ProviderWorkspace(
                id=_id(f"workspace:{provider.key}"),
                client_id=client_id,
                vendor_id=vendor.id,
                owner_user_id=None,
                filial_name="Filial principal",
                persona_type="moral",
                display_name=provider.vendor_name,
                access_token=_id(f"token:{provider.key}"),
                onboarding_completed_at=complete_at,
                profile_confirmed_at=complete_at,
                legal_consent_accepted_at=complete_at,
                legal_consent_version="v1" if provider.onboarding_complete else None,
                status="active",
            )
        )
        db.flush()
        vendor_ids[provider.key] = vendor.id
    return vendor_ids


# ============================================================================
# PRE-SEEDED REPORT (client-facing)
# ============================================================================

def _compute_report_stats(db, *, client_id: str) -> dict:
    """Live aggregates so the seeded report's numbers match the data."""
    from sqlalchemy import func

    vendors_total = db.scalar(
        select(func.count(func.distinct(Vendor.id))).where(Vendor.client_id == client_id)
    ) or 0
    at_risk = db.scalar(
        select(func.count(func.distinct(Submission.vendor_id))).where(
            Submission.client_id == client_id,
            Submission.status.in_(["posible_mismatch", "requiere_aclaracion", "rechazado", "vencido"]),
        )
    ) or 0
    in_review = db.scalar(
        select(func.count(Submission.id)).where(
            Submission.client_id == client_id,
            Submission.status == DocumentStatus.PENDIENTE_REVISION.value,
        )
    ) or 0
    # "Green" = a vendor that has submissions and every one is approved.
    green = 0
    for v in db.scalars(select(Vendor.id).where(Vendor.client_id == client_id)):
        statuses = set(
            db.scalars(select(Submission.status).where(Submission.vendor_id == v))
        )
        if statuses and statuses == {DocumentStatus.APROBADO.value}:
            green += 1
    return {
        "vendors_total": int(vendors_total),
        "at_risk": int(at_risk),
        "in_review": int(in_review),
        "green": green,
        "renewals_due": 1,  # P4 CSF
    }


def _portfolio_deadlines_data(db, *, vendor_ids: dict[str, str]) -> dict:
    """A portfolio-level upcoming_deadlines payload.

    The stock ``upcoming_deadlines`` fetcher is vendor-scoped (returns empty
    at client scope) and reads the recurring calendar only. For the client
    report we merge every vendor's upcoming calendar deadlines and inject the
    P4 CSF renewal (an onboarding-renewal the calendar fetcher doesn't carry),
    so the block surfaces the real cross-portfolio urgency incl. the renewal.
    The output shape matches what ``upcoming-deadlines.tsx`` consumes."""
    from app.services.dashboard_compute import (
        build_upcoming_deadlines_for_vendor,
        bucket_upcoming_by_urgency,
    )

    items: list[dict] = []
    for key, vid in vendor_ids.items():
        short = PROVIDERS_BY_KEY[key].vendor_name.replace(" · Sandbox", "")
        payload = build_upcoming_deadlines_for_vendor(db, vendor_id=vid, top=12)
        # Cap to the 2 soonest per vendor so the portfolio list shows variety
        # across providers instead of one vendor's many same-day obligations.
        per_vendor = sorted(
            payload.get("items", []),
            key=lambda it: (it.get("due_in_days") is None, it.get("due_in_days") or 0),
        )[:2]
        for it in per_vendor:
            it = dict(it)
            it["title"] = f"{short} · {it.get('title', '')}"
            items.append(it)

    # Inject P4's CSF renewal (due ~14 days out).
    due = TODAY + timedelta(days=14)
    items.append({
        "id": "renewal-csf-p4-casi-listo",
        "title": "Corporativo Casi Listo · Renovación CSF",
        "institution": "sat",
        "period_key": None,
        "due_month": f"{due.year:04d}-{due.month:02d}",
        "due_in_days": (due - TODAY).days,
        "state": "approved",
        "href": "/client/vendors",
        "requirement_code": CSF_CODE,
    })

    items = [i for i in items if i.get("due_in_days") is not None]
    items.sort(key=lambda i: i["due_in_days"])
    items = items[:8]
    return {
        "items": items,
        "urgency_buckets": bucket_upcoming_by_urgency(items),
        "workspace_id": None,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "as_of": TODAY.isoformat(),
        "filter_applied": {},
        "top": 8,
        "total_before_filter": len(items),
    }


def _seed_report(
    db, *, org_id: str, client_id: str, admin_user_id: str,
    vendor_ids: dict[str, str], stats: dict,
) -> None:
    """Pre-seed one client_facing report using the CANONICAL template layout.

    Builds the exact ``client-monthly-executive`` template via the shared
    deterministic layout registry (``build_deterministic_blocks``) — the same
    code path the product's pick-template → generate flow uses as its
    fallback. Keeping the seeded demo on the registry means the demo report
    and the real template can never drift."""
    from app.constants.reports import ReportAudience
    from app.services.reports.context import ReportScope
    from app.services.reports.deterministic_layouts import build_deterministic_blocks

    scope = ReportScope(
        organization_id=org_id,
        audience=ReportAudience.CLIENT_FACING,
        client_id=client_id,
        vendor_id=None,
        period=None,
    )
    blocks = build_deterministic_blocks(
        db, preset_id="client-monthly-executive", scope=scope
    )
    client_row = db.get(Client, client_id)
    client_label = client_row.name if client_row else "Demo Sandbox"

    report = Report(
        id=_id("report:portfolio"),
        organization_id=org_id,
        client_id=client_id,
        vendor_id=None,
        title=f"Resumen ejecutivo mensual · {client_label} · Jun 2026",
        description="Plantilla 'Resumen ejecutivo mensual': panorama del portafolio — cumplimiento global, por institución, radar, matriz de riesgo y recomendaciones.",
        audience="client_facing",
        status="active",
        created_by_user_id=admin_user_id,
    )
    db.add(report)
    db.flush()

    version_id = _id("report-version:portfolio")
    db.add(
        ReportVersion(
            id=version_id,
            report_id=report.id,
            version_number=1,
            parent_version_id=None,
            label="Versión inicial · demo sandbox",
            content_json={"blocks": blocks, "audience": "client_facing"},
            plan_json={
                "blocks": [{"id": b["id"], "type": b["type"], "config": b["config"]} for b in blocks],
                "rationale": "Reporte demo sembrado para el cliente sandbox.",
                "scope_hint": "Portafolio de 5 proveedores escalonados.",
            },
            generated_by="ai",
            source_snapshot_id=None,
            llm_metadata=None,
            created_by_user_id=admin_user_id,
        )
    )
    db.flush()
    report.current_version_id = version_id
    db.flush()


# ============================================================================
# WIPE / TEARDOWN
# ============================================================================

def _scenario_storage_keys(db, client_id: str) -> set[str]:
    sub_ids = set(db.scalars(select(Submission.id).where(Submission.client_id == client_id)))
    if not sub_ids:
        return set()
    return set(
        db.scalars(select(Document.storage_key).where(Document.submission_id.in_(sub_ids)))
    )


def _wipe(db, *, backend) -> int:
    """Delete everything this seeder created (DB rows + storage blobs).

    Idempotent: a no-op when nothing has been seeded. Order respects FKs.
    """
    client = db.scalar(select(Client).where(Client.name == CLIENT_NAME))
    deleted_blobs = 0

    workspace_ids = {p_id for p_id in (
        db.scalars(
            select(ProviderWorkspace.id).where(
                ProviderWorkspace.id.in_([_id(f"workspace:{p.key}") for p in PROVIDERS])
            )
        )
    )}

    if client is not None:
        # Collect + delete storage blobs before the rows that reference them.
        for key in _scenario_storage_keys(db, client.id):
            backend.delete(key)
            deleted_blobs += 1

        vendor_ids = set(db.scalars(select(Vendor.id).where(Vendor.client_id == client.id)))
        sub_ids = set(db.scalars(select(Submission.id).where(Submission.client_id == client.id)))
        doc_ids = set(
            db.scalars(select(Document.id).where(Document.submission_id.in_(sub_ids)))
        ) if sub_ids else set()

        if workspace_ids:
            db.query(WiseEvent).filter(WiseEvent.workspace_id.in_(workspace_ids)).delete(
                synchronize_session=False
            )
            db.query(RenewalReminder).filter(
                RenewalReminder.workspace_id.in_(workspace_ids)
            ).delete(synchronize_session=False)
            db.query(ProviderNotification).filter(
                ProviderNotification.workspace_id.in_(workspace_ids)
            ).delete(synchronize_session=False)
        db.query(ClientNotification).filter(
            ClientNotification.client_id == client.id
        ).delete(synchronize_session=False)

        if sub_ids:
            db.query(ValidationEvent).filter(ValidationEvent.submission_id.in_(sub_ids)).delete(
                synchronize_session=False
            )
            db.query(Validation).filter(Validation.submission_id.in_(sub_ids)).delete(
                synchronize_session=False
            )
        if doc_ids:
            db.query(DocumentInspection).filter(
                DocumentInspection.document_id.in_(doc_ids)
            ).delete(synchronize_session=False)
            db.query(DocumentStatusHistory).filter(
                DocumentStatusHistory.document_id.in_(doc_ids)
            ).delete(synchronize_session=False)
        if sub_ids:
            db.query(Document).filter(Document.submission_id.in_(sub_ids)).delete(
                synchronize_session=False
            )
            db.query(Submission).filter(Submission.id.in_(sub_ids)).delete(
                synchronize_session=False
            )
        # ComplianceSnapshot rows (created when a report is generated) FK back
        # to client AND vendor — drop them before the vendors they reference.
        db.query(ComplianceSnapshot).filter(
            ComplianceSnapshot.client_id == client.id
        ).delete(synchronize_session=False)
        if workspace_ids:
            db.query(ProviderWorkspace).filter(
                ProviderWorkspace.id.in_(workspace_ids)
            ).delete(synchronize_session=False)
        if vendor_ids:
            db.query(Vendor).filter(Vendor.id.in_(vendor_ids)).delete(synchronize_session=False)
        db.flush()

    org = db.scalar(select(Organization).where(Organization.name == CLIENT_ORG_NAME))
    if org is not None:
        report_ids = set(db.scalars(select(Report.id).where(Report.organization_id == org.id)))
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
            db.query(Report).filter(Report.id.in_(report_ids)).delete(synchronize_session=False)
        db.query(ComplianceSnapshot).filter(
            ComplianceSnapshot.organization_id == org.id
        ).delete(synchronize_session=False)
        db.query(Membership).filter(Membership.organization_id == org.id).delete(
            synchronize_session=False
        )
        db.delete(org)
        # Force the org DELETE to emit before the client DELETE below.
        # Organization.client_id is a FK column with no ORM relationship, so
        # the unit-of-work can't infer the ordering on its own.
        db.flush()

    db.query(Period).filter(Period.code.like(f"{SCENARIO_TAG}-%")).delete(
        synchronize_session=False
    )

    admin = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
    if admin is not None:
        db.query(Membership).filter(Membership.user_id == admin.id).delete(
            synchronize_session=False
        )
        db.delete(admin)

    if client is not None:
        db.delete(client)

    db.flush()
    return deleted_blobs


# ============================================================================
# ORCHESTRATION
# ============================================================================

# ============================================================================
# ATTACH MODE — seed the ladder into an EXISTING client (e.g. Rebe's)
# ============================================================================

def _resolve_attach_target(db, admin_email: str) -> tuple[str, str, str]:
    """Resolve (client_id, org_id, admin_user_id) for an existing client by
    its client_admin's email. Looks up via users → memberships →
    organizations → clients (never by name, which drifts). Raises if the
    email isn't an active client_admin of a client-kind org."""
    user = db.scalar(select(User).where(User.email == admin_email))
    if user is None:
        raise SystemExit(f"No user found with email {admin_email!r}.")
    org = db.scalar(
        select(Organization)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(
            Membership.user_id == user.id,
            Membership.role == "client_admin",
            Membership.status == "active",
            Organization.kind == "client",
            Organization.client_id.isnot(None),
        )
        .limit(1)
    )
    if org is None:
        raise SystemExit(
            f"{admin_email!r} is not an active client_admin of any client org."
        )
    return org.client_id, org.id, user.id


def _wipe_attach(db, *, backend) -> int:
    """Remove ONLY the sandbox rows this seeder created (by deterministic id),
    leaving the host client / org / user / real vendors / shared periods
    untouched. Safe to run against a real client. Requires ``_INSTANCE_KEY``
    to already be set to the target client_id so the ids resolve."""
    vendor_ids = [_id(f"vendor:{p.key}") for p in PROVIDERS]
    workspace_ids = [_id(f"workspace:{p.key}") for p in PROVIDERS]
    report_id = _id("report:portfolio")

    deleted_blobs = 0
    sub_ids = set(db.scalars(select(Submission.id).where(Submission.vendor_id.in_(vendor_ids))))
    doc_ids = set(
        db.scalars(select(Document.id).where(Document.submission_id.in_(sub_ids)))
    ) if sub_ids else set()

    if sub_ids:
        for key in db.scalars(
            select(Document.storage_key).where(Document.submission_id.in_(sub_ids))
        ):
            backend.delete(key)
            deleted_blobs += 1

    rep = db.get(Report, report_id)
    if rep is not None:
        rep.current_version_id = None
        db.flush()
        db.query(ReportConversation).filter(ReportConversation.report_id == report_id).delete(
            synchronize_session=False
        )
        db.query(ReportExport).filter(ReportExport.report_id == report_id).delete(
            synchronize_session=False
        )
        db.query(ReportShare).filter(ReportShare.report_id == report_id).delete(
            synchronize_session=False
        )
        db.query(ReportVersion).filter(ReportVersion.report_id == report_id).delete(
            synchronize_session=False
        )
        db.delete(rep)
    db.query(ComplianceSnapshot).filter(
        ComplianceSnapshot.vendor_id.in_(vendor_ids)
    ).delete(synchronize_session=False)

    db.query(WiseEvent).filter(WiseEvent.workspace_id.in_(workspace_ids)).delete(
        synchronize_session=False
    )
    db.query(RenewalReminder).filter(RenewalReminder.workspace_id.in_(workspace_ids)).delete(
        synchronize_session=False
    )
    db.query(ProviderNotification).filter(
        ProviderNotification.workspace_id.in_(workspace_ids)
    ).delete(synchronize_session=False)
    db.query(ClientNotification).filter(
        ClientNotification.vendor_id.in_(vendor_ids)
    ).delete(synchronize_session=False)

    if sub_ids:
        db.query(ValidationEvent).filter(ValidationEvent.submission_id.in_(sub_ids)).delete(
            synchronize_session=False
        )
        db.query(Validation).filter(Validation.submission_id.in_(sub_ids)).delete(
            synchronize_session=False
        )
    if doc_ids:
        db.query(DocumentInspection).filter(DocumentInspection.document_id.in_(doc_ids)).delete(
            synchronize_session=False
        )
        db.query(DocumentStatusHistory).filter(
            DocumentStatusHistory.document_id.in_(doc_ids)
        ).delete(synchronize_session=False)
    if sub_ids:
        db.query(Document).filter(Document.submission_id.in_(sub_ids)).delete(
            synchronize_session=False
        )
        db.query(Submission).filter(Submission.id.in_(sub_ids)).delete(
            synchronize_session=False
        )
    db.query(ProviderWorkspace).filter(ProviderWorkspace.id.in_(workspace_ids)).delete(
        synchronize_session=False
    )
    db.query(Vendor).filter(Vendor.id.in_(vendor_ids)).delete(synchronize_session=False)
    db.flush()
    return deleted_blobs


def _apply(db, *, sample: SampleIndex, backend, attach_admin_email: str | None = None) -> dict:
    global _INSTANCE_KEY
    if attach_admin_email:
        client_id, org_id, admin_user_id = _resolve_attach_target(db, attach_admin_email)
        _INSTANCE_KEY = client_id  # namespace ids to the target client
        _wipe_attach(db, backend=backend)
        seed_catalog(db, years=(2026,))
    else:
        _INSTANCE_KEY = ""
        _wipe(db, backend=backend)
        seed_catalog(db, years=(2026,))
        client_id, org_id = _seed_client_and_admin(db)
        admin_user_id = _id(f"user:{ADMIN_EMAIL}")

    vendor_ids = _seed_provider_rows(db, client_id=client_id)

    uploader = BlobUploader(backend)
    onboarding_total = 0
    recurring_total = 0
    for provider in PROVIDERS:
        vendor_id = vendor_ids[provider.key]
        onboarding_total += _seed_onboarding(
            db, sample=sample, uploader=uploader, provider=provider,
            client_id=client_id, vendor_id=vendor_id,
        )
        recurring_total += _seed_recurring(
            db, sample=sample, uploader=uploader, provider=provider,
            client_id=client_id, vendor_id=vendor_id,
        )
        if provider.stage == "almost_done":
            _seed_renewal_signal(
                db, provider=provider, client_id=client_id, vendor_id=vendor_id,
                workspace_id=_id(f"workspace:{provider.key}"),
            )

    _seed_report(db, org_id=org_id, client_id=client_id, admin_user_id=admin_user_id,
                 vendor_ids=vendor_ids, stats={})

    add_audit_event(
        db,
        action="demo_sandbox.scenario_seeded",
        entity_type="client",
        entity_id=client_id,
        actor_type="system",
        actor_id=None,
        metadata={
            "scenario": SCENARIO_TAG,
            "providers": [p.label for p in PROVIDERS],
            "onboarding_submissions": onboarding_total,
            "recurring_submissions": recurring_total,
            "blobs_uploaded": len(uploader._seen),
        },
    )
    db.commit()
    return {
        "client_id": client_id,
        "org_id": org_id,
        "onboarding": onboarding_total,
        "recurring": recurring_total,
        "blobs": len(uploader._seen),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the CheckWise demo sandbox (5-provider ladder).")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true", help="Wipe + reseed the demo sandbox.")
    mode.add_argument("--teardown", action="store_true", help="Delete the demo sandbox (DB + storage).")
    parser.add_argument("--confirm-prod", action="store_true",
                        help="Required to run when CHECKWISE_ENV != 'local'.")
    parser.add_argument("--sample-docs-path", default=None,
                        help="Path to _reference/sample-docs (defaults to repo root).")
    parser.add_argument(
        "--attach-client-admin", default=None, metavar="EMAIL",
        help="Attach the 5-provider ladder + report to the EXISTING client "
             "owned by this client_admin email (e.g. rebeca100901@gmail.com), "
             "instead of creating the standalone Demo Sandbox client. Teardown "
             "removes only the seeded rows, never the host client's real data.",
    )
    args = parser.parse_args()

    _assert_env(confirm_prod=args.confirm_prod)
    backend = _storage_backend()

    print(f"CHECKWISE_ENV={settings.CHECKWISE_ENV}  STORAGE_BUCKET={settings.STORAGE_BUCKET}")
    if args.attach_client_admin:
        print(f"Attach mode → existing client of {args.attach_client_admin}")

    if args.teardown:
        global _INSTANCE_KEY
        with SessionLocal() as db:
            if args.attach_client_admin:
                client_id, _org, _u = _resolve_attach_target(db, args.attach_client_admin)
                _INSTANCE_KEY = client_id
                blobs = _wipe_attach(db, backend=backend)
            else:
                blobs = _wipe(db, backend=backend)
            db.commit()
        print(f"Demo sandbox removed. Deleted {blobs} storage blob(s).")
        return

    sample_path = Path(args.sample_docs_path) if args.sample_docs_path else _default_sample_docs_path()
    sample = SampleIndex.load(sample_path)
    print(f"Sample docs: {sample_path}")

    with SessionLocal() as db:
        result = _apply(
            db, sample=sample, backend=backend,
            attach_admin_email=args.attach_client_admin,
        )

    print("")
    print("Demo sandbox ready.")
    if args.attach_client_admin:
        print(f"  Attached  → existing client (id {result['client_id']})")
        print(f"  Login     {args.attach_client_admin}  (the host client_admin, unchanged)")
    else:
        print(f"  Client    {CLIENT_NAME}  (id {result['client_id']})")
        print(f"  Login     {ADMIN_EMAIL} / {ADMIN_PASSWORD}   (client_admin)")
    print(f"  Seeded    {result['onboarding']} onboarding + {result['recurring']} recurring "
          f"submissions across {len(PROVIDERS)} providers; {result['blobs']} unique PDF blob(s).")
    print(f"  Report    1 client-facing report pre-seeded → /client/reports")
    print("")
    print("  Provider ladder:")
    for p in PROVIDERS:
        print(f"    {p.label:<34} {p.scenario_note}")
    print("")
    print("  Next: log in as the client_admin above and generate a report scoped to")
    print(f"  '{CLIENT_NAME}'. The five providers give it a full risk spectrum.")


if __name__ == "__main__":
    main()
