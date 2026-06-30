"""RBAC role names used across membership + auth dependencies."""

from __future__ import annotations

from enum import StrEnum


class MembershipRole(StrEnum):
    """Roles a user can hold within an organization.

    Role-model redesign (2026-06-23). Target vocabulary:

    - ``operations_admin`` — CheckWise superadmin. Everything, and the ONLY
      role that may create users, assign/change roles, grant admins, run
      feedback triage, and set a client's review mode.
    - ``platform_admin`` — CheckWise review team. Approve/deny documents for
      all clients & providers, add clients + providers, READ the audit log.
      May NOT manage users/roles. Absorbs the retired ``internal_admin``
      compliance surface and the retired ``reviewer`` queue.
    - ``client_admin`` — per-tenant Approver, CheckWise-granted only. Adds
      providers + (when its client is in self-review mode — Phase 3) approves
      / denies that client's documents; manages its own ``client_viewer``
      seats (cap 3).
    - ``client_viewer`` — per-tenant read + export oversight seat.
    - ``provider`` — vendor upload (a workspace session, not a Membership).

    ``Membership.role`` is a free string column, so the rename is a data
    migration (0056). ``INTERNAL_ADMIN`` and ``REVIEWER`` are retained below
    as DEPRECATED members for the transition window only: the migration
    rewrites every row off them and they are removed once a grep confirms
    zero references. Do not gate new code on them — use ``STAFF_ROLES`` /
    ``SUPERADMIN_ROLES``.
    """

    OPERATIONS_ADMIN = "operations_admin"
    PLATFORM_ADMIN = "platform_admin"
    CLIENT_ADMIN = "client_admin"
    CLIENT_VIEWER = "client_viewer"

    # --- DEPRECATED (transition only; removed after the rename sweep) ---
    INTERNAL_ADMIN = "internal_admin"
    REVIEWER = "reviewer"


# CheckWise-side, cross-tenant staff access (review team + superadmin).
# Prefer these sets over naming individual roles in gates/comparisons.
STAFF_ROLES: frozenset[str] = frozenset(
    {MembershipRole.PLATFORM_ADMIN.value, MembershipRole.OPERATIONS_ADMIN.value}
)

# Superadmin only — user/role management, feedback triage, review-mode switch.
SUPERADMIN_ROLES: frozenset[str] = frozenset(
    {MembershipRole.OPERATIONS_ADMIN.value}
)

# Protected platform owner(s). Side co-admins are full ``operations_admin``
# peers (they may provision and manage every other account), but the owner
# account is sacrosanct: it can never be disabled, demoted, soft-deleted, or
# have its password reset through the admin user-lifecycle endpoints — by
# anyone, including a peer co-admin. This guarantees at least one
# ``operations_admin`` always survives, so the platform can't be locked out.
# The owner manages their own profile/password through self-service account
# settings, not these admin routes.
#
# Mirrors the migration-0060 superadmin allowlist (``_OPERATIONS_ADMIN_EMAILS``)
# but is the RUNTIME source of truth for owner-protection guards. Compared
# case-insensitively against the lowercased account email.
PROTECTED_OWNER_EMAILS: frozenset[str] = frozenset({"jsamano@legalshelf.mx"})
