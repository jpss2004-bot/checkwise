"""Rename RBAC roles to the operations_admin / platform_admin model.

Role-model redesign (2026-06-23). The target vocabulary is:

    operations_admin  — CheckWise superadmin (everything + user/role mgmt)
    platform_admin    — CheckWise review team (was internal_admin + reviewer)
    client_admin      — per-tenant Approver (unchanged slug)
    client_viewer     — per-tenant read/export (unchanged slug)

This migration rewrites ``memberships`` off the retired ``internal_admin``
and ``reviewer`` slugs and repurposes the old IT ``platform_admin`` slug:

  * Users in the SUPERADMIN allowlist (``_OPERATIONS_ADMIN_EMAILS``) keep a
    single ``operations_admin`` membership per internal org.
  * Every other holder of ``internal_admin`` / ``reviewer`` / old
    ``platform_admin`` collapses to a single ``platform_admin`` row per org
    (the CheckWise review team).

Within each (user, org) staff group we keep ONE row (lowest id, preferring a
primary seat) set to the target role and delete the rest, so the
``uq_memberships_user_org_role`` constraint can't trip.

Denormalized role snapshots are rewritten for filter/display consistency:
``feedback_reports.user_roles``, ``notification_dispatch.recipient_role``,
and historical ``audit_log.actor_type``.

Postgres-only (tests build the schema via ``create_all`` and seed roles
directly, so they never run this migration).

MIGRATION-NUMBER NOTE: rechained after merging ``main`` (PR #32's
0056/0057/0058 + ``0059_client_acceptance_axis`` are now the head). This
revision is ``0060`` with ``down_revision = 0059_client_acceptance_axis`` —
a single linear head, no merge revision needed. The rename is lossy on
downgrade (three staff slugs collapse into one); snapshot Neon before
running on prod.
"""

from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "0060_rename_rbac_roles"
down_revision = "0059_client_acceptance_axis"
branch_labels = None
depends_on = None

# The CheckWise superadmin allowlist. Everyone else on staff becomes the new
# ``platform_admin`` (review team). Keep this list tiny.
_OPERATIONS_ADMIN_EMAILS = ("jsamano@legalshelf.mx",)

_OLD_STAFF_ROLES = ("internal_admin", "reviewer", "platform_admin")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    ops_emails = [e.lower() for e in _OPERATIONS_ADMIN_EMAILS]
    ops_ids = {
        row[0]
        for row in bind.execute(
            text("SELECT id FROM users WHERE lower(email) = ANY(:emails)"),
            {"emails": ops_emails},
        )
    }

    staff_rows = list(
        bind.execute(
            text(
                "SELECT id, user_id, organization_id, role, is_primary "
                "FROM memberships WHERE role = ANY(:roles) "
                "ORDER BY user_id, organization_id, is_primary DESC, id ASC"
            ),
            {"roles": list(_OLD_STAFF_ROLES)},
        )
    )

    # Group by (user_id, organization_id); keep the first row (primary-first,
    # then lowest id), retarget it, delete the rest of the group.
    seen_groups: set[tuple[str, str]] = set()
    keep_ids: dict[str, str] = {}  # membership_id -> target_role
    drop_ids: list[str] = []
    for mid, user_id, org_id, _role, _is_primary in staff_rows:
        key = (user_id, org_id)
        target = "operations_admin" if user_id in ops_ids else "platform_admin"
        if key in seen_groups:
            drop_ids.append(mid)
        else:
            seen_groups.add(key)
            keep_ids[mid] = target

    for mid, target in keep_ids.items():
        bind.execute(
            text("UPDATE memberships SET role = :role WHERE id = :id"),
            {"role": target, "id": mid},
        )
    if drop_ids:
        bind.execute(
            text("DELETE FROM memberships WHERE id = ANY(:ids)"),
            {"ids": drop_ids},
        )

    # ---- Denormalized role snapshots (display/filter consistency) ----
    # feedback_reports.user_roles is a comma-separated snapshot.
    bind.execute(
        text(
            "UPDATE feedback_reports SET user_roles = "
            "replace(replace(user_roles, 'internal_admin', 'platform_admin'), "
            "'reviewer', 'platform_admin') "
            "WHERE user_roles LIKE '%internal_admin%' "
            "OR user_roles LIKE '%reviewer%'"
        )
    )
    bind.execute(
        text(
            "UPDATE notification_dispatch SET recipient_role = 'platform_admin' "
            "WHERE recipient_role IN ('internal_admin', 'reviewer')"
        )
    )
    bind.execute(
        text(
            "UPDATE audit_log SET actor_type = 'platform_admin' "
            "WHERE actor_type IN ('internal_admin', 'reviewer')"
        )
    )


def downgrade() -> None:
    """Best-effort reverse. The collapse of three staff roles into one is
    lossy (we cannot tell which platform_admin rows were originally
    ``reviewer`` vs ``internal_admin``), so this maps the new vocabulary back
    to ``internal_admin`` and relies on the pre-migration Neon snapshot for a
    true restore.
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    bind.execute(
        text(
            "UPDATE memberships SET role = 'internal_admin' "
            "WHERE role IN ('operations_admin', 'platform_admin')"
        )
    )
    bind.execute(
        text(
            "UPDATE notification_dispatch SET recipient_role = 'internal_admin' "
            "WHERE recipient_role = 'platform_admin'"
        )
    )
    bind.execute(
        text(
            "UPDATE audit_log SET actor_type = 'internal_admin' "
            "WHERE actor_type = 'platform_admin'"
        )
    )
