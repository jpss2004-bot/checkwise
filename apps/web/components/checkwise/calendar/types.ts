import type { CalendarAcceptedDocument, CalendarItem } from "@/lib/api/portal";
import type { DocumentStateCode } from "@/lib/types";

export type CalendarInstitutionCode = "sat" | "imss" | "infonavit" | "stps_repse";

export const CALENDAR_INSTITUTIONS: CalendarInstitutionCode[] = [
  "sat",
  "imss",
  "infonavit",
  "stps_repse",
];

export type CalendarEntry = {
  id: string;
  year: number;
  month: number;
  institution: CalendarInstitutionCode;
  obligation: string;
  required_document: string;
  deadline_iso: string;
  state: DocumentStateCode;
  suggested_action: string;
  frequency: CalendarItem["frequency"];
  href: string;
  submission_id: string | null;
  /** Filename of the current submission's PDF, if any. Surfaced in the
   *  cell popover and drawer per Jorge feedback (2026-05-21). */
  filename: string | null;
  /** ISO timestamp of the current submission, if any. */
  submitted_at: string | null;
  anatomy: string;
  where_to_obtain: string;
  common_errors: string[];
  /** Session 3 (2026-05-21) — catalog v2 alternatives. Empty array
   *  on v1 rows; the drawer renders the legacy single disclosure
   *  when this is empty and N stacked disclosures (one per accepted
   *  doc) when populated. */
  accepts_documents: CalendarAcceptedDocument[];
};

export const URGENT_STATES: ReadonlySet<DocumentStateCode> = new Set([
  "rejected",
  "expired",
  "needs_review",
]);
