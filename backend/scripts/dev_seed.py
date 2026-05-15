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


def _utc(year: int, month: int, day: int = 1) -> datetime:
    return datetime(year, month, day, 12, 0, 0, tzinfo=UTC)


def _wipe_demo(db) -> None:
    """Remove anything tagged with the demo identifiers so the seed
    is idempotent. Order matters because of FKs."""
    workspace = db.scalar(
        select(ProviderWorkspace).where(ProviderWorkspace.id == DEMO_WORKSPACE_ID)
    )
    if workspace is not None:
        vendor_id = workspace.vendor_id
        client_id = workspace.client_id

        submissions = list(
            db.scalars(select(Submission).where(Submission.vendor_id == vendor_id))
        )
        for sub in submissions:
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

        db.query(Vendor).filter(Vendor.id == vendor_id).delete(synchronize_session=False)
        db.query(Client).filter(Client.id == client_id).delete(synchronize_session=False)
        db.flush()

    for demo_email in (DEMO_USER_EMAIL, DEMO_PROVIDER_EMAIL):
        user = db.scalar(select(User).where(User.email == demo_email))
        if user is not None:
            db.query(Membership).filter(Membership.user_id == user.id).delete(
                synchronize_session=False
            )
            db.delete(user)
            db.flush()

    org = db.scalar(select(Organization).where(Organization.name == DEMO_ORG_NAME))
    if org is not None:
        db.delete(org)
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
        requirement = db.scalar(
            select(Requirement).where(Requirement.code == spec["code"])
        )
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


def main() -> None:
    db = SessionLocal()
    try:
        _wipe_demo(db)
        user_id, org_id = _seed_admin(db)
        provider_user_id = _seed_provider_user(db)
        client_id, vendor_id, workspace_id = _seed_workspace(
            db, owner_user_id=provider_user_id
        )
        submissions = _seed_submissions(db, client_id=client_id, vendor_id=vendor_id)
        db.commit()
    finally:
        db.close()

    print("Demo data ready.")
    print()
    print("  Reviewer / admin login:")
    print("    URL       http://localhost:3000/login")
    print(f"    Email     {DEMO_USER_EMAIL}")
    print(f"    Password  {DEMO_USER_PASSWORD}")
    print("    Roles     internal_admin, reviewer")
    print()
    print("  Provider login (FIRST-LOGIN flow):")
    print("    URL       http://localhost:3000/login")
    print(f"    Email     {DEMO_PROVIDER_EMAIL}")
    print(f"    Password  {DEMO_PROVIDER_TEMP_PASSWORD}  (temporary)")
    print("    Note      must_change_password=True; after login the user is")
    print("              forced through /activate to set a permanent password,")
    print("              then enters workspace via /portal/enter.")
    print()
    print("  Pre-seeded provider workspace (assigned to the provider user):")
    print(f"    workspace_id    {workspace_id}")
    print(f"    owner_user_id   {provider_user_id}")
    print(f"    client / vendor {DEMO_CLIENT_NAME} / {DEMO_VENDOR_NAME}")
    print(f"    {submissions} demo submission(s) in queue states.")


if __name__ == "__main__":
    main()
