/**
 * MOCK invitation tokens.
 *
 * Backs the `/activate?token=…` entry point until the real backend
 * issues signed activation tokens. The token format here is
 * intentionally opaque: callers should never parse it.
 *
 * In production the same module surface (issueInvitation / verifyToken)
 * will exist server-side; the frontend will simply call backend
 * endpoints.
 *
 * TODO[backend-integration]:
 *   - Move issueInvitation server-side; persist `Invitation` rows.
 *   - Move verifyToken server-side; check expiry + single-use.
 *   - Emit the welcome email via `lib/email/welcome.ts` from the
 *     server when issueInvitation succeeds.
 */

import type { InvitationRole } from "@/lib/email/welcome";

export interface InvitationPayload {
  email: string;
  role: InvitationRole;
  company_hint?: string | null;
  inviter: string;
  /** Expiry hint in days. Default 7. */
  expires_in_days?: number;
}

export interface Invitation {
  token: string;
  email: string;
  role: InvitationRole;
  company_hint: string | null;
  inviter: string;
  expires_at_iso: string;
  expires_at_human: string;
}

const STORAGE_KEY = "checkwise.mock.invitations.v1";

/**
 * Hardcoded demo invitation. Any `/activate?token=demo` URL resolves
 * to this. Useful for screenshots / smoke tests / sales demos.
 */
const DEMO_INVITATION: Invitation = {
  token: "demo",
  email: "juan.perez@constructoraabc.com",
  role: "provider",
  company_hint: "Constructora ABC",
  inviter: "Equipo Legal Shelf",
  expires_at_iso: "2099-12-31T00:00:00.000Z",
  expires_at_human: "vigente para esta demo",
};

function loadStore(): Record<string, Invitation> {
  if (typeof window === "undefined") return { demo: DEMO_INVITATION };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { demo: DEMO_INVITATION };
    const parsed = JSON.parse(raw) as Record<string, Invitation>;
    return { demo: DEMO_INVITATION, ...parsed };
  } catch {
    return { demo: DEMO_INVITATION };
  }
}

function saveStore(store: Record<string, Invitation>) {
  if (typeof window === "undefined") return;
  // Always persist without the demo (it's recreated on every load).
  const { demo: _demo, ...rest } = store;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(rest));
}

function newToken(): string {
  return `inv-${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36).slice(-4)}`;
}

function humanExpiry(iso: string): string {
  try {
    return new Date(iso).toLocaleString("es-MX", {
      day: "2-digit",
      month: "long",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

/**
 * Issue an invitation (mock). Returns the persisted Invitation,
 * which the caller can feed to `renderWelcomeEmailHtml` for preview
 * or transport.
 */
export function issueInvitation(payload: InvitationPayload): Invitation {
  const expires_in_days = payload.expires_in_days ?? 7;
  const expires_at = new Date(Date.now() + expires_in_days * 24 * 60 * 60 * 1000);
  const invitation: Invitation = {
    token: newToken(),
    email: payload.email.trim().toLowerCase(),
    role: payload.role,
    company_hint: payload.company_hint?.trim() || null,
    inviter: payload.inviter,
    expires_at_iso: expires_at.toISOString(),
    expires_at_human: humanExpiry(expires_at.toISOString()),
  };
  const store = loadStore();
  store[invitation.token] = invitation;
  saveStore(store);
  return invitation;
}

export type InvitationVerifyError = "unknown" | "expired";

export interface InvitationVerifyResult {
  ok: boolean;
  invitation?: Invitation;
  error?: InvitationVerifyError;
}

/**
 * Verify an activation token. Read-only — caller decides whether to
 * consume / mark used.
 */
export function verifyToken(token: string): InvitationVerifyResult {
  if (!token) return { ok: false, error: "unknown" };
  const store = loadStore();
  const inv = store[token];
  if (!inv) return { ok: false, error: "unknown" };
  if (token !== "demo" && Date.parse(inv.expires_at_iso) < Date.now()) {
    return { ok: false, error: "expired" };
  }
  return { ok: true, invitation: inv };
}

/**
 * Consume an invitation. After this it cannot be reused.
 * The "demo" token is permanent and never consumed.
 */
export function consumeInvitation(token: string): void {
  if (token === "demo") return;
  const store = loadStore();
  delete store[token];
  saveStore(store);
}
