/**
 * Typed wrappers for the three /search endpoints (admin / client /
 * portal). Each role talks to its own backend route and the backend
 * enforces the data scope — the frontend just passes the query string.
 */

import { getAdminAccessToken } from "@/lib/session/admin";
import { fetchWithTimeout, FetchTimeoutError } from "@/lib/api/fetch-timeout";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

// The omnibox fires on user input and the backend query joins submissions
// across the whole tenant scope. Without a ceiling a server-side hang leaves
// the result promise unsettled and the search UI spinning with no error
// (resilience audit 2026-06-21). 15s sits in the audited 15-25s band.
const SEARCH_TIMEOUT_MS = 15_000;

export type SearchMatchType = "rfc" | "period" | "folio" | "name";

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
  token: string | null,
  init: RequestInit = {},
): Promise<SearchResponse> {
  const url = `${API_BASE_URL}${path}?q=${encodeURIComponent(query)}&limit=50`;
  const headers = new Headers(init.headers ?? {});
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  let response: Response;
  try {
    response = await fetchWithTimeout(
      url,
      { ...init, headers, credentials: "include" },
      SEARCH_TIMEOUT_MS,
    );
  } catch (err) {
    if (err instanceof FetchTimeoutError) {
      throw new SearchApiError(
        0,
        "La búsqueda tardó demasiado. Inténtalo de nuevo.",
      );
    }
    throw err;
  }
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new SearchApiError(response.status, detail || response.statusText);
  }
  return (await response.json()) as SearchResponse;
}

/**
 * Admin-scope search. Sees every submission CheckWise stores.
 * JWT-first (in-memory bearer), cookie-fallback — same dual-auth path
 * as the rest of the admin surfaces.
 */
export async function adminSearch(query: string): Promise<SearchResponse> {
  return searchFetch("/api/v1/admin/search", query, getAdminAccessToken());
}

/**
 * Client-scope search. Backend filters to the client_admin user's
 * reachable client_ids.
 */
export async function clientSearch(query: string): Promise<SearchResponse> {
  return searchFetch("/api/v1/client/search", query, getAdminAccessToken());
}

/**
 * Portal-scope search. Backend filters to the active workspace's
 * vendor. Uses the portal session cookie (credentials: 'include') plus
 * the in-memory JWT to satisfy the dual-auth path.
 */
export async function portalSearch(query: string): Promise<SearchResponse> {
  return searchFetch("/api/v1/portal/search", query, getAdminAccessToken());
}
