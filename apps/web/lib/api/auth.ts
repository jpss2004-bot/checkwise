/**
 * Typed wrapper over the Patch 6 auth endpoints.
 *
 * The admin shell uses these helpers for the login form and to
 * re-hydrate the current user from a stored JWT (e.g. after a refresh).
 */

import type { AdminSession, AdminSessionUser } from "@/lib/session/admin";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export class AuthApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "AuthApiError";
  }
}

async function fetchJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  // FE-SEC-1: every auth call sends the httpOnly session cookie. login's
  // Set-Cookie is only stored by the browser when the request opts into
  // credentials:"include"; /me, /set-password, /enter then authenticate
  // via that cookie instead of a localStorage bearer token.
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new AuthApiError(response.status, detail || response.statusText);
  }
  return (await response.json()) as T;
}

type LoginResponse = {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: AdminSessionUser & { must_change_password?: boolean };
  roles: string[];
  organization_ids: string[];
  must_change_password?: boolean;
};

export type LoginResult = AdminSession & { must_change_password: boolean };

export async function login(
  email: string,
  password: string,
): Promise<LoginResult> {
  const payload = await fetchJson<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  return {
    // FE-SEC-1: the real JWT is NOT persisted client-side anymore — it
    // lives only in the httpOnly cookie the backend just set. We carry a
    // placeholder so existing TypeScript consumers keep compiling (mirrors
    // the provider portal's "cookie-managed" sentinel).
    access_token: "cookie-managed",
    expires_at: payload.expires_at,
    user: payload.user,
    roles: payload.roles,
    organization_ids: payload.organization_ids,
    must_change_password:
      payload.must_change_password ??
      payload.user.must_change_password ??
      false,
  };
}

type MeResponse = {
  user: AdminSessionUser & { must_change_password?: boolean };
  roles: string[];
  organization_ids: string[];
  token_expires_at: string;
};

export async function getCurrentAdmin(): Promise<MeResponse> {
  // FE-SEC-1: re-hydrate via the httpOnly session cookie (credentials:
  // include in fetchJson). The token param is vestigial — kept so callers
  // that still pass the placeholder keep compiling.
  return await fetchJson<MeResponse>("/api/v1/auth/me", { method: "GET" });
}

type SetPasswordResponse = {
  user: AdminSessionUser & { must_change_password: boolean };
  must_change_password: boolean;
};

export async function setPassword(
  newPassword: string,
): Promise<SetPasswordResponse> {
  // FE-SEC-1: authenticate via the session cookie set at login (the
  // /activate flow logs in first). Token param vestigial.
  return await fetchJson<SetPasswordResponse>("/api/v1/auth/set-password", {
    method: "POST",
    body: JSON.stringify({ new_password: newPassword }),
  });
}

type AuthMessageResponse = {
  message: string;
};

export async function requestPasswordReset(
  email: string,
): Promise<AuthMessageResponse> {
  return await fetchJson<AuthMessageResponse>("/api/v1/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<AuthMessageResponse> {
  return await fetchJson<AuthMessageResponse>("/api/v1/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

export type ResetPasswordPreview = {
  email: string;
};

/**
 * Audit-finding #5 — resolve a reset token to the recipient email
 * so /reset-password can show "Cambiando contraseña para X" before
 * the user invests effort typing a new password. Errors with the
 * same 400 shape as the POST handler when the token is bad/used/
 * expired; callers should treat any failure as "ask for a new link".
 */
export async function previewResetPassword(
  token: string,
): Promise<ResetPasswordPreview> {
  const qs = new URLSearchParams({ token });
  return await fetchJson<ResetPasswordPreview>(
    `/api/v1/auth/reset-password/preview?${qs.toString()}`,
  );
}

type EnterResponse = {
  workspace_id: string;
  persona_type: string;
  client_name: string;
  vendor_name: string;
  vendor_rfc: string;
  filial_name: string | null;
  contract_reference: string | null;
  onboarding_completed_at: string | null;
};

/**
 * Mint the portal session cookie for an authenticated user.
 *
 * Requires the admin/user JWT issued by /auth/login. Sends
 * credentials:include so the response Set-Cookie is honored by the
 * browser. After this call, /portal/* endpoints work via cookie.
 */
export async function enterPortal(
  _token?: string,
  workspaceId?: string,
): Promise<EnterResponse> {
  // FE-SEC-1: mint the portal cookie off the admin session cookie
  // (credentials:include in fetchJson). The backend /portal/enter
  // resolves the user via that cookie and verifies workspace ownership.
  // Token param vestigial.
  return await fetchJson<EnterResponse>("/api/v1/portal/enter", {
    method: "POST",
    body: JSON.stringify(workspaceId ? { workspace_id: workspaceId } : {}),
  });
}
