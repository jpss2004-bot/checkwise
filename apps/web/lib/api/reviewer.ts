/**
 * Typed wrapper over the Patch 7 reviewer endpoints.
 *
 * All calls expect a JWT (issued by /api/v1/auth/login) carrying either
 * the ``reviewer`` or ``internal_admin`` role.
 */

import type { RequirementStatus, SubmissionDetail } from "@/lib/api/portal";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ReviewerApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ReviewerApiError";
  }
}

async function fetchJson<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ReviewerApiError(response.status, detail || response.statusText);
  }
  return (await response.json()) as T;
}

// ---------------------------------------------------------------------------
// Queue
// ---------------------------------------------------------------------------

export type QueueItem = {
  submission_id: string;
  status: RequirementStatus;
  submitted_at: string;
  age_hours: number;
  requirement: {
    requirement_code: string | null;
    name: string | null;
    institution: string | null;
  };
  period: {
    period_key: string | null;
    code: string | null;
  };
  provider: {
    vendor_name: string;
    vendor_rfc: string | null;
    client_name: string;
    /** Item 5 follow-up — surfaced so the reviewer queue can link
     *  the vendor name to /client/vendors/[id]?client_id=…. Nullable
     *  for legacy backend builds and for rows where the underlying
     *  Vendor/Client row was deleted. */
    vendor_id: string | null;
    client_id: string | null;
  };
  signal_count: number;
  has_mismatch: boolean;
  /** Phase A document revalidation — authenticity verdict from the
   *  local PDF-forensics analyzer. null = not analyzed (legacy rows
   *  or analyzer failure; intake is fail-open). */
  authenticity_risk: "clean" | "suspicious" | "high_risk" | null;
};

export type QueueResponse = {
  items: QueueItem[];
  total: number;
  next_cursor: string | null;
  /** Phase 9 / Slice 9A — rolling 7-day count of submissions that
   *  resolved positively (aprobado + excepción legal). Drives the
   *  stat strip above the queue. Always present (backend defaults
   *  to 0). */
  approved_last_7d_count: number;
  /** Phase 9 / Slice 9A — rolling 7-day count of submissions
   *  rejected by the reviewer in the same window. */
  rejected_last_7d_count: number;
};

export type QueueFilters = {
  status?: RequirementStatus;
  institution?: string;
  limit?: number;
  /** Keyset cursor from a prior page's ``next_cursor`` — opaque,
   *  pass back verbatim to fetch the next FIFO page. */
  cursor?: string;
  /** Phase A — server-side authenticity-risk filter. */
  risk?: "clean" | "suspicious" | "high_risk";
};

export async function getReviewerQueue(
  token: string,
  filters: QueueFilters = {},
): Promise<QueueResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.institution) params.set("institution", filters.institution);
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.cursor) params.set("cursor", filters.cursor);
  if (filters.risk) params.set("risk", filters.risk);
  const qs = params.toString();
  return await fetchJson<QueueResponse>(
    `/api/v1/reviewer/queue${qs ? `?${qs}` : ""}`,
    token,
  );
}

// ---------------------------------------------------------------------------
// Detail
// ---------------------------------------------------------------------------

/**
 * Vendor identity block — reviewer endpoint only (P1 audit fix,
 * 2026-06-10). ``vendor_rfc`` is the EXPECTED RFC from the vendor
 * registry, so the decision screen can compare it against the
 * OCR-detected RFC and surface a ✓/✗ match without the reviewer
 * memorizing the queue row.
 */
export type ReviewerVendorBlock = {
  vendor_id: string | null;
  vendor_name: string | null;
  vendor_rfc: string | null;
  persona_type: string | null;
  client_id: string | null;
  client_name: string | null;
  workspace_id: string | null;
};

/** Phase A document revalidation — one named reason the forensics
 *  analyzer flagged. ``detail_es`` is reviewer-facing Spanish. */
export type AuthenticityReason = {
  code: string;
  severity: "info" | "medium" | "high";
  detail_es: string;
};

/** The authenticity verdict block on the reviewer detail. ``analyzed``
 *  is false for legacy rows or when the fail-open analyzer errored. */
export type AuthenticityBlock = {
  risk: "clean" | "suspicious" | "high_risk" | null;
  reasons: AuthenticityReason[];
  forensics: Record<string, unknown> | null;
  analyzed: boolean;
};

/** Phase B document revalidation — one QR code decoded from the PDF.
 *  ``official`` is true only when the host is on the government-domain
 *  allowlist; the UI must NEVER render a clickable link for
 *  non-official hosts (a malicious upload could embed a phishing QR). */
export type VerificationQrCode = {
  page: number;
  content: string;
  is_url: boolean;
  host: string | null;
  official: boolean;
  institution_guess: "sat" | "imss" | "infonavit" | "stps" | null;
};

export type VerificationFolio = {
  kind: string;
  value: string;
};

/** QR/folio verification anchors on the reviewer detail. ``analyzed``
 *  is false for legacy rows (pre-0039) or extraction failure. */
export type VerificationBlock = {
  qr_codes: VerificationQrCode[];
  folios: VerificationFolio[];
  analyzed: boolean;
};

/** The reviewer detail = the shared submission detail + the vendor
 *  identity block + the authenticity verdict + verification anchors
 *  (all absent on the provider-facing portal endpoint). */
/** Phase E — the system's pre-computed approval recommendation. The
 *  reviewer always decides; this only pre-selects and explains. Null
 *  when there is no document inspection to judge against. */
export type ApprovalSuggestion = {
  /** True only when every criterion below passed. */
  suggested: boolean;
  /** Best available match confidence, or null when none exists. */
  confidence: number | null;
  confidence_source: "shadow" | "heuristic" | null;
  criteria: {
    match_ok: boolean;
    risk_clean: boolean;
    recurring: boolean;
  };
  /** One-sentence Spanish rationale for the suggested action. */
  detail_es: string;
};

export type ReviewerSubmissionDetail = SubmissionDetail & {
  vendor: ReviewerVendorBlock | null;
  authenticity: AuthenticityBlock | null;
  verification: VerificationBlock | null;
  approval_suggestion: ApprovalSuggestion | null;
};

export async function getReviewerSubmission(
  token: string,
  submissionId: string,
): Promise<ReviewerSubmissionDetail> {
  return await fetchJson<ReviewerSubmissionDetail>(
    `/api/v1/reviewer/submissions/${submissionId}`,
    token,
  );
}

// ---------------------------------------------------------------------------
// Decision
// ---------------------------------------------------------------------------

export type DecisionAction =
  | "approve"
  | "reject"
  | "request_clarification"
  | "mark_exception";

export type DecisionResponse = {
  submission_id: string;
  previous_status: string;
  new_status: string;
  action: DecisionAction;
  reason: string | null;
  /** Phase 9 / Slice 9A — optional reviewer observation for the
   *  provider. ``null`` when not sent. */
  observations: string | null;
  decided_at: string;
  reviewer_user_id: string;
  /** Oldest submission still pending review after this decision
   *  (global FIFO), or null when the queue is drained. Drives the
   *  "Siguiente documento" auto-advance. */
  next_pending_submission_id: string | null;
};

export async function submitDecision(
  token: string,
  submissionId: string,
  action: DecisionAction,
  reason: string | null,
  observations: string | null = null,
  /** Phase E — suggestion-acceptance telemetry. Pass true/false when
   *  the decision screen showed an approval suggestion (accepted vs
   *  overridden); leave null when no suggestion was shown. Feeds the
   *  human-agreement rate that gates per-type auto-approve unlock. */
  acceptedSuggestion: boolean | null = null,
): Promise<DecisionResponse> {
  return await fetchJson<DecisionResponse>(
    `/api/v1/reviewer/submissions/${submissionId}/decision`,
    token,
    {
      method: "POST",
      body: JSON.stringify({
        action,
        reason,
        observations,
        accepted_suggestion: acceptedSuggestion,
      }),
    },
  );
}

/**
 * Absolute URL of the reviewer-side PDF streaming endpoint. The
 * caller follows this URL as a top-level navigation
 * (``<a target="_blank">``) when the user clicks "Descargar PDF".
 * The backend writes a ``reviewer.document_downloaded`` audit row
 * on ``?download=1``.
 */
export function reviewerDocumentUrl(submissionId: string): string {
  return `${API_BASE_URL}/api/v1/reviewer/submissions/${submissionId}/document`;
}

export function reviewerDocumentDownloadUrl(submissionId: string): string {
  return `${reviewerDocumentUrl(submissionId)}?download=1`;
}

/**
 * Fetch the submission's PDF with the reviewer JWT and return a Blob
 * URL the iframe can render. Mirrors the portal-side helper but uses
 * the admin/reviewer token. The caller MUST ``URL.revokeObjectURL``
 * the returned string when the iframe unmounts.
 */
export async function fetchReviewerSubmissionDocumentBlob(
  token: string,
  submissionId: string,
): Promise<string> {
  const headers = new Headers();
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(reviewerDocumentUrl(submissionId), {
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ReviewerApiError(
      response.status,
      detail || response.statusText,
    );
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}
