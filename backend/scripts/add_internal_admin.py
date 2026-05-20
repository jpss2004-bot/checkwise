"""Add an internal_admin user to a CheckWise database.

One-off operator script. Reuses the same models, password hasher,
and audit-log shape as ``backend/scripts/dev_seed.py`` so the row this
script creates is indistinguishable from one created by the seed.

What it does:

1. Finds or creates the LegalShelf-internal Organization
   (``kind="internal"``). Default name: ``LegalShelf — Internal``.
   Matches the existing dev seed's ``LegalShelf — Demo`` shape but
   stays distinct so production data does not collide with dev data.
2. Creates the User row with:
   - the bcrypt hash of a freshly-generated temporary password,
   - ``status="active"``,
   - ``must_change_password=True`` so the first login is forced
     through ``/activate`` to set a permanent password.
3. Creates a Membership row binding the user to the org with
   ``role="internal_admin"`` (and any additional roles passed on the
   command line). The roles taxonomy is enforced loosely by the API
   layer; this script does not validate role names beyond the small
   accepted list.
4. Writes an ``audit_log`` row capturing actor=system, action
   ``admin.user.created`` so the change is traceable from
   ``/admin/audit-log`` immediately.
5. Prints the new user id, org id, and the temporary password to
   stdout. The password is the only thing the operator needs to copy
   into the onboarding email.

The script is **idempotent on the org**: re-running with the same
``--org-name`` reuses the existing organisation. It is **not**
idempotent on the user: if a user with that email already exists the
script refuses and exits non-zero, so a repeat invocation cannot
silently rotate someone's password. Use ``--add-role-only`` to grant
additional roles to an existing user without touching the password
hash.

DB target: whatever ``DATABASE_URL`` points at — same env variable the
backend reads. For Neon production:

    export DATABASE_URL='postgresql+psycopg://...@.../checkwise'
    cd backend
    .venv/bin/python scripts/add_internal_admin.py \
        --email iharas@samanosc.com.mx \
        --full-name "Issac Haras"

Dry run (no DB writes):

    .venv/bin/python scripts/add_internal_admin.py \
        --email iharas@samanosc.com.mx \
        --full-name "Issac Haras" \
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
from app.models import AuditLog, Membership, Organization, User  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

DEFAULT_ORG_NAME = "LegalShelf — Internal"

# Roles a person can hold via this script. Mirrors the taxonomy
# enforced by the auth + reviewer dependencies. ``client_admin`` is
# explicitly excluded because it requires a client_id binding the
# script is not built to negotiate; use a different flow for that.
ACCEPTED_ROLES = frozenset({"internal_admin", "reviewer"})


def generate_temp_password(length: int = 16) -> str:
    """Generate a random temp password that satisfies both the frontend
    PASSWORD_RULES (≥10 chars, upper, lower, digit — see
    frontend/lib/email-inference.ts) and the backend set-password
    minimum (12 chars, see backend/app/api/v1/auth.py::SetPasswordRequest).

    Composition: one of each required class, plus filler from a wider
    URL-safe alphabet, then shuffled. Excludes characters that look
    alike (0/O, 1/l, I) so the temp password stays copy-paste safe.
    """
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
    # Fisher-Yates via secrets so the required positions are not
    # always at the front of the string.
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def _get_or_create_internal_org(db, name: str) -> Organization:
    org = db.scalar(
        select(Organization)
        .where(Organization.name == name, Organization.kind == "internal")
        .limit(1)
    )
    if org is None:
        org = Organization(name=name, kind="internal", status="active")
        db.add(org)
        db.flush()
    return org


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


def _grant_membership(db, *, user: User, org: Organization, role: str) -> Membership | None:
    """Insert one membership row, no-op if it already exists.

    Idempotent so ``--add-role-only`` and re-runs against an existing
    user behave predictably.
    """
    existing = db.scalar(
        select(Membership)
        .where(
            Membership.user_id == user.id,
            Membership.organization_id == org.id,
            Membership.role == role,
        )
        .limit(1)
    )
    if existing is not None:
        return None
    membership = Membership(
        user_id=user.id,
        organization_id=org.id,
        role=role,
        status="active",
    )
    db.add(membership)
    db.flush()
    return membership


def _audit(db, *, user: User, action: str, after: dict) -> None:
    event = AuditLog(
        action=action,
        entity_type="user",
        entity_id=user.id,
        actor_type="system",
        actor_id="scripts/add_internal_admin.py",
        before=None,
        after=after,
        event_metadata={"source": "scripts/add_internal_admin.py"},
    )
    db.add(event)
    db.flush()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an internal_admin user in the CheckWise database.",
    )
    parser.add_argument("--email", required=True, help="Email address (must be unique).")
    parser.add_argument("--full-name", required=True, help="Display name shown in admin chrome.")
    parser.add_argument(
        "--role",
        action="append",
        dest="roles",
        default=None,
        help=(
            "Role to grant. Repeat the flag to grant several. "
            "Defaults to internal_admin only. Accepted: "
            + ", ".join(sorted(ACCEPTED_ROLES))
            + "."
        ),
    )
    parser.add_argument(
        "--org-name",
        default=DEFAULT_ORG_NAME,
        help=f"Internal organisation name. Default: {DEFAULT_ORG_NAME!r}.",
    )
    parser.add_argument(
        "--add-role-only",
        action="store_true",
        help=(
            "If the user already exists, add the requested roles to "
            "the existing user instead of refusing. Does not touch the "
            "password hash or full_name."
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

    roles = args.roles or ["internal_admin"]
    bad_roles = [r for r in roles if r not in ACCEPTED_ROLES]
    if bad_roles:
        parser.error(
            "Unsupported role(s): "
            + ", ".join(bad_roles)
            + ". Accepted: "
            + ", ".join(sorted(ACCEPTED_ROLES))
        )

    db = SessionLocal()
    try:
        org = _get_or_create_internal_org(db, args.org_name)

        existing_user = db.scalar(select(User).where(User.email == email).limit(1))
        temp_password: str | None = None

        if existing_user is not None and not args.add_role_only:
            print(
                f"❌  A user with email {email!r} already exists "
                "(id={existing_user.id}). Re-run with --add-role-only "
                "if you only want to grant additional roles, or pick "
                "a different email.".format(existing_user=existing_user),
                file=sys.stderr,
            )
            db.rollback()
            return 2

        if existing_user is not None:
            user = existing_user
            print(
                f"⚠  User {email!r} already exists; granting role(s) "
                f"without rotating the password hash."
            )
        else:
            temp_password = generate_temp_password()
            user = _create_user(
                db,
                email=email,
                full_name=full_name,
                temp_password=temp_password,
            )
            _audit(
                db,
                user=user,
                action="admin.user.created",
                after={
                    "email": user.email,
                    "full_name": user.full_name,
                    "status": user.status,
                    "must_change_password": user.must_change_password,
                    "organization_id": org.id,
                    "organization_name": org.name,
                },
            )

        granted: list[str] = []
        for role in roles:
            membership = _grant_membership(db, user=user, org=org, role=role)
            if membership is not None:
                granted.append(role)
                _audit(
                    db,
                    user=user,
                    action="admin.membership.granted",
                    after={
                        "user_id": user.id,
                        "organization_id": org.id,
                        "role": role,
                    },
                )

        if args.dry_run:
            print("─── DRY RUN ──────────────────────────────────────")
            print(f"User           : {email}")
            print(f"User id (sim)  : {user.id}")
            print(f"Full name      : {user.full_name}")
            print(f"Org            : {org.name} (id={org.id})")
            print(f"Roles granted  : {', '.join(granted) if granted else '(no new roles)'}")
            print(f"Temp password  : {temp_password or '(unchanged — user already existed)'}")
            print("No DB writes committed. Roll back complete.")
            db.rollback()
            return 0

        db.commit()
        print("─── DONE ─────────────────────────────────────────")
        print(f"User           : {email}")
        print(f"User id        : {user.id}")
        print(f"Full name      : {user.full_name}")
        print(f"Org            : {org.name} (id={org.id})")
        print(f"Roles granted  : {', '.join(granted) if granted else '(no new roles)'}")
        if temp_password is not None:
            print(f"Temp password  : {temp_password}")
            print("")
            print(
                "Copy the temp password into the onboarding email. The user will be"
            )
            print(
                "forced through /activate on first login to set a permanent password."
            )
        else:
            print("(Existing user — password hash untouched.)")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
