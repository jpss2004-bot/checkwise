/**
 * Provider correction-request API client (Stage 2.7-a).
 *
 * Replaces the localStorage-only ``lib/mock/corrections.ts`` with the
 * real ``POST /api/v1/portal/workspaces/{id}/correction-requests``
 * endpoint. Tier B-locked: the form can only submit changes to
 * ``contact_email`` / ``contact_phone`` / ``contact_name``. Anything
 * else needs to go through support — the backend rejects with 422 and
 * a Spanish "escríbenos a soporte" detail.
 *
 * Auth resolution mirrors the rest of the portal API:
 *   1. ``Authorization: Bearer <jwt>`` from the admin/user session
 *      (cross-origin-safe, immune to third-party cookie blocking).
 *   2. ``credentials: "include"`` so the httpOnly portal session
 *      cookie still gets sent when the browser permits it.
 */

import { adminAuthHeader } from "@/lib/session/admin";

const API_BASE_URL =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) ||
  "http://127.0.0.1:8000";

/**
 * Locked Tier B field whitelist. Mirrors
 * ``apps/api/app/services/correction_request_service.py::TIER_B_FIELDS``
 * — keep these two lists in sync.
 */
export const TIER_B_FIELDS = [
  "contact_email",
  "contact_phone",
  "contact_name",
] as const;

export type TierBField = (typeof TIER_B_FIELDS)[number];

export const TIER_B_FIELD_LABEL_ES: Record<TierBField, string> = {
  contact_email: "Correo de contacto",
  contact_phone: "Teléfono de contacto",
  contact_name: "Nombre de la persona de contacto",
};

export interface CorrectionRequestInput {
  workspace_id: string;
  field: TierBField;
  current_value: string;
  proposed_value: string;
  reason: string;
  message?: string;
}

export interface CorrectionRequestRecord {
  id: string;
  field: TierBField;
  status: "pending";
  created_at_iso: string;
}

export type CorrectionErrorCode =
  | "missing_reason"
  | "no_change"
  | "unknown_field"
  | "rate_limited"
  | "unauthorized"
  | "network";

export interface CorrectionRequestResult {
  ok: boolean;
  request?: CorrectionRequestRecord;
  error?: CorrectionErrorCode;
  detail?: string;
}

/**
 * Submit a Tier B correction request to the backend.
 *
 * Errors are returned as a result object rather than thrown so the
 * form can render them inline. The detail field carries the backend's
 * Spanish copy verbatim when available — caller may render it.
 */
export async function submitCorrectionRequest(
  input: CorrectionRequestInput,
): Promise<CorrectionRequestResult> {
  const proposed = input.proposed_value.trim();
  const current = input.current_value.trim();
  if (!proposed || proposed === current) {
    return { ok: false, error: "no_change" };
  }
  if (input.reason.trim().length < 4) {
    return { ok: false, error: "missing_reason" };
  }
  if (!TIER_B_FIELDS.includes(input.field)) {
    return { ok: false, error: "unknown_field" };
  }

  const body = {
    field: input.field,
    current_value: current,
    proposed_value: proposed,
    reason: input.reason.trim(),
    message: input.message?.trim() || undefined,
  };

  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/api/v1/portal/workspaces/${encodeURIComponent(
        input.workspace_id,
      )}/correction-requests`,
      {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          ...adminAuthHeader(),
        },
        body: JSON.stringify(body),
      },
    );
  } catch {
    return { ok: false, error: "network" };
  }

  if (response.status === 401 || response.status === 403) {
    return { ok: false, error: "unauthorized" };
  }
  if (response.status === 429) {
    let detail: string | undefined;
    try {
      detail = (await response.json())?.detail;
    } catch {
      detail = undefined;
    }
    return { ok: false, error: "rate_limited", detail };
  }
  if (response.status === 422) {
    let detail: string | undefined;
    try {
      detail = (await response.json())?.detail;
    } catch {
      detail = undefined;
    }
    return { ok: false, error: "unknown_field", detail };
  }
  if (!response.ok) {
    return { ok: false, error: "network" };
  }

  const payload = (await response.json()) as CorrectionRequestRecord;
  return { ok: true, request: payload };
}
