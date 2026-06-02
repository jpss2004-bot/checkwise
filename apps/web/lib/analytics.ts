/**
 * Lightweight analytics shim.
 *
 * CheckWise does not currently ship with an analytics SDK (no PostHog,
 * Plausible, Mixpanel, Amplitude, etc. wired into the web app). When a
 * provider is chosen, the body of ``track`` becomes a one-line call to
 * that provider's SDK and every call-site in the codebase starts
 * emitting real events without further changes.
 *
 * Until then, ``track`` is a no-op in production and console.debug-logs
 * in development. This lets us instrument the codebase now (so the
 * events the team cares about are baked into the components from the
 * start) without committing to a provider or paying for an SDK that
 * isn't pulling its weight yet.
 *
 * Naming convention: ``surface.thing.verb`` (lowercase, dot-separated,
 * past-tense or present-tense verb). Examples:
 *   - ``prevalidation.summary.shown``
 *   - ``prevalidation.tecnicos.expanded``
 *   - ``prevalidation.ai_hint.shown``
 *   - ``decision.action_clicked``
 *
 * Keep property payloads small and free of PII (no document content,
 * no full names, no RFCs in the payload — IDs are fine).
 */

export type AnalyticsProps = Record<string, string | number | boolean | null>;

/** Emit a single analytics event. No-op in production until an SDK is wired. */
export function track(event: string, props: AnalyticsProps = {}): void {
  if (typeof window === "undefined") {
    return;
  }
  if (process.env.NODE_ENV !== "production") {
    console.debug(`[analytics] ${event}`, props);
  }
  // When an SDK is added, wire it here. Examples (do not enable until chosen):
  //   posthog?.capture(event, props);
  //   plausible?.(event, { props });
}
