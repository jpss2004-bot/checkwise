"use client";

import { AuditLogExplorer } from "@/components/checkwise/audit-log/audit-log-explorer";

import { AdminShell } from "../_shell";

/**
 * /admin/audit-log — the review team's path into the audit log.
 *
 * ``roles.py`` grants ``platform_admin`` a documented "READ the audit
 * log" permission and the backend ``GET /admin/audit-log`` authorizes
 * BOTH staff roles, but the only UI lived under ``/platform`` (gated to
 * ``operations_admin``), so the review team could never reach it (audit
 * F2). This mounts the same shared ``<AuditLogExplorer>`` inside the
 * Operaciones shell, whose gate admits all ``STAFF_ROLES``.
 */
export default function AdminAuditLogPage() {
  return (
    <AdminShell
      title="Audit log"
      description="Bitácora completa de eventos del sistema. Cada cambio firma el actor, la acción, la entidad y el diff antes/después."
    >
      <AuditLogExplorer />
    </AdminShell>
  );
}
