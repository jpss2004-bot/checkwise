"""Add a client_admin user to a CheckWise database.

One-off operator script that bridges the gap left by add_internal_admin.py
(which deliberately excludes `client_admin` because that role requires a
Client + client-Organization binding the simpler script does not handle).

What it does:

1. Finds or creates the **Client** row (the company whose vendors are
   being audited). Lookup is by name; if a row with the same name
   already exists, it is reused (so re-runs don't duplicate). RFC is
   stored exactly as passed.
2. Finds or creates the **Organization** with `kind="client"` bound to
   that client.id. Default name: `<client_name> — Cliente`.
3. Creates the **User** row with:
   - the bcrypt hash of a freshly-generated temporary password,
   - ``status="active"``,
   - ``must_change_password=True`` so the first login is forced
     through ``/activate`` to set a permanent password.
4. Creates a **Membership** row binding the user to the client-org
   with ``role="client_admin"``.
5. Optionally seeds a starter **portfolio** (Vendor + ProviderWorkspace
   rows under the new client) so the client_admin sees real entries
   on first login instead of an empty dashboard. Pass
   `--portfolio demo` to clone the cliente.demo shape from dev_seed.py
   (3 vendors, complete/complete/in-progress). Pass `--portfolio none`
   to skip the portfolio entirely.
6. Writes audit_log rows capturing actor=system for both the user
   create and each membership/vendor create so the change is
   traceable from /admin/audit-log immediately.
7. Prints the new ids and the temporary password to stdout. The
   password is the only thing the operator needs to copy into the
   onboarding email.

Idempotency:
- Client lookup-by-name reuses an existing Client; otherwise creates one.
- Organization lookup-by-(kind=client, client_id) reuses; otherwise creates.
- Vendor lookup-by-(client_id, rfc) reuses; otherwise creates.
- User refuses with exit code 2 if email already exists (matches
  add_internal_admin.py). Use a different email or remove the user
  via direct DB access before re-running.

DB target: whatever ``DATABASE_URL`` points at — same env variable the
backend reads. For Neon production:

    export DATABASE_URL='postgresql+psycopg://...@.../checkwise'
    cd apps/api
    .venv/bin/python scripts/add_client_admin.py \\
        --email rebeca100901@gmail.com \\
        --full-name "Rebe Martinez" \\
        --client-name "Cliente de Rebe Martinez" \\
        --client-rfc "TEMP010101AA"

Dry run (no DB writes):

    .venv/bin/python scripts/add_client_admin.py \\
        --email rebeca100901@gmail.com \\
        --full-name "Rebe Martinez" \\
        --client-name "Cliente de Rebe Martinez" \\
        --client-rfc "TEMP010101AA" \\
        --dry-run

The dry-run path still connects to the database (so a bad URL fails
loudly) but rolls back the transaction at the end.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

# Make ``app`` importable when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AuditLog,
    Client,
    Membership,
    Organization,
    ProviderWorkspace,
    User,
    Vendor,
)
from app.services.auth import hash_password  # noqa: E402

# Portfolio presets. Mirrors the cliente.demo seed in dev_seed.py so the
# starter view feels familiar. RFCs are scoped per-client via the
# uq_vendors_client_rfc constraint, so re-using these strings under a
# new client is safe.
DEMO_PORTFOLIO = [
    {
        "name": "Logística Andina · Demo",
        "rfc": "LAN020202IJ5",
        "complete": True,
    },
    {
        "name": "Servicios Hidalgo · Demo",
        "rfc": "SHI030303KL6",
        "complete": True,
    },
    {
        "name": "Constructora Pacífico · Demo",
        "rfc": "CPA040404MN7",
        "complete": False,
    },
]

PORTFOLIO_PRESETS = {
    "demo": DEMO_PORTFOLIO,
    "none": [],
}

PERSONA_TYPES = frozenset({"moral", "fisica"})


def generate_temp_password(length: int = 16) -> str:
    """Same composition rules as add_internal_admin.py's temp password
    helper: ≥12 chars, one upper, one lower, one digit, one symbol,
    look-alike chars (0/O/1/l/I) excluded for copy-paste safety."""
    if length < 12:
        raise ValueError("temp password length must be ≥ 12")

    uppercase = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I, O
    lowercase = "abcdefghijkmnopqrstuvwxyz"  # no l
    digits = "23456789"  # no 0, 1
    symbols = "-_"

    required = [
        secrets.choice(uppercase),
        secrets.choice(lowercase),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]
    pool = uppercase + lowercase + digits + symbols
    filler = [secrets.choice(pool) for _ in range(length - len(required))]
    chars = required + filler
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def _get_or_create_client(db, *, name: str, rfc: str) -> tuple[Client, bool]:
    """Look up by name (case-sensitive, exact). Returns (client, created)."""
    existing = db.scalar(
        select(Client).where(Client.name == name).limit(1)
    )
    if existing is not None:
        return existing, False
    client = Client(name=name, rfc=rfc, status="active")
    db.add(client)
    db.flush()
    return client, True


def _get_or_create_client_org(db, *, client: Client, name: str) -> tuple[Organization, bool]:
    """Look up by (kind=client, client_id). Returns (org, created)."""
    existing = db.scalar(
        select(Organization)
        .where(Organization.kind == "client", Organization.client_id == client.id)
        .limit(1)
    )
    if existing is not None:
        return existing, False
    org = Organization(name=name, kind="client", client_id=client.id, status="active")
    db.add(org)
    db.flush()
    return org, True


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


def _grant_membership(db, *, user: User, org: Organization) -> Membership | None:
    """Insert one client_admin membership, no-op if it already exists."""
    existing = db.scalar(
        select(Membership)
        .where(
            Membership.user_id == user.id,
            Membership.organization_id == org.id,
            Membership.role == "client_admin",
        )
        .limit(1)
    )
    if existing is not None:
        return None
    membership = Membership(
        user_id=user.id,
        organization_id=org.id,
        role="client_admin",
        status="active",
    )
    db.add(membership)
    db.flush()
    return membership


def _seed_portfolio(
    db,
    *,
    client: Client,
    owner_user: User,
    portfolio: list[dict],
    persona_type: str,
) -> list[ProviderWorkspace]:
    """Create Vendor + ProviderWorkspace rows for the starter portfolio.

    Idempotent on (client_id, rfc): if a vendor with the same RFC under
    this client already exists, it is reused and the workspace is also
    reused if one is bound to it.
    """
    created_workspaces: list[ProviderWorkspace] = []
    for spec in portfolio:
        vendor = db.scalar(
            select(Vendor)
            .where(Vendor.client_id == client.id, Vendor.rfc == spec["rfc"])
            .limit(1)
        )
        if vendor is None:
            vendor = Vendor(
                client_id=client.id,
                name=spec["name"],
                rfc=spec["rfc"],
                persona_type=persona_type,
            )
            db.add(vendor)
            db.flush()

        workspace = db.scalar(
            select(ProviderWorkspace)
            .where(
                ProviderWorkspace.client_id == client.id,
                ProviderWorkspace.vendor_id == vendor.id,
            )
            .limit(1)
        )
        if workspace is None:
            workspace = ProviderWorkspace(
                client_id=client.id,
                vendor_id=vendor.id,
                owner_user_id=owner_user.id,
                filial_name="Filial principal",
                persona_type=persona_type,
                display_name=spec["name"],
                access_token=secrets.token_urlsafe(32),
            )
            db.add(workspace)
            db.flush()
            created_workspaces.append(workspace)

    return created_workspaces


def _audit(db, *, entity_type: str, entity_id: str, action: str, after: dict) -> None:
    event = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_type="system",
        actor_id="scripts/add_client_admin.py",
        before=None,
        after=after,
        event_metadata={"source": "scripts/add_client_admin.py"},
    )
    db.add(event)
    db.flush()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a client_admin user (+ optional starter portfolio) in CheckWise.",
    )
    parser.add_argument("--email", required=True, help="Email address (must be unique).")
    parser.add_argument("--full-name", required=True, help="Display name shown in the client portal.")
    parser.add_argument("--client-name", required=True, help="Company name (Client.name).")
    parser.add_argument("--client-rfc", required=True, help="Company RFC (Client.rfc).")
    parser.add_argument(
        "--org-name",
        default=None,
        help="Organization (kind=client) name. Defaults to '<client_name> — Cliente'.",
    )
    parser.add_argument(
        "--persona-type",
        default="moral",
        choices=sorted(PERSONA_TYPES),
        help="Persona type for the new vendors (moral|fisica). Default: moral.",
    )
    parser.add_argument(
        "--portfolio",
        default="demo",
        choices=sorted(PORTFOLIO_PRESETS),
        help=(
            "Which starter vendor portfolio to seed under the new client. "
            "'demo' clones the cliente.demo shape (3 vendors); 'none' "
            "leaves the dashboard empty. Default: demo."
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
    client_rfc = args.client_rfc.strip().upper()
    org_name = args.org_name.strip() if args.org_name else f"{client_name} — Cliente"

    if "@" not in email:
        parser.error(f"--email looks malformed: {email!r}")
    if not full_name:
        parser.error("--full-name must not be empty.")
    if not client_name:
        parser.error("--client-name must not be empty.")
    if len(client_rfc) not in (12, 13):
        parser.error(
            f"--client-rfc must be 12 (moral) or 13 (fisica) characters, got {len(client_rfc)}."
        )

    db = SessionLocal()
    try:
        # 1. Client
        client, client_created = _get_or_create_client(
            db, name=client_name, rfc=client_rfc
        )

        # 2. Client-kind Organization bound to the client
        org, org_created = _get_or_create_client_org(
            db, client=client, name=org_name
        )

        # 3. User refusal guard — matches add_internal_admin.py.
        existing_user = db.scalar(select(User).where(User.email == email).limit(1))
        if existing_user is not None:
            print(
                f"❌  A user with email {email!r} already exists "
                f"(id={existing_user.id}). Pick a different email or "
                "remove the existing user before re-running.",
                file=sys.stderr,
            )
            db.rollback()
            return 2

        temp_password = generate_temp_password()
        user = _create_user(
            db, email=email, full_name=full_name, temp_password=temp_password
        )
        _audit(
            db,
            entity_type="user",
            entity_id=user.id,
            action="admin.user.created",
            after={
                "email": user.email,
                "full_name": user.full_name,
                "status": user.status,
                "must_change_password": user.must_change_password,
                "organization_id": org.id,
                "organization_name": org.name,
                "client_id": client.id,
                "client_name": client.name,
                "role": "client_admin",
            },
        )

        # 4. Membership
        membership = _grant_membership(db, user=user, org=org)
        if membership is not None:
            _audit(
                db,
                entity_type="user",
                entity_id=user.id,
                action="admin.membership.granted",
                after={
                    "user_id": user.id,
                    "organization_id": org.id,
                    "role": "client_admin",
                },
            )

        # 5. Portfolio
        portfolio_spec = PORTFOLIO_PRESETS[args.portfolio]
        workspaces = _seed_portfolio(
            db,
            client=client,
            owner_user=user,
            portfolio=portfolio_spec,
            persona_type=args.persona_type,
        )
        for ws in workspaces:
            _audit(
                db,
                entity_type="provider_workspace",
                entity_id=ws.id,
                action="admin.workspace.created",
                after={
                    "workspace_id": ws.id,
                    "client_id": client.id,
                    "vendor_id": ws.vendor_id,
                    "owner_user_id": user.id,
                    "source": "add_client_admin.py portfolio preset",
                },
            )

        # 6. Report
        def _print_summary(committed: bool) -> None:
            header = "─── DONE ─────────────────────────────────────────" if committed else "─── DRY RUN ──────────────────────────────────────"
            print(header)
            print(f"User           : {email}")
            print(f"User id        : {user.id}")
            print(f"Full name      : {user.full_name}")
            print(
                f"Client         : {client.name} (id={client.id}) "
                f"{'(created)' if client_created else '(reused existing)'}"
            )
            print(f"Client RFC     : {client.rfc}")
            print(
                f"Organization   : {org.name} (id={org.id}) "
                f"{'(created)' if org_created else '(reused existing)'}"
            )
            print(f"Role           : client_admin")
            print(f"Portfolio set  : {args.portfolio} ({len(portfolio_spec)} vendor spec(s))")
            print(f"Workspaces new : {len(workspaces)}")
            print(f"Temp password  : {temp_password}")

        if args.dry_run:
            _print_summary(committed=False)
            print("No DB writes committed. Roll back complete.")
            db.rollback()
            return 0

        db.commit()
        _print_summary(committed=True)
        print("")
        print(
            "Copy the temp password into the onboarding email. The user will be"
        )
        print(
            "forced through /activate on first login to set a permanent password."
        )
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
