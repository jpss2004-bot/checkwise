/**
 * Typed wrappers for the three /search endpoints (admin / client /
 * portal). Each role talks to its own backend route and the backend
 * enforces the data scope — the frontend just passes the query string.
 */

import { readAdminSession } from "@/lib/session/admin";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type SearchMatchType = "rfc" | "period" | "folio";

export type SearchHit = {
  submission_id: string;
  vendor_id: string;
  vendor_name: string;
  vendor_rfc: string | null;
  client_id: string;
  client_name: string;
  client_rfc: string | null;
  period_key: string | null;
  institution_code: string | null;
  institution_label: string | null;
  requirement_name: string | null;
  status: string;
  contract_folio: string | null;
  matched_by: SearchMatchType;
  created_at: string;
};

export type SearchResponse = {
  query: string;
  matched_by: SearchMatchType;
  total: number;
  items: SearchHit[];
};

export class SearchApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "SearchApiError";
  }
}

async function searchFetch(
  path: string,
  query: string,
  _token: string | null,
  init: RequestInit = {},
): Promise<SearchResponse> {
  const url = `${API_BASE_URL}${path}?q=${encodeURIComponent(query)}&limit=50`;
  // FE-SEC-1: auth via the httpOnly session cookie (credentials:include);
  // the token param is vestigial.
  const headers = new Headers(init.headers ?? {});
  const response = await fetch(url, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new SearchApiError(response.status, detail || response.statusText);
  }
  return (await response.json()) as SearchResponse;
}

/**
 * Admin-scope search. Sees every submission CheckWise stores.
 * Reads the staff JWT from localStorage (the same session the rest of
 * the admin surfaces use).
 */
export async function adminSearch(query: string): Promise<SearchResponse> {
  const session = readAdminSession();
  if (!session?.access_token) {
    throw new SearchApiError(401, "No active admin session.");
  }
  return searchFetch("/api/v1/admin/search", query, session.access_token);
}

/**
 * Client-scope search. Backend filters to the client_admin user's
 * reachable client_ids.
 */
export async function clientSearch(query: string): Promise<SearchResponse> {
  const session = readAdminSession();
  if (!session?.access_token) {
    throw new SearchApiError(401, "No active client session.");
  }
  return searchFetch("/api/v1/client/search", query, session.access_token);
}

/**
 * Portal-scope search. Backend filters to the active workspace's
 * vendor. Uses the portal session cookie (credentials: 'include') plus
 * the JWT in localStorage to satisfy the dual-auth path.
 */
export async function portalSearch(query: string): Promise<SearchResponse> {
  const session = readAdminSession();
  return searchFetch(
    "/api/v1/portal/search",
    query,
    session?.access_token ?? null,
  );
}
