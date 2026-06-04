"use client";

import { useParams } from "next/navigation";

import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { ReportEditor } from "@/components/checkwise/reports/editor/report-editor";
import { withOnboardingGate } from "@/lib/session/with-onboarding-gate";
import type { PortalSession } from "@/lib/session/portal";

/**
 * Provider portal report editor.
 *
 * Thin wrapper around the shared <ReportEditor>. The onboarding gate
 * still protects this route — providers in their first-login flow
 * are bounced back to /portal/onboarding before reaching the editor.
 */
function PortalReportEditorPage({ session }: { session: PortalSession }) {
  const params = useParams();
  const reportId = typeof params?.id === "string" ? params.id : "";
  return (
    <PortalAppShell session={session}>
      <ReportEditor
        reportId={reportId}
        backHref="/portal/reports"
        readOnly
      />
    </PortalAppShell>
  );
}

export default withOnboardingGate(PortalReportEditorPage);
