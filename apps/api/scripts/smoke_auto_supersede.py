"""Live in-process smoke for the auto-supersede invariant (audit 2026-06-09).

Boots the REAL FastAPI app (real routes, real upload handling, real DB
session) against a throwaway SQLite DB and drives the actual provider
flow over HTTP via TestClient:

    enter workspace -> upload to a slot -> approve it -> re-upload the
    same slot WITHOUT a `supersedes_submission_id`.

It then prints the lineage so you can see auto-supersede fire: the second
upload links to the (approved) first instead of spawning a parallel
genesis row, the slot returns to review, and the slot keeps exactly one
genesis. This is the behaviour migration 0035's unique index relies on —
verified here end-to-end, and confirmed clean in prod by the 0-row
invariant check in docs/audits/verify-checklist-migrations.sql.

Run: cd apps/api && .venv/bin/python -m scripts.smoke_auto_supersede
"""

from __future__ import annotations

import os
from io import BytesIO

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.setdefault("CHECKWISE_LLM_BACKEND", "mock")

from fastapi.testclient import TestClient  # noqa: E402
from pypdf import PdfWriter  # noqa: E402
from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.compliance_catalog import recurring_for_year  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Client, ProviderWorkspace, Submission, User, Vendor  # noqa: E402
from app.services.auth import hash_password, issue_access_token  # noqa: E402


def _pdf() -> bytes:
    buf = BytesIO()
    w = PdfWriter()
    w.add_blank_page(width=612, height=792)
    w.write(buf)
    return buf.getvalue()


def main() -> int:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    client = TestClient(app)

    # --- seed one provider workspace + owner -------------------------------
    db = Session()
    try:
        user = User(
            email="smoke-owner@checkwise.test",
            password_hash=hash_password("Smoke!2026"),
            full_name="Smoke Owner",
            status="active",
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        org = Client(name="Smoke Client")
        db.add(org)
        db.flush()
        vendor = Vendor(
            client_id=org.id, name="Smoke Vendor", rfc="SMK010101AA1",
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        ws = ProviderWorkspace(
            client_id=org.id, vendor_id=vendor.id, owner_user_id=user.id,
            persona_type="moral", display_name="Smoke Vendor",
            access_token="placeholder",
        )
        db.add(ws)
        db.commit()
        ws_id, user_id, user_email = ws.id, user.id, user.email
    finally:
        db.close()

    token = issue_access_token(user_id=user_id, email=user_email, roles=[], orgs=[])
    auth = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/portal/enter", json={"workspace_id": ws_id},
                       headers=auth).status_code == 200

    item = next(
        i for i in recurring_for_year(2026)
        if i.institution == "infonavit" and i.period_key == "2026-B1"
    )
    form = {
        "period_code": "2026-B1", "period_key": item.period_key,
        "load_type": "bimestral", "institution_code": "infonavit",
        "requirement_name": item.name, "requirement_code": item.code,
        "initial_status": "pendiente_revision", "comments": "smoke",
    }

    def upload(label: str) -> str:
        r = client.post(
            f"/api/v1/portal/workspaces/{ws_id}/submissions",
            data=form, files={"file": (f"{label}.pdf", _pdf(), "application/pdf")},
            headers=auth,
        )
        assert r.status_code == 202, r.text
        return r.json()["submission_id"]

    def status_of(sub_id: str) -> str:
        db = Session()
        try:
            return db.get(Submission, sub_id).status
        finally:
            db.close()

    def approve(sub_id: str) -> None:
        db = Session()
        try:
            db.get(Submission, sub_id).status = "aprobado"
            db.commit()
        finally:
            db.close()

    def genesis_count() -> int:
        db = Session()
        try:
            return db.scalar(
                select(func.count(Submission.id)).where(
                    Submission.client_id == ws_id_to_client(),
                    Submission.requirement_code == item.code,
                    Submission.period_key == item.period_key,
                    Submission.supersedes_submission_id.is_(None),
                )
            )
        finally:
            db.close()

    def ws_id_to_client() -> str:
        db = Session()
        try:
            return db.get(ProviderWorkspace, ws_id).client_id
        finally:
            db.close()

    print("\n=== Auto-supersede live smoke (slot: INFONAVIT 2026-B1) ===")
    a = upload("first")
    print(f"  upload #1  -> submission {a[:8]}  status={status_of(a)}  genesis_in_slot={genesis_count()}")
    approve(a)
    print(f"  reviewer approves #1 -> status={status_of(a)}")
    b = upload("second")
    detail = client.get(
        f"/api/v1/portal/workspaces/{ws_id}/submissions/{b}", headers=auth
    ).json()
    print(f"  upload #2  -> submission {b[:8]}  status={status_of(b)}")
    print(f"             -> supersedes_submission_id = {str(detail.get('supersedes_submission_id'))[:8]}  (expected {a[:8]})")
    print(f"  genesis rows in slot now = {genesis_count()}  (expected 1)")

    ok = (
        detail.get("supersedes_submission_id") == a
        and status_of(b) == "pendiente_revision"
        and status_of(a) == "aprobado"
        and genesis_count() == 1
    )
    print(f"\n  RESULT: {'PASS — re-upload auto-superseded the approved occupant; one genesis; slot back in review.' if ok else 'FAIL'}\n")
    app.dependency_overrides.clear()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
