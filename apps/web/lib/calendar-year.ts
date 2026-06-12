/**
 * Year parsing + bounds for the client calendar (`/client/calendar`).
 *
 * Extracted from the page component so the parsing rules are unit
 * testable. REPSE compliance starts in 2021 — the floor matches the
 * backend MIN_YEAR=2021 (apps/api/app/core/period_validation.py). The
 * 2030 ceiling is a UI-side guard against accidental far-future input;
 * the API itself accepts up to MAX_YEAR=2099.
 */

export const CALENDAR_MIN_YEAR = 2021;
export const CALENDAR_MAX_YEAR = 2030;

/**
 * Resolve the calendar year from the `?year=` search param.
 *
 * Missing, empty, or non-numeric input falls back to the current year.
 * Out-of-range numeric input is clamped to [CALENDAR_MIN_YEAR,
 * CALENDAR_MAX_YEAR].
 *
 * Prod bug (2026-06-12): `Number(null)` and `Number("")` evaluate to
 * `0` — not `NaN` — so a missing param sailed past the
 * `Number.isFinite` fallback and the clamp turned it into
 * CALENDAR_MIN_YEAR. Every bare visit to /client/calendar landed on an
 * empty 2021 instead of the current year. The explicit null/empty
 * guard below is load-bearing.
 */
export function parseCalendarYear(raw: string | null): number {
  const fallback = new Date().getFullYear() || 2026;
  if (raw === null || raw.trim() === "") return fallback;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(CALENDAR_MAX_YEAR, Math.max(CALENDAR_MIN_YEAR, Math.trunc(parsed)));
}
