"use client";

import { useEffect } from "react";
import { ArrowSquareOut, DownloadSimple, X } from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";

/**
 * In-app PDF preview.
 *
 * Renders the finished report PDF in an iframe inside a focused modal,
 * INSTEAD of opening a browser tab. The old "open a blank tab, then point
 * it at the URL once the render finishes" pattern stole focus to the
 * blank tab mid-render, which backgrounded the app tab — and browsers
 * throttle background-tab timers, so the poll loop stalled until the user
 * clicked back. Keeping the preview in-app means the render completes in
 * the foreground and the result appears in place. "Abrir en pestaña" and
 * "Descargar" stay available as one-click, user-gesture actions (no
 * popup-blocker or focus issues, because they fire on a real click).
 */
export function ReportPreviewModal({
  url,
  onClose,
  onDownload,
  downloading,
}: {
  /** Inline-disposition URL for the PDF (presigned R2 in prod, blob locally). */
  url: string;
  onClose: () => void;
  onDownload: () => void;
  downloading: boolean;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Vista previa del reporte"
      className="cw-fade-in fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6"
      style={{ background: "hsl(var(--navy-950) / 0.6)" }}
      onClick={onClose}
    >
      <div
        className="cw-fade-up flex h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-[0_24px_60px_-24px_hsl(var(--navy-950)/0.5)]"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between gap-3 border-b border-[color:var(--border-subtle)] px-4 py-2.5">
          <div className="min-w-0">
            <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-[color:var(--text-ai)]">
              CheckWise · Reporte
            </p>
            <h2 className="truncate text-[14px] font-semibold tracking-tight text-[color:var(--text-primary)]">
              Vista previa
            </h2>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={onDownload}
              disabled={downloading}
              title="Descargar el PDF"
            >
              <DownloadSimple className="h-4 w-4" weight="bold" aria-hidden="true" />
              {downloading ? "Descargando…" : "Descargar"}
            </Button>
            <Button
              asChild
              variant="ghost"
              size="sm"
              title="Abrir en una pestaña nueva"
            >
              <a href={url} target="_blank" rel="noopener noreferrer">
                <ArrowSquareOut className="h-4 w-4" weight="bold" aria-hidden="true" />
                Pestaña
              </a>
            </Button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Cerrar vista previa"
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]"
            >
              <X className="h-4 w-4" weight="bold" aria-hidden="true" />
            </button>
          </div>
        </header>
        <iframe
          src={url}
          title="Vista previa del reporte"
          className="h-full w-full flex-1 border-0 bg-[color:var(--surface-page)]"
        />
      </div>
    </div>
  );
}
