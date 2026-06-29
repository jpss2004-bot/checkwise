/**
 * Typed wrapper over the Reports API (apps/api/app/api/v1/reports.py).
 *
 * Phase 3.2 — entity-layer endpoints only. AI / streaming / conversation
 * / share / export wrappers land alongside their sub-phases.
 *
 * Auth: JWT-first (in-memory bearer via ``adminAuthHeader``),
 * cookie-fallback (``credentials: "include"``). All seeded users
 * (internal_admin, reviewer, client_admin, providers via the
 * /portal/enter flow) authenticate the same way.
 */

import { adminAuthHeader } from "@/lib/session/admin";
import { redirectToLoginIfSessionLost } from "@/lib/session/expiry";
import { fetchWithTimeout, FetchTimeoutError } from "@/lib/api/fetch-timeout";
import { saveBlob } from "@/lib/api/download";
import type {
  ReportAudience,
  ReportStatus,
  ReportVersionOrigin,
} from "@/lib/reports/constants";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

// Client-side ceiling for read calls (list / presets / single report).
// Converts a request that hangs server-side into a visible error instead
// of an infinite spinner — the reports-section "enter" outage. AI-heavy
// POSTs (generate / plan / regenerate) intentionally omit this.
const READ_TIMEOUT_MS = 25_000;

// Client-side ceiling for quick (non-AI) writes — entity create/patch, version
// save, share + export create. These are short DB round-trips, so a timeout
// converts a hung backend into a visible error instead of an infinite spinner.
// AI POSTs (generate/regenerate/explain/suggest/refresh and auto-generate
// presets) and downloads stay unbounded on purpose — they legitimately run
// long (the backend LLM cap is ~120s).
const WRITE_TIMEOUT_MS = 30_000;

// Client-side ceiling for the one-click preset generation (hybrid AI +
// deterministic). Set generously ABOVE the backend ~120s LLM cap so a
// legitimate slow generation still completes, but bounded so a true
// server-side hang on the buyer's marquee action rejects into the 408
// handler instead of spinning the full-screen overlay forever.
const GENERATE_TIMEOUT_MS = 180_000;

// Ceiling for the export blob / inline-preview / presign streams. These
// bypass fetchJson (they return bytes or a presigned URL, not JSON), so a
// stalled R2/local-disk stream would hang the preview/download UI forever.
// Generous (120s) since large PDFs legitimately take a while; matches the
// DOWNLOAD_TIMEOUT_MS convention used by the client portal helpers.
const BLOB_TIMEOUT_MS = 120_000;

export class ReportsApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ReportsApiError";
  }
}

async function fetchJson<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs?: number,
): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  const auth = adminAuthHeader();
  if (auth.Authorization && !headers.has("Authorization")) {
    headers.set("Authorization", auth.Authorization);
  }
  // When `timeoutMs` is set, abort the request after the deadline and
  // raise a 408 so the caller's existing `.catch` renders an error state.
  // Without this a server-side hang leaves the promise unsettled forever
  // and the UI spins indefinitely.
  const controller = timeoutMs ? new AbortController() : undefined;
  const timer = timeoutMs
    ? setTimeout(() => controller!.abort(), timeoutMs)
    : undefined;
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      credentials: "include",
      signal: controller?.signal ?? init.signal,
    });
    if (!response.ok) {
      if (redirectToLoginIfSessionLost(response.status)) {
        throw new ReportsApiError(
          401,
          "Tu sesión expiró. Vuelve a iniciar sesión.",
        );
      }
      const raw = await response.text().catch(() => "");
      // FastAPI serialises errors as ``{"detail": "..."}``. Unwrap that
      // envelope so callers (and the UI alert) surface the human sentence
      // instead of echoing raw JSON at the user — the reports-page "Audience
      // client-facing requires…" leak. Non-JSON bodies pass through verbatim.
      let message = raw || response.statusText;
      if (raw) {
        try {
          const parsed = JSON.parse(raw) as { detail?: unknown };
          if (typeof parsed.detail === "string") message = parsed.detail;
        } catch {
          // body wasn't JSON — keep the raw text
        }
      }
      throw new ReportsApiError(response.status, message);
    }
    if (response.status === 204) return undefined as unknown as T;
    return (await response.json()) as T;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ReportsApiError(
        408,
        "La solicitud al servidor tardó demasiado. Vuelve a intentarlo.",
      );
    }
    throw err;
  } finally {
    if (timer) clearTimeout(timer);
  }
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
  return fetchJson<ReportRead>(
    `/api/v1/reports${qs}`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
    WRITE_TIMEOUT_MS,
  );
}

export interface ListReportsOptions {
  organizationId?: string;
  status?: ReportStatus;
  audience?: ReportAudience;
  limit?: number;
  offset?: number;
}

export function listReports(
  options: ListReportsOptions = {},
): Promise<ReportList> {
  const params = new URLSearchParams();
  if (options.organizationId) params.set("organization_id", options.organizationId);
  if (options.status) params.set("status", options.status);
  if (options.audience) params.set("audience", options.audience);
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.offset !== undefined) params.set("offset", String(options.offset));
  const qs = params.toString();
  return fetchJson<ReportList>(
    `/api/v1/reports${qs ? `?${qs}` : ""}`,
    {},
    READ_TIMEOUT_MS,
  );
}

export function getReport(reportId: string): Promise<ReportRead> {
  return fetchJson<ReportRead>(
    `/api/v1/reports/${reportId}`,
    {},
    READ_TIMEOUT_MS,
  );
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
  return fetchJson<ReportRead>(
    `/api/v1/reports/${reportId}`,
    {
      method: "PATCH",
      body: JSON.stringify(input),
    },
    WRITE_TIMEOUT_MS,
  );
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
  return fetchJson<ReportVersionRead>(
    `/api/v1/reports/${reportId}/versions`,
    {
      method: "POST",
      body: JSON.stringify({ ...input, generated_by: input.generated_by ?? "user" }),
    },
    WRITE_TIMEOUT_MS,
  );
}

export function listVersions(reportId: string): Promise<ReportVersionList> {
  return fetchJson<ReportVersionList>(
    `/api/v1/reports/${reportId}/versions`,
    {},
    READ_TIMEOUT_MS,
  );
}

export function getVersion(
  reportId: string,
  versionNumber: number,
): Promise<ReportVersionRead> {
  return fetchJson<ReportVersionRead>(
    `/api/v1/reports/${reportId}/versions/${versionNumber}`,
    {},
    READ_TIMEOUT_MS,
  );
}

// ─── Helpers ─────────────────────────────────────────────────────

export function emptyContent(): ReportContent {
  return { schema_version: 1, blocks: [], global: {} };
}

// ─── Phase 3.3c — per-block actions ──────────────────────────────

export interface ExplainBlockResponse {
  block_id: string;
  explanation: string;
  llm_backend: string;
}

export function explainBlock(
  reportId: string,
  blockId: string,
  question?: string,
): Promise<ExplainBlockResponse> {
  return fetchJson<ExplainBlockResponse>(
    `/api/v1/reports/${reportId}/blocks/${blockId}/explain`,
    {
      method: "POST",
      body: JSON.stringify({ question: question ?? null }),
    },
  );
}

export interface RegenerateBlockResponse {
  block_id: string;
  ai_summary_text: string;
  model: string;
  llm_backend: string;
  version_id: string;
  version_number: number;
}

export function regenerateBlock(
  reportId: string,
  blockId: string,
): Promise<RegenerateBlockResponse> {
  return fetchJson<RegenerateBlockResponse>(
    `/api/v1/reports/${reportId}/blocks/${blockId}/regenerate`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

// ─── R6 — copilot block-composition suggestions ──────────────────

export interface BlockSuggestion {
  /** Block type from the registry, e.g. "kpi_strip". */
  type: string;
  /** Validated config matching the catalog's input_schema. */
  config: Record<string, unknown>;
  /** One-sentence reason the model gave for proposing this block. */
  rationale: string;
}

export interface SuggestBlocksResponse {
  suggestions: BlockSuggestion[];
  llm_backend: string;
  model: string;
}

/**
 * Ask the copilot for up to 4 block drafts to insert into the canvas.
 * The backend forces tool-use against the block catalog so every
 * returned draft is guaranteed to (a) reference a real block type
 * and (b) carry a config that already passes the registry's
 * JSON-schema. The frontend can splice them straight into the
 * canvas without re-validating.
 */
export function suggestBlocks(
  reportId: string,
  body: { intent: string; canvas_summary?: Record<string, unknown> },
): Promise<SuggestBlocksResponse> {
  return fetchJson<SuggestBlocksResponse>(
    `/api/v1/reports/${reportId}/copilot/suggest-blocks`,
    {
      method: "POST",
      body: JSON.stringify({
        intent: body.intent,
        canvas_summary: body.canvas_summary ?? {},
      }),
    },
  );
}

// ─── P1.7 — Refresh data (no LLM) ────────────────────────────────

export interface RefreshedBlockSummary {
  block_id: string;
  block_type: string;
  refreshed: boolean;
}

export interface RefreshDataResponse {
  version_id: string;
  version_number: number;
  refreshed_blocks: RefreshedBlockSummary[];
  fetched_at: string;
}

/**
 * Re-run every block's data fetcher against today's snapshot.
 * Deterministic — never re-prompts the LLM. `ai_summary` payloads
 * are preserved verbatim. Persists a new ReportVersion labeled
 * "Datos actualizados". Used by the editor's "Actualizar con datos
 * de hoy" toolbar action and the per-block inline refresh affordance.
 */
export function refreshReportData(
  reportId: string,
): Promise<RefreshDataResponse> {
  return fetchJson<RefreshDataResponse>(
    `/api/v1/reports/${reportId}/refresh-data`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

// ─── Engine info — used to surface "AI not configured" banner ────

export interface ReportsEngineInfo {
  backend: string;
  planner_model: string;
  content_model: string;
}

export function getReportsEngine(
  init?: { signal?: AbortSignal },
): Promise<ReportsEngineInfo> {
  return fetchJson<ReportsEngineInfo>(`/api/v1/reports/_engine`, init);
}

// ─── Presets (R1.0) ──────────────────────────────────────────────

export interface ReportPresetSummary {
  id: string;
  title: string;
  description: string;
  audience: ReportAudience;
  recommended_prompt: string;
}

export interface ReportPresetList {
  items: ReportPresetSummary[];
}

export function listPresets(): Promise<ReportPresetList> {
  return fetchJson<ReportPresetList>(
    `/api/v1/reports/_presets`,
    {},
    READ_TIMEOUT_MS,
  );
}

export function createReportFromPreset(
  presetId: string,
  autoGenerate = false,
  opts?: { vendorId?: string; clientId?: string },
): Promise<ReportRead> {
  // ``auto_generate`` makes the server build the first populated version
  // inline (hybrid: AI with deterministic fallback) so the caller can route
  // straight to a finished, read-only report — no client-side AI streaming,
  // no editing. ``vendorId`` scopes a per-provider report (client-vendor-detail).
  return fetchJson<ReportRead>(
    `/api/v1/reports/from-preset`,
    {
      method: "POST",
      body: JSON.stringify({
        preset_id: presetId,
        auto_generate: autoGenerate,
        ...(opts?.vendorId ? { vendor_id: opts.vendorId } : {}),
        ...(opts?.clientId ? { client_id: opts.clientId } : {}),
      }),
    },
    // Auto-generate runs the inline AI build; bound it so a hung backend
    // surfaces an error instead of an infinite overlay. The metadata-only
    // create (autoGenerate=false) is a quick write, so reuse the write cap.
    autoGenerate ? GENERATE_TIMEOUT_MS : WRITE_TIMEOUT_MS,
  );
}

// ─── Exports (Phase 10A) ─────────────────────────────────────────
//
// HTML is the only format wired in 10A; PDF (10B) and Excel (10C)
// will land alongside their renderer choices.

export type ReportExportFormat = "html" | "pdf";

export interface ReportExport {
  id: string;
  report_id: string;
  version_id: string;
  format: string;
  status: "pending" | "rendering" | "ready" | "failed";
  bytes: number | null;
  requested_at: string;
  ready_at: string | null;
  error_text: string | null;
}

export function createReportExport(
  reportId: string,
  params: { format: ReportExportFormat; version_id?: string },
): Promise<ReportExport> {
  return fetchJson<ReportExport>(
    `/api/v1/reports/${reportId}/exports`,
    {
      method: "POST",
      body: JSON.stringify(params),
    },
    WRITE_TIMEOUT_MS,
  );
}

export function getReportExport(exportId: string): Promise<ReportExport> {
  return fetchJson<ReportExport>(
    `/api/v1/reports/exports/${exportId}`,
    {},
    READ_TIMEOUT_MS,
  );
}

/**
 * Resolve a ready export to a directly-navigable presigned URL.
 *
 * Prod stores artifacts in R2; the ``/download`` endpoint 302-redirects
 * to a presigned R2 URL. A browser ``fetch()`` that follows that
 * redirect does a CROSS-ORIGIN read of R2 → blocked by CORS ("failed to
 * fetch"). So we ask the API (bearer-authed, same-origin JSON) for the
 * presigned URL and navigate straight to it instead — a top-level
 * navigation/download is not subject to CORS. Returns ``url: null`` on
 * local-disk storage, where the caller streams ``/download`` as a blob.
 */
async function getReportExportPresignedUrl(
  exportId: string,
  disposition: "attachment" | "inline",
): Promise<{ url: string | null; filename: string }> {
  const headers: Record<string, string> = { ...adminAuthHeader() };
  let response: Response;
  try {
    response = await fetchWithTimeout(
      `${API_BASE_URL}/api/v1/reports/exports/${exportId}/download-url?disposition=${disposition}`,
      { headers, credentials: "include" },
      BLOB_TIMEOUT_MS,
    );
  } catch (err) {
    if (err instanceof FetchTimeoutError) {
      throw new ReportsApiError(
        408,
        "No pudimos preparar la descarga: el servidor tardó demasiado.",
      );
    }
    throw err;
  }
  if (!response.ok) {
    throw new ReportsApiError(
      response.status,
      `No pudimos preparar la descarga (HTTP ${response.status}).`,
    );
  }
  return (await response.json()) as { url: string | null; filename: string };
}

/** Stream a ready export as a blob and trigger a save. Local-disk
 *  storage only — same-origin, so no cross-origin/CORS concern. */
async function streamExportAsBlob(
  exportId: string,
  filename: string,
): Promise<void> {
  const headers: Record<string, string> = {
    Accept: "application/octet-stream, application/pdf, text/html",
    ...adminAuthHeader(),
  };
  let response: Response;
  try {
    response = await fetchWithTimeout(
      `${API_BASE_URL}/api/v1/reports/exports/${exportId}/download`,
      { headers, credentials: "include" },
      BLOB_TIMEOUT_MS,
    );
  } catch (err) {
    if (err instanceof FetchTimeoutError) {
      throw new ReportsApiError(
        408,
        "La descarga del export tardó demasiado. Inténtalo de nuevo.",
      );
    }
    throw err;
  }
  if (!response.ok) {
    throw new ReportsApiError(
      response.status,
      `No pudimos descargar el export (HTTP ${response.status}).`,
    );
  }
  const blob = await response.blob();
  // Reuse the shared saveBlob helper so the object URL is revoked on the
  // Safari-safe 60s delay (a 1s delay could abort an in-progress save of a
  // large PDF/HTML export on Safari).
  saveBlob(blob, filename);
}

/**
 * Download a ready export. In prod, navigates directly to the presigned
 * R2 URL (R2 serves it as an attachment — a top-level navigation, NOT a
 * fetch, so it sidesteps the cross-origin CORS block that broke the old
 * blob-fetch path). Falls back to streaming the bytes on local-disk
 * storage where no presigned URL exists.
 */
export async function downloadReportExport(
  exportId: string,
  filename: string,
): Promise<void> {
  const { url } = await getReportExportPresignedUrl(exportId, "attachment");
  if (!url) {
    await streamExportAsBlob(exportId, filename);
    return;
  }
  const a = document.createElement("a");
  a.href = url;
  // ``download`` is ignored for cross-origin hrefs, but R2 returns
  // Content-Disposition: attachment so the save dialog fires anyway.
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

/**
 * Poll an export row until it reaches ``ready`` (or ``failed``).
 * Shared by the download and preview buttons so both honour the same
 * cadence and surface the renderer's ``error_text`` verbatim.
 */
export async function pollReportExportUntilReady(
  exportId: string,
  {
    intervalMs = 1000,
    maxAttempts = 30,
    onStatus,
  }: {
    intervalMs?: number;
    maxAttempts?: number;
    /** Called with each polled status so a progress UI can reflect the
     *  real export phase (pending → rendering → ready). */
    onStatus?: (status: ReportExport["status"]) => void;
  } = {},
): Promise<ReportExport> {
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const current = await getReportExport(exportId);
    onStatus?.(current.status);
    if (current.status === "ready") return current;
    if (current.status === "failed") {
      throw new ReportsApiError(
        502,
        current.error_text ?? "El renderizador falló sin mensaje.",
      );
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new ReportsApiError(
    504,
    "El export tardó demasiado. Intenta de nuevo en unos segundos.",
  );
}

/**
 * Resolve a ready export to a URL the caller opens inline (preview the
 * PDF in a new tab). In prod this is the presigned R2 URL with an
 * ``inline`` disposition — the browser renders it directly, no
 * cross-origin fetch. On local-disk storage it falls back to a
 * same-origin blob URL. A blob URL should be revoked by the caller; a
 * presigned URL needs no cleanup (revokeObjectURL is a no-op on it).
 */
export async function fetchReportExportObjectUrl(
  exportId: string,
): Promise<string> {
  const { url } = await getReportExportPresignedUrl(exportId, "inline");
  if (url) return url;
  // Local-disk storage: stream same-origin and hand back a blob URL.
  const headers: Record<string, string> = {
    Accept: "application/pdf, application/octet-stream",
    ...adminAuthHeader(),
  };
  let response: Response;
  try {
    response = await fetchWithTimeout(
      `${API_BASE_URL}/api/v1/reports/exports/${exportId}/download`,
      { headers, credentials: "include" },
      BLOB_TIMEOUT_MS,
    );
  } catch (err) {
    if (err instanceof FetchTimeoutError) {
      throw new ReportsApiError(
        408,
        "La vista previa tardó demasiado en abrir. Inténtalo de nuevo.",
      );
    }
    throw err;
  }
  if (!response.ok) {
    throw new ReportsApiError(
      response.status,
      `No pudimos abrir la vista previa (HTTP ${response.status}).`,
    );
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

// ─── Shares (Phase 10D) ──────────────────────────────────────────
//
// Mint / list / revoke share links. The raw token is returned ONCE
// from createReportShare and never re-fetched — listReportShares
// only returns metadata (no token, no hash).

export interface ReportShare {
  id: string;
  report_id: string;
  version_id: string;
  audience: string;
  expires_at: string | null;
  revoked_at: string | null;
  last_accessed_at: string | null;
  access_count: number;
  has_password: boolean;
  created_at: string;
}

export interface CreateReportShareResponse {
  share: ReportShare;
  /** Raw token. Only returned on mint; never persisted or re-fetched. */
  token: string;
  /** Absolute consume URL ready to copy/paste. */
  url: string;
}

export async function createReportShare(
  reportId: string,
  params: { version_id?: string; expires_at?: string; password?: string } = {},
): Promise<CreateReportShareResponse> {
  const result = await fetchJson<CreateReportShareResponse>(
    `/api/v1/reports/${reportId}/shares`,
    {
      method: "POST",
      body: JSON.stringify(params),
    },
    WRITE_TIMEOUT_MS,
  );
  // The backend returns an ABSOLUTE consume URL only when PUBLIC_BASE_URL
  // is configured; otherwise it falls back to a bare path like
  // ``/api/v1/r/<token>`` (what the user saw as "api/xxx"). The consume
  // page is served by the API itself (GET /api/v1/r/<token> → HTML), so
  // resolve a relative URL against the API host — NOT the Vercel origin,
  // which doesn't serve /api/v1/. Yields a real, copy-pasteable link.
  return {
    ...result,
    url: result.url.startsWith("/")
      ? `${API_BASE_URL.replace(/\/$/, "")}${result.url}`
      : result.url,
  };
}

export function listReportShares(
  reportId: string,
): Promise<{ items: ReportShare[] }> {
  return fetchJson<{ items: ReportShare[] }>(
    `/api/v1/reports/${reportId}/shares`,
    {},
    READ_TIMEOUT_MS,
  );
}

export async function revokeReportShare(shareId: string): Promise<void> {
  const headers: Record<string, string> = { ...adminAuthHeader() };
  const response = await fetch(
    `${API_BASE_URL}/api/v1/reports/shares/${shareId}`,
    { method: "DELETE", headers, credentials: "include" },
  );
  if (response.status !== 204) {
    throw new ReportsApiError(
      response.status,
      `No pudimos revocar el enlace (HTTP ${response.status}).`,
    );
  }
}
