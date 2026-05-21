/**
 * Frontend mirror of apps/api/app/constants/reports.py.
 *
 * Keep in sync. When the backend adds a new enum value, add it here
 * and run `tsc --noEmit` — any block / canvas code switching on the
 * old set will fail to compile, which is the signal to update.
 *
 * See docs/REPORTS_ARCHITECTURE.md §13 for the wire shapes.
 */

export const REPORT_AUDIENCES = [
  "internal_only",
  "client_facing",
  "vendor_facing",
  "external_signed",
] as const;
export type ReportAudience = (typeof REPORT_AUDIENCES)[number];

export const REPORT_STATUSES = ["draft", "active", "archived"] as const;
export type ReportStatus = (typeof REPORT_STATUSES)[number];

export const VERSION_ORIGINS = ["user", "ai", "ai_refined"] as const;
export type ReportVersionOrigin = (typeof VERSION_ORIGINS)[number];

export const CONVERSATION_ROLES = [
  "user",
  "assistant",
  "system",
  "tool",
] as const;
export type ConversationRole = (typeof CONVERSATION_ROLES)[number];

export const EXPORT_FORMATS = ["pdf", "docx", "pptx", "html"] as const;
export type ExportFormat = (typeof EXPORT_FORMATS)[number];

export const EXPORT_STATUSES = [
  "pending",
  "rendering",
  "ready",
  "failed",
] as const;
export type ExportStatus = (typeof EXPORT_STATUSES)[number];

/**
 * Spanish display labels for audience. Used on report headers and in
 * the create-report form. Stays separate from the canonical wire enum
 * because user-facing copy should drift independently of the API.
 */
export const REPORT_AUDIENCE_LABEL: Record<ReportAudience, string> = {
  internal_only: "Solo interno",
  client_facing: "Para el cliente",
  vendor_facing: "Para el proveedor",
  external_signed: "Enlace externo firmado",
};

export const REPORT_STATUS_LABEL: Record<ReportStatus, string> = {
  draft: "Borrador",
  active: "Activo",
  archived: "Archivado",
};
