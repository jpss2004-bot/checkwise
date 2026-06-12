/**
 * Tiny helpers for preserving list context when a user drills into a
 * detail page and then returns.
 *
 * `returnTo` is intentionally path-only. We never accept absolute URLs
 * or protocol-relative values, so these helpers cannot become an open
 * redirect primitive.
 */

export function pathWithParams(
  pathname: string,
  params: URLSearchParams | null | undefined,
  omit: ReadonlyArray<string> = ["returnTo"],
): string {
  const next = new URLSearchParams();
  params?.forEach((value, key) => {
    if (!omit.includes(key)) next.append(key, value);
  });
  const qs = next.toString();
  return qs ? `${pathname}?${qs}` : pathname;
}

export function withReturnTo(href: string, returnTo?: string | null): string {
  if (!returnTo) return href;
  const [path, query = ""] = href.split("?");
  const params = new URLSearchParams(query);
  params.set("returnTo", returnTo);
  return `${path}?${params.toString()}`;
}

export function safeReturnTo(
  raw: string | null | undefined,
  allowedPrefixes: ReadonlyArray<string>,
  fallback: string,
): string {
  if (!raw) return fallback;
  if (!raw.startsWith("/") || raw.startsWith("//")) return fallback;
  if (raw.includes("\n") || raw.includes("\r")) return fallback;

  let parsed: URL;
  try {
    parsed = new URL(raw, "https://checkwise.local");
  } catch {
    return fallback;
  }
  if (parsed.origin !== "https://checkwise.local") return fallback;

  const path = `${parsed.pathname}${parsed.search}${parsed.hash}`;
  const allowed = allowedPrefixes.some(
    (prefix) =>
      path === prefix ||
      path.startsWith(`${prefix}?`) ||
      path.startsWith(`${prefix}/`),
  );
  return allowed ? path : fallback;
}
