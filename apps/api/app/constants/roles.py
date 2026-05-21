"""RBAC role names used across membership + auth dependencies."""

from __future__ import annotations

from enum import StrEnum


class MembershipRole(StrEnum):
    """Roles a user can hold within an organization."""

    INTERNAL_ADMIN = "internal_admin"
    REVIEWER = "reviewer"
    CLIENT_ADMIN = "client_admin"
