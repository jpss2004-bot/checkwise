"use client";

import { useSearchParams } from "next/navigation";

import { ClientWiseDock } from "@/components/checkwise/wise/client-wise-dock";

/**
 * Conditional Wise mount for the admin surface.
 *
 * Internal-admin users don't have a default client (per the backend's
 * ``_resolve_client_id`` — returns 400 without ``?client_id=``), so
 * mounting the cliente Wise dock unconditionally in AdminShell would
 * mean ``/api/v1/client/wise/ask`` 400s every time the dock tried to
 * submit. We avoid that by rendering the dock only when an explicit
 * ``client_id`` is present in the URL — i.e. when the admin is
 * drilling into a specific client's data (vendor detail, report
 * editor, calendar, etc.).
 *
 * M1-follow-up (2026-06-02) — pragmatic version. A proper admin Wise
 * with cross-tenant context (aggregate questions across all 5 clients)
 * is a separate, larger task. For the user-testing round, scoping
 * Wise to a single client at a time is enough: admins drill into
 * Mayela's tenant to inspect Beta/Cobre and Wise answers about that
 * scope.
 */
export function AdminWiseMount() {
  const params = useSearchParams();
  const clientId = params?.get("client_id");
  if (!clientId) return null;
  return <ClientWiseDock />;
}
