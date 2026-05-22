"""Provision a provider login that is bound to an *existing* Client.

Sibling of ``add_test_provider.py``. The difference: that script always
creates a brand-new Client + Organization for the QA provider. This one
refuses to create a Client — it looks up an existing one by name and
binds a new Vendor + ProviderWorkspace under it, so the provider lands
in the *same* client_admin's portfolio.

Use case it was written for: link ``fmedina@legalshelf.mx`` (Francisco
Medina) into ``Cliente de Rebe Martinez`` (Rebe's real client where
``rebeca100901@gmail.com`` is the client_admin), so Rebe sees Francisco
in her vendor list and Francisco can log in as that vendor.

What it writes (idempotent where the data model allows):

- ``Client`` — looked up by name. **Refuses with exit code 2 if not
  found** (this is the whole point — no silent client creation).
- ``Organization(kind="client", client_id=...)`` — find-or-create.
  Needed for the report service's owning-org resolution.
- ``Vendor`` — find-or-create by ``(client_id, vendor_rfc)``. RFC
  defaults to a derived test RFC from the email local-part.
- ``User`` — refuses to overwrite an existing user (matches
  ``add_test_provider.py``).
- ``ProviderWorkspace`` — find-or-create by ``vendor_id``. ``owner_user_id``
  is set to the new user. ``onboarding_completed_at`` is pre-set by
  default so the dashboard unlocks on first login.
- ``audit_log`` rows for every write.

Run from local against the prod Neon URL:

    cd apps/api
    export DATABASE_URL='postgresql+psycopg://...@.../checkwise?sslmode=require'
    .venv/bin/python scripts/add_provider_to_existing_client.py \\
        --email fmedina@legalshelf.mx \\
        --full-name "Francisco Medina" \\
        --client-name "Cliente de Rebe Martinez"

Add ``--dry-run`` to roll back at the end. The script prints the temp
password + access_token ONCE on success.
"""

from __future__ import annotations

import argparse
import re
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AuditLog,
    Client,
    Organization,
    ProviderWorkspace,
    User,
    Vendor,
)
from app.services.auth import hash_password  # noqa: E402
from scripts.add_client_admin import generate_temp_password  # noqa: E402

_RFC_DIGITS = "23456789"
_RFC_HOMOCLAVE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _safe_localpart(email: str) -> str:
    local = email.split("@", 1)[0]
    cleaned = re.sub(r"[^A-Za-z0-9]", "", local).upper()
    return cleaned or "QAU"


def _derive_default_rfc(email: str, *, persona_type: str) -> str:
    stem = (_safe_localpart(email) + "QAU")[:3]
    homoclave = "".join(secrets.choice(_RFC_HOMOCLAVE) for _ in range(3))
    if persona_type == "fisica":
        return f"{stem}010101{secrets.choice(_RFC_DIGITS)}{homoclave}"
    return f"{stem}010101{homoclave}"


def _audit(
    db,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    after: dict,
) -> None:
    db.add(
        AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_type="system",
            actor_id="scripts/add_provider_to_existing_client.py",
            before=None,
            after=after,
            event_metadata={"source": "scripts/add_provider_to_existing_client.py"},
        )
    )
    db.flush()


def _get_or_create_client_org(db, *, client: Client) -> tuple[Organization, bool]:
    existing = db.scalar(
        select(Organization)
        .where(Organization.client_id == client.id, Organization.kind == "client")
        .limit(1)
    )
    if existing is not None:
        return existing, False
    org = Organization(
        name=f"{client.name} — Cliente",
        kind="client",
        client_id=client.id,
        status="active",
    )
    db.add(org)
    db.flush()
    return org, True


def _get_or_create_vendor(
    db,
    *,
    client: Client,
    name: str,
    rfc: str,
    persona_type: str,
    contact_name: str,
    contact_email: str,
) -> tuple[Vendor, bool]:
    existing = db.scalar(
        select(Vendor)
        .where(Vendor.client_id == client.id, Vendor.rfc == rfc)
        .limit(1)
    )
    if existing is not None:
        return existing, False
    vendor = Vendor(
        client_id=client.id,
        name=name,
        rfc=rfc,
        persona_type=persona_type,
        contact_name=contact_name,
        contact_email=contact_email,
        status="active",
    )
    db.add(vendor)
    db.flush()
    return vendor, True


def _create_user(db, *, email: str, full_name: str, temp_password: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password(temp_password),
        full_name=full_name,
        status="active",
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    return user


def _get_or_create_workspace(
    db,
    *,
    client: Client,
    vendor: Vendor,
    owner_user_id: str,
    persona_type: str,
    display_name: str,
    skip_onboarding: bool,
) -> tuple[ProviderWorkspace, bool, str | None]:
    existing = db.scalar(
        select(ProviderWorkspace)
        .where(ProviderWorkspace.vendor_id == vendor.id)
        .order_by(ProviderWorkspace.id)
        .limit(1)
    )
    if existing is not None:
        return existing, False, None

    token = secrets.token_urlsafe(48)
    if len(token) > 64:
        token = token[:64]

    workspace = ProviderWorkspace(
        client_id=client.id,
        vendor_id=vendor.id,
        contract_id=None,
        owner_user_id=owner_user_id,
        filial_name=None,
        persona_type=persona_type,
        display_name=display_name,
        access_token=token,
        onboarding_completed_at=(
            datetime.now(UTC) - timedelta(days=14) if skip_onboarding else None
        ),
        status="active",
    )
    db.add(workspace)
    db.flush()
    return workspace, True, token


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Add a provider login under an EXISTING client. Refuses to "
            "create a new client — fails loudly if the client_name is not "
            "already present."
        ),
    )
    parser.add_argument("--email", required=True, help="Login email (unique).")
    parser.add_argument("--full-name", required=True, help="User.full_name.")
    parser.add_argument(
        "--client-name",
        required=True,
        help="Exact Client.name to bind the provider to (must already exist).",
    )
    parser.add_argument(
        "--vendor-name",
        default=None,
        help=(
            "Vendor display name under the client. Defaults to the user's "
            "full_name."
        ),
    )
    parser.add_argument(
        "--vendor-rfc",
        default=None,
        help=(
            "Vendor RFC. Defaults to a derived test RFC from the email "
            "local-part (12 chars for moral, 13 for fisica)."
        ),
    )
    parser.add_argument(
        "--persona-type",
        choices=("moral", "fisica"),
        default="moral",
        help="Persona type for the vendor + workspace. Default 'moral'.",
    )
    parser.add_argument(
        "--no-skip-onboarding",
        action="store_true",
        help=(
            "Leave onboarding_completed_at NULL so first login lands in "
            "/portal/entra-a-tu-espacio. By default the dashboard unlocks "
            "immediately (matches the linking pattern used for prior "
            "client_admin↔provider patches)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Connect to the DB, simulate the writes, then roll back.",
    )
    args = parser.parse_args()

    email = args.email.strip().lower()
    full_name = args.full_name.strip()
    client_name = args.client_name.strip()
    if "@" not in email:
        parser.error(f"--email looks malformed: {email!r}")
    if not full_name:
        parser.error("--full-name must not be empty.")
    if not client_name:
        parser.error("--client-name must not be empty.")

    vendor_name = (args.vendor_name or full_name).strip()
    vendor_rfc = (
        args.vendor_rfc or _derive_default_rfc(email, persona_type=args.persona_type)
    ).upper()
    expected_vendor_len = 13 if args.persona_type == "fisica" else 12
    if len(vendor_rfc) != expected_vendor_len:
        parser.error(
            f"--vendor-rfc must be {expected_vendor_len} chars for "
            f"persona_type={args.persona_type}, got {len(vendor_rfc)}: "
            f"{vendor_rfc!r}"
        )

    skip_onboarding = not args.no_skip_onboarding

    db = SessionLocal()
    try:
        client = db.scalar(
            select(Client).where(Client.name == client_name).limit(1)
        )
        if client is None:
            print(
                f"❌  No Client with name {client_name!r} exists on this DB. "
                "This script refuses to create one — pass a name that "
                "already exists, or use scripts/add_client_admin.py to "
                "provision the client first.",
                file=sys.stderr,
            )
            db.rollback()
            return 2

        existing_user = db.scalar(select(User).where(User.email == email).limit(1))
        if existing_user is not None:
            print(
                f"❌  A user with email {email!r} already exists "
                f"(id={existing_user.id}). This script does not silently "
                "rotate passwords. Pick a different email or rotate the "
                "password manually.",
                file=sys.stderr,
            )
            db.rollback()
            return 2

        org, org_created = _get_or_create_client_org(db, client=client)
        vendor, vendor_created = _get_or_create_vendor(
            db,
            client=client,
            name=vendor_name,
            rfc=vendor_rfc,
            persona_type=args.persona_type,
            contact_name=full_name,
            contact_email=email,
        )

        temp_password = generate_temp_password()
        user = _create_user(
            db,
            email=email,
            full_name=full_name,
            temp_password=temp_password,
        )

        workspace, workspace_created, new_access_token = _get_or_create_workspace(
            db,
            client=client,
            vendor=vendor,
            owner_user_id=user.id,
            persona_type=args.persona_type,
            display_name=vendor.name,
            skip_onboarding=skip_onboarding,
        )

        _audit(
            db,
            action="admin.user.created",
            entity_type="user",
            entity_id=user.id,
            after={
                "email": user.email,
                "full_name": user.full_name,
                "status": user.status,
                "must_change_password": user.must_change_password,
                "purpose": "provider_login_under_existing_client",
                "client_id": client.id,
                "client_name": client.name,
            },
        )
        if org_created:
            _audit(
                db,
                action="admin.organization.created",
                entity_type="organization",
                entity_id=org.id,
                after={"name": org.name, "kind": org.kind, "client_id": client.id},
            )
        if vendor_created:
            _audit(
                db,
                action="admin.vendor.created",
                entity_type="vendor",
                entity_id=vendor.id,
                after={
                    "name": vendor.name,
                    "rfc": vendor.rfc,
                    "client_id": client.id,
                    "persona_type": vendor.persona_type,
                    "status": vendor.status,
                },
            )
        if workspace_created:
            _audit(
                db,
                action="admin.workspace.created",
                entity_type="provider_workspace",
                entity_id=workspace.id,
                after={
                    "client_id": client.id,
                    "vendor_id": vendor.id,
                    "owner_user_id": user.id,
                    "display_name": workspace.display_name,
                    "onboarding_completed_at": (
                        workspace.onboarding_completed_at.isoformat()
                        if workspace.onboarding_completed_at
                        else None
                    ),
                    "status": workspace.status,
                },
            )

        def _print_summary(committed: bool) -> None:
            header = (
                "─── DONE ─────────────────────────────────────────"
                if committed
                else "─── DRY RUN ──────────────────────────────────────"
            )
            print(header)
            print(f"User            : {email}  (id={user.id})  [new]")
            print(f"Full name       : {full_name}")
            print(f"Client          : {client.name}  (id={client.id})  [reused — existing]")
            print(f"                  rfc={client.rfc}")
            tag_org = "new" if org_created else "reused"
            print(f"Organization    : kind=client, id={org.id}  [{tag_org}]")
            tag_vendor = "new" if vendor_created else "reused"
            print(f"Vendor          : {vendor.name}  (id={vendor.id})  [{tag_vendor}]")
            print(f"                  rfc={vendor.rfc}, persona={vendor.persona_type}")
            tag_ws = "new" if workspace_created else "reused"
            print(f"Workspace       : id={workspace.id}  [{tag_ws}]")
            if new_access_token is not None:
                print(f"Access token    : {new_access_token}")
            else:
                print("Access token    : (re-used existing token — not printed)")
            onboarding_state = (
                "completed (dashboard unlocked)"
                if skip_onboarding
                else "pending — first login lands in /portal/entra-a-tu-espacio"
            )
            print(f"Onboarding      : {onboarding_state}")
            print(f"Temp password   : {temp_password}")

        if args.dry_run:
            _print_summary(committed=False)
            print("No DB writes committed. Roll back complete.")
            db.rollback()
            return 0

        db.commit()
        _print_summary(committed=True)
        print()
        print("Copy the temp password into the onboarding email. On first login")
        print("the user is redirected to /activate to set a permanent password.")
        print("The temp password becomes invalid as soon as they save the new one.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
