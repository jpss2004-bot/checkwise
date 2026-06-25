"use client";

import { AuditLogExplorer } from "@/components/checkwise/audit-log/audit-log-explorer";

import { PlatformShell } from "../_shell";

/**
 * /platform/audit-log — the superadmin's entry into the cross-tenant
 * audit log. The browser itself lives in the shared
 * ``<AuditLogExplorer>`` so the review team can reach the same view from
 * the Operaciones console (``/admin/audit-log``) without duplicating the
 * ~770-line table (audit F2). ``PlatformShell`` supplies the
 * superadmin-only gate.
 */
export default function PlatformAuditLogPage() {
  return (
    <PlatformShell
      title="Audit log"
      description="Bitácora completa de eventos del sistema. Cada cambio firma el actor, la acción, la entidad y el diff antes/después."
    >
      <AuditLogExplorer />
    </PlatformShell>
  );
}
