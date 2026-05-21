/**
 * Phase 7 — typed wrapper over the admin operations API.
 *
 * Every endpoint requires an ``internal_admin`` JWT (issued by
 * ``POST /api/v1/auth/login``). The token is pulled from
 * ``readAdminSession()`` so callers don't pass it explicitly.
 */

import { readAdminSession } from "@/lib/session/admin";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export class AdminApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "AdminApiError";
  }
}

async function fetchJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const session = readAdminSession();
  if (!session?.access_token) {
    throw new AdminApiError(401, "No active admin session.");
  }
  const headers = new Headers(init.headers ?? {});
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Authorization", `Bearer ${session.access_token}`);
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new AdminApiError(response.status, detail || response.statusText);
  }
  if (response.status === 204) return undefined as unknown as T;
  return (await response.json()) as T;
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

export type AdminOverview = {
  clients_total: number;
  vendors_total: number;
  active_workspaces_total: number;
  pending_reviews_total: number;
  rejected_or_correction_total: number;
  recent_submissions_total: number;
  recent_audit_events_total: number;
};

export async function getAdminOverview(): Promise<AdminOverview> {
  return fetchJson<AdminOverview>("/api/v1/admin/overview");
}

// ---------------------------------------------------------------------------
// Clients
// ---------------------------------------------------------------------------

export type AdminClient = {
  id: string;
  name: string;
  rfc: string | null;
  responsible_name: string | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
};

type ListResponse<T> = { items: T[]; total: number };

export async function listClients(): Promise<ListResponse<AdminClient>> {
  return fetchJson("/api/v1/admin/clients");
}

export async function getClient(id: string): Promise<AdminClient> {
  return fetchJson(`/api/v1/admin/clients/${id}`);
}

export async function createClient(body: {
  name: string;
  rfc?: string | null;
  responsible_name?: string | null;
  status?: string;
}): Promise<AdminClient> {
  return fetchJson("/api/v1/admin/clients", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateClient(
  id: string,
  body: Partial<{
    name: string;
    rfc: string | null;
    responsible_name: string | null;
    status: string;
  }>,
): Promise<AdminClient> {
  return fetchJson(`/api/v1/admin/clients/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Vendors
// ---------------------------------------------------------------------------

export type AdminVendor = {
  id: string;
  client_id: string;
  name: string;
  rfc: string;
  contact_name: string | null;
  contact_email: string | null;
  repse_id: string | null;
  persona_type: "moral" | "fisica" | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
};

export async function listVendors(params?: {
  client_id?: string;
}): Promise<ListResponse<AdminVendor>> {
  const qs = new URLSearchParams();
  if (params?.client_id) qs.set("client_id", params.client_id);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/vendors${suffix}`);
}

export async function getVendor(id: string): Promise<AdminVendor> {
  return fetchJson(`/api/v1/admin/vendors/${id}`);
}

export async function createVendor(body: {
  client_id: string;
  name: string;
  rfc: string;
  contact_name?: string | null;
  contact_email?: string | null;
  repse_id?: string | null;
  persona_type?: "moral" | "fisica" | null;
  status?: string;
}): Promise<AdminVendor> {
  return fetchJson("/api/v1/admin/vendors", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateVendor(
  id: string,
  body: Partial<{
    name: string;
    contact_name: string | null;
    contact_email: string | null;
    repse_id: string | null;
    persona_type: "moral" | "fisica" | null;
    status: string;
  }>,
): Promise<AdminVendor> {
  return fetchJson(`/api/v1/admin/vendors/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Workspaces
// ---------------------------------------------------------------------------

export type AdminWorkspace = {
  id: string;
  client_id: string;
  vendor_id: string;
  contract_id: string | null;
  owner_user_id: string | null;
  persona_type: string;
  display_name: string | null;
  filial_name: string | null;
  onboarding_completed_at: string | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
};

export async function listWorkspaces(params?: {
  client_id?: string;
  vendor_id?: string;
}): Promise<ListResponse<AdminWorkspace>> {
  const qs = new URLSearchParams();
  if (params?.client_id) qs.set("client_id", params.client_id);
  if (params?.vendor_id) qs.set("vendor_id", params.vendor_id);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/workspaces${suffix}`);
}

export async function getWorkspace(id: string): Promise<AdminWorkspace> {
  return fetchJson(`/api/v1/admin/workspaces/${id}`);
}

export async function updateWorkspace(
  id: string,
  body: Partial<{
    status: string;
    owner_user_id: string | null;
    display_name: string | null;
    filial_name: string | null;
  }>,
): Promise<AdminWorkspace> {
  return fetchJson(`/api/v1/admin/workspaces/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Metadata workbook exports
// ---------------------------------------------------------------------------

export type MetadataExportItem = {
  id: string;
  submission_id: string;
  document_id: string | null;
  client_id: string | null;
  result: "completed" | "skipped" | "failed" | string;
  severity: string;
  document_type_code: string | null;
  client_name: string | null;
  vendor_name: string | null;
  requirement_name: string | null;
  period_key: string | null;
  original_filename: string | null;
  output_path: string | null;
  latest_path: string | null;
  master_path: string | null;
  file_exists: boolean;
  preview_available: boolean;
  master_available: boolean;
  reason: string | null;
  created_at: string;
};

export type MetadataExportList = {
  items: MetadataExportItem[];
  total: number;
  limit: number;
};

export type MetadataExportSheetPreview = {
  name: string;
  rows: string[][];
};

export type MetadataExportPreview = {
  export: MetadataExportItem;
  sheets: MetadataExportSheetPreview[];
};

export type ClientMasterMetadataPreview = {
  client_id: string;
  client_name: string;
  master_path: string;
  sheets: MetadataExportSheetPreview[];
};

export async function listMetadataExports(params?: {
  result?: "completed" | "skipped" | "failed";
  limit?: number;
}): Promise<MetadataExportList> {
  const qs = new URLSearchParams();
  if (params?.result) qs.set("result", params.result);
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/metadata-exports${suffix}`);
}

export async function getMetadataExportPreview(
  id: string,
): Promise<MetadataExportPreview> {
  return fetchJson(`/api/v1/admin/metadata-exports/${id}`);
}

export async function downloadMetadataExport(id: string): Promise<Blob> {
  const session = readAdminSession();
  if (!session?.access_token) {
    throw new AdminApiError(401, "No active admin session.");
  }
  const response = await fetch(
    `${API_BASE_URL}/api/v1/admin/metadata-exports/${id}/download`,
    { headers: { Authorization: `Bearer ${session.access_token}` } },
  );
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new AdminApiError(response.status, detail || response.statusText);
  }
  return response.blob();
}

export async function getClientMasterMetadataPreview(
  clientId: string,
): Promise<ClientMasterMetadataPreview> {
  return fetchJson(`/api/v1/admin/metadata-exports/clients/${clientId}/master`);
}

export async function downloadClientMasterMetadata(
  clientId: string,
): Promise<Blob> {
  const session = readAdminSession();
  if (!session?.access_token) {
    throw new AdminApiError(401, "No active admin session.");
  }
  const response = await fetch(
    `${API_BASE_URL}/api/v1/admin/metadata-exports/clients/${clientId}/master/download`,
    { headers: { Authorization: `Bearer ${session.access_token}` } },
  );
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new AdminApiError(response.status, detail || response.statusText);
  }
  return response.blob();
}

// ---------------------------------------------------------------------------
// Requirements
// ---------------------------------------------------------------------------

export type AdminRequirementVersion = {
  id: string;
  version: number;
  legal_basis: string | null;
  applicability_rule: string | null;
  minimum_validation: string | null;
  automatic_signals: string | null;
  human_review_required: boolean;
  missing_state: string | null;
  temporal_rule: string | null;
  source_url: string | null;
  implementation_notes: string | null;
  required: boolean;
  effective_from: string | null;
  effective_to: string | null;
};

export type AdminRequirement = {
  id: string;
  code: string;
  name: string;
  institution_id: string;
  load_type: string;
  frequency: string;
  risk_level: string;
  is_active: boolean;
  current_version: number;
  version: AdminRequirementVersion | null;
  created_at: string | null;
  updated_at: string | null;
};

export async function listRequirements(params?: {
  institution_id?: string;
  is_active?: boolean;
}): Promise<ListResponse<AdminRequirement>> {
  const qs = new URLSearchParams();
  if (params?.institution_id) qs.set("institution_id", params.institution_id);
  if (params?.is_active !== undefined) qs.set("is_active", String(params.is_active));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/requirements${suffix}`);
}

export async function getRequirement(id: string): Promise<AdminRequirement> {
  return fetchJson(`/api/v1/admin/requirements/${id}`);
}

export async function createRequirement(body: {
  code: string;
  name: string;
  institution_id: string;
  load_type: string;
  frequency: string;
  risk_level?: string;
  is_active?: boolean;
  legal_basis?: string | null;
  applicability_rule?: string | null;
  minimum_validation?: string | null;
  automatic_signals?: string | null;
  human_review_required?: boolean;
  missing_state?: string | null;
  temporal_rule?: string | null;
  source_url?: string | null;
  implementation_notes?: string | null;
  required?: boolean;
}): Promise<AdminRequirement> {
  return fetchJson("/api/v1/admin/requirements", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateRequirement(
  id: string,
  body: Partial<{
    name: string;
    institution_id: string;
    load_type: string;
    frequency: string;
    risk_level: string;
    is_active: boolean;
  }>,
): Promise<AdminRequirement> {
  return fetchJson(`/api/v1/admin/requirements/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Periods + calendar
// ---------------------------------------------------------------------------

export type AdminPeriod = {
  id: string;
  code: string;
  period_key: string | null;
  year: number | null;
  month: number | null;
  period_type: string;
  starts_on: string | null;
  ends_on: string | null;
  due_on: string | null;
};

export async function listPeriods(params?: {
  year?: number;
  period_type?: string;
  limit?: number;
}): Promise<ListResponse<AdminPeriod>> {
  const qs = new URLSearchParams();
  if (params?.year !== undefined) qs.set("year", String(params.year));
  if (params?.period_type) qs.set("period_type", params.period_type);
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/periods${suffix}`);
}

export type AdminCalendarMonth = {
  month: number;
  expected_total: number;
  institutions: { institution: string; expected: number }[];
};

export type AdminCalendar = {
  metadata: { source: string; version: string };
  year: number;
  persona_type: "moral" | "fisica";
  months: AdminCalendarMonth[];
};

export async function getAdminCalendar(params?: {
  year?: number;
  persona_type?: "moral" | "fisica";
}): Promise<AdminCalendar> {
  const qs = new URLSearchParams();
  if (params?.year !== undefined) qs.set("year", String(params.year));
  if (params?.persona_type) qs.set("persona_type", params.persona_type);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/calendar${suffix}`);
}

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------

export type AdminAuditLogItem = {
  id: string;
  actor_id: string | null;
  actor_type: string;
  action: string;
  entity_type: string;
  entity_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  event_metadata: Record<string, unknown> | null;
  created_at: string;
};

export type AdminAuditLogResponse = {
  items: AdminAuditLogItem[];
  total: number;
  limit: number;
};

export async function listAuditLog(params?: {
  actor_id?: string;
  actor_type?: string;
  action?: string;
  entity_type?: string;
  entity_id?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
}): Promise<AdminAuditLogResponse> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      qs.set(key, String(value));
    }
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/audit-log${suffix}`);
}

// ---------------------------------------------------------------------------
// Contact requests (P0-3 follow-up)
// ---------------------------------------------------------------------------

export type ContactRequestStatus =
  | "new"
  | "reviewed"
  | "contacted"
  | "closed";

export interface AdminContactRequest {
  id: string;
  name: string;
  email: string;
  company: string | null;
  role: string | null;
  message: string;
  source: string;
  status: ContactRequestStatus;
  ip_hash: string | null;
  user_agent: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminContactRequestList {
  items: AdminContactRequest[];
  total: number;
  limit: number;
  offset: number;
}

export async function listContactRequests(params?: {
  status?: ContactRequestStatus;
  limit?: number;
  offset?: number;
}): Promise<AdminContactRequestList> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === null) continue;
    const asString = String(value);
    if (!asString) continue;
    qs.set(key, asString);
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/contact-requests${suffix}`);
}

export async function updateContactRequestStatus(
  id: string,
  status: ContactRequestStatus,
): Promise<AdminContactRequest> {
  return fetchJson(`/api/v1/admin/contact-requests/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

// ---------------------------------------------------------------------------
// Feedback reports (bug + improvement reports from the Reportar launcher)
// ---------------------------------------------------------------------------

export type FeedbackKind = "bug" | "improvement";
export type FeedbackSource = "authenticated" | "public";
export type FeedbackStatus =
  | "new"
  | "triaged"
  | "in_progress"
  | "resolved"
  | "wont_fix";
export type FeedbackSlackDeliveryStatus =
  | "pending"
  | "sent"
  | "failed"
  | "skipped";

export interface AdminFeedbackReport {
  id: string;
  kind: FeedbackKind;
  description: string;
  source: FeedbackSource;
  is_public: boolean;
  status: FeedbackStatus;
  url: string | null;
  path: string | null;
  viewport: string | null;
  user_agent: string | null;
  console_logs: string | null;
  user_id: string | null;
  user_email: string | null;
  user_full_name: string | null;
  user_roles: string | null;
  contact_email: string | null;
  ip_hash: string | null;
  screenshot_storage_key: string | null;
  screenshot_size_bytes: number | null;
  /** Presigned download URL — populated on detail responses when the
   *  storage backend supports pre-signing (S3/R2). Null on local. */
  screenshot_url: string | null;
  slack_message_ts: string | null;
  slack_delivery_status: FeedbackSlackDeliveryStatus;
  slack_delivery_error: string | null;
  resolution_note: string | null;
  triaged_by_user_id: string | null;
  triaged_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminFeedbackReportList {
  items: AdminFeedbackReport[];
  total: number;
  limit: number;
  offset: number;
}

export async function listFeedbackReports(params?: {
  status?: FeedbackStatus;
  kind?: FeedbackKind;
  source?: FeedbackSource;
  limit?: number;
  offset?: number;
}): Promise<AdminFeedbackReportList> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === null) continue;
    const asString = String(value);
    if (!asString) continue;
    qs.set(key, asString);
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/feedback-reports${suffix}`);
}

export async function getFeedbackReport(
  id: string,
): Promise<AdminFeedbackReport> {
  return fetchJson(`/api/v1/admin/feedback-reports/${id}`);
}

export async function updateFeedbackReportStatus(
  id: string,
  payload: { status: FeedbackStatus; resolution_note?: string | null },
): Promise<AdminFeedbackReport> {
  return fetchJson(`/api/v1/admin/feedback-reports/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
