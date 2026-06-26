"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowSquareOut, DownloadSimple, Eye } from "@phosphor-icons/react";

import { PdfCanvas } from "@/components/checkwise/pdf-canvas";

/**
 * Shared PDF preview surface.
 *
 * Background — the recurring "blank Vista previa del PDF" bug:
 *   Every preview surface used to render a bare `<iframe src={blobUrl}>` that
 *   leaned entirely on the browser's *native* PDF viewer. That fails silently
 *   in several environments, regardless of CSP:
 *     - iOS / iPadOS WebKit cannot reliably render a multi-page PDF in an
 *       <iframe>; it shows blank or a cropped first page.
 *     - In-app webviews (Gmail, WhatsApp, Facebook, …) often have no PDF
 *       renderer at all.
 *     - A managed/enterprise browser with the built-in PDF viewer disabled.
 *     - A blob whose Content-Type is not `application/pdf`.
 *
 * Strategy (most robust → graceful degradation), always with an escape hatch:
 *   1. Desktop browsers that render PDFs in an <iframe> keep the native viewer
 *      (free zoom/print/search toolbar).
 *   2. Environments known to blank the native iframe (iOS/iPadOS, in-app
 *      webviews) — and any iframe that silently fails on desktop — fall to a
 *      pdf.js <canvas> renderer (<PdfCanvas>), which renders everywhere.
 *   3. If even canvas can't render (e.g. a JPEG2000 scan that would need WASM
 *      we deliberately don't enable), show an open-in-new-tab card.
 *   In every branch a persistent "Abrir en una pestaña nueva" link is rendered,
 *   so the user is never stuck on a silent blank box.
 *
 * This component is *presentational*: the caller owns minting and revoking
 * `blobUrl` (each surface already does, with different auth / lifecycle rules).
 */

type PdfPreviewProps = {
  /** A ready same-origin `blob:` URL. The caller owns revoke(). */
  blobUrl: string | null;
  /** Used for a11y labels. */
  fileName?: string;
  /** Accessible title for the iframe. */
  title?: string;
  /** Tailwind sizing for the preview frame. Default: `h-[420px] w-full`. */
  className?: string;
  /**
   * Optional download action. When provided, the fallback row also offers a
   * "Descargar" affordance wired to it (e.g. a server re-fetch with
   * `download=true`). Omit it on surfaces that already expose their own
   * download button, or where the file is the user's own local pick.
   */
  onDownload?: () => void;
  /** Reflects an in-flight `onDownload`. */
  downloading?: boolean;
};

/**
 * Environments where a native `<iframe>` PDF render is known to be unreliable
 * (blank or first-page-only) no matter what the CSP says. There we skip the
 * iframe and go straight to the pdf.js canvas renderer.
 */
function nativePdfIframeUnsupported(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  // iOS / iPadOS — including iPadOS 13+ which reports as "Mac" but exposes
  // touch points.
  const isAppleTouch =
    /iP(hone|ad|od)/.test(navigator.platform) ||
    (ua.includes("Mac") && (navigator.maxTouchPoints ?? 0) > 1);
  // Common in-app webviews with no PDF renderer.
  const isInAppWebview = /(FBAN|FBAV|Instagram|Line\/|WhatsApp|GSA\/)/.test(ua);
  return isAppleTouch || isInAppWebview;
}

// If the iframe neither loads nor errors within this window, treat it as a
// silent blank (CSP-blocked / disabled-viewer frames fire neither) and escalate
// to the pdf.js canvas renderer.
const IFRAME_ESCALATE_MS = 7000;

export function PdfPreview({
  blobUrl,
  fileName = "documento.pdf",
  title = "Vista previa del documento",
  className = "h-[420px] w-full",
  onDownload,
  downloading = false,
}: PdfPreviewProps) {
  // Resolved on the client only, to avoid an SSR/CSR hydration mismatch.
  const [unsupported, setUnsupported] = useState(false);
  const [iframeLoaded, setIframeLoaded] = useState(false);
  const [iframeFailed, setIframeFailed] = useState(false);
  const [canvasFailed, setCanvasFailed] = useState(false);

  useEffect(() => {
    setUnsupported(nativePdfIframeUnsupported());
  }, []);

  // Reset the renderer state whenever the source changes.
  useEffect(() => {
    setIframeLoaded(false);
    setIframeFailed(false);
    setCanvasFailed(false);
  }, [blobUrl]);

  const showIframe = !!blobUrl && !unsupported && !iframeFailed;

  // Escalate a silently-blank iframe to the canvas renderer.
  useEffect(() => {
    if (!showIframe || iframeLoaded) return;
    const timer = window.setTimeout(
      () => setIframeFailed(true),
      IFRAME_ESCALATE_MS,
    );
    return () => window.clearTimeout(timer);
  }, [showIframe, iframeLoaded]);

  const handleCanvasFail = useCallback(() => setCanvasFailed(true), []);

  if (!blobUrl) return null;

  const useCanvas = (unsupported || iframeFailed) && !canvasFailed;

  // A persistent escape hatch — rendered in EVERY branch. A `target="_blank"`
  // navigation to a blob: is a top-level navigation and works even when the
  // inline frame is blocked or blanks.
  const fallbackRow = (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border bg-white px-3 py-2 text-xs">
      <a
        href={blobUrl}
        target="_blank"
        rel="noreferrer"
        aria-label={`Abrir ${fileName} en una pestaña nueva`}
        className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline"
      >
        <ArrowSquareOut className="h-3.5 w-3.5" aria-hidden="true" />
        Abrir en una pestaña nueva
      </a>
      {onDownload ? (
        <button
          type="button"
          onClick={onDownload}
          disabled={downloading}
          className="inline-flex items-center gap-1.5 font-medium text-muted-foreground hover:text-primary hover:underline disabled:opacity-60"
        >
          <DownloadSimple className="h-3.5 w-3.5" aria-hidden="true" />
          {downloading ? "Descargando…" : "Descargar PDF"}
        </button>
      ) : null}
    </div>
  );

  return (
    <div className="overflow-hidden rounded-md border border-border bg-muted/30">
      <div className="flex items-center gap-2 border-b border-border bg-white px-3 py-2 text-xs font-medium text-muted-foreground">
        <Eye className="h-3.5 w-3.5" aria-hidden="true" />
        Vista previa del PDF
      </div>

      {showIframe ? (
        <iframe
          src={blobUrl}
          title={title}
          className={`block bg-white ${className}`}
          onLoad={() => setIframeLoaded(true)}
          onError={() => setIframeFailed(true)}
        />
      ) : useCanvas ? (
        <PdfCanvas
          blobUrl={blobUrl}
          onFail={handleCanvasFail}
          heightClassName={className}
        />
      ) : (
        // Last resort: nothing could render inline (e.g. a JPEG2000 scan that
        // would need WASM we deliberately don't enable under the strict CSP).
        <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
          <Eye className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">
            No pudimos mostrar el PDF aquí mismo. Ábrelo en una pestaña nueva
            para revisarlo.
          </p>
          <a
            href={blobUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-white px-3 py-2 text-sm font-medium text-primary hover:bg-muted/50"
          >
            <ArrowSquareOut className="h-4 w-4" aria-hidden="true" />
            Abrir el PDF
          </a>
        </div>
      )}

      {fallbackRow}
    </div>
  );
}

export default PdfPreview;
