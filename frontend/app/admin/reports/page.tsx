"use client";

import { AdminShell } from "../_shell";
import { ReportsListView } from "@/components/checkwise/reports/list/reports-list-view";

/**
 * Admin reports list — R1.0 + R2.
 *
 * Internal team entry point. Thin wrapper around the shared
 * <ReportsListView>. The shell is set ``unframed`` so the list view
 * renders its own full-width title and metadata strip without a
 * duplicate header.
 */
export default function AdminReportsPage() {
  return (
    <AdminShell unframed>
      <ReportsListView
        role="admin"
        editorHrefBase="/admin/reports"
        presetCreateRedirectBase="/admin/reports"
        eyebrowDescription="Centro de inteligencia operativa. Genera reportes internos sobre la bandeja de revisión, proveedores en riesgo y cumplimiento mensual."
        showAudienceFilter
      />
    </AdminShell>
  );
}
