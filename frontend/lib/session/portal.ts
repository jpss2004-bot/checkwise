/**
 * Demo-only provider session helpers backed by localStorage.
 *
 * V1.2 does not implement real authentication. The portal issues an opaque
 * access_token at /api/v1/portal/access; we cache it here so subsequent calls
 * can present `X-Workspace-Token`. V1.3 must replace this with real auth.
 */

const STORAGE_KEY = "checkwise.portal.session.v1";

export type PersonaType = "moral" | "fisica";

export type PortalSession = {
  workspace_id: string;
  access_token: string;
  persona_type: PersonaType;
  client_name: string;
  vendor_name: string;
  vendor_rfc: string;
  filial_name: string | null;
  contract_reference: string | null;
  onboarding_completed_at: string | null;
};

export function readPortalSession(): PortalSession | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as PortalSession;
    if (!parsed.workspace_id || !parsed.access_token) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function writePortalSession(session: PortalSession): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearPortalSession(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(STORAGE_KEY);
}
