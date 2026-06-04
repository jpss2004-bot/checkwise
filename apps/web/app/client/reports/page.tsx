"use client";

import { ClientShell } from "../_shell";
import { ReportsListView } from "@/components/checkwise/reports/list/reports-list-view";

/**
 * The four client-facing presets, in display order: executive summary,
 * provider risk matrix, missing-evidence across all providers, and the
 * per-provider deep dive. Pinned here so the client gallery shows exactly
 * these — provider-facing presets that leak in for client_admins who also
 * own a workspace (and 403 on generate) are hidden.
 */
const CLIENT_PRESET_IDS = [
  "client-monthly-executive",
  "client-vendor-risk-matrix",
  "client-missing-evidence",
  "client-vendor-detail",
] as const;

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
        allowedPresetIds={CLIENT_PRESET_IDS}
      />
    </ClientShell>
  );
}
