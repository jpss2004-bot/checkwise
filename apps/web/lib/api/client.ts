/**
 * Phase 8 — typed wrapper over the client portal API.
 *
 * Every endpoint requires a JWT carrying the ``client_admin`` role
 * (or ``internal_admin`` for support visibility). The token is
 * pulled from ``readAdminSession()`` — same staff JWT used by the
 * admin + reviewer surfaces. Provider portal pages keep their own
 * cookie-based path; this client is staff-only.
 */

import { readAdminSession } from "@/lib/session/admin";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ClientApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ClientApiError";
  }
}

async function fetchJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const session = readAdminSession();
  if (!session?.access_token) {
    throw new ClientApiError(401, "No active staff session.");
  }
  const headers = new Headers(init.headers ?? {});
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Authorization", `Bearer ${session.access_token}`);
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ClientApiError(response.status, detail || response.statusText);
  }
  if (response.status === 204) return undefined as unknown as T;
  return (await response.json()) as T;
}

function qs(params?: Record<string, string | number | boolean | undefined | null>): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    sp.set(key, String(value));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ClientMe = {
  user_id: string;
  email: string;
  roles: string[];
  visible_client_ids: string[];
  default_client_id: string | null;
};

export type ClientOverview = {
  client_id: string;
  client_name: string;
  vendors_total: number;
  active_workspaces_total: number;
  compliance_pct: number;
  green_count: number;
  yellow_count: number;
  red_count: number;
  pending_reviews_total: number;
  rejected_or_correction_total: number;
  missing_required_total: number;
  due_soon_total: number;
  recent_submissions_total: number;
  last_activity_at: string | null;
};

export type ClientVendorRow = {
  vendor_id: string;
  workspace_id: string;
  vendor_name: string;
  vendor_rfc: string | null;
  persona_type: string | null;
  workspace_status: string;
  compliance_pct: number;
  semaphore_level: "green" | "yellow" | "red";
  pending_reviews_count: number;
  missing_required_count: number;
  rejected_or_correction_count: number;
  due_soon_count: number;
  last_submission_at: string | null;
  last_review_at: string | null;
};

export type ClientVendorListResponse = {
  client_id: string;
  items: ClientVendorRow[];
  total: number;
};

export type ClientVendorDetail = {
  client_id: string;
  vendor_id: string;
  workspace_id: string;
  vendor: Record<string, unknown>;
  workspace: Record<string, unknown>;
  onboarding_summary: {
    total_required: number;
    completed: number;
    in_review: number;
    needs_action: number;
    optional_pending: number;
    completion_pct: number;
    is_gate_satisfied: boolean;
  };
  document_state_counts: {
    approved: number;
    in_review: number;
    uploaded: number;
    pending: number;
    needs_review: number;
    rejected: number;
    expired: number;
    exception: number;
  };
  semaphore: {
    level: "green" | "yellow" | "red";
    label: string;
    reason: string;
    compliance_pct: number;
    total_tracked: number;
    on_track: number;
  };
  suggested_actions: Array<{
    id: string;
    type: string;
    title: string;
    body: string;
    priority: "low" | "medium" | "high";
    href: string;
    requirement_code: string | null;
    period_key: string | null;
  }>;
  attention_today: Array<{
    id: string;
    title: string;
    institution: string;
    state: string;
    due_in_days: number | null;
    href: string;
  }>;
  upcoming_deadlines: Array<{
    id: string;
    title: string;
    institution: string;
    period_key: string | null;
    due_month: number;
    state: string;
    href: string;
  }>;
  recent_submissions: Array<{
    submission_id: string;
    requirement_code: string | null;
    requirement_name: string | null;
    period_key: string | null;
    status: string;
    filename: string | null;
    submitted_at: string;
    supersedes_submission_id: string | null;
    superseded_by_submission_id: string | null;
  }>;
  recent_reviewer_notes: Array<{
    submission_id: string;
    result: string;
    message: string | null;
    occurred_at: string;
  }>;
};

export type ClientCalendarItem = {
  vendor_id: string;
  workspace_id: string;
  vendor_name: string;
  requirement_code: string | null;
  requirement_name: string;
  institution: string;
  frequency: string;
  period_key: string | null;
  period_label: string;
  status: string;
  submission_id: string | null;
  deadline_iso: string;
  risk_level: string | null;
  href: string;
};

export type ClientCalendarMonth = {
  month: number;
  month_label: string;
  vendors_total: number;
  due_total: number;
  approved_total: number;
  pending_total: number;
  rejected_or_correction_total: number;
  missing_total: number;
  due_soon_total: number;
  items: ClientCalendarItem[];
};

export type ClientCalendar = {
  metadata: { source: string; version: string };
  client_id: string;
  year: number;
  months: ClientCalendarMonth[];
};

export type ClientSubmissionItem = {
  submission_id: string;
  vendor_id: string;
  vendor_name: string;
  requirement_code: string | null;
  requirement_name: string | null;
  /** Phase 3 / Slice 3A — institution code (``sat``, ``imss``,
   *  ``infonavit``, ``stps_repse``, ``interno_cliente``). Surfaced so
   *  the client portal table can render an institution column AND so
   *  the new ``?institution=`` filter on this endpoint stays
   *  round-trippable. */
  institution: string | null;
  period_key: string | null;
  status: string;
  filename: string | null;
  submitted_at: string;
  reviewed_at: string | null;
  reviewer_note: string | null;
  supersedes_submission_id: string | null;
  superseded_by_submission_id: string | null;
};

export type ClientSubmissionsResponse = {
  client_id: string;
  items: ClientSubmissionItem[];
  total: number;
};

export type ClientActivityItem = {
  id: string;
  occurred_at: string;
  actor_type: string;
  action: string;
  entity_type: string;
  entity_id: string;
  vendor_id: string | null;
  vendor_name: string | null;
  summary: string;
};

export type ClientActivityResponse = {
  client_id: string;
  items: ClientActivityItem[];
  total: number;
  limit: number;
};

export type ClientNotificationItem = {
  id: string;
  notification_type: string;
  title: string;
  body: string;
  action_url: string | null;
  vendor_id: string | null;
  vendor_name: string | null;
  submission_id: string | null;
  payload: Record<string, unknown> | null;
  read_at: string | null;
  created_at: string;
};

export type ClientNotificationsResponse = {
  client_id: string;
  items: ClientNotificationItem[];
  total: number;
  unread_count: number;
  limit: number;
};

export type ClientNotificationSummary = {
  client_id: string;
  unread_count: number;
};

export type ClientMetadataDocument = {
  cliente: string;
  proveedor: string;
  periodo: string;
  nombre_documento: string;
  tipo_documento: string;
  subtipo: string;
  institucion: string;
  fecha_principal: string;
  participantes: string;
  descripcion: string;
  anexos: string;
  etiquetas: string;
  archivo_pdf: string;
};

export type ClientMetadataResponse = {
  client_id: string;
  client_name: string;
  master_available: boolean;
  master_path: string | null;
  documents: ClientMetadataDocument[];
};

// ---------------------------------------------------------------------------
// Calls
// ---------------------------------------------------------------------------

export async function getClientMe(): Promise<ClientMe> {
  return fetchJson<ClientMe>("/api/v1/client/me");
}

export async function getClientOverview(params?: {
  client_id?: string;
  year?: number;
}): Promise<ClientOverview> {
  return fetchJson<ClientOverview>(`/api/v1/client/overview${qs(params)}`);
}

export async function listClientVendors(params?: {
  client_id?: string;
  status?: string;
  semaphore_level?: "green" | "yellow" | "red";
  search?: string;
  limit?: number;
}): Promise<ClientVendorListResponse> {
  return fetchJson<ClientVendorListResponse>(`/api/v1/client/vendors${qs(params)}`);
}

export async function getClientVendorDetail(
  vendor_id: string,
  params?: { client_id?: string; year?: number },
): Promise<ClientVendorDetail> {
  return fetchJson<ClientVendorDetail>(
    `/api/v1/client/vendors/${vendor_id}${qs(params)}`,
  );
}

export async function getClientCalendar(params?: {
  client_id?: string;
  year?: number;
}): Promise<ClientCalendar> {
  return fetchJson<ClientCalendar>(`/api/v1/client/calendar${qs(params)}`);
}

export async function listClientSubmissions(params?: {
  client_id?: string;
  vendor_id?: string;
  status?: string;
  requirement_code?: string;
  period_key?: string;
  /** Phase 3 / Slice 3A — institution code filter. Pass the canonical
   *  lowercase code (``sat`` / ``imss`` / ``infonavit`` / ``stps_repse``
   *  / ``interno_cliente``). Unknown codes return an empty list. */
  institution?: string;
  limit?: number;
}): Promise<ClientSubmissionsResponse> {
  return fetchJson<ClientSubmissionsResponse>(
    `/api/v1/client/submissions${qs(params)}`,
  );
}

export async function listClientActivity(params?: {
  client_id?: string;
  limit?: number;
}): Promise<ClientActivityResponse> {
  return fetchJson<ClientActivityResponse>(`/api/v1/client/activity${qs(params)}`);
}

export async function getClientNotificationSummary(params?: {
  client_id?: string;
}): Promise<ClientNotificationSummary> {
  return fetchJson<ClientNotificationSummary>(
    `/api/v1/client/notifications/summary${qs(params)}`,
  );
}

export async function listClientNotifications(params?: {
  client_id?: string;
  unread_only?: boolean;
  limit?: number;
}): Promise<ClientNotificationsResponse> {
  return fetchJson<ClientNotificationsResponse>(
    `/api/v1/client/notifications${qs(params)}`,
  );
}

export async function markClientNotificationRead(
  notificationId: string,
  params?: { client_id?: string },
): Promise<ClientNotificationItem> {
  return fetchJson<ClientNotificationItem>(
    `/api/v1/client/notifications/${notificationId}/read${qs(params)}`,
    { method: "POST" },
  );
}

export async function markAllClientNotificationsRead(params?: {
  client_id?: string;
}): Promise<ClientNotificationSummary> {
  return fetchJson<ClientNotificationSummary>(
    `/api/v1/client/notifications/read-all${qs(params)}`,
    { method: "POST" },
  );
}

export async function getClientMetadata(params?: {
  client_id?: string;
}): Promise<ClientMetadataResponse> {
  return fetchJson<ClientMetadataResponse>(`/api/v1/client/metadata${qs(params)}`);
}

export async function downloadClientMetadata(params?: {
  client_id?: string;
}): Promise<Blob> {
  const session = readAdminSession();
  if (!session?.access_token) {
    throw new ClientApiError(401, "No active staff session.");
  }
  const response = await fetch(
    `${API_BASE_URL}/api/v1/client/metadata/download${qs(params)}`,
    {
      headers: {
        Authorization: `Bearer ${session.access_token}`,
      },
    },
  );
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ClientApiError(response.status, detail || response.statusText);
  }
  return response.blob();
}
