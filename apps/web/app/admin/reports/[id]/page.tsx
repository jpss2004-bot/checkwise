"use client";

import { useParams } from "next/navigation";

import { AdminShell } from "../../_shell";
import { ReportEditor } from "@/components/checkwise/reports/editor/report-editor";

/**
 * Admin report editor — R1.0.1.
 *
 * Mounts the shared <ReportEditor> inside AdminShell so internal
 * users stay in their own shell instead of being bounced to the
 * portal. The shell is set unframed so the editor renders its own
 * full page header (with the report-specific title + AI actions).
 *
 * Print route is shared (/portal/reports/[id]/print) — chrome-less
 * and identical across roles.
 */
export default function AdminReportEditorPage() {
  const params = useParams();
  const reportId = typeof params?.id === "string" ? params.id : "";
  return (
    <AdminShell unframed>
      <ReportEditor
        reportId={reportId}
        backHref="/admin/reports"
        readOnly
      />
    </AdminShell>
  );
}
