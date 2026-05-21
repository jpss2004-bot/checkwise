"""Provision a single QA-grade provider login against any CheckWise
database.

Sibling of ``backend/scripts/add_internal_admin.py``. That script
provisions LegalShelf staff (internal_admin Membership in the
internal Organization). This one provisions the *other* side of the
product: a provider account that authenticates with email + password
and lands on the ``/portal`` workspace, exactly like a real external
provider would.

The flow this script unlocks:

1. The new user lands on ``/login`` with the temp password.
2. Because ``must_change_password=True``, they are redirected to
   ``/activate`` to set a permanent password.
3. They then enter their workspace at ``/portal/entra-a-tu-espacio``
   and run through the onboarding wizard before the dashboard
   unlocks. ``onboarding_completed_at`` is ``None`` so the gate
   activates; pass ``--skip-onboarding`` to bypass the gate when you
   only want to exercise the dashboard / reports surface.

What it writes (idempotent where the data model allows):

- ``Client`` (find-or-create by RFC).
- ``Organization(kind="client", client_id=...)`` so the report
  service can resolve an owning-org for vendor_facing reports
  authored by this provider. Boss-demo pattern from ``dev_seed.py``.
- ``Vendor`` (find-or-create by ``(client_id, rfc)`` — the unique
  index already enforced by the schema).
- ``User`` (refuses to overwrite an existing user). Email is the
  unique key. Password hash is bcrypt; the plaintext is printed once
  to stdout and never persisted.
- ``ProviderWorkspace`` (find-or-create by ``vendor_id`` — re-runs
  do not generate a new access_token if a workspace already exists
  for the vendor). Generates a 48-byte URL-safe access token.
- ``audit_log`` rows for every write (``admin.user.created``,
  ``admin.client.created``, ``admin.vendor.created``,
  ``admin.workspace.created``).

What it deliberately does NOT do (contrast with the existing
``provision_test_provider.py``):

- No sample submissions. The QA account starts empty so the operator
  experiences the actual onboarding flow.
- No supersession chains, no canonical catalog probing, no period
  seeding. If the operator wants those, run ``dev_seed.py`` locally
  or extend this script behind an opt-in flag.

Run from local against the prod Neon URL:

    cd backend
    export DATABASE_URL='postgresql+psycopg://...@.../checkwise?sslmode=require'
    .venv/bin/python scripts/add_test_provider.py \\
        --email rmartinez@legalshelf.mx \\
        --full-name "Rebeca Martinez"

The script prints the temp password + access_token + workspace id ONCE
at the end. Copy them, then close the terminal scrollback.
"""

from __future__ import annotations

import argparse
import re
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Make ``app`` importable when running this script directly.
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

# Reuse the temp-password generator from the sister script. It already
# satisfies both the frontend PASSWORD_RULES (≥10 chars, upper, lower,
# digit) and the backend SetPasswordRequest minimum (≥12 chars), and
# excludes look-alike chars (0/O, 1/l, I) for copy-paste safety.
from scripts.add_internal_admin import generate_temp_password  # noqa: E402

# Allowed RFC alphabet for derived test RFCs. Real Mexican RFCs use
# A-Z + 0-9 (with two letter-only positions for "letras del nombre" +
# six digits for the date + three-char homoclave). We keep the same
# alphabet so the value passes the loose 12/13-char checks downstream.
_RFC_DIGITS = "23456789"
_RFC_HOMOCLAVE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _safe_localpart(email: str) -> str:
    """Return the alphanumeric portion of the email local-part,
    upper-cased and ASCII-only.

    Used to derive test RFCs and display defaults from the email so
    the artefacts read as "obviously this account's stuff" instead of
    a random blob.
    """
    local = email.split("@", 1)[0]
    cleaned = re.sub(r"[^A-Za-z0-9]", "", local).upper()
    return cleaned or "QAU"


def _derive_default_rfc(email: str, *, persona_type: str) -> str:
    """Generate a 12- or 13-char test RFC that fits the SAT-shaped slot.

    Format mirrors the dev_seed pattern (``DNG890101AB1``): three
    letters from the email local-part + six date digits (frozen at the
    QA-safe ``010101``) + three-char homoclave. The homoclave is
    random per call so two re-runs against the same DB produce
    different RFCs and the unique index does not block the second
    call from creating an independent QA record.

    13-char form (persona física) gets one extra digit between the
    date and the homoclave.
    """
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
            actor_id="scripts/add_test_provider.py",
            before=None,
            after=after,
            event_metadata={"source": "scripts/add_test_provider.py"},
        )
    )
    db.flush()


def _get_or_create_client(db, *, name: str, rfc: str) -> tuple[Client, bool]:
    """Find by RFC (unique). Returns (client, created)."""
    existing = db.scalar(select(Client).where(Client.rfc == rfc).limit(1))
    if existing is not None:
        return existing, False
    client = Client(name=name, rfc=rfc, status="active")
    db.add(client)
    db.flush()
    return client, True


def _get_or_create_client_org(db, *, client: Client, name: str) -> tuple[Organization, bool]:
    existing = db.scalar(
        select(Organization)
        .where(Organization.client_id == client.id, Organization.kind == "client")
        .limit(1)
    )
    if existing is not None:
        return existing, False
    org = Organization(name=name, kind="client", client_id=client.id, status="active")
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
    contact_name: str | None,
    contact_email: str | None,
) -> tuple[Vendor, bool]:
    """Find by (client_id, rfc) — the existing unique index. Returns
    (vendor, created).
    """
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
        # Forces the /activate redirect on first login so the temp
        # password from this script cannot become permanent by
        # accident.
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
    """Find by vendor_id (one active workspace per vendor in V1) or
    create a fresh one. Returns (workspace, created, new_access_token).

    ``new_access_token`` is None on the find branch so the printed
    summary can flag "re-using existing token" instead of leaking a
    fresh-looking token that does not actually authenticate.
    """
    existing = db.scalar(
        select(ProviderWorkspace)
        .where(ProviderWorkspace.vendor_id == vendor.id)
        .order_by(ProviderWorkspace.id)
        .limit(1)
    )
    if existing is not None:
        return existing, False, None

    # 48 URL-safe bytes ≈ 64 chars of base64url, which fits the
    # access_token VARCHAR(64) column exactly.
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
        description="Provision a QA provider account in the CheckWise database.",
    )
    parser.add_argument("--email", required=True, help="Login email (must be unique).")
    parser.add_argument("--full-name", required=True, help="User.full_name.")
    parser.add_argument(
        "--client-name",
        default=None,
        help="Client display name. Defaults to 'QA · Cliente — {full_name}'.",
    )
    parser.add_argument(
        "--client-rfc",
        default=None,
        help=(
            "Client RFC (12 chars for moral). Defaults to a deterministic "
            "test RFC derived from the email."
        ),
    )
    parser.add_argument(
        "--vendor-name",
        default=None,
        help="Vendor display name. Defaults to 'QA · Proveedor — {full_name}'.",
    )
    parser.add_argument(
        "--vendor-rfc",
        default=None,
        help=(
            "Vendor RFC (12 chars for moral, 13 for fisica). Defaults to a "
            "deterministic test RFC derived from the email."
        ),
    )
    parser.add_argument(
        "--persona-type",
        choices=("moral", "fisica"),
        default="moral",
        help="Persona type for the vendor + workspace. Default 'moral'.",
    )
    parser.add_argument(
        "--skip-onboarding",
        action="store_true",
        help=(
            "Set onboarding_completed_at so the dashboard unlocks "
            "immediately. By default the new account goes through "
            "onboarding like a real provider."
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
    if "@" not in email:
        parser.error(f"--email looks malformed: {email!r}")
    if not full_name:
        parser.error("--full-name must not be empty.")

    client_name = args.client_name or f"QA · Cliente — {full_name}"
    vendor_name = args.vendor_name or f"QA · Proveedor — {full_name}"
    client_rfc = (args.client_rfc or _derive_default_rfc(email, persona_type="moral")).upper()
    vendor_rfc = (
        args.vendor_rfc or _derive_default_rfc(email, persona_type=args.persona_type)
    ).upper()

    # Length sanity checks — the DB column is VARCHAR(13).
    if not (12 <= len(client_rfc) <= 13):
        parser.error(f"--client-rfc must be 12 or 13 chars, got {len(client_rfc)}: {client_rfc!r}")
    expected_vendor_len = 13 if args.persona_type == "fisica" else 12
    if len(vendor_rfc) != expected_vendor_len:
        parser.error(
            f"--vendor-rfc must be {expected_vendor_len} chars for "
            f"persona_type={args.persona_type}, got {len(vendor_rfc)}: "
            f"{vendor_rfc!r}"
        )

    db = SessionLocal()
    try:
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

        client, client_created = _get_or_create_client(db, name=client_name, rfc=client_rfc)
        org, org_created = _get_or_create_client_org(
            db, client=client, name=f"{client.name} — Cliente"
        )
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
            skip_onboarding=args.skip_onboarding,
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
                "purpose": "qa_provider_login",
            },
        )
        if client_created:
            _audit(
                db,
                action="admin.client.created",
                entity_type="client",
                entity_id=client.id,
                after={"name": client.name, "rfc": client.rfc, "status": client.status},
            )
        if org_created:
            _audit(
                db,
                action="admin.organization.created",
                entity_type="organization",
                entity_id=org.id,
                after={
                    "name": org.name,
                    "kind": org.kind,
                    "client_id": client.id,
                },
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

        if args.dry_run:
            print("─── DRY RUN ──────────────────────────────────────")
            _print_summary(
                email=email,
                full_name=full_name,
                user=user,
                client=client,
                client_created=client_created,
                org_created=org_created,
                vendor=vendor,
                vendor_created=vendor_created,
                workspace=workspace,
                workspace_created=workspace_created,
                new_access_token=new_access_token,
                temp_password=temp_password,
                skip_onboarding=args.skip_onboarding,
                committed=False,
            )
            db.rollback()
            return 0

        db.commit()
        print("─── DONE ─────────────────────────────────────────")
        _print_summary(
            email=email,
            full_name=full_name,
            user=user,
            client=client,
            client_created=client_created,
            org_created=org_created,
            vendor=vendor,
            vendor_created=vendor_created,
            workspace=workspace,
            workspace_created=workspace_created,
            new_access_token=new_access_token,
            temp_password=temp_password,
            skip_onboarding=args.skip_onboarding,
            committed=True,
        )
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _print_summary(
    *,
    email: str,
    full_name: str,
    user: User,
    client: Client,
    client_created: bool,
    org_created: bool,
    vendor: Vendor,
    vendor_created: bool,
    workspace: ProviderWorkspace,
    workspace_created: bool,
    new_access_token: str | None,
    temp_password: str,
    skip_onboarding: bool,
    committed: bool,
) -> None:
    def tag(created: bool) -> str:
        return "new" if created else "reused"

    print(f"User            : {email}  (id={user.id})  [new]")
    print(f"Full name       : {full_name}")
    print(f"Client          : {client.name}  (id={client.id})  [{tag(client_created)}]")
    print(f"                  rfc={client.rfc}")
    print(f"Organization    : kind=client, client_id={client.id}  [{tag(org_created)}]")
    print(f"Vendor          : {vendor.name}  (id={vendor.id})  [{tag(vendor_created)}]")
    print(f"                  rfc={vendor.rfc}, persona={vendor.persona_type}")
    print(f"Workspace       : id={workspace.id}  [{tag(workspace_created)}]")
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
    print()
    if committed:
        print("Copy the temp password into the onboarding email. On first login the")
        print("user is redirected to /activate to set a permanent password. The temp")
        print("password becomes invalid as soon as they save the new one.")
    else:
        print("No DB writes committed. Roll back complete.")


if __name__ == "__main__":
    raise SystemExit(main())
