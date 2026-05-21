/**
 * MOCK profile / workspace correction request submission.
 *
 * The 1.6 brief says: when a user wants to change a tenant-locked
 * field (RFC, role, company, workspace_id …) the change MUST NOT be
 * applied on the client. Instead a ProfileCorrectionRequest is
 * recorded for backend review.
 *
 * This mock persists requests in localStorage so the UI can show a
 * success state. Nothing leaves the browser yet.
 *
 * TODO[backend-integration]:
 *   - POST /api/v1/workspace/corrections  → persist + audit-log
 *   - GET  /api/v1/workspace/corrections  → list for admin review
 *   - POST /api/v1/workspace/corrections/{id}/approve|reject
 *   - Notify CheckWise / Legal Shelf staff (Slack / email)
 *
 * TODO[security-backend]:
 *   - Verify the user owns the workspace_id they reference.
 *   - Reject correction targets that aren't in the allowed field list.
 *   - Throttle to prevent abuse.
 *   - Sanitize current_value / proposed_value before display.
 */

import type {
  EditableProfileFields,
  ProfileCorrectionRequest,
  ProtectedWorkspaceFields,
} from "@/lib/workspace/types";

const STORAGE_KEY = "checkwise.mock.corrections.v1";

/** Fields that always require admin review when corrected. */
const PROTECTED_KEYS = new Set<keyof ProtectedWorkspaceFields>([
  "workspace_id",
  "tenant_id",
  "client_id",
  "provider_id",
  "role",
  "rfc",
  "email",
  "company_legal_name",
  "email_domain",
]);

export function isProtectedField(
  field: string,
): field is keyof ProtectedWorkspaceFields {
  return PROTECTED_KEYS.has(field as keyof ProtectedWorkspaceFields);
}

function newId(): string {
  return `cor-${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36).slice(-4)}`;
}

function load(): ProfileCorrectionRequest[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ProfileCorrectionRequest[]) : [];
  } catch {
    return [];
  }
}

function save(list: ProfileCorrectionRequest[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
}

export interface SubmitCorrectionInput {
  workspace_id: string;
  field: ProfileCorrectionRequest["field"];
  current_value: string;
  proposed_value: string;
  reason: string;
  message?: string;
}

export interface SubmitCorrectionResult {
  ok: boolean;
  request?: ProfileCorrectionRequest;
  error?: "missing_reason" | "no_change" | "unknown_field";
}

/**
 * Persist a correction request locally + return the created record.
 *
 * Light client-side validation; canonical validation happens on the
 * backend later.
 */
export async function submitCorrection(
  input: SubmitCorrectionInput,
): Promise<SubmitCorrectionResult> {
  // Simulate the network.
  await new Promise((r) => setTimeout(r, 500));

  const proposed = input.proposed_value.trim();
  const current = input.current_value.trim();

  if (proposed.length === 0 || proposed === current) {
    return { ok: false, error: "no_change" };
  }
  if (isProtectedField(input.field) && input.reason.trim().length < 4) {
    return { ok: false, error: "missing_reason" };
  }

  const request: ProfileCorrectionRequest = {
    id: newId(),
    workspace_id: input.workspace_id,
    field: input.field,
    current_value: current,
    proposed_value: proposed,
    reason: input.reason.trim(),
    message: input.message?.trim() || undefined,
    requires_admin_review:
      input.field === "other" ||
      input.field === "company_display_name" ||
      isProtectedField(input.field),
    created_at_iso: new Date().toISOString(),
  };

  const list = load();
  list.unshift(request);
  save(list);
  return { ok: true, request };
}

/** Update editable (non-protected) profile fields. Persists locally only. */
export async function saveEditableProfile(
  workspace_id: string,
  next: Partial<EditableProfileFields>,
): Promise<{ ok: boolean }> {
  await new Promise((r) => setTimeout(r, 300));
  if (typeof window === "undefined") return { ok: true };
  const key = `checkwise.mock.profile.${workspace_id}.v1`;
  const prev = (() => {
    try {
      const raw = window.localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as Partial<EditableProfileFields>) : {};
    } catch {
      return {};
    }
  })();
  window.localStorage.setItem(key, JSON.stringify({ ...prev, ...next }));
  return { ok: true };
}

export function readEditableProfile(
  workspace_id: string,
): Partial<EditableProfileFields> {
  if (typeof window === "undefined") return {};
  const key = `checkwise.mock.profile.${workspace_id}.v1`;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as Partial<EditableProfileFields>) : {};
  } catch {
    return {};
  }
}

export function listCorrections(): ProfileCorrectionRequest[] {
  return load();
}
