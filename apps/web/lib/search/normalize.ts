/**
 * Client-side search normalization.
 *
 * CheckWise is a Mexican product: vendor/client names, RFCs-with-Ñ, and
 * document text are full of Spanish diacritics (á é í ó ú ñ ü). A naive
 * `.toLowerCase().includes()` is accent-SENSITIVE, so a search for "Gonzalez"
 * misses "González", "Anahuac" misses "Anáhuac", "Pena" misses "Peña". This
 * folds case AND strips combining diacritics so search is accent-insensitive,
 * matching how a human expects search to behave.
 *
 * Mirrors the backend's accent-insensitive SQL search (Postgres `unaccent`),
 * so client-side and server-side searches behave the same way.
 */
export function normalizeForSearch(value: string): string {
  return value
    .normalize("NFD") // split base char + combining diacritic
    .replace(/\p{Diacritic}/gu, "") // drop the combining diacritics
    .toLowerCase()
    .trim();
}

/**
 * True if `needle` is found in ANY of `fields` (accent- and case-insensitive).
 *
 * Match each field independently — never join fields into one string, which
 * produces false positives across field boundaries (e.g. joining
 * "proveedor periodo" lets a query span two unrelated columns).
 */
export function matchesAnyField(
  fields: ReadonlyArray<string | null | undefined>,
  needle: string,
): boolean {
  const n = normalizeForSearch(needle);
  if (!n) return true;
  return fields.some(
    (field) => field != null && normalizeForSearch(String(field)).includes(n),
  );
}
