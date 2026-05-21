"use client";

import { ClientShell } from "../_shell";
import { ReportsListView } from "@/components/checkwise/reports/list/reports-list-view";

/**
 * Client reports list — R1.1 + R2.
 *
 * Client-executive entry point. Thin wrapper around the shared
 * <ReportsListView>. The audience filter is hidden because
 * client_admin's visible_audiences() set is a single value
 * (client_facing) — there is nothing for the user to pick.
 */
export default function ClientReportsPage() {
  return (
    <ClientShell unframed>
      <ReportsListView
        role="client"
        editorHrefBase="/client/reports"
        presetCreateRedirectBase="/client/reports"
        eyebrowDescription="Centro de inteligencia para tu portafolio: estado de cumplimiento, proveedores en riesgo y evidencia documental pendiente."
      />
    </ClientShell>
  );
}
