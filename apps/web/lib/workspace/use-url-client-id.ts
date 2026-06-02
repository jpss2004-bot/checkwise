"use client";

import { useSearchParams } from "next/navigation";

/**
 * Read ``?client_id=<uuid>`` from the current URL. Returns ``null``
 * when the param is absent or empty.
 *
 * Internal-admin users have no default client (their ``/client/me``
 * carries ``default_client_id = null``), so the only way to scope the
 * client portal pages to a specific tenant during inspection is via
 * this URL param. Regular ``client_admin`` users may also pass it to
 * switch between their visible clients — the backend's
 * ``_resolve_client_id`` enforces that they can only target clients
 * reachable through their memberships, so the override is never a
 * tenant-bleed vector.
 */
export function useUrlClientId(): string | null {
  const params = useSearchParams();
  const v = params?.get("client_id");
  return v && v.length > 0 ? v : null;
}
