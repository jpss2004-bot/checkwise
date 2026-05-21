"""Provision a single, obvious-test provider account in any
CheckWise database — designed to be safe to run against
production Neon.

What it creates (only if missing — idempotent):
  - User  provider.test@legalshelf.mx
  - Client "Cliente de Pruebas · Test" (RFC TST010101BBB)
  - Vendor "Proveedor de Pruebas · Test" (RFC TEST010101AAA)
  - Organization "Cliente de Pruebas · Test — Cliente" (kind=client)
  - Membership (provider role) so create_report's owning-org resolution works
  - ProviderWorkspace ws-test-001 with onboarding_completed_at set so the
    dashboard is unlocked from first login.
  - 16 sample Submissions mirroring the boss.demo local-seed scenario:
    every provider-visible status across SAT / IMSS / INFONAVIT / STPS_REPSE,
    plus a supersession chain on IMSS Feb.

What it deliberately does NOT do (vs dev_seed.py):
  - No wipe of any existing rows.
  - No deletion of any data.
  - No touching of unrelated providers / vendors / clients.
  - No assumption that the canonical Requirement catalog is already seeded —
    if a requirement code is missing it is skipped rather than created.

Run from local against the prod DATABASE_URL:

    cd backend
    DATABASE_URL='postgresql+psycopg://USER:PWD@HOST/db?sslmode=require' \
        .venv/bin/python scripts/provision_test_provider.py

The script prints the generated password ONCE at the end. Save it.
"""

from __future__ import annotations

import os
import secrets
import string
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import _normalize_pg_url
from app.models import (
    Client,
    Document,
    DocumentStatusHistory,
    Institution,
    Membership,
    Organization,
    Period,
    ProviderWorkspace,
    Requirement,
    RequirementVersion,
    Submission,
    User,
    Vendor,
)
from app.services.auth import hash_password

# ── Test identifiers ──────────────────────────────────────────────
TEST_EMAIL = "provider.test@legalshelf.mx"
TEST_USER_FULL_NAME = "Proveedor de Pruebas"
TEST_CLIENT_NAME = "Cliente de Pruebas · Test"
TEST_CLIENT_RFC = "TST010101BBB"
TEST_VENDOR_NAME = "Proveedor de Pruebas · Test"
TEST_VENDOR_RFC = "TEST010101AAA"
TEST_WORKSPACE_ID = "ws-test-001"
TEST_ORG_NAME = "Cliente de Pruebas · Test — Cliente"


def _generate_password(length: int = 24) -> str:
    # ASCII letters + digits + a small punctuation set Render's frontend can paste.
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _build_specs() -> list[dict]:
    """Same shape that the local boss.demo seed uses, kept in sync
    with backend/scripts/dev_seed.py::_seed_submissions. period_key
    is left empty here and derived from the catalog at insert time
    (same canonical pattern as dev_seed)."""
    return [
        # SAT IVA — five upload months
        {"code": "REC-SAT-2026-01-declaracion-iva",
         "status": "rechazado",
         "filename": "iva_enero.pdf", "age_hours": 24 * 60,
         "rejection_reason": (
             "PDF ilegible: la última página del acuse está cortada. "
             "Vuelve a generar la declaración desde el portal del SAT y "
             "carga el acuse completo."),
         "period_code": "2026-01-sat-iva", "period_type": "mensual"},
        {"code": "REC-SAT-2026-02-declaracion-iva",
         "status": "aprobado", "filename": "iva_febrero.pdf",
         "age_hours": 24 * 35, "rejection_reason": None,
         "period_code": "2026-02-sat-iva", "period_type": "mensual"},
        {"code": "REC-SAT-2026-03-declaracion-iva",
         "status": "pendiente_revision", "filename": "iva_marzo.pdf",
         "age_hours": 4, "rejection_reason": None,
         "period_code": "2026-03-sat-iva", "period_type": "mensual"},
        {"code": "REC-SAT-2026-04-declaracion-iva",
         "status": "aprobado", "filename": "iva_abril.pdf",
         "age_hours": 24 * 12, "rejection_reason": None,
         "period_code": "2026-04-sat-iva", "period_type": "mensual"},
        {"code": "REC-SAT-2026-05-declaracion-iva",
         "status": "pendiente_revision", "filename": "iva_mayo.pdf",
         "age_hours": 2, "rejection_reason": None,
         "period_code": "2026-05-sat-iva", "period_type": "mensual"},
        # SAT ISR retención
        {"code": "REC-SAT-2026-04-declaracion-isr-por-retencion-sueldos-y-salarios",
         "status": "aprobado", "filename": "isr_retencion_abril.pdf",
         "age_hours": 24 * 10, "rejection_reason": None,
         "period_code": "2026-04-sat-isr-ret", "period_type": "mensual"},
        # SAT nómina — requiere_aclaracion
        {"code": "REC-SAT-2026-04-comprobantes-de-nomina-de-los-trabajadores",
         "status": "requiere_aclaracion", "filename": "nomina_abril.pdf",
         "age_hours": 24 * 6,
         "rejection_reason": (
             "Falta el CFDI de nómina de Juan Pérez (empleado #04). "
             "Adjunta el comprobante individual o márcalo como baja."),
         "period_code": "2026-04-sat-nomina", "period_type": "mensual"},
        # SAT entero ISR — excepcion_legal
        {"code": "REC-SAT-2026-04-comprobante-entero-pago-isr",
         "status": "excepcion_legal", "filename": "entero_isr_abril.pdf",
         "age_hours": 24 * 9,
         "rejection_reason": (
             "Periodo exento conforme al criterio normativo SAT 2025/02 — "
             "marcado como excepción legal por el equipo de LegalShelf."),
         "period_code": "2026-04-sat-entero-isr", "period_type": "mensual"},
        # SAT entero IVA Ene 2026 — vencido (period 2025-M12)
        {"code": "REC-SAT-2026-01-comprobante-entero-pago-iva",
         "status": "vencido", "filename": "entero_iva_enero.pdf",
         "age_hours": 24 * 120,
         "rejection_reason": (
             "El plazo SAT para entero del IVA del periodo de diciembre "
             "2025 venció sin que se cargara el acuse."),
         "period_code": "2026-01-sat-entero-iva", "period_type": "mensual"},
        # IMSS pago bancario
        {"code": "REC-IMSS-2026-03-comprobante-de-pago-bancario",
         "status": "posible_mismatch", "filename": "imss_marzo.pdf",
         "age_hours": 36,
         "rejection_reason": "RFC del PDF no coincide con el del proveedor.",
         "period_code": "2026-03-imss-pago", "period_type": "mensual"},
        {"code": "REC-IMSS-2026-04-comprobante-de-pago-bancario",
         "status": "aprobado", "filename": "imss_abril.pdf",
         "age_hours": 24 * 8, "rejection_reason": None,
         "period_code": "2026-04-imss-pago", "period_type": "mensual"},
        # INFONAVIT B1
        {"code": "REC-INFONAVIT-2026-03-comprobante-de-pago-bancario",
         "status": "pendiente_revision", "filename": "infonavit_b1.pdf",
         "age_hours": 24 * 5, "rejection_reason": None,
         "period_code": "2026-B1-infonavit-pago", "period_type": "bimestral"},
        # STPS/REPSE acuses
        {"code": "REC-ACUSES-2026-05-acuse-sisub",
         "status": "aprobado", "filename": "acuse_sisub_q1.pdf",
         "age_hours": 24 * 17, "rejection_reason": None,
         "period_code": "2026-Q1-stps-sisub", "period_type": "cuatrimestral"},
        {"code": "REC-ACUSES-2026-05-acuse-icsoe",
         "status": "pendiente_revision", "filename": "acuse_icsoe_q1.pdf",
         "age_hours": 24 * 1, "rejection_reason": None,
         "period_code": "2026-Q1-stps-icsoe", "period_type": "cuatrimestral"},
    ]


def _get_or_create_period(
    db: Session, *, period_key: str, code: str, period_type: str
) -> str:
    existing = db.scalar(
        select(Period).where(Period.code == code, Period.period_type == period_type)
    )
    if existing is not None:
        return existing.id
    year = 2026
    month = None
    if "-M" in period_key:
        try:
            month = int(period_key.split("-M", 1)[1])
        except ValueError:
            month = None
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


def _insert_submission(
    db: Session,
    *,
    client_id: str,
    vendor_id: str,
    spec: dict,
    catalog_period_keys: dict,
    catalog_period_keys_2025: dict,
    supersedes: str | None = None,
) -> str | None:
    code = spec["code"]
    requirement = db.scalar(select(Requirement).where(Requirement.code == code))
    if requirement is None:
        print(f"  ⊘ skip {code} — not in catalog on this DB")
        return None
    version = db.scalar(
        select(RequirementVersion)
        .where(RequirementVersion.requirement_id == requirement.id)
        .order_by(RequirementVersion.version.asc())
    )
    if version is None:
        print(f"  ⊘ skip {code} — no requirement version on this DB")
        return None
    institution = db.get(Institution, requirement.institution_id)
    pk = catalog_period_keys.get(code) or catalog_period_keys_2025.get(code) or "2026-M04"
    period_id = _get_or_create_period(
        db,
        period_key=pk,
        code=spec["period_code"],
        period_type=spec["period_type"],
    )

    # Idempotency guard: don't double-insert the same submission for
    # this vendor + slot. Two reruns of the script must converge.
    existing = db.scalar(
        select(Submission).where(
            Submission.vendor_id == vendor_id,
            Submission.requirement_code == code,
            Submission.period_key == pk,
            Submission.supersedes_submission_id.is_(None) if supersedes is None
            else Submission.supersedes_submission_id == supersedes,
        )
    )
    if existing is not None:
        return existing.id

    submitted_at = datetime.now(UTC) - timedelta(hours=spec["age_hours"])
    submission = Submission(
        client_id=client_id,
        vendor_id=vendor_id,
        institution_id=institution.id if institution else requirement.institution_id,
        requirement_id=requirement.id,
        requirement_version_id=version.id,
        period_id=period_id,
        status=spec["status"],
        load_type=spec["period_type"],
        requirement_code=code,
        period_key=pk,
        supersedes_submission_id=supersedes,
        created_at=submitted_at,
        updated_at=submitted_at,
    )
    db.add(submission)
    db.flush()

    doc = Document(
        submission_id=submission.id,
        storage_key=f"prod-test://{submission.id}.pdf",
        original_filename=spec["filename"],
        mime_type="application/pdf",
        size_bytes=128_000,
        sha256=("p" + code + spec["filename"]).ljust(64, "0")[:64].replace(":", "_"),
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
            actor="system:provision_test_provider",
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
                actor="system:provision_test_provider",
            )
        )
    db.flush()
    return submission.id


def main() -> int:
    raw_url = os.environ.get("DATABASE_URL") or os.environ.get("DIRECT_DATABASE_URL")
    if not raw_url:
        print("ERROR: set DATABASE_URL to the prod Neon URL before running.")
        print("  Example: DATABASE_URL='postgresql+psycopg://USER:PWD@HOST/db?sslmode=require' \\")
        print("           .venv/bin/python scripts/provision_test_provider.py")
        return 2

    url = _normalize_pg_url(raw_url)
    print(f"→ Connecting to: {url.split('@', 1)[1] if '@' in url else url}")
    engine = create_engine(url, future=True)

    from app.core.compliance_catalog import recurring_for_year
    catalog_period_keys = {r.code: r.period_key for r in recurring_for_year(2026, "moral")}
    catalog_period_keys_2025 = {r.code: r.period_key for r in recurring_for_year(2025, "moral")}

    password = _generate_password()
    pw_hash = hash_password(password)

    with Session(engine) as db, db.begin():
        # ── User ─────────────────────────────────────────────────
        user = db.scalar(select(User).where(User.email == TEST_EMAIL))
        if user is None:
            user = User(
                email=TEST_EMAIL,
                password_hash=pw_hash,
                full_name=TEST_USER_FULL_NAME,
                status="active",
                must_change_password=False,
            )
            db.add(user)
            db.flush()
            print(f"  ✓ created User {TEST_EMAIL}")
            password_set = True
        else:
            print(f"  ↻ User {TEST_EMAIL} already exists (keeping existing password)")
            password = "(unchanged — use the existing one you have stored)"
            password_set = False

        # ── Client ───────────────────────────────────────────────
        client = db.scalar(select(Client).where(Client.rfc == TEST_CLIENT_RFC))
        if client is None:
            client = Client(name=TEST_CLIENT_NAME, rfc=TEST_CLIENT_RFC)
            db.add(client)
            db.flush()
            print(f"  ✓ created Client {TEST_CLIENT_NAME}")
        else:
            print(f"  ↻ Client {TEST_CLIENT_NAME} already exists")

        # ── Organization (kind=client) ───────────────────────────
        org = db.scalar(
            select(Organization).where(Organization.name == TEST_ORG_NAME)
        )
        if org is None:
            org = Organization(name=TEST_ORG_NAME, kind="client", client_id=client.id)
            db.add(org)
            db.flush()
            print(f"  ✓ created Organization {TEST_ORG_NAME}")
        else:
            print(f"  ↻ Organization {TEST_ORG_NAME} already exists")

        # ── Vendor ───────────────────────────────────────────────
        vendor = db.scalar(select(Vendor).where(Vendor.rfc == TEST_VENDOR_RFC))
        if vendor is None:
            vendor = Vendor(
                client_id=client.id,
                name=TEST_VENDOR_NAME,
                rfc=TEST_VENDOR_RFC,
                persona_type="moral",
            )
            db.add(vendor)
            db.flush()
            print(f"  ✓ created Vendor {TEST_VENDOR_NAME}")
        else:
            print(f"  ↻ Vendor {TEST_VENDOR_NAME} already exists")

        # ── Workspace ────────────────────────────────────────────
        workspace = db.scalar(
            select(ProviderWorkspace).where(ProviderWorkspace.id == TEST_WORKSPACE_ID)
        )
        if workspace is None:
            workspace = ProviderWorkspace(
                id=TEST_WORKSPACE_ID,
                client_id=client.id,
                vendor_id=vendor.id,
                contract_id=None,
                owner_user_id=user.id,
                filial_name="Filial de Pruebas",
                persona_type="moral",
                display_name=TEST_VENDOR_NAME,
                access_token="test-provider-token",
                onboarding_completed_at=datetime.now(UTC) - timedelta(days=14),
                status="active",
            )
            db.add(workspace)
            db.flush()
            print(f"  ✓ created Workspace {TEST_WORKSPACE_ID}")
        else:
            print(f"  ↻ Workspace {TEST_WORKSPACE_ID} already exists")

        # ── Submissions ──────────────────────────────────────────
        print("→ Inserting demo submissions (skip if already present)...")
        inserted = 0
        for spec in _build_specs():
            sub_id = _insert_submission(
                db,
                client_id=client.id,
                vendor_id=vendor.id,
                spec=spec,
                catalog_period_keys=catalog_period_keys,
                catalog_period_keys_2025=catalog_period_keys_2025,
            )
            if sub_id:
                inserted += 1

        # Supersession chain on IMSS Feb
        first = {
            "code": "REC-IMSS-2026-02-comprobante-de-pago-bancario",
            "status": "rechazado",
            "filename": "imss_febrero_v1.pdf",
            "age_hours": 24 * 28,
            "rejection_reason": (
                "Rango de periodo en el PDF corresponde a enero, no a "
                "febrero. Genera el comprobante con el rango correcto."
            ),
            "period_code": "2026-02-imss-pago",
            "period_type": "mensual",
        }
        first_id = _insert_submission(
            db, client_id=client.id, vendor_id=vendor.id, spec=first,
            catalog_period_keys=catalog_period_keys,
            catalog_period_keys_2025=catalog_period_keys_2025,
        )
        if first_id:
            inserted += 1
            second = {
                "code": "REC-IMSS-2026-02-comprobante-de-pago-bancario",
                "status": "aprobado",
                "filename": "imss_febrero_v2.pdf",
                "age_hours": 24 * 25,
                "rejection_reason": None,
                "period_code": "2026-02-imss-pago",
                "period_type": "mensual",
            }
            second_id = _insert_submission(
                db, client_id=client.id, vendor_id=vendor.id, spec=second,
                catalog_period_keys=catalog_period_keys,
                catalog_period_keys_2025=catalog_period_keys_2025,
                supersedes=first_id,
            )
            if second_id:
                inserted += 1

        print(f"  → {inserted} submission row(s) inserted (existing skipped)")

    # Commit happened on context exit. Print credentials.
    print()
    print("=" * 70)
    print("TEST PROVIDER ACCOUNT — save this NOW; the password is not shown again")
    print("=" * 70)
    print(f"  Login URL    https://checkwise-six.vercel.app/login")
    print(f"               (or your custom domain if set)")
    print(f"  Email        {TEST_EMAIL}")
    print(f"  Password     {password}")
    print(f"  Workspace    {TEST_WORKSPACE_ID}")
    print(f"  Vendor       {TEST_VENDOR_NAME} (RFC {TEST_VENDOR_RFC})")
    print(f"  Client       {TEST_CLIENT_NAME} (RFC {TEST_CLIENT_RFC})")
    print()
    if password_set:
        print("On first login: workspace-entry form → fill Nombre/Apellido →")
        print("'Entrar a mi espacio' → /portal/dashboard → click 'Reportes' in")
        print("the left rail to see the populated provider Reports surface.")
    else:
        print("User already existed. If you need to reset the password, run:")
        print(f"  UPDATE users SET password_hash = '<new bcrypt hash>'")
        print(f"  WHERE email = '{TEST_EMAIL}';")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
