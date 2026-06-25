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

/** Structured error codes the Phase A/B backend returns in ``detail.code``. */
export type ClientErrorCode =
  | "provider_limit_reached"
  | "provider_archived"
  | "trial_expired"
  | "plan_capability_required";

export type ParsedClientError = {
  /** ``detail.code`` when the backend sent a structured error; else undefined. */
  code?: ClientErrorCode | string;
  /** Human Spanish message (the structured ``message`` or the ``apiErrorDetail`` fallback). */
  detail: string;
  limit?: number;
  used?: number;
  vendor_id?: string;
  capability?: string;
};

/**
 * Parse a thrown client-API error into its structured shape. The Phase A/B
 * 409/403s carry ``{"detail": {"code": ..., ...}}`` (object-shaped detail),
 * unlike the plain ``{"detail": "..."}`` ``apiErrorDetail`` handles. When the
 * detail isn't an object, ``code`` is undefined and ``detail`` falls back to
 * ``apiErrorDetail`` — so callers can branch on ``code`` and always have a
 * displayable message. Never throws.
 */
export function parseClientErrorCode(err: unknown): ParsedClientError {
  const fallback = apiErrorDetail(err);
  if (err instanceof ClientApiError) {
    try {
      const parsed = JSON.parse(err.message) as { detail?: unknown };
      const d = parsed.detail;
      if (d && typeof d === "object") {
        const o = d as Record<string, unknown>;
        return {
          code: typeof o.code === "string" ? o.code : undefined,
          detail: typeof o.message === "string" ? o.message : fallback,
          limit: typeof o.limit === "number" ? o.limit : undefined,
          used: typeof o.used === "number" ? o.used : undefined,
          vendor_id: typeof o.vendor_id === "string" ? o.vendor_id : undefined,
          capability:
            typeof o.capability === "string" ? o.capability : undefined,
        };
      }
    } catch {
      /* body wasn't JSON — fall through to the plain detail */
    }
  }
  return { detail: fallback };
}
