"use client";

import { useCallback, useState } from "react";
import { DownloadSimple } from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import {
  ReportsApiError,
  createReportExport,
  downloadReportExport,
  getReportExport,
  type ReportExport,
} from "@/lib/api/reports";

/**
 * Phase 10A — server-side export trigger.
 *
 * Calls ``POST /api/v1/reports/{id}/exports`` to create a pending
 * ``ReportExport`` row, polls ``GET /api/v1/reports/exports/{id}``
 * until the row reaches ``ready`` (or ``failed``), then opens the
 * download URL in a new tab.
 *
 * Slice 10A only wires the ``html`` format. Once 10B (PDF) and 10C
 * (Excel) land, this component evolves into a dropdown with one
 * trigger per format. The polling + status flow stays.
 *
 * Polling cadence: 1s, capped at 30s (= 30 polls). Most exports
 * complete in <500ms because BackgroundTasks runs the renderer
 * inline before the response cleanup. The 30s cap is for the future
 * when PDF rendering goes async through Playwright.
 */

const POLL_INTERVAL_MS = 1000;
const POLL_MAX_ATTEMPTS = 30;

export function ExportButton({ reportId }: { reportId: string }) {
  const [busy, setBusy] = useState(false);

  // Note: no unmount-cancellation guard. The earlier version used a
  // useEffect cleanup that flipped a ref to "cancelled", but React
  // StrictMode fires that cleanup immediately after mount in dev,
  // which made the very first poll throw. Letting the poll loop
  // continue after unmount is safe — the toast call would target a
  // gone-Toaster (no-op), and we never touch state with setBusy
  // after the async chain unwinds.
  const pollUntilReady = useCallback(
    async (exportId: string): Promise<ReportExport> => {
      for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt += 1) {
        const current = await getReportExport(exportId);
        if (current.status === "ready") return current;
        if (current.status === "failed") {
          throw new Error(
            current.error_text ?? "El renderizador falló sin mensaje.",
          );
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      }
      throw new Error(
        "El export tardó demasiado. Intenta de nuevo en unos segundos.",
      );
    },
    [],
  );

  const onClick = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      const created = await createReportExport(reportId, { format: "html" });
      const ready = await pollUntilReady(created.id);
      // Pull the bytes via fetch so the bearer token flows; then
      // trigger an anchor-click download. window.open doesn't carry
      // the Authorization header so a plain navigation would 401.
      await downloadReportExport(
        ready.id,
        `checkwise-reporte-${reportId.slice(0, 8)}.html`,
      );
      toast.success("Reporte exportado.");
    } catch (err) {
      const message =
        err instanceof ReportsApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "No pudimos exportar el reporte.";
      toast.error(message);
    } finally {
      setBusy(false);
    }
  }, [busy, pollUntilReady, reportId]);

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      onClick={onClick}
      disabled={busy}
      title="Exportar el reporte como archivo HTML autocontenido"
    >
      <DownloadSimple className="h-4 w-4" weight="bold" aria-hidden="true" />
      {busy ? "Exportando…" : "Descargar HTML"}
    </Button>
  );
}
