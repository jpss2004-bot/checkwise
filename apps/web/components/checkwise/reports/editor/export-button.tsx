"use client";

import { useCallback, useState } from "react";
import { DownloadSimple, Eye, FilePdf } from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import { OVERFLOW_MENU_ROW_CLASS } from "@/components/ui/overflow-menu";
import { toast } from "@/components/ui/toast";
import {
  ReportExportOverlay,
  type ExportPhase,
} from "@/components/checkwise/reports/report-export-overlay";
import { ReportPreviewModal } from "@/components/checkwise/reports/report-preview-modal";
import { cn } from "@/lib/utils";
import {
  ReportsApiError,
  createReportExport,
  downloadReportExport,
  fetchReportExportObjectUrl,
  pollReportExportUntilReady,
  type ReportExportFormat,
} from "@/lib/api/reports";

/**
 * Phase 10 — server-side export trigger.
 *
 * Calls ``POST /api/v1/reports/{id}/exports`` to create a pending
 * ``ReportExport`` row, polls ``GET /api/v1/reports/exports/{id}``
 * until the row reaches ``ready`` (or ``failed``), then fetches the
 * artifact as a Blob and triggers an anchor-click download.
 *
 * One instance per format so the editor toolbar renders two adjacent
 * buttons ("Descargar HTML" + "Descargar PDF") rather than a
 * dropdown — the project's UI primitives don't include a dropdown
 * menu yet and adding one for two options would expand scope.
 *
 * Polling cadence: 1s, capped at 30 attempts. HTML renders complete
 * in <500ms (pure Python). PDF renders take 1-3s in dev (chromium
 * cold-start dominates) and ~500ms once Playwright's browser process
 * is warm. The 30s cap leaves generous headroom for Render's cold
 * start.
 */

const FORMAT_META: Record<
  ReportExportFormat,
  { label: string; busyLabel: string; title: string; icon: React.ElementType }
> = {
  html: {
    label: "Descargar HTML",
    busyLabel: "Exportando HTML…",
    title: "Exportar el reporte como archivo HTML autocontenido",
    icon: DownloadSimple,
  },
  pdf: {
    label: "Descargar PDF",
    busyLabel: "Generando PDF…",
    title: "Descargar el reporte como un PDF limpio, renderizado en el servidor.",
    icon: FilePdf,
  },
};

export function ExportButton({
  reportId,
  format,
  variant = "ghost",
  className,
  asMenuItem = false,
}: {
  reportId: string;
  format: ReportExportFormat;
  // R2 (promoted CTAs): editor promotes the primary export to
  // ``variant="default"`` once the report has content so the user
  // doesn't have to hunt for the download path in a row of ghost
  // buttons.
  variant?: "ghost" | "default" | "outline";
  // M2 (2026-06-02): the Reportes header overflow menu reskins the
  // export buttons as menu rows. Optional className lets the consumer
  // override the default Button styling so the trigger looks like a
  // menuitem (full-width, left-aligned, no rounded corners) rather
  // than a sized button.
  className?: string;
  // 2026-06-02 fix: when rendered inside an OverflowMenuItem, the
  // <Button>'s default chrome (size="sm" fixed height, ghost-variant
  // hover styles, inline-flex/justify-center base) fights with the
  // menu-row layout — items rendered visibly bigger than the plain
  // <button>/<Link> rows around them. Setting ``asMenuItem`` switches
  // to a bare <button> styled with OVERFLOW_MENU_ROW_CLASS so every
  // row in the menu looks identical.
  asMenuItem?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<ExportPhase>("queued");
  const meta = FORMAT_META[format];

  // Note: no unmount-cancellation guard. The earlier version used a
  // useEffect cleanup that flipped a ref to "cancelled", but React
  // StrictMode fires that cleanup immediately after mount in dev,
  // which made the very first poll throw. Letting the poll loop
  // continue after unmount is safe — the toast call targets a
  // gone-Toaster (no-op) and we never touch state with setBusy
  // after the async chain unwinds.
  const onClick = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setPhase("queued");
    try {
      const created = await createReportExport(reportId, { format });
      const ready = await pollReportExportUntilReady(created.id, {
        onStatus: (s) => setPhase(s === "rendering" ? "rendering" : "queued"),
      });
      setPhase("finalizing");
      await downloadReportExport(
        ready.id,
        `checkwise-reporte-${reportId.slice(0, 8)}.${format}`,
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
  }, [busy, format, reportId]);

  // Only PDF gets the full progress overlay; HTML renders in <500ms in
  // the overflow menu, where the button's busy label is enough.
  const overlay =
    format === "pdf" ? (
      <ReportExportOverlay open={busy} mode="download" phase={phase} />
    ) : null;

  const Icon = meta.icon;
  if (asMenuItem) {
    return (
      <>
        <button
          type="button"
          onClick={onClick}
          disabled={busy}
          title={meta.title}
          className={cn(OVERFLOW_MENU_ROW_CLASS, className)}
        >
          <Icon className="h-4 w-4 shrink-0" weight="bold" aria-hidden="true" />
          <span>{busy ? meta.busyLabel : meta.label}</span>
        </button>
        {overlay}
      </>
    );
  }
  return (
    <>
      <Button
        type="button"
        variant={variant}
        size="sm"
        onClick={onClick}
        disabled={busy}
        title={meta.title}
        className={className}
      >
        <Icon className="h-4 w-4" weight="bold" aria-hidden="true" />
        {busy ? meta.busyLabel : meta.label}
      </Button>
      {overlay}
    </>
  );
}

/**
 * Inline PDF preview — renders the SAME server-rendered PDF the Download
 * button produces, in an in-app modal (iframe) rather than a browser tab.
 *
 * Why not a new tab: the old approach opened a blank tab synchronously on
 * click (to dodge popup blockers) and pointed it at the URL once the
 * render finished. But opening the tab stole focus to it, which
 * backgrounded the app tab — and browsers throttle background-tab timers,
 * so the poll loop stalled until the user clicked back into the app. The
 * render now stays in the foreground and the result appears in place; the
 * modal still offers "Abrir en pestaña" / "Descargar" as one-click
 * gesture actions.
 */
export function PreviewPdfButton({
  reportId,
  variant = "outline",
  className,
  asMenuItem = false,
}: {
  reportId: string;
  variant?: "ghost" | "default" | "outline";
  className?: string;
  // Render as an overflow-menu row (bare button styled with
  // OVERFLOW_MENU_ROW_CLASS) instead of a sized Button — same pattern as
  // ExportButton, so every row in a menu looks identical.
  asMenuItem?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<ExportPhase>("queued");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewExportId, setPreviewExportId] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const onClick = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setPhase("queued");
    try {
      const created = await createReportExport(reportId, { format: "pdf" });
      const ready = await pollReportExportUntilReady(created.id, {
        onStatus: (s) => setPhase(s === "rendering" ? "rendering" : "queued"),
      });
      setPhase("finalizing");
      // ``inline`` disposition URL — the modal's iframe renders it in place.
      const objectUrl = await fetchReportExportObjectUrl(ready.id);
      setPreviewExportId(ready.id);
      setPreviewUrl(objectUrl);
    } catch (err) {
      const message =
        err instanceof ReportsApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "No pudimos generar la vista previa.";
      toast.error(message);
    } finally {
      setBusy(false);
    }
  }, [busy, reportId]);

  const closePreview = useCallback(() => {
    setPreviewUrl((current) => {
      // Only blob URLs (local-disk storage) need revoking; presigned R2
      // URLs are plain links.
      if (current && current.startsWith("blob:")) URL.revokeObjectURL(current);
      return null;
    });
    setPreviewExportId(null);
  }, []);

  const onDownloadFromPreview = useCallback(async () => {
    if (!previewExportId || downloading) return;
    setDownloading(true);
    try {
      await downloadReportExport(
        previewExportId,
        `checkwise-reporte-${reportId.slice(0, 8)}.pdf`,
      );
    } catch (err) {
      toast.error(
        err instanceof ReportsApiError
          ? err.message
          : "No pudimos descargar el PDF.",
      );
    } finally {
      setDownloading(false);
    }
  }, [previewExportId, downloading, reportId]);

  const label = busy ? "Generando vista previa…" : "Vista previa";
  const overlay = (
    <>
      <ReportExportOverlay open={busy} mode="preview" phase={phase} />
      {previewUrl ? (
        <ReportPreviewModal
          url={previewUrl}
          onClose={closePreview}
          onDownload={onDownloadFromPreview}
          downloading={downloading}
        />
      ) : null}
    </>
  );
  if (asMenuItem) {
    return (
      <>
        <button
          type="button"
          onClick={onClick}
          disabled={busy}
          title="Abrir una vista previa del PDF en una pestaña nueva"
          className={cn(OVERFLOW_MENU_ROW_CLASS, className)}
        >
          <Eye className="h-4 w-4 shrink-0" weight="bold" aria-hidden="true" />
          <span>{label}</span>
        </button>
        {overlay}
      </>
    );
  }
  return (
    <>
      <Button
        type="button"
        variant={variant}
        size="sm"
        onClick={onClick}
        disabled={busy}
        title="Abrir una vista previa del PDF en una pestaña nueva"
        className={className}
      >
        <Eye className="h-4 w-4" weight="bold" aria-hidden="true" />
        {label}
      </Button>
      {overlay}
    </>
  );
}
