/**
 * Typed wrapper over the Patch 6 auth endpoints.
 *
 * The admin shell uses these helpers for the login form and to
 * re-hydrate the current user from a stored JWT (e.g. after a refresh).
 */

import type { AdminSession, AdminSessionUser } from "@/lib/session/admin";
import { adminAuthHeader } from "@/lib/session/admin";

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
  // FE-SEC-1 — always send the httpOnly session cookie. On /login this is
  // what makes the Set-Cookie stick; on cookie-authenticated calls (after
  // a reload, when the in-memory bearer is gone) it's what authenticates.
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

/**
 * Login result. ``access_token`` is a TRANSIENT field — the caller seeds
 * it into the in-memory store (``setAdminAccessToken``) and persists only
 * the identity slice (``AdminSession``). It is never written to
 * localStorage.
 */
export type LoginResult = AdminSession & {
  access_token: string;
  must_change_password: boolean;
};

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
  // CW-AUTH-002 — set-password bumps the server session epoch, invalidating
  // the token this request authenticated with. The backend re-mints the
  // current session's token (and refreshes the httpOnly cookie); the caller
  // MUST adopt this token or the next request 401s.
  access_token: string;
  expires_at: string;
};

export async function setPassword(
  newPassword: string,
): Promise<SetPasswordResponse> {
  // JWT-first (in-memory bearer), cookie-fallback. After a reload on
  // /activate the in-memory token is gone, so the httpOnly cookie
  // authenticates this POST instead (CSRF-guarded by Origin/Referer
  // server-side). The response re-mints the token at the new session
  // epoch — the caller adopts it via setAdminAccessToken.
  return await fetchJson<SetPasswordResponse>("/api/v1/auth/set-password", {
    method: "POST",
    headers: { ...adminAuthHeader() },
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
 * Authenticates with the in-memory admin/user JWT when we hold it
 * (JWT-first); after a reload it falls back to the httpOnly staff
 * cookie (``credentials: "include"``). Either way the response
 * Set-Cookie deposits the portal session cookie. After this call,
 * /portal/* endpoints work via cookie.
 */
export async function enterPortal(
  workspaceId?: string,
): Promise<EnterResponse> {
  return await fetchJson<EnterResponse>("/api/v1/portal/enter", {
    method: "POST",
    headers: { ...adminAuthHeader() },
    body: JSON.stringify(workspaceId ? { workspace_id: workspaceId } : {}),
  });
}

/**
 * Clear the server-side staff session cookie (FE-SEC-1). Best-effort and
 * idempotent — the backend returns 204 even for an anonymous/expired
 * token. Callers should also drop the local session
 * (``clearAdminSession``) and route to /login. Bounded so a stalled
 * request can't hang the logout UX.
 */
export async function logoutAdmin(): Promise<void> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5_000);
  try {
    await fetch(`${API_BASE_URL}/api/v1/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: { ...adminAuthHeader() },
      signal: controller.signal,
    });
  } catch {
    /* logout is best-effort — the local session is cleared regardless */
  } finally {
    clearTimeout(timeoutId);
  }
}
