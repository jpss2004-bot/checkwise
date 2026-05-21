"""Canonical string constants used across the backend.

Every string literal that previously appeared as a magic value in routers,
services, models, or seeds lives here as a typed `StrEnum`. Equality with
plain `str` still works (StrEnum is a str subclass), so existing comparisons
keep working without touching every callsite at once.
"""

from app.constants.institutions import Institution
from app.constants.roles import MembershipRole
from app.constants.statuses import REVIEWER_DECISION_STATUS, DocumentStatus, ReviewerAction

__all__ = [
    "DocumentStatus",
    "Institution",
    "MembershipRole",
    "REVIEWER_DECISION_STATUS",
    "ReviewerAction",
]
