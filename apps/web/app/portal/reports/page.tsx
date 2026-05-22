"use client";

import { CompliancePulseStrip } from "@/components/checkwise/reports/list/compliance-pulse-strip";
import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { ReportsListView } from "@/components/checkwise/reports/list/reports-list-view";
import { withOnboardingGate } from "@/lib/session/with-onboarding-gate";
import type { PortalSession } from "@/lib/session/portal";

/**
 * Provider portal reports list — P1.
 *
 * Migrated from the V2.1 inline-create implementation to the shared
 * <ReportsListView>. The provider role gets:
 *   - the three vendor_facing preset cards (server-filtered by the
 *     workspace-owner branch in presets_for_roles)
 *   - the R2 filter bar (search + Estado; Audiencia hidden because
 *     visible_audiences returns a single audience for workspace owners)
 *   - the shared empty-state behavior
 *
 * The editor still lives at /portal/reports/[id] and mounts inside
 * PortalAppShell via the shared <ReportEditor> from R1.0.1.
 */
function PortalReportsListPage({ session }: { session: PortalSession }) {
  return (
    <PortalAppShell session={session}>
      <ReportsListView
        role="portal"
        editorHrefBase="/portal/reports"
        presetCreateRedirectBase="/portal/reports"
        eyebrowDescription="Centro de cumplimiento personal: estado del expediente, obligaciones pendientes y rechazos por corregir."
        headerSlot={<CompliancePulseStrip session={session} />}
        diagnosticCode={session.workspace_id}
      />
    </PortalAppShell>
  );
}

export default withOnboardingGate(PortalReportsListPage);
