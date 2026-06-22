/**
 * Cached `Intl.DateTimeFormat` helpers.
 *
 * `Date.prototype.toLocaleString` / `toLocaleDateString` construct a fresh
 * `Intl.DateTimeFormat` on every call — one of the more expensive JS
 * operations when done once per table row. These helpers cache one formatter
 * per (locale, options) signature so long lists (submissions up to 500 rows,
 * the audit log, metadata) format dates without rebuilding the formatter each
 * row.
 *
 * For a given options object the output is byte-identical to
 * `new Date(value).toLocaleString("es-MX", options)` — `toLocaleString` /
 * `toLocaleDateString` are defined in terms of `Intl.DateTimeFormat` with the
 * same options; they only differ in their *default* options, which is why
 * these helpers require options to be passed explicitly.
 */

const LOCALE = "es-MX";
/**
 * CheckWise is a Mexico-only product, so every user-facing timestamp is read in
 * America/Mexico_City (UTC-6/-5). Anchoring the formatter to that zone keeps the
 * rendered wall-clock time correct regardless of where the code runs (the
 * browser's local zone, or a server during SSR which is UTC on Render).
 */
const MX_TZ = "America/Mexico_City";
const formatterCache = new Map<string, Intl.DateTimeFormat>();

/** Bare calendar dates with no time/offset, e.g. "2026-06-17". */
const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/;

function getFormatter(options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = JSON.stringify(options);
  let formatter = formatterCache.get(key);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(LOCALE, options);
    formatterCache.set(key, formatter);
  }
  return formatter;
}

/**
 * Format a date / ISO string / epoch with a cached es-MX formatter. Returns
 * `fallback` (default `""`) when the value is not a valid date.
 *
 * Timezone handling (Mexico-only product):
 *  - A bare `YYYY-MM-DD` value is a *calendar date* with no instant. `new Date()`
 *    parses it as UTC midnight, which renders as the previous day in MX (UTC-6).
 *    We instead build the Date at UTC midnight and format with `timeZone: "UTC"`
 *    so the literal Y/M/D the caller passed is preserved (no day shift).
 *  - Any value with a real instant (full timestamp / epoch / Date) is rendered
 *    in `America/Mexico_City` unless the caller pins an explicit `timeZone`.
 */
export function formatDateTime(
  value: string | number | Date,
  options: Intl.DateTimeFormatOptions,
  fallback = "",
): string {
  // Date-only string: preserve the literal calendar day, no instant / no shift.
  if (typeof value === "string" && DATE_ONLY_RE.test(value)) {
    const date = new Date(`${value}T00:00:00Z`);
    if (Number.isNaN(date.getTime())) return fallback;
    return getFormatter({ timeZone: "UTC", ...options }).format(date);
  }

  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return getFormatter({ timeZone: MX_TZ, ...options }).format(date);
}
