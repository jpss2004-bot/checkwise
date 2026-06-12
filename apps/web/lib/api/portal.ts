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

// Default per-request timeout for JSON calls. A stalled API should
// surface a clear error rather than spin forever (audit 2026-06-09).
const REQUEST_TIMEOUT_MS = 30_000;

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
  /** Stage 2 (BL-002, 2026-05-20) — first-upload guidance copy.
   *  ``anatomy`` is the 2–4 sentence description of what the document
   *  must contain; ``where_to_obtain`` explains how to get it;
   *  ``common_errors`` is a short list of pitfalls. All three default
   *  to per-institution fallbacks on the backend so the field is never
   *  null — an empty string / empty array means "no extra guidance for
   *  this institution," not "missing." */
  anatomy: string;
  where_to_obtain: string;
  common_errors: string[];
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
  /** Filename of the current submission's PDF, when one exists. Surfaced
   *  in the calendar cell popover + drawer per Jorge feedback. */
  filename: string | null;
  /** ISO timestamp of the current submission, when one exists. */
  submitted_at: string | null;
  /** Phase 5 — backend-owned UX enrichment. */
  required_document: string;
  due_month: number;
  /** ISO date (``YYYY-MM-DD``). Conventional day-17 cutoff for monthly /
   *  bimestral / cuatrimestral slots; the SAT annual slot uses day 30. */
  deadline_iso: string;
  suggested_action: string;
  /** Canonical upload URL ready to use as ``<Link href>``. */
  href: string;
  /** Stage 2.7 (T5 parity, 2026-05-20) — first-upload guidance.
   *  Populated by the backend with per-institution fallbacks and
   *  per-doc-name overrides for the highest-volume recurring items.
   *  Empty string / empty array means "no extra guidance," never
   *  "missing data." */
  anatomy: string;
  where_to_obtain: string;
  common_errors: string[];
  /** Catalog v2 (Session 2, 2026-05-21) — accepted-document
   *  alternatives. Empty list on v1 rows (default backend behavior).
   *  Non-empty on v2 rows, one entry per acceptable doc type. The
   *  wizard's alternatives-mode UX renders these as a radio picker;
   *  the calendar drawer renders one DocumentGuidanceDisclosure per
   *  entry. */
  accepts_documents: CalendarAcceptedDocument[];
  /** Catalog v2 — how many of accepts_documents must be submitted
   *  to satisfy the obligation. ``"one"`` is the production default
   *  for every v2 row today (either-or-both semantics). ``"all"`` is
   *  reserved for future obligations that need a complete package. */
  minimum_documents: "one" | "all";
};

/** A single entry inside CalendarItem.accepts_documents — the rich
 *  per-doc detail the frontend renders for v2 rows. */
export type CalendarAcceptedDocument = {
  name: string;
  anatomy: string;
  where_to_obtain: string;
  common_errors: string[];
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
  // Fail fast instead of hanging forever if the API stalls (audit
  // 2026-06-09). A caller-provided signal wins; otherwise we apply a
  // default timeout so a hung request surfaces a clear error rather than
  // an infinite spinner.
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
    if (controller?.signal.aborted) {
      throw new PortalApiError(
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

/** Current occupant of an obligation slot — drives the upload wizard's
 *  "this replaces an existing document" warning. All nulls when empty. */
export type SlotState = {
  requirement_code: string;
  period_key: string | null;
  current_status: RequirementStatus | null;
  current_submission_id: string | null;
};

export async function getSlotState(
  session: PortalSession,
  opts: { requirement_code: string; period_key?: string | null },
): Promise<SlotState> {
  const params = new URLSearchParams({ requirement_code: opts.requirement_code });
  if (opts.period_key) params.set("period_key", opts.period_key);
  return await fetchJson<SlotState>(
    `/api/v1/portal/workspaces/${session.workspace_id}/slot-state?${params.toString()}`,
    { method: "GET" },
    session,
  );
}

/** Provider-facing soft match feedback (2026-06-11). Non-null means
 *  "this file probably isn't the requested document" — a friendly,
 *  informational warning. The upload is still accepted and queued for
 *  normal review; this never blocks. Match-only by design: authenticity
 *  and risk signals are never provider-facing. Returned on the single
 *  upload response and on each ``documents[]`` entry of the batch
 *  response. */
export type MatchFeedback = {
  confidence: number | null;
  warning_es: string;
  expected_label: string | null;
};

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

/** Phase 2 (Claude shadow) — internal AI comparison block, present
 *  ONLY on the admin reviewer endpoint. The provider portal endpoint
 *  never emits this field. Both `heuristic` and `shadow` carry the
 *  same `signals` shape so the comparison card can render a single
 *  diff table; `shadow.completed_at === null` means the background
 *  shadow run has not finished yet.
 */
export type ShadowAnalysisSignals = {
  detected_institution: string | null;
  detected_document_type: string | null;
  detected_rfcs: string[];
  detected_dates: string[];
  period_mentions: string[];
  requirement_match_confidence: number | null;
  mismatch_reason: string | null;
  anomaly_codes?: string[];
  _meta?: Record<string, unknown>;
};

export type ShadowAnalysisPayload = {
  heuristic: {
    provider_id: string;
    completed_at: string | null;
    signals: ShadowAnalysisSignals;
  };
  shadow: {
    provider_id: string | null;
    prompt_version: string | null;
    completed_at: string | null;
    latency_ms: number | null;
    error: string | null;
    confidence: number | null;
    signals: ShadowAnalysisSignals | null;
  };
};

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
  /** Phase 2 / Slice 2B — the reviewer's plain-Spanish reason for the
   *  most recent decision (reject / clarification / mark-exception),
   *  or null when no reviewer decision has been applied. The page
   *  renders this as a hero card for actionable statuses so the
   *  reviewer's words aren't buried in the timeline. */
  reviewer_note: string | null;
  /** Phase 2 (Claude shadow) — admin-only comparison block. Omitted
   *  on the provider-facing endpoint. */
  shadow_analysis?: ShadowAnalysisPayload | null;
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

/**
 * Absolute URL of the PDF-streaming endpoint. Used as the
 * ``Authorization``-carrying fetch target by
 * ``fetchSubmissionDocumentBlob`` and as an opt-out fallback for
 * callers that don't need the Blob-URL behavior.
 */
export function submissionDocumentUrl(
  session: PortalSession,
  submissionId: string,
): string {
  return `${API_BASE_URL}/api/v1/portal/workspaces/${session.workspace_id}/submissions/${submissionId}/document`;
}

/**
 * Absolute URL of the PDF download endpoint (attachment disposition).
 *
 * Phase 5 / Slice 5A — the same backend endpoint as
 * ``submissionDocumentUrl`` but with ``?download=1``. When the user
 * follows this URL the browser triggers a save dialog instead of
 * inline-rendering the PDF, AND the backend writes a
 * ``provider.document_downloaded`` audit row. Use this for the
 * "Descargar PDF" button on the submission detail page; keep the
 * inline URL for the iframe preview.
 *
 * Authentication note: the URL is hit as a top-level navigation
 * (``window.open`` / ``<a target="_blank">``), so it relies on the
 * portal session cookie. On dev with same-origin SameSite=Lax the
 * cookie tags along; on prod with SameSite=None+Secure it also
 * works. If a deploy ever breaks cookie delivery, the redirect to a
 * presigned S3 URL would still work (S3 doesn't need the cookie),
 * and the local fallback would 401 — which the page can surface as
 * "intenta de nuevo" rather than failing silently.
 */
export function submissionDownloadUrl(
  session: PortalSession,
  submissionId: string,
): string {
  return `${submissionDocumentUrl(session, submissionId)}?download=1`;
}

/**
 * Phase 5 / Slice 5C — optional filter set passed via query string
 * to the expediente ZIP endpoint. ``null``/empty values omit the
 * filter — the backend treats no param as "no filter" so the
 * caller doesn't need to distinguish.
 */
export type ExpedienteZipFilters = {
  status?: string | null;
  period_key?: string | null;
  institution?: string | null;
};

/**
 * Absolute URL of the workspace's expediente ZIP endpoint.
 *
 * Phase 5 / Slice 5B — backend-streamed ZIP of every uploaded
 * document on the workspace (institution/period folder layout,
 * 200-file / 500MB caps). The backend writes a
 * ``provider.expediente_downloaded`` audit row before streaming
 * begins, so the audit trail records intent even if the user
 * aborts mid-download. Same cookie-auth navigation pattern as the
 * single-document download.
 *
 * Slice 5C — accepts optional ``filters`` (status / period_key /
 * institution). The same backend caps apply to the filtered subset.
 */
export function expedienteZipUrl(
  session: PortalSession,
  filters: ExpedienteZipFilters = {},
): string {
  const base = `${API_BASE_URL}/api/v1/portal/workspaces/${session.workspace_id}/expediente.zip`;
  const qs = _buildExpedienteQuery(filters);
  return qs ? `${base}?${qs}` : base;
}

function _buildExpedienteQuery(filters: ExpedienteZipFilters): string {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.period_key) params.set("period_key", filters.period_key);
  if (filters.institution) params.set("institution", filters.institution);
  return params.toString();
}

/**
 * Fetch the submission's PDF with the same auth pattern as the rest
 * of the portal client (Bearer JWT + cookie fallback) and return a
 * Blob URL the iframe can render.
 *
 * Background: pointing an ``<iframe src={apiUrl}>`` directly at the
 * API endpoint relies on the browser sending the portal session
 * cookie on a cross-site subresource request. In local dev the
 * cookie is ``SameSite=Lax`` (Chrome blocks it for iframe loads
 * across origins); in production the cookie is ``SameSite=None;
 * Secure`` but third-party cookie blocking can still drop it. The
 * Bearer JWT is only sendable via ``fetch`` headers — not directly
 * from an iframe ``src`` — so we fetch + Blob-URL the bytes
 * ourselves. The caller MUST ``URL.revokeObjectURL`` the returned
 * string when the iframe unmounts.
 */
export async function fetchSubmissionDocumentBlob(
  session: PortalSession,
  submissionId: string,
): Promise<string> {
  const headers = new Headers();
  const adminSession = readAdminSession();
  if (adminSession?.access_token) {
    headers.set("Authorization", `Bearer ${adminSession.access_token}`);
  }
  if (
    session.access_token &&
    session.access_token !== "cookie-managed"
  ) {
    headers.set("X-Workspace-Token", session.access_token);
  }
  const response = await fetch(submissionDocumentUrl(session, submissionId), {
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new PortalApiError(response.status, detail || response.statusText);
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export type WorkspaceSubmissionListItem = {
  submission_id: string;
  requirement_code: string | null;
  requirement_name: string;
  institution: string;
  period_key: string | null;
  status: string;
  submitted_at: string;
  filename: string | null;
  href: string;
};

export type WorkspaceSubmissionsList = {
  items: WorkspaceSubmissionListItem[];
  total: number;
};

export async function listWorkspaceSubmissions(
  session: PortalSession,
): Promise<WorkspaceSubmissionsList> {
  return await fetchJson<WorkspaceSubmissionsList>(
    `/api/v1/portal/workspaces/${session.workspace_id}/submissions`,
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
  | "upcoming"
  // P1-c (2026-05-20): EXPIRED required slots emit "regularize"
  // so the provider sees the missed obligation in their action list.
  | "regularize";

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
  /** Wise Phase 1 (2026-05-21) — the reviewer's most recent
   *  decision message for rejected / needs_correction /
   *  possible_mismatch slots. Null otherwise. Surfaces inline in
   *  the Wise dock so providers see the literal instruction. */
  reviewer_note?: string | null;
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
  /** P1.6: days-until-deadline so the reports pulse strip can bucket
   *  upcoming items by urgency without re-parsing period_key. May be
   *  undefined on older payloads or null when the period_key isn't
   *  parseable. */
  due_in_days?: number | null;
};

export type DashboardInstitutionBreakdown = {
  /** Lowercase institution code (``sat``, ``imss``, ``infonavit``,
   *  ``stps_repse``, ``interno_cliente``, …). */
  institution: string;
  approved: number;
  in_review: number;
  needs_action: number;
  pending: number;
  total: number;
};

export type DashboardRecentUpload = {
  submission_id: string;
  requirement_code: string | null;
  requirement_name: string;
  institution: string;
  period_key: string | null;
  /** Canonical RequirementStatus value from the backend (e.g.
   *  ``aprobado``, ``pendiente_revision``). Mapped to a UI state
   *  via ``statusToDocumentStateCode``. */
  status: string;
  /** ISO timestamp — when the provider uploaded this submission. */
  submitted_at: string;
  filename: string | null;
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
  /** Session 4 (2026-05-21) — most recent submissions, newest
   *  first. Older payloads may omit; default to ``[]`` defensively. */
  recent_uploads?: DashboardRecentUpload[];
  /** Session 5 (2026-05-21) — per-institution rollup of required
   *  slot states. Older payloads may omit; default to ``[]``. */
  institution_breakdown?: DashboardInstitutionBreakdown[];
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
  // Full register: roomy surfaces (filters, expediente card, audit preview)
  // use "Interno / Cliente". Dense report-surface chips deliberately use the
  // short "Interno" — see the note in compliance-pulse-strip.tsx.
  interno_cliente: "Interno / Cliente",
  // Synthetic code the audit-package backend mints for contract-type
  // submissions (item 1 follow-up). Lets the auditoria preview chip,
  // the tree picker group label, and any future surface that reads
  // these labels render "Contrato" consistently.
  contrato: "Contrato",
  // Synthetic code for onboarding corporate docs (acta constitutiva,
  // official ID) lifted into the dedicated "corporativo" group — mirrors
  // the contract carve-out so the preview chip and tree label match.
  corporativo: "Documentación Corporativa",
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

// ---------------------------------------------------------------------------
// Wise copilot — analytics events (Phase 1, 2026-05-21)
// ---------------------------------------------------------------------------

/** Allowed Wise event types — mirrors the backend's
 *  ``_WISE_ALLOWED_EVENT_TYPES`` frozenset. Kept as a union here so
 *  callers get autocompletion and a typo-proof emission API. */
export type WiseEventType =
  | "wise.first_render"
  | "wise.opened"
  | "wise.collapsed"
  | "wise.suggestion_clicked"
  | "wise.suggestion_dismissed"
  // Phase 2.a (2026-05-21) — chat composer submits a prompt.
  | "wise.question_asked";

export type WiseEventPayload = Record<string, unknown>;

export type WiseEventResponse = {
  id: string;
  event_type: WiseEventType;
  occurred_at: string;
};

/**
 * Fire-and-forget telemetry for the Wise copilot dock.
 *
 * Swallows network/auth errors silently — analytics is best-effort
 * and must never block the UI thread or surface a toast to the
 * vendor. Backend rejects unknown event_type strings with a 400;
 * that's fine to drop too.
 */
export async function postWiseEvent(
  session: PortalSession,
  event_type: WiseEventType,
  payload?: WiseEventPayload,
): Promise<void> {
  try {
    await fetchJson<WiseEventResponse>(
      `/api/v1/portal/workspaces/${session.workspace_id}/wise/events`,
      {
        method: "POST",
        body: JSON.stringify({ event_type, payload: payload ?? null }),
      },
      session,
    );
  } catch {
    // Analytics is best-effort. Stay quiet.
  }
}

// ---------------------------------------------------------------------------
// Wise copilot — LLM ask endpoint (Phase 2.b)
// ---------------------------------------------------------------------------

/** One CTA option the dock offers the model. ``id`` is the canonical
 *  matcher the model picks; the backend echoes back ``label`` +
 *  ``href`` (or null if the model didn't pick one / picked an
 *  invalid id). */
export type WiseAskCta = {
  id: string;
  label: string;
  href: string;
  description?: string;
};

/** Phase 4 (2026-05-21) — per-page context shipped by the dock so
 *  the LLM knows which portal screen the user is on and what task
 *  (requirement / period / submission) they're working on. Matches
 *  the backend ``WisePageContextIn`` schema one-for-one. */
export type WisePageContext = {
  route: string;
  page_label: string;
  requirement_code?: string;
  requirement_name?: string;
  submission_id?: string;
  period_key?: string;
};

export type WiseAskResponse = {
  body: string;
  cta_label: string | null;
  cta_href: string | null;
  source: "llm" | "fallback";
};

/**
 * Ask Wise — LLM-backed free-text reply for the copilot dock.
 *
 * Phase 3 (2026-05-21) — the backend now assembles the full
 * workspace + catalog + glossary context server-side from the DB,
 * so the dock only ships the prompt and the allowed CTAs. The
 * backend still accepts a legacy ``digest`` field for backward
 * compat during the deploy transition, but we no longer send it.
 *
 * Returns the structured reply. Rethrows on hard failures (auth
 * error, 5xx) so the dock can show a "tuve un problema" bubble
 * instead of pretending nothing happened.
 */
export async function postWiseAsk(
  session: PortalSession,
  prompt: string,
  ctas: WiseAskCta[],
  page_context?: WisePageContext,
): Promise<WiseAskResponse> {
  return await fetchJson<WiseAskResponse>(
    `/api/v1/portal/workspaces/${session.workspace_id}/wise/ask`,
    {
      method: "POST",
      body: JSON.stringify({
        prompt,
        ctas,
        ...(page_context ? { page_context } : {}),
      }),
    },
    session,
  );
}

// ---------------------------------------------------------------------------
// Phase 4 / Slice 4B — provider notifications
// ---------------------------------------------------------------------------
//
// Mirrors the client-side notification API. Severity is the shared
// ``NotificationSeverity`` literal (re-exported from
// ``lib/api/client``) so the portal page can reuse the same
// severity-tone tokens. All four routes are workspace-scoped under
// ``/api/v1/portal/workspaces/{id}/notifications`` and gated by the
// existing ``current_portal_workspace`` tenant guard.

export type ProviderNotificationItem = {
  id: string;
  notification_type: string;
  severity: "green" | "yellow" | "red" | "info";
  /** Phase 7 / Slice N9b — canonical category for chip filtering. */
  category:
    | "renewal"
    | "reporting"
    | "verification"
    | "account"
    | "admin"
    | "other";
  title: string;
  body: string;
  action_url: string | null;
  submission_id: string | null;
  payload: Record<string, unknown> | null;
  read_at: string | null;
  created_at: string;
};

export type ProviderNotificationsResponse = {
  workspace_id: string;
  items: ProviderNotificationItem[];
  total: number;
  unread_count: number;
  /** Phase 7 / Slice N9b — subset of ``unread_count`` whose
   *  severity is ``red`` or ``yellow``. Drives the portal bell. */
  unread_actionable_count: number;
  limit: number;
};

export type ProviderNotificationSummary = {
  workspace_id: string;
  unread_count: number;
  unread_actionable_count: number;
};

export async function getProviderNotificationSummary(
  session: PortalSession,
): Promise<ProviderNotificationSummary> {
  return await fetchJson<ProviderNotificationSummary>(
    `/api/v1/portal/workspaces/${session.workspace_id}/notifications/summary`,
    { method: "GET" },
    session,
  );
}

export async function listProviderNotifications(
  session: PortalSession,
  params: { unread_only?: boolean; limit?: number } = {},
): Promise<ProviderNotificationsResponse> {
  const search = new URLSearchParams();
  if (params.unread_only) search.set("unread_only", "true");
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  const qs = search.toString();
  return await fetchJson<ProviderNotificationsResponse>(
    `/api/v1/portal/workspaces/${session.workspace_id}/notifications${qs ? `?${qs}` : ""}`,
    { method: "GET" },
    session,
  );
}

export async function markProviderNotificationRead(
  session: PortalSession,
  notificationId: string,
): Promise<ProviderNotificationItem> {
  return await fetchJson<ProviderNotificationItem>(
    `/api/v1/portal/workspaces/${session.workspace_id}/notifications/${encodeURIComponent(notificationId)}/read`,
    { method: "POST" },
    session,
  );
}

export async function markAllProviderNotificationsRead(
  session: PortalSession,
): Promise<ProviderNotificationSummary> {
  return await fetchJson<ProviderNotificationSummary>(
    `/api/v1/portal/workspaces/${session.workspace_id}/notifications/read-all`,
    { method: "POST" },
    session,
  );
}
