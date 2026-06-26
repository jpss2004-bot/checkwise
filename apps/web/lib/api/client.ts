/**
 * Phase 8 — typed wrapper over the client portal API.
 *
 * Every endpoint requires a JWT carrying the ``client_admin`` role
 * (or ``internal_admin`` for support visibility) — the same staff JWT
 * used by the admin + reviewer surfaces. Auth is JWT-first (in-memory
 * bearer), cookie-fallback (``credentials: "include"``). Provider
 * portal pages keep their own cookie-based path; this client is
 * staff-only.
 */

import { adminAuthHeader } from "@/lib/session/admin";
import { dedupeRead, invalidateRead } from "@/lib/api/request-cache";
import { parseContentDispositionFilename } from "@/lib/api/download";
import { toPdfBlob } from "@/lib/api/pdf-blob";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

// Default per-request timeout so a stalled API surfaces a clear error
// instead of an infinite spinner (audit 2026-06-09).
const REQUEST_TIMEOUT_MS = 30_000;
// File/blob downloads (metadata XLSX, document PDFs) bypass fetchJson, so they
// need their own abort ceiling — without it a stalled stream hangs the button
// indefinitely (perf audit P1-5). More generous than JSON since files are bigger.
const DOWNLOAD_TIMEOUT_MS = 120_000;

export class ClientApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ClientApiError";
  }
}

async function fetchJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  // JWT-first (in-memory bearer); the httpOnly cookie (credentials:
  // include) authenticates after a reload. A logged-out call 401s from
  // the server and the caller routes to /login.
  const auth = adminAuthHeader();
  if (auth.Authorization && !headers.has("Authorization")) {
    headers.set("Authorization", auth.Authorization);
  }
  const controller = init.signal ? null : new AbortController();
  const timeoutId = controller
    ? setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
    : null;
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      credentials: "include",
      signal: init.signal ?? controller?.signal,
    });
  } catch (err) {
    // Surface aborts (timeout OR a caller-supplied signal) as a typed
    // ClientApiError so callers branching on `err instanceof ClientApiError`
    // handle them consistently instead of seeing a raw AbortError DOMException.
    if (
      controller?.signal.aborted ||
      init.signal?.aborted ||
      (err instanceof DOMException && err.name === "AbortError")
    ) {
      throw new ClientApiError(
        0,
        "La solicitud tardó demasiado. Revisa tu conexión e inténtalo de nuevo.",
      );
    }
    throw err;
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
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
  // Client-side legal-consent gate (v2+). The shell blocks the
  // dashboard until legal_consent_version === current_legal_consent_version.
  legal_consent_accepted_at: string | null;
  legal_consent_version: string | null;
  current_legal_consent_version: string | null;
};

export type ClientLegalConsentResponse = {
  user_id: string;
  legal_consent_accepted_at: string;
  legal_consent_version: string;
};

// One provider on the dashboard "Requieren tu atención" worklist.
export type ClientRiskVendor = {
  vendor_id: string;
  vendor_name: string;
  semaphore_level: "green" | "yellow" | "red";
  compliance_pct: number;
  overdue_count: number;
  missing_required_count: number;
  rejected_or_correction_count: number;
  top_reason: string;
  // Per-vendor approval-rate momentum (points vs the prior active month);
  // null until two active months exist. ▲ improving / ▼ sliding.
  momentum_delta: number | null;
};

// The single biggest legal/tax exposure right now (or null → hide the card).
export type ClientExposure = {
  vendor_id: string;
  vendor_name: string;
  requirement_name: string;
  institution: string;
  period_label: string | null;
  deadline_iso: string | null;
  days_overdue: number;
  headline: string;
  reason: string;
  detail: string | null;
  href: string;
};

// The dominant recurring failure across the portfolio (root-cause line).
export type ClientFailurePattern = {
  requirement_name: string;
  institution: string;
  vendor_count: number;
  obligation_count: number;
};

export type ClientOverview = {
  client_id: string;
  client_name: string;
  vendors_total: number;
  active_workspaces_total: number;
  // CANONICAL pooled obligation-level "% al día (de las ya vencidas)".
  compliance_pct: number;
  // Numerator / denominator behind compliance_pct ("236 de 248").
  obligations_on_track_total: number;
  obligations_due_total: number;
  // Month-over-month approval-rate momentum in points; null when there
  // aren't two active months yet.
  compliance_trend_delta: number | null;
  green_count: number;
  yellow_count: number;
  red_count: number;
  pending_reviews_total: number;
  rejected_or_correction_total: number;
  missing_required_total: number;
  due_soon_total: number;
  // Lapsed obligations across the portfolio (highest-liability state).
  overdue_total: number;
  // Obligations not yet due (future periods) — the "Próximas" tile.
  proxima_total: number;
  recent_submissions_total: number;
  last_activity_at: string | null;
  biggest_exposure: ClientExposure | null;
  // Count of in-queue docs an AI pass flagged; 0 → hide the indicator.
  ia_revisar_total: number;
  top_failure_pattern: ClientFailurePattern | null;
  // Worst-first ranked attention list (top 5).
  top_risk_vendors: ClientRiskVendor[];
};

export type ClientTrajectoryPoint = {
  period: string;
  label: string;
  due_total: number;
  on_track: number;
  compliance_pct: number;
};

export type ClientTrajectory = {
  points: ClientTrajectoryPoint[];
  target_pct: number;
  has_history: boolean;
};

// Phase 6D — most-urgent renewal-bearing slot for this vendor.
// ``null`` when nothing is in the 30-day window or overdue.
// ``days_remaining`` is signed; negative values mean overdue.
export type ClientVendorNextRenewal = {
  requirement_code: string;
  requirement_name: string;
  due_date: string;
  status: "due_soon" | "overdue";
  days_remaining: number;
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
  next_renewal: ClientVendorNextRenewal | null;
};

export type ClientVendorSort =
  | "risk"
  | "compliance_asc"
  | "compliance_desc"
  | "missing_desc"
  | "name"
  | "recent";

export type ClientVendorListResponse = {
  client_id: string;
  items: ClientVendorRow[];
  total: number;
  // True when more rows exist past this page.
  has_more?: boolean;
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
  // Year-to-date (matches the dashboard) + current-period compliance lenses.
  compliance_breakdown: {
    year: number;
    current_period_pct: number;
    current_period_on_track: number;
    current_period_due: number;
    year_to_date_pct: number;
    year_to_date_on_track: number;
    year_to_date_due: number;
  };
  document_action_items: Array<ClientVendorDocumentActionItem>;
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
    // Axis 2 — client acceptance (Phase 5).
    client_acceptance?: string;
    client_decided_at?: string | null;
    client_decision_reason?: string | null;
  }>;
  recent_reviewer_notes: Array<{
    submission_id: string;
    result: string;
    message: string | null;
    occurred_at: string;
  }>;
  /**
   * Item 1 — every contract-type submission attached to this vendor,
   * newest first. The signed services contract (ONB-CONT-001) plus
   * any modifications (ONB-CONT-002) and service orders (ONB-CONT-003).
   * View + Download buttons resolve against
   * ``/api/v1/client/submissions/:submission_id/document``.
   */
  contracts: Array<ClientVendorContractDoc>;
};

export type ClientVendorDocumentActionItem = {
  id: string;
  kind:
    | "missing"
    | "rejected"
    | "needs_correction"
    | "possible_mismatch"
    | "expired"
    | "due_soon";
  requirement_code: string | null;
  requirement_name: string | null;
  institution: string | null;
  period_key: string | null;
  deadline_iso: string | null;
  state: string;
  due_in_days: number | null;
  // The client monitors; it does not upload. Action items carry no upload
  // href — the detail card opens the document itself via submission_id.
  href: string | null;
  submission_id: string | null;
};

export type ClientVendorContractDoc = {
  submission_id: string;
  requirement_code: string;
  requirement_name: string;
  status: string;
  filename: string | null;
  submitted_at: string;
  size_bytes: number | null;
};

/** Per-obligation severity computed by the backend (no longer null).
 *  Ordered most-severe-first; the agenda bands by it and the matrix
 *  colors by it. See ``_calendar_item_risk`` in apps/api. */
export type ClientCalendarRisk =
  | "overdue"
  | "action_required"
  | "due_soon"
  | "in_review"
  | "upcoming"
  | "on_track";

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
  risk_level: ClientCalendarRisk | null;
  /** Server-owned next step in the client's oversight voice (chase/wait).
   *  Optional so a stale backend falls back to the FE `nextActionFor`. */
  suggested_action?: string;
  /** Oversight evidence: what the provider delivered + when, and the
   *  reviewer's reason on rejected items. Null/absent until applicable. */
  filename?: string | null;
  submitted_at?: string | null;
  reviewer_note?: string | null;
  /** Supporting document guidance shown inline on the review card
   *  (requirement_name is the document; these describe + locate it).
   *  `accepts_documents` is non-empty only for v2 obligations satisfiable
   *  by any one of several documents. `?? []`/`?? ""` on the consumer side
   *  keeps a stale backend safe. */
  anatomy: string;
  where_to_obtain: string;
  common_errors?: string[];
  accepts_documents?: ClientCalendarAcceptedDoc[];
  href: string;
};

/** One acceptable document for a v2 obligation that any single member of
 *  satisfies (e.g. IMSS monthly = comprobante bancario OR CFDI OR cédula). */
export type ClientCalendarAcceptedDoc = {
  name: string;
  anatomy: string;
  where_to_obtain: string;
  common_errors: string[];
};

/** Per-provider rollup the calendar leads with: which providers put the
 *  client at risk. ``semaphore_level`` / ``compliance_pct`` match the
 *  /vendors list exactly (same backend semáforo). Sorted worst-first. */
export type ClientCalendarProvider = {
  vendor_id: string;
  vendor_name: string;
  semaphore_level: "red" | "yellow" | "green";
  compliance_pct: number;
  overdue_count: number;
  due_soon_count: number;
  action_required_count: number;
  next_deadline_iso: string | null;
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
  providers: ClientCalendarProvider[];
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
  /** ``alta_inicial`` for one-time onboarding/expediente docs (which have no
   *  recurring period), or a recurring frequency. Lets the table show
   *  "Único" instead of an ambiguous "—" when ``period_key`` is null. */
  load_type: string | null;
  status: string;
  current_slot_status: string | null;
  is_current_for_slot: boolean;
  filename: string | null;
  submitted_at: string;
  reviewed_at: string | null;
  reviewer_note: string | null;
  supersedes_submission_id: string | null;
  superseded_by_submission_id: string | null;
  /** Axis 2 — the client's business-acceptance verdict ("pending" |
   *  "accepted" | "rejected"), orthogonal to ``status``. */
  client_acceptance?: string;
  client_decided_at?: string | null;
  client_decision_reason?: string | null;
};

export type ClientSubmissionsResponse = {
  client_id: string;
  scope: "submitted_documents";
  scope_description: string;
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

/** Phase 4 / Slice 4A — semáforo discriminator on a notification row.
 *  Canonical values: ``green`` (approved / complete), ``yellow``
 *  (pending / in review / due soon), ``red`` (rejected / missing /
 *  expired), ``info`` (background automation). */
export type NotificationSeverity = "green" | "yellow" | "red" | "info";

/** Phase 7 / Slice N9b — canonical category vocabulary. Derived
 *  server-side from notification_type at insert time. ``other`` is
 *  the catch-all for legacy types that don't match a known prefix. */
export type NotificationCategory =
  | "renewal"
  | "reporting"
  | "verification"
  | "account"
  | "admin"
  | "other";

export type ClientNotificationItem = {
  id: string;
  notification_type: string;
  severity: NotificationSeverity;
  category: NotificationCategory;
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
  /** Phase 7 / Slice N9b — subset of ``unread_count`` whose
   *  severity is ``red`` or ``yellow``. Drives the sidebar bell. */
  unread_actionable_count: number;
  limit: number;
};

export type ClientNotificationSummary = {
  client_id: string;
  unread_count: number;
  unread_actionable_count: number;
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
  // The shell's consent gate (re-runs on every navigation) and the dashboard
  // both read /me. Coalesce concurrent calls and serve a short TTL so moving
  // around the portal doesn't re-hit the network each time.
  // ``acceptClientLegalConsent`` invalidates this key so a freshly granted
  // consent is observed immediately by the gate (no stale "blocked" loop).
  return dedupeRead(
    "client:me",
    () => fetchJson<ClientMe>("/api/v1/client/me"),
    30_000,
  );
}

/** Record the client_admin's acceptance of the current legal package. */
export async function acceptClientLegalConsent(): Promise<ClientLegalConsentResponse> {
  const result = await fetchJson<ClientLegalConsentResponse>(
    "/api/v1/client/legal-consent",
    { method: "POST" },
  );
  // The consent gate re-reads /me after acceptance; drop the cached identity
  // so it observes the new consent state instead of the pre-grant snapshot.
  invalidateRead("client:me");
  return result;
}

export async function getClientOverview(params?: {
  client_id?: string;
  year?: number;
}): Promise<ClientOverview> {
  return fetchJson<ClientOverview>(`/api/v1/client/overview${qs(params)}`);
}

export async function getClientOverviewTrajectory(params?: {
  client_id?: string;
  months?: number;
}): Promise<ClientTrajectory> {
  return fetchJson<ClientTrajectory>(
    `/api/v1/client/overview/trajectory${qs(params)}`,
  );
}

export async function listClientVendors(params?: {
  client_id?: string;
  status?: string;
  semaphore_level?: "green" | "yellow" | "red";
  search?: string;
  sort?: ClientVendorSort;
  limit?: number;
  offset?: number;
}): Promise<ClientVendorListResponse> {
  return fetchJson<ClientVendorListResponse>(`/api/v1/client/vendors${qs(params)}`);
}

/**
 * Item 8 v2 — a client_admin invites a provider directly from their
 * profile page. The backend builds the full provider stack (User +
 * Vendor + ProviderWorkspace) and emails the invitation
 * automatically. The temp password is NEVER returned to the client
 * — only the email-delivery status surfaces.
 */
export type ClientProviderCreateBody = {
  vendor_name: string;
  vendor_rfc: string;
  persona_type: "moral" | "fisica";
  contact_name: string;
  contact_email: string;
  contact_phone?: string | null;
};

export type ClientProviderCreateResponse = {
  vendor_id: string;
  workspace_id: string;
  user_id: string;
  contact_email: string;
  email_status: string;
  email_error: string | null;
};

export async function createClientProvider(
  body: ClientProviderCreateBody,
  params?: { client_id?: string },
): Promise<ClientProviderCreateResponse> {
  const result = await fetchJson<ClientProviderCreateResponse>(
    `/api/v1/client/providers${qs(params)}`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
  invalidateClientPlan(params?.client_id);
  return result;
}

export async function getClientVendorDetail(
  vendor_id: string,
  params?: { client_id?: string; year?: number },
): Promise<ClientVendorDetail> {
  return fetchJson<ClientVendorDetail>(
    `/api/v1/client/vendors/${vendor_id}${qs(params)}`,
  );
}

// ---------------------------------------------------------------------------
// Phase 3 — archive / restore a provider in the portfolio
// ---------------------------------------------------------------------------

export type ClientProviderStatusResponse = {
  vendor_id: string;
  // "active" | "inactive"
  status: string;
  // False when the provider was already in the target state (no-op).
  changed: boolean;
};

export async function deactivateClientProvider(
  vendor_id: string,
  params?: { client_id?: string },
): Promise<ClientProviderStatusResponse> {
  const result = await fetchJson<ClientProviderStatusResponse>(
    `/api/v1/client/vendors/${vendor_id}/deactivate${qs(params)}`,
    { method: "POST" },
  );
  invalidateClientPlan(params?.client_id);
  return result;
}

export async function reactivateClientProvider(
  vendor_id: string,
  params?: { client_id?: string },
): Promise<ClientProviderStatusResponse> {
  const result = await fetchJson<ClientProviderStatusResponse>(
    `/api/v1/client/vendors/${vendor_id}/reactivate${qs(params)}`,
    { method: "POST" },
  );
  invalidateClientPlan(params?.client_id);
  return result;
}

// ---------------------------------------------------------------------------
// Phase A/B — subscription plan + provider-usage meter
// ---------------------------------------------------------------------------

export type ClientPlanCapabilities = {
  export_audit_package: boolean;
  bulk_export: boolean;
  download_documents: boolean;
};

export type ClientPlan = {
  client_id: string;
  organization_id: string;
  plan: string;
  plan_label: string;
  /** null ⇒ uncapped (legacy / enterprise). */
  provider_limit: number | null;
  providers_used: number;
  /** null ⇒ uncapped. */
  providers_available: number | null;
  /** ISO; null ⇒ not a demo (no deadline). */
  demo_expires_at: string | null;
  capabilities: ClientPlanCapabilities;
  /** Whether the caller may change the plan / manage seats (owner / internal). */
  can_manage: boolean;
};

export const CLIENT_PLAN_KEY = "client:plan";

/** The caller's subscription plan + provider usage. Deduped (15s TTL); the
 *  provider add/archive/restore mutations invalidate it so the meter is fresh. */
export async function getClientPlan(params?: {
  client_id?: string;
}): Promise<ClientPlan> {
  const key = params?.client_id
    ? `${CLIENT_PLAN_KEY}:${params.client_id}`
    : CLIENT_PLAN_KEY;
  return dedupeRead(
    key,
    () => fetchJson<ClientPlan>(`/api/v1/client/plan${qs(params)}`),
    15_000,
  );
}

export function invalidateClientPlan(client_id?: string): void {
  invalidateRead(
    client_id ? `${CLIENT_PLAN_KEY}:${client_id}` : CLIENT_PLAN_KEY,
  );
}

// ---------------------------------------------------------------------------
// Phase 2 — client seat management (/client/users)
//
// The seat API has existed (owner-gated, server-side) since the
// multi-user rollout; these wrappers + the /client/configuracion/usuarios
// page are the first UI to reach it.
// ---------------------------------------------------------------------------

export type ClientUserRole = "client_admin" | "client_viewer";

export type ClientUserItem = {
  user_id: string;
  email: string;
  full_name: string;
  is_primary: boolean;
  // Seat tier (Phase 4). "client_admin" = Approver (full write);
  // "client_viewer" = Viewer (read + export only). The Primary Owner is
  // always an Approver.
  role: ClientUserRole;
  // "active" | "disabled"
  status: string;
  // True while the seat hasn't completed first login (temp password).
  pending_first_login: boolean;
  last_login_at: string | null;
  joined_at: string;
};

export type ClientUsersList = {
  client_id: string;
  organization_id: string;
  // Cap on total seats of any tier (the Primary Owner included).
  seat_limit: number;
  seats_used: number;
  seats_available: number;
  // Seat management (create / disable / reset / remove / change tier).
  // True for any Approver of the org or CheckWise staff; false for Viewers.
  can_manage: boolean;
  users: ClientUserItem[];
};

export type CreateClientUserResponse = {
  user_id: string;
  email: string;
  full_name: string;
  // Plaintext, shown ONCE for the owner to relay.
  temp_password: string;
  login_url: string;
  email_status: string;
  email_error: string | null;
  reinstated: boolean;
  seats_used: number;
  seat_limit: number;
};

export type ClientUserActionResponse = {
  user_id: string;
  status: string;
  seats_used: number;
  seat_limit: number;
};

export type ResetClientUserPasswordResponse = {
  user_id: string;
  email: string;
  temp_password: string;
  email_status: string;
  email_error: string | null;
};

export type ClientUserRoleResponse = {
  user_id: string;
  role: ClientUserRole;
};

export async function listClientUsers(params?: {
  client_id?: string;
}): Promise<ClientUsersList> {
  return fetchJson<ClientUsersList>(`/api/v1/client/users${qs(params)}`);
}

export async function createClientUser(
  body: {
    full_name: string;
    email: string;
    // Seat tier. Omit for the default read-only Viewer; an Approver may
    // pass "client_admin" to create another Approver.
    role?: ClientUserRole;
  },
  params?: { client_id?: string },
): Promise<CreateClientUserResponse> {
  return fetchJson<CreateClientUserResponse>(
    `/api/v1/client/users${qs(params)}`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function updateClientUserRole(
  user_id: string,
  role: ClientUserRole,
  params?: { client_id?: string },
): Promise<ClientUserRoleResponse> {
  return fetchJson<ClientUserRoleResponse>(
    `/api/v1/client/users/${user_id}/role${qs(params)}`,
    { method: "PATCH", body: JSON.stringify({ role }) },
  );
}

export async function updateClientUserStatus(
  user_id: string,
  status: "active" | "disabled",
  params?: { client_id?: string },
): Promise<ClientUserActionResponse> {
  return fetchJson<ClientUserActionResponse>(
    `/api/v1/client/users/${user_id}${qs(params)}`,
    { method: "PATCH", body: JSON.stringify({ status }) },
  );
}

export async function removeClientUser(
  user_id: string,
  params?: { client_id?: string },
): Promise<ClientUserActionResponse> {
  return fetchJson<ClientUserActionResponse>(
    `/api/v1/client/users/${user_id}${qs(params)}`,
    { method: "DELETE" },
  );
}

export async function resetClientUserPassword(
  user_id: string,
  params?: { client_id?: string },
): Promise<ResetClientUserPasswordResponse> {
  return fetchJson<ResetClientUserPasswordResponse>(
    `/api/v1/client/users/${user_id}/reset-password${qs(params)}`,
    { method: "POST" },
  );
}

export async function getClientCalendar(params?: {
  client_id?: string;
  year?: number;
  /** Item 3 — narrow the calendar to a subset of vendors. Omit or
   *  pass an empty array to receive the portfolio-wide view. */
  vendor_ids?: string[];
}): Promise<ClientCalendar> {
  const sp = new URLSearchParams();
  if (params?.client_id) sp.set("client_id", params.client_id);
  if (params?.year !== undefined) sp.set("year", String(params.year));
  for (const vid of params?.vendor_ids ?? []) {
    if (vid) sp.append("vendor_ids", vid);
  }
  const s = sp.toString();
  return fetchJson<ClientCalendar>(
    `/api/v1/client/calendar${s ? `?${s}` : ""}`,
  );
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
  /** Phase 5 / Axis 2 — filter by acceptance state
   *  ("pending" | "accepted" | "rejected"). */
  client_acceptance?: string;
  limit?: number;
}): Promise<ClientSubmissionsResponse> {
  return fetchJson<ClientSubmissionsResponse>(
    `/api/v1/client/submissions${qs(params)}`,
  );
}

// ── Phase 5 — client acceptance axis (Axis 2) ──────────────────────────────

export type ClientDecisionAction = "accept" | "reject" | "reset";

/** Shape of POST /client/submissions/{id}/decision — NOT a Submission.
 *  ``new_acceptance`` is what the row's ``client_acceptance`` becomes. */
export type ClientDecisionResponse = {
  submission_id: string;
  previous_acceptance: string;
  new_acceptance: string;
  action: string;
  reason: string | null;
  override: boolean;
  decided_at: string;
  decided_by_user_id: string;
};

export async function decideClientSubmission(
  submissionId: string,
  body: { action: ClientDecisionAction; reason?: string | null },
  params?: { client_id?: string },
): Promise<ClientDecisionResponse> {
  return fetchJson<ClientDecisionResponse>(
    `/api/v1/client/submissions/${submissionId}/decision${qs(params)}`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export type ClientBulkDecisionResponse = {
  decided: string[];
  failed: Array<{ submission_id: string; detail: string }>;
  decided_count: number;
  failed_count: number;
};

export async function bulkDecideClientSubmissions(
  body: {
    submission_ids: string[];
    action: ClientDecisionAction;
    reason?: string | null;
  },
  params?: { client_id?: string },
): Promise<ClientBulkDecisionResponse> {
  return fetchJson<ClientBulkDecisionResponse>(
    `/api/v1/client/submissions/bulk-decision${qs(params)}`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export type ClientAcceptancePrefs = { auto_accept_valid: boolean };

export async function getClientAcceptancePrefs(params?: {
  client_id?: string;
}): Promise<ClientAcceptancePrefs> {
  return fetchJson<ClientAcceptancePrefs>(
    `/api/v1/client/acceptance-preferences${qs(params)}`,
  );
}

export async function updateClientAcceptancePrefs(
  body: ClientAcceptancePrefs,
  params?: { client_id?: string },
): Promise<ClientAcceptancePrefs> {
  return fetchJson<ClientAcceptancePrefs>(
    `/api/v1/client/acceptance-preferences${qs(params)}`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
}

export async function listClientActivity(params?: {
  client_id?: string;
  limit?: number;
}): Promise<ClientActivityResponse> {
  return fetchJson<ClientActivityResponse>(`/api/v1/client/activity${qs(params)}`);
}

// Key prefix for the bell-summary cache; mutations that change the unread set
// invalidate it so the badge never shows a stale count.
const CLIENT_NOTIFICATION_SUMMARY_KEY = "GET /api/v1/client/notifications/summary";
// The shell remounts on every navigation and re-reads this, and it does not
// poll — so a short TTL coalesces the per-navigation refetches without risking
// staleness (mark-read mutations invalidate it explicitly). Perf audit P2-2.
const CLIENT_NOTIFICATION_SUMMARY_TTL_MS = 15_000;

export async function getClientNotificationSummary(params?: {
  client_id?: string;
}): Promise<ClientNotificationSummary> {
  const path = `/api/v1/client/notifications/summary${qs(params)}`;
  return dedupeRead(
    `GET ${path}`,
    () => fetchJson<ClientNotificationSummary>(path),
    CLIENT_NOTIFICATION_SUMMARY_TTL_MS,
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
  const result = await fetchJson<ClientNotificationItem>(
    `/api/v1/client/notifications/${notificationId}/read${qs(params)}`,
    { method: "POST" },
  );
  // The unread set changed — drop the cached bell summary so the next read is
  // fresh (perf audit P2-2).
  invalidateRead(CLIENT_NOTIFICATION_SUMMARY_KEY);
  return result;
}

export async function markAllClientNotificationsRead(params?: {
  client_id?: string;
}): Promise<ClientNotificationSummary> {
  const result = await fetchJson<ClientNotificationSummary>(
    `/api/v1/client/notifications/read-all${qs(params)}`,
    { method: "POST" },
  );
  invalidateRead(CLIENT_NOTIFICATION_SUMMARY_KEY);
  return result;
}

export async function getClientMetadata(params?: {
  client_id?: string;
}): Promise<ClientMetadataResponse> {
  return fetchJson<ClientMetadataResponse>(`/api/v1/client/metadata${qs(params)}`);
}

export async function downloadClientMetadata(params?: {
  client_id?: string;
}): Promise<Blob> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), DOWNLOAD_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/api/v1/client/metadata/download${qs(params)}`,
      {
        headers: { ...adminAuthHeader() },
        credentials: "include",
        signal: controller.signal,
      },
    );
  } catch (err) {
    if (controller.signal.aborted) {
      throw new ClientApiError(
        0,
        "La descarga tardó demasiado. Inténtalo de nuevo.",
      );
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ClientApiError(response.status, detail || response.statusText);
  }
  return response.blob();
}

/**
 * Phase 5 / Slice 5C — optional filter set passed via query string
 * to the client-scoped vendor expediente ZIP. Same shape as the
 * provider-side ``ExpedienteZipFilters``.
 */
export type ClientVendorExpedienteFilters = {
  status?: string | null;
  period_key?: string | null;
  institution?: string | null;
};

/**
 * Absolute URL of the client-scoped vendor expediente ZIP endpoint.
 *
 * Used by the client portal's vendor detail page. A client_admin
 * resolves a vendor in their portfolio and pulls the expediente
 * as a single ZIP. Backend audits each request as
 * ``client.vendor_expediente_downloaded``. Cookie-auth navigation
 * pattern (open in a new tab so the bearer cookie carries).
 */
/**
 * Item 1 — URL of the per-submission document endpoint. Used by the
 * contract list on the vendor expediente page (and any future
 * per-document open/download action in the client portal). Cookie-
 * auth pattern via `Authorization` header would not work for
 * top-level navigation, so the endpoint also accepts the bearer
 * cookie set by the staff session middleware; opening in a new tab
 * lets the browser carry it. When ``download`` is true the response
 * forces an attachment disposition and the backend writes a
 * ``client.document_downloaded`` audit row.
 */
export function clientSubmissionDocumentUrl(
  submissionId: string,
  opts: { download?: boolean; proxy?: boolean } = {},
): string {
  const params = new URLSearchParams();
  if (opts.download) params.set("download", "1");
  if (opts.proxy) params.set("proxy", "1");
  const qs = params.toString();
  const base = `${API_BASE_URL}/api/v1/client/submissions/${encodeURIComponent(submissionId)}/document`;
  return qs ? `${base}?${qs}` : base;
}

/**
 * Fetch a submission's PDF with the staff JWT and return a Blob URL
 * the caller can hand to an iframe or `window.open`. Mirrors the
 * reviewer-side helper — top-level navigation cannot carry the
 * localStorage bearer, so the only reliable way to preview/open a
 * document is to fetch the bytes with the header and stream them to
 * an object URL. Caller MUST ``URL.revokeObjectURL`` when done.
 */
export async function fetchClientSubmissionDocumentBlob(
  submissionId: string,
  opts: { download?: boolean } = {},
): Promise<string> {
  const headers = new Headers(adminAuthHeader());
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), DOWNLOAD_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(
      clientSubmissionDocumentUrl(submissionId, { ...opts, proxy: true }),
      {
        headers,
        credentials: "include",
        signal: controller.signal,
      },
    );
  } catch (err) {
    if (controller.signal.aborted) {
      throw new ClientApiError(
        0,
        "La descarga tardó demasiado. Inténtalo de nuevo.",
      );
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ClientApiError(response.status, detail || response.statusText);
  }
  const blob = await response.blob();
  return URL.createObjectURL(await toPdfBlob(blob));
}

/**
 * Absolute URL of the vendor expediente ZIP endpoint. Auth is
 * Bearer-only — pass this URL to ``downloadAuthenticatedFile``
 * (``lib/api/download.ts``); a plain ``<a href>`` navigation cannot
 * carry the staff JWT and 401s (audit 2026-06-12).
 */
export function clientVendorExpedienteZipUrl(
  vendorId: string,
  filters: ClientVendorExpedienteFilters = {},
): string {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.period_key) params.set("period_key", filters.period_key);
  if (filters.institution) params.set("institution", filters.institution);
  const qs = params.toString();
  const base = `${API_BASE_URL}/api/v1/client/vendors/${encodeURIComponent(vendorId)}/expediente.zip`;
  return qs ? `${base}?${qs}` : base;
}

/**
 * Absolute URL of the per-provider metadata Excel download (CW-15) — the
 * client master filtered to one provider. Same Bearer-only auth as the
 * expediente ZIP; pass to ``downloadAuthenticatedFile``. Optional
 * ``periodKey`` narrows it to a single period.
 */
export function clientVendorMetadataDownloadUrl(
  vendorId: string,
  periodKey?: string,
): string {
  const base = `${API_BASE_URL}/api/v1/client/vendors/${encodeURIComponent(vendorId)}/metadata/download`;
  return periodKey ? `${base}?period_key=${encodeURIComponent(periodKey)}` : base;
}

// ---------------------------------------------------------------------------
// Junta 2026-05-23 — client onboarding profile
// ---------------------------------------------------------------------------

export type ClientProfile = {
  id: string;
  name: string;
  rfc: string | null;
  email: string | null;
  responsible_name: string | null;
  industry: string | null;
  fiscal_address: string | null;
  phone: string | null;
  notes: string | null;
  onboarding_completed_at: string | null;
};

export type ClientProfileUpdate = {
  responsible_name?: string | null;
  industry?: string | null;
  fiscal_address?: string | null;
  phone?: string | null;
  notes?: string | null;
  /** Item 8 — true on the first-login save so the backend can write
   *  the ``client.legal_consent_accepted`` audit row. */
  terms_accepted?: boolean;
};

export async function getClientProfile(params?: {
  client_id?: string;
}): Promise<ClientProfile> {
  return fetchJson<ClientProfile>(`/api/v1/client/profile${qs(params)}`);
}

export async function updateClientProfile(
  body: ClientProfileUpdate,
  params?: { client_id?: string },
): Promise<ClientProfile> {
  return fetchJson<ClientProfile>(`/api/v1/client/profile${qs(params)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Junta 2026-05-23 — cross-vendor audit package
// ---------------------------------------------------------------------------

/**
 * Filter set sent to the audit-package endpoints. Mirrors the
 * backend ``AuditPackageFilters`` shape. ``null``/empty values omit
 * the corresponding query param so the backend defaults apply
 * (notably: empty ``statuses`` → aprobado-only).
 */
export type AuditPackageFilters = {
  client_id?: string | null;
  period_from?: string | null;
  period_to?: string | null;
  institutions?: string[];
  requirement_codes?: string[];
  statuses?: string[];
  vendor_ids?: string[];
};

export type AuditPackagePreview = {
  file_count: number;
  total_bytes: number;
  vendor_count: number;
  institution_breakdown: Array<{ institution: string; file_count: number }>;
  vendor_breakdown: Array<{ vendor_id: string; file_count: number }>;
  requirement_breakdown: Array<{ requirement_code: string; file_count: number }>;
  over_file_cap: boolean;
  over_bytes_cap: boolean;
  file_cap: number;
  bytes_cap: number;
};

function _appendAuditPackageFilters(
  params: URLSearchParams,
  filters: AuditPackageFilters,
): void {
  if (filters.client_id) params.set("client_id", filters.client_id);
  if (filters.period_from) params.set("period_from", filters.period_from);
  if (filters.period_to) params.set("period_to", filters.period_to);
  for (const inst of filters.institutions ?? []) {
    params.append("institutions", inst);
  }
  for (const code of filters.requirement_codes ?? []) {
    params.append("requirement_codes", code);
  }
  for (const status of filters.statuses ?? []) {
    params.append("statuses", status);
  }
  for (const vid of filters.vendor_ids ?? []) {
    params.append("vendor_ids", vid);
  }
}

/**
 * Pre-flight count + breakdowns used by the live counter on
 * ``/client/auditoria``. Pure read — does not write an audit row.
 */
export async function getClientAuditPackagePreview(
  filters: AuditPackageFilters = {},
): Promise<AuditPackagePreview> {
  const params = new URLSearchParams();
  _appendAuditPackageFilters(params, filters);
  const qs = params.toString();
  const suffix = qs ? `?${qs}` : "";
  return fetchJson<AuditPackagePreview>(
    `/api/v1/client/audit-package/preview${suffix}`,
  );
}

/**
 * Absolute URL of the cross-vendor audit-package ZIP endpoint. Auth
 * is Bearer-only — there is no session cookie on the staff surfaces,
 * so this URL must be fetched via ``downloadAuthenticatedFile``
 * (``lib/api/download.ts``), never followed as a navigation (audit
 * 2026-06-12). Backend renders the INDICE.pdf cover and writes a
 * ``client.audit_package_downloaded`` audit row.
 */
export function clientAuditPackageZipUrl(
  filters: AuditPackageFilters = {},
): string {
  const params = new URLSearchParams();
  _appendAuditPackageFilters(params, filters);
  const qs = params.toString();
  const base = `${API_BASE_URL}/api/v1/client/audit-package.zip`;
  return qs ? `${base}?${qs}` : base;
}

// ---------------------------------------------------------------------------
// Item 2 — audit-package tree picker
// ---------------------------------------------------------------------------

export type AuditPackageTreeNode = {
  submission_id: string;
  vendor_id: string;
  vendor_name: string;
  institution_code: string;
  institution_name: string;
  period_key: string;
  requirement_code: string | null;
  requirement_name: string;
  filename: string;
  size_bytes: number;
  status: string;
  submitted_at_iso: string | null;
};

export type AuditPackageTreeResponse = {
  items: AuditPackageTreeNode[];
  file_count: number;
  total_bytes: number;
  file_cap: number;
  bytes_cap: number;
};

/**
 * Flat list of every document matching the filter set. The frontend
 * composes the Vendor → Institution → Period → Document hierarchy
 * with cascading checkboxes and POSTs the selected ``submission_ids``
 * to the audit-zip endpoint.
 */
export async function getClientAuditPackageTree(
  filters: AuditPackageFilters = {},
): Promise<AuditPackageTreeResponse> {
  const params = new URLSearchParams();
  _appendAuditPackageFilters(params, filters);
  const qs = params.toString();
  const suffix = qs ? `?${qs}` : "";
  return fetchJson<AuditPackageTreeResponse>(
    `/api/v1/client/audit-package/tree${suffix}`,
  );
}

/**
 * POST the audit ZIP with an explicit ``submission_ids`` whitelist.
 * Fetches the response as a Blob so the staff JWT (header bearer)
 * carries the request — top-level navigation cannot.
 */
export async function downloadClientAuditPackageZipPost(
  body: AuditPackageFilters & { submission_ids: string[] },
): Promise<{ blob: Blob; filename: string }> {
  const headers = new Headers(adminAuthHeader());
  headers.set("Content-Type", "application/json");
  // Bound the request the same way the GET download path is: a stalled
  // large-ZIP / headless-Chromium INDICE.pdf stream during a live audit
  // must reject into a visible error, not an infinite "Preparando…"
  // spinner. 120s matches DOWNLOAD_TIMEOUT_MS in download.ts.
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 120_000);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/client/audit-package.zip`, {
      method: "POST",
      headers,
      credentials: "include",
      signal: controller.signal,
      body: JSON.stringify({
        client_id: body.client_id ?? null,
        period_from: body.period_from ?? null,
        period_to: body.period_to ?? null,
        institutions: body.institutions ?? null,
        requirement_codes: body.requirement_codes ?? null,
        statuses: body.statuses ?? null,
        vendor_ids: body.vendor_ids ?? null,
        submission_ids: body.submission_ids,
      }),
    });
  } catch (err) {
    if (controller.signal.aborted) {
      throw new ClientApiError(
        408,
        "La preparación del paquete tardó demasiado. Inténtalo de nuevo.",
      );
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ClientApiError(response.status, detail || response.statusText);
  }
  // Parse a filename hint from Content-Disposition when present so
  // the user gets the same auditoria-<rfc>-<date>.zip naming.
  const disp = response.headers.get("Content-Disposition") || "";
  const filename = parseContentDispositionFilename(disp) ?? "auditoria.zip";
  const blob = await response.blob();
  return { blob, filename };
}

// ─── Cliente Wise copilot — M1 (2026-06-02) ───────────────────────
//
// Mirror of `lib/api/portal.ts`'s `postWiseAsk` / `postWiseEvent` for
// the cliente surface. The cliente Wise dock (`<ClientWiseDock>`)
// reasons about the buyer's portfolio of vendors rather than a single
// vendor's onboarding state; the backend assembles that portfolio
// context server-side from `_resolve_client_id(current, requested)`,
// so the frontend just ships the prompt + allowed CTAs.

export type ClientWiseAskCta = {
  id: string;
  label: string;
  href: string;
  description?: string;
};

export type ClientWisePageContext = {
  route: string;
  page_label: string;
  vendor_id?: string;
  report_id?: string;
  period_key?: string;
};

export type ClientWiseAskResponse = {
  body: string;
  cta_label: string | null;
  cta_href: string | null;
  source: "llm" | "fallback";
};

/** P1 (2026-06-12) — one prior cliente dock turn, shipped so the LLM
 *  can resolve follow-up questions across the portfolio conversation. */
export type ClientWiseHistoryTurn = {
  role: "user" | "assistant";
  content: string;
};

export type ClientWiseEventType =
  | "wise.first_render"
  | "wise.opened"
  | "wise.collapsed"
  | "wise.suggestion_clicked"
  | "wise.suggestion_dismissed"
  | "wise.question_asked"
  // P2 (2026-06-13) — thumbs up/down on a cliente Wise answer.
  | "wise.feedback";

export type ClientWiseEventPayload = Record<string, unknown>;

export async function postClientWiseAsk(
  prompt: string,
  ctas: ClientWiseAskCta[],
  pageContext?: ClientWisePageContext,
  params?: { client_id?: string },
  history?: ClientWiseHistoryTurn[],
): Promise<ClientWiseAskResponse> {
  return fetchJson<ClientWiseAskResponse>(
    `/api/v1/client/wise/ask${qs(params)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        ctas,
        page_context: pageContext ?? null,
        history: history ?? [],
      }),
    },
  );
}

export async function postClientWiseEvent(
  eventType: ClientWiseEventType,
  payload?: ClientWiseEventPayload,
  params?: { client_id?: string },
): Promise<void> {
  // Events route is fire-and-forget telemetry. Swallow any error so
  // a single dropped /events call never blocks the dock from firing
  // subsequent ones. The route returns 202 with a small JSON body
  // we don't need to parse.
  try {
    await fetchJson<unknown>(`/api/v1/client/wise/events${qs(params)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_type: eventType, payload: payload ?? null }),
    });
  } catch {
    // intentional silent swallow — analytics never blocks UX.
  }
}
