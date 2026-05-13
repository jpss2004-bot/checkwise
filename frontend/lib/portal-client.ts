/**
 * Typed wrapper over the V1.2 portal + compliance endpoints.
 *
 * All calls require a PortalSession (returned by `createPortalAccess`). The
 * session's `access_token` is sent as the `X-Workspace-Token` header.
 */

import type { PersonaType, PortalSession } from "@/lib/portal-session";

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
