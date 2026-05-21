import type { CalendarItem } from "@/lib/api/portal";
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
  anatomy: string;
  where_to_obtain: string;
  common_errors: string[];
};

export const URGENT_STATES: ReadonlySet<DocumentStateCode> = new Set([
  "rejected",
  "expired",
  "needs_review",
]);
