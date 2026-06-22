/**
 * Shared fetch wrapper that bounds a request with an ``AbortController``
 * deadline. Without one, a stalled R2/backend stream leaves the promise
 * unsettled forever and the calling UI spins indefinitely (resilience
 * audit 2026-06-21, Batch 5).
 *
 * Design notes:
 *   - This is a thin, auth-agnostic primitive. It does NOT add headers,
 *     bearer tokens or credentials — each role client (client.ts,
 *     portal.ts, reports.ts, search.ts) keeps owning its own auth and
 *     just delegates the raw fetch here so the timeout logic lives in one
 *     place.
 *   - If the caller already passed a ``signal`` we respect it and DO NOT
 *     add our own controller (the caller owns cancellation). Otherwise we
 *     install a timeout controller that aborts after ``timeoutMs``.
 *   - On a timeout-triggered abort we throw a ``FetchTimeoutError`` so the
 *     caller can map it onto its own typed error ("tardó demasiado").
 *     A caller-driven abort (their own signal) rethrows verbatim.
 *   - The timeout is always cleared in ``finally`` so a fast happy-path
 *     response leaves no dangling timer. Behaviour on the happy path is
 *     identical to a bare ``fetch``.
 */

/** Raised when ``fetchWithTimeout`` aborts a request because the deadline
 *  elapsed (as opposed to a caller-provided signal firing). Callers catch
 *  this to render a friendly "tardó demasiado" state. */
export class FetchTimeoutError extends Error {
  readonly timeoutMs: number;
  constructor(timeoutMs: number) {
    super(`Request exceeded the ${timeoutMs}ms timeout`);
    this.name = "FetchTimeoutError";
    this.timeoutMs = timeoutMs;
  }
}

/**
 * ``fetch`` with an abort-on-timeout ceiling.
 *
 * When the caller did not supply ``init.signal`` we attach a private
 * ``AbortController`` that aborts after ``timeoutMs``; the resulting
 * ``AbortError`` is rethrown as a {@link FetchTimeoutError}. When the
 * caller DID supply a signal, we leave cancellation entirely to them and
 * only forward their signal (no timeout is layered on, since combining the
 * two would silently override the caller's intent).
 */
export async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMs?: number,
): Promise<Response> {
  // Caller owns cancellation, or no timeout requested → passthrough.
  if (init.signal || !timeoutMs) {
    return fetch(input, init);
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (err) {
    if (controller.signal.aborted) {
      throw new FetchTimeoutError(timeoutMs);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}
