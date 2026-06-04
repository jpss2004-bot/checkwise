"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowsClockwise, FilePdf, WarningCircle } from "@phosphor-icons/react";

import {
  ReportsApiError,
  createReportExport,
  fetchReportExportObjectUrl,
  pollReportExportUntilReady,
} from "@/lib/api/reports";

/**
 * Standalone PDF tab.
 *
 * The "Vista previa" button opens this route in a NEW tab. Generating the
 * PDF here (in the now-foreground tab) instead of the source tab avoids
 * the background-tab timer throttling that stalled the old approach: the
 * source tab just opens this URL, and this tab creates the export, polls
 * to ready, then replaces itself with the PDF — landing in the browser's
 * native PDF viewer (download / print built in). No focus theft, no
 * popup-blocker dance, no in-app modal.
 *
 * Auth rides the localStorage session, shared across same-origin tabs.
 */
export default function ReportPdfTabPage() {
  const params = useParams();
  const reportId = typeof params?.id === "string" ? params.id : "";
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!reportId) return;
    let cancelled = false;
    (async () => {
      try {
        const created = await createReportExport(reportId, { format: "pdf" });
        const ready = await pollReportExportUntilReady(created.id);
        const url = await fetchReportExportObjectUrl(ready.id); // inline
        if (cancelled) return;
        // ``replace`` so the back button returns to the report, not this loader.
        window.location.replace(url);
      } catch (err) {
        if (cancelled) return;
        setErrorMsg(
          err instanceof ReportsApiError
            ? err.message
            : "No pudimos generar el PDF. Cierra esta pestaña e intenta de nuevo.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reportId]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-[color:var(--surface-page)] p-6">
      {errorMsg ? (
        <div className="cw-fade-up flex max-w-sm flex-col items-center gap-3 text-center">
          <span className="inline-flex h-11 w-11 items-center justify-center rounded-md bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]">
            <WarningCircle className="h-6 w-6" weight="bold" aria-hidden="true" />
          </span>
          <h1 className="text-[15px] font-semibold text-[color:var(--text-primary)]">
            No se pudo generar el PDF
          </h1>
          <p className="text-[13px] leading-relaxed text-[color:var(--text-secondary)]">
            {errorMsg}
          </p>
        </div>
      ) : (
        <div className="cw-fade-up flex max-w-sm flex-col items-center gap-4 text-center">
          <span className="cw-pulse-soft inline-flex h-12 w-12 items-center justify-center rounded-lg bg-[color:var(--surface-ai-muted)] text-[color:var(--text-ai)]">
            <FilePdf className="h-6 w-6" weight="duotone" aria-hidden="true" />
          </span>
          <div className="space-y-1">
            <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-[color:var(--text-ai)]">
              CheckWise · Reporte
            </p>
            <h1 className="text-[16px] font-semibold tracking-tight text-[color:var(--text-primary)]">
              Preparando tu PDF
            </h1>
          </div>
          <div className="h-1 w-48 overflow-hidden rounded-full bg-[color:var(--surface-sunken)]">
            <div className="cw-indeterminate h-full w-2/5 rounded-full bg-[color:var(--interactive-ai)]" />
          </div>
          <p className="flex items-center gap-1.5 text-[12px] text-[color:var(--text-tertiary)]">
            <ArrowsClockwise
              className="h-3.5 w-3.5 animate-spin"
              aria-hidden="true"
            />
            El documento se abrirá aquí en cuanto esté listo.
          </p>
        </div>
      )}
    </main>
  );
}
