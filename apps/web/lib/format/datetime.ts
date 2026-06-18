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
const formatterCache = new Map<string, Intl.DateTimeFormat>();

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
 */
export function formatDateTime(
  value: string | number | Date,
  options: Intl.DateTimeFormatOptions,
  fallback = "",
): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return getFormatter(options).format(date);
}
