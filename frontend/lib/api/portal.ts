/**
 * Typed wrapper over the V1.2 portal + compliance endpoints.
 *
 * All calls require a PortalSession (returned by `createPortalAccess`). The
 * session's `access_token` is sent as the `X-Workspace-Token` header.
 */

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
  if (session) {
    headers.set("X-Workspace-Token", session.access_token);
  }
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
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
