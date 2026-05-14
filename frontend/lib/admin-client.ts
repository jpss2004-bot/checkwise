/**
 * Typed wrapper over the Patch 6 auth endpoints.
 *
 * The admin shell uses these helpers for the login form and to
 * re-hydrate the current user from a stored JWT (e.g. after a refresh).
 */

import type { AdminSession, AdminSessionUser } from "@/lib/admin-session";

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
  user: AdminSessionUser;
  roles: string[];
  organization_ids: string[];
};

export async function login(
  email: string,
  password: string,
): Promise<AdminSession> {
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
  };
}

type MeResponse = {
  user: AdminSessionUser;
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
