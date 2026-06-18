/**
 * Append the inspection-scope ``?client_id`` to an in-app href.
 *
 * The client portal scopes every page to a tenant via ``?client_id`` —
 * the ONLY mechanism for internal-admin users (whose default client is
 * null) and multi-client admins to view a specific tenant
 * (see ``useUrlClientId``). The shell's nav links, bell, logo, search and
 * back bar were static literals that DROPPED this param on the first
 * click, silently switching such users to the wrong tenant (audit P2.14).
 *
 * Wrap those hrefs with this helper so the scope survives navigation.
 * No-ops when ``clientId`` is absent, so single-client users (the common
 * case, where the param is never set) get clean URLs.
 */
export function withClientId(
  href: string,
  clientId: string | null | undefined,
): string {
  if (!clientId) return href;
  const [base, hash] = href.split("#");
  const sep = base.includes("?") ? "&" : "?";
  const suffix = hash ? `#${hash}` : "";
  return `${base}${sep}client_id=${encodeURIComponent(clientId)}${suffix}`;
}
