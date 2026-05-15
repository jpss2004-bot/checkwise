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
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
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
    access_token: payload.access_token,
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

export async function getCurrentAdmin(token: string): Promise<MeResponse> {
  return await fetchJson<MeResponse>("/api/v1/auth/me", {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
  });
}

type SetPasswordResponse = {
  user: AdminSessionUser & { must_change_password: boolean };
  must_change_password: boolean;
};

export async function setPassword(
  token: string,
  newPassword: string,
): Promise<SetPasswordResponse> {
  return await fetchJson<SetPasswordResponse>("/api/v1/auth/set-password", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ new_password: newPassword }),
  });
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
  token: string,
  workspaceId?: string,
): Promise<EnterResponse> {
  return await fetchJson<EnterResponse>("/api/v1/portal/enter", {
    method: "POST",
    credentials: "include",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(workspaceId ? { workspace_id: workspaceId } : {}),
  });
}
