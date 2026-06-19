import type { CalendarAcceptedDocument, CalendarItem } from "@/lib/api/portal";
import type { DocumentStateCode } from "@/lib/types";

import type { CalendarRisk } from "./calendar-shared";

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
  /** Wave 1 / A1 — server-computed urgency tier from the shared
   *  ``calendar_item_risk`` classifier. ``state`` is the document status
   *  (pending/approved/…); ``risk_level`` is the orthogonal severity axis
   *  (overdue/due_soon/…) used for the drawer severity badge and, later,
   *  urgency sorting. Null only when a stale backend omits the field. */
  risk_level: CalendarRisk | null;
  suggested_action: string;
  frequency: CalendarItem["frequency"];
  /** Human label of the period this obligation *covers* (e.g. "IMSS
   *  Mayo"), distinct from the deadline month. Surfaced on the cell
   *  popover, mobile list, and drawer so the provider can tell which
   *  period each entry is for (§2.2). */
  period_label: string;
  period_key: string;
  href: string;
  submission_id: string | null;
  /** Filename of the current submission's PDF, if any. Surfaced in the
   *  cell popover and drawer per Jorge feedback (2026-05-21). */
  filename: string | null;
  /** ISO timestamp of the current submission, if any. */
  submitted_at: string | null;
  /** A4 — reviewer's reason on a bounced obligation (rejected /
   *  needs-clarification / mismatch); null otherwise. */
  reviewer_note: string | null;
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
  "possible_mismatch",
  "needs_review",
]);
