/**
 * Typed wrapper over the V1.2 portal + compliance endpoints.
 *
 * Auth resolution (CheckWise 1.8):
 *   1. ``Authorization: Bearer <jwt>`` from the admin/user session in
 *      localStorage — primary, cross-origin safe.
 *   2. ``credentials: "include"`` so the portal session cookie still
 *      gets sent when the browser allows it.
 *   3. Legacy ``X-Workspace-Token`` header when the caller passes a
 *      PortalSession with a real token (kept for backward compat).
 */

import { readAdminSession } from "@/lib/session/admin";
import type { PersonaType, PortalSession } from "@/lib/session/portal";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type RequirementStatus =
  | "pendiente"
  | "recibido"
  | "pendiente_revision"
  | "prevalidado"
  | "posible_mismatch"
  | "aprobado"
  | "rechazado"
  | "vencido"
  | "no_aplica"
  | "requiere_aclaracion"
  | "excepcion_legal";

export type OnboardingItem = {
  code: string;
  name: string;
  institution: string;
  required: boolean;
  note: string | null;
  status: RequirementStatus;
  submission_id: string | null;
  submitted_at: string | null;
  /** Original PDF filename of the attached document, when one exists. */
  filename: string | null;
  /** Phase 5 — backend-owned UX enrichment. ``why`` and ``format`` are
   *  static catalog copy; ``next_action`` and ``reviewer_note`` are
   *  computed against the slot's current submission (lineage-aware). */
  why: string;
  format: string;
  next_action: string;
  reviewer_note: string | null;
};

export type OnboardingSection = {
  section: string;
  items: OnboardingItem[];
  received: number;
  required: number;
};

export type OnboardingSummary = {
  metadata: { source: string; version: string };
  workspace_id: string;
  persona_type: PersonaType;
  sections: OnboardingSection[];
  summary: {
    received_required: number;
    total_required: number;
    completion_pct: number;
    completed: boolean;
    onboarding_completed_at: string | null;
  };
};

export type CalendarItem = {
  code: string;
  name: string;
  frequency: "mensual" | "bimestral" | "cuatrimestral" | "anual";
  period_label: string;
  period_key: string;
  status: RequirementStatus;
  submission_id: string | null;
  /** Phase 5 — backend-owned UX enrichment. */
  required_document: string;
  due_month: number;
  /** ISO date (``YYYY-MM-DD``). Conventional day-17 cutoff for monthly /
   *  bimestral / cuatrimestral slots; the SAT annual slot uses day 30. */
  deadline_iso: string;
  suggested_action: string;
  /** Canonical upload URL ready to use as ``<Link href>``. */
  href: string;
};

export type CalendarInstitution = {
  institution: string;
  items: CalendarItem[];
  received: number;
  expected: number;
};

export type CalendarMonth = {
  month: number;
  expected: number;
  received: number;
  institutions: CalendarInstitution[];
};

export type CalendarPayload = {
  metadata: { source: string; version: string };
  workspace_id: string;
  year: number;
  persona_type: PersonaType;
  months: CalendarMonth[];
};

export type AccessRequest = {
  client_name: string;
  filial_name?: string | null;
  vendor_name: string;
  vendor_rfc: string;
  persona_type: PersonaType;
  contract_reference?: string | null;
};

export type AccessResponse = PortalSession & { note: string };

async function fetchJson<T>(
  path: string,
  init: RequestInit = {},
  session?: PortalSession,
): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  // 1. Bearer JWT — the cross-origin-safe primary path.
  const adminSession = readAdminSession();
  if (adminSession?.access_token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${adminSession.access_token}`);
  }
  // 2. Legacy X-Workspace-Token still supported when a caller passes one.
  if (
    session &&
    session.access_token &&
    session.access_token !== "cookie-managed"
  ) {
    headers.set("X-Workspace-Token", session.access_token);
  }
  // 3. credentials: "include" so the cookie tags along when the browser allows.
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new PortalApiError(response.status, detail || response.statusText);
  }
  return (await response.json()) as T;
}

export class PortalApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "PortalApiError";
  }
}

export async function createPortalAccess(
  payload: AccessRequest,
): Promise<AccessResponse> {
  return await fetchJson<AccessResponse>("/api/v1/portal/access", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getOnboarding(
  session: PortalSession,
): Promise<OnboardingSummary> {
  return await fetchJson<OnboardingSummary>(
    `/api/v1/portal/workspaces/${session.workspace_id}/onboarding`,
    { method: "GET" },
    session,
  );
}

export async function getCalendar(
  session: PortalSession,
  year: number,
): Promise<CalendarPayload> {
  return await fetchJson<CalendarPayload>(
    `/api/v1/portal/workspaces/${session.workspace_id}/calendar?year=${year}`,
    { method: "GET" },
    session,
  );
}

export type SubmissionRequirementSummary = {
  code: string | null;
  name: string | null;
  institution: string | null;
  load_type: string | null;
  requirement_code: string | null;
  requirement_version: number | null;
};

export type SubmissionPeriodSummary = {
  code: string | null;
  period_key: string | null;
  period_type: string | null;
};

export type SubmissionDocumentSummary = {
  document_id: string;
  filename: string;
  sha256: string;
  size_bytes: number;
  page_count: number | null;
  has_text: boolean | null;
  is_probably_scanned: boolean | null;
  detected_institution: string | null;
  detected_document_type: string | null;
  mismatch_reason: string | null;
};

export type SubmissionReason = {
  rule_code: string;
  severity: string;
  message: string | null;
  requires_human_review: boolean;
};

export type SubmissionEvent = {
  event_type: string;
  result: string;
  severity: string;
  message: string | null;
  confidence: number | null;
  actor_type: string;
  occurred_at: string;
};

export type SubmissionHistoryEntry = {
  from_status: string | null;
  to_status: string;
  reason: string | null;
  actor: string;
  occurred_at: string;
};

export type SubmissionPreviousAttempt = {
  submission_id: string;
  status: string;
  submitted_at: string;
  filename: string | null;
};

export type SubmissionSuggestedAction =
  | "reupload"
  | "verify_and_reupload"
  | "wait_for_review"
  | "no_action";

export type SubmissionDetail = {
  submission_id: string;
  workspace_id: string;
  status: RequirementStatus;
  load_type: string;
  submitted_at: string;
  comments: string | null;
  requirement: SubmissionRequirementSummary;
  period: SubmissionPeriodSummary;
  document: SubmissionDocumentSummary | null;
  reasons: SubmissionReason[];
  events: SubmissionEvent[];
  history: SubmissionHistoryEntry[];
  previous_attempts: SubmissionPreviousAttempt[];
  suggested_action: SubmissionSuggestedAction;
  /** Phase 4 — id of the prior submission this one replaces, or null. */
  supersedes_submission_id: string | null;
  /** Phase 4 — id of the newer submission that replaced this one, or null. */
  superseded_by_submission_id: string | null;
};

export async function getSubmissionDetail(
  session: PortalSession,
  submissionId: string,
): Promise<SubmissionDetail> {
  return await fetchJson<SubmissionDetail>(
    `/api/v1/portal/workspaces/${session.workspace_id}/submissions/${submissionId}`,
    { method: "GET" },
    session,
  );
}

export type CompleteOnboardingResponse = {
  workspace_id: string;
  onboarding_completed_at: string;
  expediente_status: "complete";
};

/**
 * Mark the provider's initial expediente as complete.
 *
 * Backend gates ownership via the same JWT/cookie chain — the user
 * can only complete their own workspace, never another company's.
 * Idempotent on the server side: re-calling keeps the original
 * timestamp.
 */
export async function completeOnboarding(
  session: PortalSession,
): Promise<CompleteOnboardingResponse> {
  return await fetchJson<CompleteOnboardingResponse>(
    `/api/v1/portal/workspaces/${session.workspace_id}/complete-onboarding`,
    { method: "POST" },
    session,
  );
}

// ---------------------------------------------------------------------------
// Provider dashboard read model (Phase 4)
// ---------------------------------------------------------------------------

export type DashboardSemaphoreLevel = "green" | "yellow" | "red";
export type DashboardActionPriority = "low" | "medium" | "high";
export type DashboardActionType =
  | "complete_onboarding"
  | "reupload"
  | "verify_mismatch"
  | "clarify"
  | "upcoming";

export type DashboardOnboardingSummary = {
  total_required: number;
  completed: number;
  in_review: number;
  needs_action: number;
  optional_pending: number;
  completion_pct: number;
  is_gate_satisfied: boolean;
};

export type DashboardDocumentStateCounts = {
  approved: number;
  in_review: number;
  uploaded: number;
  pending: number;
  needs_review: number;
  rejected: number;
  expired: number;
  exception: number;
};

export type DashboardSemaphore = {
  level: DashboardSemaphoreLevel;
  label: string;
  reason: string;
  compliance_pct: number;
  total_tracked: number;
  on_track: number;
};

export type DashboardSuggestedAction = {
  id: string;
  type: DashboardActionType;
  title: string;
  body: string;
  priority: DashboardActionPriority;
  href: string;
  requirement_code: string | null;
  period_key: string | null;
};

export type DashboardAttentionItem = {
  id: string;
  title: string;
  institution: string;
  state: string;
  due_in_days: number | null;
  href: string;
};

export type DashboardUpcomingDeadline = {
  id: string;
  title: string;
  institution: string;
  period_key: string | null;
  due_month: number;
  state: string;
  href: string;
};

export type DashboardPayload = {
  workspace_id: string;
  persona_type: string;
  onboarding_summary: DashboardOnboardingSummary;
  document_state_counts: DashboardDocumentStateCounts;
  semaphore: DashboardSemaphore;
  suggested_actions: DashboardSuggestedAction[];
  attention_today: DashboardAttentionItem[];
  upcoming_deadlines: DashboardUpcomingDeadline[];
};

export async function getDashboard(
  session: PortalSession,
): Promise<DashboardPayload> {
  return await fetchJson<DashboardPayload>(
    `/api/v1/portal/workspaces/${session.workspace_id}/dashboard`,
    { method: "GET" },
    session,
  );
}


export type DuplicateCheck = {
  exists: boolean;
  submission_id: string | null;
  status: string | null;
  submitted_at: string | null;
  requirement_name: string | null;
  period_label: string | null;
  filename: string | null;
};

export async function checkDuplicateBySha256(
  session: PortalSession,
  sha256: string,
): Promise<DuplicateCheck> {
  return await fetchJson<DuplicateCheck>(
    `/api/v1/portal/workspaces/${session.workspace_id}/duplicate-check?sha256=${encodeURIComponent(sha256)}`,
    { method: "GET" },
    session,
  );
}

export const INSTITUTION_LABELS: Record<string, string> = {
  sat: "SAT",
  imss: "IMSS",
  infonavit: "INFONAVIT",
  stps_repse: "STPS / REPSE",
  interno_cliente: "Interno / Cliente",
};

export const MONTH_LABELS_ES: Record<number, string> = {
  1: "Enero",
  2: "Febrero",
  3: "Marzo",
  4: "Abril",
  5: "Mayo",
  6: "Junio",
  7: "Julio",
  8: "Agosto",
  9: "Septiembre",
  10: "Octubre",
  11: "Noviembre",
  12: "Diciembre",
};

export const MONTH_LABELS_SHORT_ES: readonly string[] = [
  "Ene",
  "Feb",
  "Mar",
  "Abr",
  "May",
  "Jun",
  "Jul",
  "Ago",
  "Sep",
  "Oct",
  "Nov",
  "Dic",
];

/**
 * Map the canonical Spanish ``RequirementStatus`` to the UI's
 * ``DocumentStateCode``. Centralised here (Phase 5) so the onboarding
 * + calendar pages can render backend data without re-deriving the
 * mapping per surface. Exhaustive over the backend's status set.
 */
export function statusToDocumentStateCode(
  status: RequirementStatus,
): import("@/lib/types").DocumentStateCode {
  switch (status) {
    case "pendiente":
      return "pending";
    case "recibido":
      return "uploaded";
    case "pendiente_revision":
    case "prevalidado":
      return "in_review";
    case "aprobado":
      return "approved";
    case "rechazado":
      return "rejected";
    case "vencido":
      return "expired";
    case "posible_mismatch":
    case "requiere_aclaracion":
      return "needs_review";
    case "no_aplica":
    case "excepcion_legal":
      return "approved";
    default:
      return "empty";
  }
}
