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
};

export async function getReviewerQueue(
  token: string,
  filters: QueueFilters = {},
): Promise<QueueResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.institution) params.set("institution", filters.institution);
  if (filters.limit) params.set("limit", String(filters.limit));
  const qs = params.toString();
  return await fetchJson<QueueResponse>(
    `/api/v1/reviewer/queue${qs ? `?${qs}` : ""}`,
    token,
  );
}

// ---------------------------------------------------------------------------
// Detail
// ---------------------------------------------------------------------------

export async function getReviewerSubmission(
  token: string,
  submissionId: string,
): Promise<SubmissionDetail> {
  return await fetchJson<SubmissionDetail>(
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
};

export async function submitDecision(
  token: string,
  submissionId: string,
  action: DecisionAction,
  reason: string | null,
  observations: string | null = null,
): Promise<DecisionResponse> {
  return await fetchJson<DecisionResponse>(
    `/api/v1/reviewer/submissions/${submissionId}/decision`,
    token,
    {
      method: "POST",
      body: JSON.stringify({ action, reason, observations }),
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
