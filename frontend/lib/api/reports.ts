/**
 * Typed wrapper over the Reports API (backend/app/api/v1/reports.py).
 *
 * Phase 3.2 — entity-layer endpoints only. AI / streaming / conversation
 * / share / export wrappers land alongside their sub-phases.
 *
 * Auth: pulls the bearer JWT from readAdminSession(). All seeded
 * users (internal_admin, reviewer, client_admin, providers via the
 * /portal/enter flow) carry a JWT under the same key.
 */

import { readAdminSession } from "@/lib/session/admin";
import type {
  ReportAudience,
  ReportStatus,
  ReportVersionOrigin,
} from "@/lib/reports/constants";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ReportsApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ReportsApiError";
  }
}

async function fetchJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const session = readAdminSession();
  if (!session?.access_token) {
    throw new ReportsApiError(401, "No active session.");
  }
  const headers = new Headers(init.headers ?? {});
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Authorization", `Bearer ${session.access_token}`);
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ReportsApiError(response.status, detail || response.statusText);
  }
  if (response.status === 204) return undefined as unknown as T;
  return (await response.json()) as T;
}

// ─── Wire shapes ─────────────────────────────────────────────────

/**
 * The canvas tree persisted inside a ReportVersion. Schema is open at
 * the entity-API level; per-block schemas are enforced by the
 * registry (see lib/reports/registry.ts).
 */
export interface ReportContent {
  schema_version: number;
  blocks: ReportBlock[];
  global?: Record<string, unknown>;
}

export interface ReportBlock<TConfig = unknown> {
  id: string;
  type: string;
  config: TConfig;
  data?: unknown;
  ai_summary?: AISummary | null;
  layout?: {
    width?: "full" | "half" | "third";
    collapsed?: boolean;
  };
  locked?: boolean;
}

export interface AISummary {
  text: string;
  model: string;
  prompt_hash: string;
  generated_at: string;
  source_snapshot_id: string;
  citations?: Citation[];
}

export interface Citation {
  block_id?: string;
  label: string;
  href?: string;
}

export interface ReportSummary {
  id: string;
  title: string;
  description: string | null;
  audience: ReportAudience;
  status: ReportStatus;
  organization_id: string;
  client_id: string | null;
  vendor_id: string | null;
  current_version_id: string | null;
  created_by_user_id: string;
  created_at: string;
  updated_at: string;
}

export interface ReportVersionSummary {
  id: string;
  report_id: string;
  version_number: number;
  label: string | null;
  parent_version_id: string | null;
  generated_by: ReportVersionOrigin;
  created_by_user_id: string;
  created_at: string;
}

export interface ReportVersionRead extends ReportVersionSummary {
  content_json: ReportContent;
  plan_json: unknown | null;
  source_snapshot_id: string | null;
  llm_metadata: unknown | null;
}

export interface ReportRead extends ReportSummary {
  current_version: ReportVersionRead | null;
}

export interface ReportList {
  items: ReportSummary[];
  total: number;
}

export interface ReportVersionList {
  items: ReportVersionSummary[];
  total: number;
}

// ─── Endpoints ───────────────────────────────────────────────────

export interface CreateReportInput {
  title: string;
  description?: string | null;
  audience: ReportAudience;
  client_id?: string | null;
  vendor_id?: string | null;
  initial_content_json?: ReportContent | null;
}

export function createReport(
  input: CreateReportInput,
  options: { organizationId?: string } = {},
): Promise<ReportRead> {
  const qs = options.organizationId
    ? `?organization_id=${encodeURIComponent(options.organizationId)}`
    : "";
  return fetchJson<ReportRead>(`/api/v1/reports${qs}`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export interface ListReportsOptions {
  organizationId?: string;
  status?: ReportStatus;
  limit?: number;
  offset?: number;
}

export function listReports(
  options: ListReportsOptions = {},
): Promise<ReportList> {
  const params = new URLSearchParams();
  if (options.organizationId) params.set("organization_id", options.organizationId);
  if (options.status) params.set("status", options.status);
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.offset !== undefined) params.set("offset", String(options.offset));
  const qs = params.toString();
  return fetchJson<ReportList>(`/api/v1/reports${qs ? `?${qs}` : ""}`);
}

export function getReport(reportId: string): Promise<ReportRead> {
  return fetchJson<ReportRead>(`/api/v1/reports/${reportId}`);
}

export interface PatchReportInput {
  title?: string;
  description?: string | null;
  audience?: ReportAudience;
  status?: ReportStatus;
  client_id?: string | null;
  vendor_id?: string | null;
}

export function patchReport(
  reportId: string,
  input: PatchReportInput,
): Promise<ReportRead> {
  return fetchJson<ReportRead>(`/api/v1/reports/${reportId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export interface CreateVersionInput {
  content_json: ReportContent;
  label?: string | null;
  plan_json?: unknown | null;
  generated_by?: ReportVersionOrigin;
  parent_version_id?: string | null;
  source_snapshot_id?: string | null;
  llm_metadata?: unknown | null;
}

export function createVersion(
  reportId: string,
  input: CreateVersionInput,
): Promise<ReportVersionRead> {
  return fetchJson<ReportVersionRead>(`/api/v1/reports/${reportId}/versions`, {
    method: "POST",
    body: JSON.stringify({ ...input, generated_by: input.generated_by ?? "user" }),
  });
}

export function listVersions(reportId: string): Promise<ReportVersionList> {
  return fetchJson<ReportVersionList>(`/api/v1/reports/${reportId}/versions`);
}

export function getVersion(
  reportId: string,
  versionNumber: number,
): Promise<ReportVersionRead> {
  return fetchJson<ReportVersionRead>(
    `/api/v1/reports/${reportId}/versions/${versionNumber}`,
  );
}

// ─── Helpers ─────────────────────────────────────────────────────

export function emptyContent(): ReportContent {
  return { schema_version: 1, blocks: [], global: {} };
}
