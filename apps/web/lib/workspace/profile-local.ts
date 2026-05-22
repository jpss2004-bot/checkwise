/**
 * Local-only persistence for editable provider profile fields.
 *
 * The "Confirma tus datos de contacto" form on /portal/entra-a-tu-espacio
 * lets a provider enter first/last name, phone, job title and contact
 * preference. None of those fields have a backend home yet, so this
 * module persists them in localStorage keyed by workspace_id. The
 * trade-offs:
 *
 *   - Cleared browser data wipes the form.
 *   - Shared devices can leak between workspaces with the same id
 *     (theoretical — workspace_id is a UUID, but worth flagging).
 *   - Channel preference is read but not honoured (no notification
 *     pipeline reads it back yet).
 *
 * Real persistence is tracked as a follow-up: add
 * first_name / last_name / phone / job_title / contact_preference
 * columns to ProviderWorkspace (or a sibling user_profile table) and
 * expose them via PATCH /portal/me, then rip this module out.
 *
 * This file replaces the previous ``lib/mock/corrections.ts``. The
 * non-profile helpers in that file (submitCorrection, listCorrections,
 * isProtectedField) were dead code — the real correction-request path
 * lives in ``lib/api/corrections.ts`` and is consumed by the
 * <CorrectionRequestForm> component verbatim.
 */

import type { EditableProfileFields } from "@/lib/workspace/types";

function storageKey(workspace_id: string): string {
  return `checkwise.workspace.profile.${workspace_id}.v1`;
}

export async function saveEditableProfile(
  workspace_id: string,
  next: Partial<EditableProfileFields>,
): Promise<{ ok: boolean }> {
  // Keep the brief await so the consuming form's loading state has
  // time to render — the real backend round-trip will reintroduce
  // a similar latency.
  await new Promise((r) => setTimeout(r, 300));
  if (typeof window === "undefined") return { ok: true };
  const prev = readEditableProfile(workspace_id);
  window.localStorage.setItem(
    storageKey(workspace_id),
    JSON.stringify({ ...prev, ...next }),
  );
  return { ok: true };
}

export function readEditableProfile(
  workspace_id: string,
): Partial<EditableProfileFields> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(storageKey(workspace_id));
    return raw ? (JSON.parse(raw) as Partial<EditableProfileFields>) : {};
  } catch {
    return {};
  }
}
