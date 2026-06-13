"""RBAC role names used across membership + auth dependencies."""

from __future__ import annotations

from enum import StrEnum


class MembershipRole(StrEnum):
    """Roles a user can hold within an organization."""

    INTERNAL_ADMIN = "internal_admin"
    REVIEWER = "reviewer"
    CLIENT_ADMIN = "client_admin"
    # IT / platform-administration role (platform rework, Phase 1).
    # Separated from ``internal_admin`` so the IT duties exposed at
    # ``/platform/*`` (user provisioning, audit log, feedback triage)
    # can be held independently of day-to-day compliance operations.
    # Migration 0044 backfilled this onto every existing internal_admin
    # so the split is non-breaking; a person may hold both roles.
    PLATFORM_ADMIN = "platform_admin"
