/**
 * MOCK reports data.
 *
 * The reports surface is a CheckWise differentiator: not just exports
 * but summaries of risk, faltantes, deadlines, responsable parties,
 * and next actions. This mock seeds the scaffold so the UI looks
 * complete during demos before the real generation pipeline ships.
 *
 * TODO[backend-integration]:
 *   - GET  /api/v1/reports                       → list
 *   - POST /api/v1/reports                       → trigger generation
 *   - GET  /api/v1/reports/{id}                  → detail / metadata
 *   - GET  /api/v1/reports/{id}/download.pdf     → blob download
 *   - POST /api/v1/reports/{id}/send-to-client   → email to client
 *
 * The report types listed below map to the four reports the brief
 * names (monthly compliance, provider expediente, missing documents,
 * risk/action). Future report types can be appended to ReportType.
 */

import type { DocumentStateCode } from "@/lib/types";

export type ReportType =
  | "monthly_compliance"
  | "provider_expediente"
  | "missing_documents"
  | "risk_action";

export type ReportStatus =
  | "ready"
  | "generating"
  | "needs_review"
  | "blocked"
  | "unavailable"
  | "not_available";

export interface ReportMeta {
  id: string;
  type: ReportType;
  /** Display title (Spanish). */
  title: string;
  /** Plain-language one-liner shown under the title. */
  blurb: string;
  /** Period covered (e.g. "Mayo 2026", "Q2 2026", "Anual 2026"). */
  period: string;
  /** Client / vendor focus. */
  scope: string;
  /** Generation date ISO string. */
  generated_at_iso: string | null;
  /** Compliance score 0–100 (if applicable). */
  compliance_pct: number | null;
  /** Document coverage 0–100 (if applicable). */
  document_coverage_pct: number | null;
  /** Open action items the report flags. */
  pending_actions: number;
  /** Highlighted issues — used by the missing-docs report tile. */
  highlights: { label: string; state: DocumentStateCode }[];
  status: ReportStatus;
}

export const REPORT_TYPE_LABEL: Record<ReportType, string> = {
  monthly_compliance: "Reporte mensual de cumplimiento",
  provider_expediente: "Expediente de proveedor",
  missing_documents: "Faltantes y vencimientos",
  risk_action: "Riesgo y acciones",
};

export const REPORT_TYPE_BLURB: Record<ReportType, string> = {
  monthly_compliance:
    "Resumen ejecutivo del periodo: cumplimiento global, instituciones, semáforo y firmas pendientes.",
  provider_expediente:
    "Estado del expediente inicial y obligaciones recurrentes para un proveedor específico.",
  missing_documents:
    "Documentos pendientes, vencidos o sin enviar — con responsables y deadlines.",
  risk_action:
    "Lista accionable de riesgos, observaciones y siguientes pasos legales.",
};

export const REPORT_STATUS_LABEL: Record<ReportStatus, string> = {
  ready: "Listo",
  generating: "Generando…",
  needs_review: "Necesita revisión",
  blocked: "Bloqueado",
  unavailable: "No disponible aún",
  not_available: "No disponible",
};

/** Variant lookup for the design system's status badges. */
export const REPORT_STATUS_VARIANT: Record<
  ReportStatus,
  "success" | "info" | "warning" | "destructive" | "outline"
> = {
  ready: "success",
  generating: "info",
  needs_review: "warning",
  blocked: "destructive",
  unavailable: "outline",
  not_available: "outline",
};

export const MOCK_REPORTS: ReportMeta[] = [
  {
    id: "rep-2026-05-monthly",
    type: "monthly_compliance",
    title: "Reporte mensual · Mayo 2026",
    blurb: "Cumplimiento global del mes y firmas pendientes.",
    period: "Mayo 2026",
    scope: "Cliente Demo · 14 proveedores",
    generated_at_iso: "2026-05-13T18:22:00.000Z",
    compliance_pct: 78,
    document_coverage_pct: 86,
    pending_actions: 6,
    highlights: [
      { label: "12 documentos aprobados", state: "approved" },
      { label: "3 en revisión humana", state: "in_review" },
      { label: "2 rechazados pendientes", state: "rejected" },
    ],
    status: "ready",
  },
  {
    id: "rep-distri-nogal-expediente",
    type: "provider_expediente",
    title: "Expediente · Distribuidora Nogal SA",
    blurb: "Alta inicial completa, calendario REPSE recurrente activo.",
    period: "2026",
    scope: "Proveedor",
    generated_at_iso: "2026-05-12T10:08:00.000Z",
    compliance_pct: 92,
    document_coverage_pct: 100,
    pending_actions: 1,
    highlights: [
      { label: "7 obligaciones aprobadas", state: "approved" },
      { label: "1 acuse en revisión", state: "in_review" },
    ],
    status: "ready",
  },
  {
    id: "rep-2026-05-missing",
    type: "missing_documents",
    title: "Faltantes · 14 proveedores",
    blurb: "Documentos sin enviar, rechazados o vencidos del periodo.",
    period: "Mayo 2026",
    scope: "Cliente Demo · cartera completa",
    generated_at_iso: null,
    compliance_pct: null,
    document_coverage_pct: null,
    pending_actions: 9,
    highlights: [
      { label: "4 faltantes obligatorios", state: "pending" },
      { label: "3 documentos vencidos", state: "expired" },
      { label: "2 rechazados", state: "rejected" },
    ],
    status: "generating",
  },
  {
    id: "rep-2026-05-risk",
    type: "risk_action",
    title: "Riesgo y acciones · cartera de mayo",
    blurb: "Riesgos legales, observaciones y acciones recomendadas.",
    period: "Mayo 2026",
    scope: "Cliente Demo · cartera completa",
    generated_at_iso: "2026-05-10T16:45:00.000Z",
    compliance_pct: 64,
    document_coverage_pct: 71,
    pending_actions: 12,
    highlights: [
      { label: "2 proveedores en alto riesgo", state: "rejected" },
      { label: "4 alertas por vencimiento próximo", state: "expired" },
      { label: "3 documentos necesitan revisión", state: "needs_review" },
    ],
    status: "needs_review",
  },
  {
    // Demonstrates the new "blocked" state — reports for a tenant
    // with critical expediente gaps cannot be generated until the
    // documentation is fixed (the report would otherwise carry
    // misleading data).
    id: "rep-tenant-blocked",
    type: "provider_expediente",
    title: "Expediente · Tenant con expediente incompleto",
    blurb: "Bloqueado hasta que el expediente inicial obligatorio quede atendido.",
    period: "2026",
    scope: "Proveedor (otro tenant)",
    generated_at_iso: null,
    compliance_pct: null,
    document_coverage_pct: null,
    pending_actions: 4,
    highlights: [
      { label: "Documento mandatorio rechazado", state: "rejected" },
      { label: "RFC en disputa", state: "needs_review" },
    ],
    status: "blocked",
  },
];
