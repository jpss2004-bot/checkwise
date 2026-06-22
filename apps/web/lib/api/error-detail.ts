import { ClientApiError } from "@/lib/api/client";

/**
 * Human-readable detail from a thrown client-API error.
 *
 * ``ClientApiError.message`` carries the raw response body, which the FastAPI
 * backend formats as ``{"detail": "..."}``. Unwrap that so the UI shows the
 * Spanish message instead of a raw JSON string; fall back gracefully for
 * non-API errors.
 */
export function apiErrorDetail(
  err: unknown,
  fallback = "Ocurrió un error.",
): string {
  if (err instanceof ClientApiError) {
    try {
      const parsed = JSON.parse(err.message) as { detail?: unknown };
      if (typeof parsed.detail === "string") return parsed.detail;
    } catch {
      /* body wasn't JSON — use the raw message */
    }
    return err.message || fallback;
  }
  return err instanceof Error && err.message ? err.message : fallback;
}
