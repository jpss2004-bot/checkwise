/**
 * MOCK activation client.
 *
 * The provider portal currently uses opaque workspace tokens (V1.2
 * demo auth). Real email/password account activation is a backend
 * roadmap item (V1.5+). This module simulates the temp-credential
 * → password-setup → identity-completion handshake against canned
 * data so the frontend flow can be built ahead of the API.
 *
 * TODO[backend-integration]: Replace every function in this file
 * with calls to the real /api/v1/activation/* endpoints once the
 * backend ships them.
 */

/** Demo temp credentials. Any email + this code unlocks the flow. */
export const MOCK_TEMP_CODE = "CW-DEMO-2026";

export interface TempCredentials {
  email: string;
  temp_code: string;
}

export interface ActivationSession {
  /** Server-issued token after temp-creds validate. */
  activation_token: string;
  email: string;
  /** Optional company name pre-filled by the inviter on the backend. */
  company_hint: string | null;
}

export type ActivationError =
  | "invalid_credentials"
  | "expired_invitation"
  | "missing_invitation"
  | "network";

export interface ActivationErrorResult {
  ok: false;
  error: ActivationError;
}

export interface ActivationOkResult<T> {
  ok: true;
  data: T;
}

export type ActivationResult<T> = ActivationOkResult<T> | ActivationErrorResult;

async function fakeDelay(ms = 700): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Step 1 — validate temp credentials.
 *
 * Demo behaviour:
 *   - empty email or code → "missing_invitation"
 *   - code !== MOCK_TEMP_CODE → "invalid_credentials"
 *   - email contains "expired" → "expired_invitation"
 *   - otherwise → ok with mock activation token
 *
 * TODO[backend-integration]: POST /api/v1/activation/verify { email, temp_code }
 */
export async function verifyTempCredentials(
  creds: TempCredentials,
): Promise<ActivationResult<ActivationSession>> {
  await fakeDelay();

  const email = creds.email.trim().toLowerCase();
  const code = creds.temp_code.trim().toUpperCase();

  if (!email || !code) return { ok: false, error: "missing_invitation" };
  if (code !== MOCK_TEMP_CODE) return { ok: false, error: "invalid_credentials" };
  if (email.includes("expired")) return { ok: false, error: "expired_invitation" };

  return {
    ok: true,
    data: {
      activation_token: `mock-act-${Math.random().toString(36).slice(2, 10)}`,
      email,
      company_hint: null,
    },
  };
}

/**
 * Step 2 — set the new password.
 *
 * TODO[backend-integration]: POST /api/v1/activation/password
 *   { activation_token, password }
 */
export async function setPassword(
  activation_token: string,
  password: string,
): Promise<ActivationResult<{ password_set_at: string }>> {
  await fakeDelay();
  if (!activation_token || password.length < 10) {
    return { ok: false, error: "invalid_credentials" };
  }
  return { ok: true, data: { password_set_at: new Date().toISOString() } };
}

export interface IdentityPayload {
  first_name: string;
  last_name: string;
  email: string;
  company: string;
}

/**
 * Step 3 — submit identity. Returns the workspace handle that the
 * provider portal session will use.
 *
 * TODO[backend-integration]: POST /api/v1/activation/identity
 *   { activation_token, first_name, last_name, company }
 *   → { workspace_id, access_token, persona_type, ... }
 */
export async function submitIdentity(
  activation_token: string,
  payload: IdentityPayload,
): Promise<ActivationResult<{ workspace_id: string; access_token: string }>> {
  await fakeDelay();
  if (!activation_token || !payload.first_name || !payload.last_name || !payload.company) {
    return { ok: false, error: "invalid_credentials" };
  }
  return {
    ok: true,
    data: {
      workspace_id: `ws-mock-${Math.random().toString(36).slice(2, 8)}`,
      access_token: `tok-mock-${Math.random().toString(36).slice(2, 16)}`,
    },
  };
}
