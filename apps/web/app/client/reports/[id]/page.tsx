"use client";

import { useParams } from "next/navigation";

import { ClientShell } from "../../_shell";
import { ReportEditor } from "@/components/checkwise/reports/editor/report-editor";

/**
 * Client report editor — R1.0.1.
 *
 * Mounts the shared <ReportEditor> inside ClientShell so client_admins
 * stay in their own shell. Mirrors the admin route exactly except for
 * the back href.
 */
export default function ClientReportEditorPage() {
  const params = useParams();
  const reportId = typeof params?.id === "string" ? params.id : "";
  return (
    <ClientShell unframed>
      <ReportEditor
        reportId={reportId}
        backHref="/client/reports"
        printHref={`/portal/reports/${reportId}/print`}
        readOnly
      />
    </ClientShell>
  );
}
