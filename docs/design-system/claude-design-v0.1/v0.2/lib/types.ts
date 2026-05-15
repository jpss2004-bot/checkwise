/**
 * CheckWise · Shared types
 * Consolidated in v0.2 phase 1 — types previously duplicated across:
 *   - components/checkwise/portal/requirement-status-badge.tsx
 *   - components/checkwise/validation-summary.tsx
 *   - components/checkwise/intake-wizard.tsx
 *   - lib/mock/expediente.ts
 *
 * Domain: REPSE compliance (not IMPI).
 */

// ────────────────────────────────────────────────────────────────────
// Validation signal — used by form fields and inline summaries
// ────────────────────────────────────────────────────────────────────
export type ValidationSignal = 'valid' | 'warning' | 'error' | 'pending';

// ────────────────────────────────────────────────────────────────────
// REPSE document / requirement lifecycle
// ────────────────────────────────────────────────────────────────────
export type RequirementStatus =
  | 'empty'         // No document uploaded for this slot yet
  | 'pending'       // Marked required but action not started
  | 'uploaded'      // File received, not yet validated
  | 'in_review'     // Awaiting human reviewer or AI validation
  | 'needs_review'  // AI flagged something / human signoff required
  | 'rejected'      // Rejected, must be resubmitted
  | 'expired'       // Was approved, period elapsed
  | 'approved';     // Final approved state

export const REQUIREMENT_STATUS_VALUES: RequirementStatus[] = [
  'empty',
  'pending',
  'uploaded',
  'in_review',
  'needs_review',
  'rejected',
  'expired',
  'approved',
];

// ────────────────────────────────────────────────────────────────────
// AI / OCR confidence tier
//
// Drives the triage routing logic in the AI/OCR review pattern:
//   high   → auto-accept (still editable, shows source link on hover)
//   medium → inline-confirm (filled but not committed; one keystroke accepts)
//   low    → block (filing cannot be approved until human signs off)
//   none   → human-only (model declined to extract; manual entry required)
// ────────────────────────────────────────────────────────────────────
export type ConfidenceLevel = 'high' | 'medium' | 'low' | 'none';

export interface ConfidenceSignal {
  level: ConfidenceLevel;
  /** 0–100 percentage when known; undefined for `none`. */
  pct?: number;
  /** Where in the source document the value came from, e.g. "p.1 · L.4". */
  source?: string;
  /** Whether a human must explicitly approve before the value commits. */
  requiresHumanReview?: boolean;
}

/** Pure helper — routing logic for confidence tiers. */
export function shouldRequireHumanReview(c: ConfidenceSignal): boolean {
  if (c.requiresHumanReview !== undefined) return c.requiresHumanReview;
  return c.level === 'low' || c.level === 'none';
}

/** Map a raw percentage to a confidence tier. */
export function pctToConfidenceLevel(pct: number | null | undefined): ConfidenceLevel {
  if (pct == null) return 'none';
  if (pct >= 95) return 'high';
  if (pct >= 70) return 'medium';
  if (pct >= 50) return 'low';
  return 'none';
}

// ────────────────────────────────────────────────────────────────────
// Document grouping — REPSE expediente structure
// ────────────────────────────────────────────────────────────────────
export type DocumentGroup =
  | 'expediente_inicial'    // Onboarding / one-time documents
  | 'cumplimiento_repse'    // Monthly/quarterly compliance documents
  | 'icsoe'                 // IMSS ICSOE submissions
  | 'sisub'                 // INFONAVIT SISUB submissions
  | 'sat_opinion'           // SAT opinión de cumplimiento
  | 'stps'                  // STPS cuatrimestral
  | 'contratos'             // Contract documents
  | 'identidad';            // Identity / legal personhood

// ────────────────────────────────────────────────────────────────────
// Tenant role (driven by invitation; protected from inline edit per v1.6)
// ────────────────────────────────────────────────────────────────────
export type TenantRole = 'provider' | 'client' | 'admin' | 'reviewer';

// ────────────────────────────────────────────────────────────────────
// Density — drives layout token selection (net-new in v0.2)
//
// Use compact on operational surfaces:
//   /portal/dashboard, /portal/calendar, /portal/reports, queue tables,
//   AI/OCR review panels.
// Use comfortable on guided surfaces:
//   /, /login, /activate, /portal/onboarding, /portal/entra-a-tu-espacio,
//   settings, billing, marketing.
// ────────────────────────────────────────────────────────────────────
export type Density = 'compact' | 'comfortable';

// ────────────────────────────────────────────────────────────────────
// Compliance period
// ────────────────────────────────────────────────────────────────────
export interface CompliancePeriod {
  year: number;
  month: number;   // 1–12
}

export type PeriodHealth = 'complete' | 'partial' | 'pending' | 'overdue' | 'current';

// ────────────────────────────────────────────────────────────────────
// Report status (extends 1.6 — see lib/mock/reports.ts)
// ────────────────────────────────────────────────────────────────────
export type ReportStatus =
  | 'ready'         // Generated; can download / send
  | 'generating'    // Async job in progress
  | 'needs_review'  // Has flagged items requiring human signoff
  | 'blocked'       // Data integrity issue — cannot generate
  | 'unavailable';  // Period not yet closed
