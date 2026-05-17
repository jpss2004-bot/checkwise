"""Reports-domain enums.

Source of truth for audience / status / version-origin / conversation-
role / export shape. The frontend mirrors these values in
``frontend/lib/reports/constants.ts`` when that file ships in Phase 3.2.
"""

from __future__ import annotations

from enum import StrEnum


class ReportAudience(StrEnum):
    """Who is allowed to read a given report.

    Enforced at the API layer. UI hiding alone is never the protection.
    See docs/REPORTS_ARCHITECTURE.md §12.
    """

    INTERNAL_ONLY = "internal_only"
    CLIENT_FACING = "client_facing"
    VENDOR_FACING = "vendor_facing"
    EXTERNAL_SIGNED = "external_signed"


class ReportStatus(StrEnum):
    """High-level lifecycle of a report. Distinct from version state."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ReportVersionOrigin(StrEnum):
    """How a particular ``report_versions`` row was produced."""

    USER = "user"
    AI = "ai"
    AI_REFINED = "ai_refined"


class ConversationRole(StrEnum):
    """Role of a single chat turn inside the copilot history."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ExportFormat(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    HTML = "html"


class ExportStatus(StrEnum):
    PENDING = "pending"
    RENDERING = "rendering"
    READY = "ready"
    FAILED = "failed"
