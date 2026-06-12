/**
 * Legacy calendar shapes + Spanish month labels.
 *
 * Originally a full MOCK REPSE calendar; the live `/portal/calendar`
 * consumes the backend response, so the generated mock data
 * (buildMockCalendar / MOCK_CALENDAR_2026) was deleted on 2026-06-12.
 * What remains is the event shape `lib/api/portal-adapters.ts` still
 * adapts backend payloads into, plus the month labels it renders with.
 * New code should not import from here — prefer the backend payload
 * types in `lib/api/portal.ts`.
 */

import type { DocumentStateCode } from "@/lib/types";

export type CalendarInstitution = "sat" | "imss" | "infonavit" | "stps_repse";

export interface CalendarEvent {
  id: string;
  year: number;
  /** 1–12. */
  month: number;
  institution: CalendarInstitution;
  /** Display name shown on the cell + drawer header. */
  obligation: string;
  /** Required document name shown in the drawer. */
  required_document: string;
  /** Deadline ISO date (YYYY-MM-DD). */
  deadline_iso: string;
  /** Current REPSE state for this slot. */
  state: DocumentStateCode;
  /** Plain-language suggested action. */
  suggested_action: string;
  /** Frequency tag. */
  frequency: "monthly" | "bimonthly" | "four_monthly" | "annual";
}

export const MONTH_LABELS = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];
