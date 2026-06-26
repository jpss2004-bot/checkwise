"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowSquareOut,
  DownloadSimple,
  Eye,
  Warning,
} from "@phosphor-icons/react";

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
 *   The enforced production CSP separately blocked the blob iframe until the
 *   `frame-src 'self' blob:` fix shipped — but that only covered desktop
 *   Chromium. The component below makes the failure *recoverable everywhere*:
 *   it ALWAYS renders an open-in-new-tab / download affordance, never a silent
 *   blank box, and on environments known to blank the native iframe it leads
 *   with that affordance instead of the (useless) frame.
 *
 * This component is intentionally *presentational*: the caller owns minting
 * and revoking `blobUrl` (each surface already does, with different auth /
 * lifecycle rules). Pass a ready-to-use same-origin blob URL.
 */

type PdfPreviewProps = {
  /** A ready same-origin `blob:` URL. The caller owns revoke(). */
  blobUrl: string | null;
  /** Used for a11y labels (and the iframe title when `title` is omitted). */
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
 * (blank or first-page-only) no matter what the CSP says. We skip the iframe
 * there and lead with the open/download card. The fallback link is rendered in
 * every branch, so a wrong guess here never strands the user.
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

// If the iframe has neither fired `onLoad` nor `onError` within this window,
// treat it as a silent blank (CSP-blocked frames frequently fire neither) and
// surface the escape-hatch hint more prominently.
const LOAD_TIMEOUT_MS = 4000;

export function PdfPreview({
  blobUrl,
  fileName = "documento.pdf",
  title = "Vista previa del documento",
  className = "h-[420px] w-full",
  onDownload,
  downloading = false,
}: PdfPreviewProps) {
  const [loaded, setLoaded] = useState(false);
  const [errored, setErrored] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  // Resolved on the client only, to avoid an SSR/CSR hydration mismatch.
  const [unsupported, setUnsupported] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    setUnsupported(nativePdfIframeUnsupported());
  }, []);

  // Reset load state whenever the source changes, and arm the silent-blank
  // timeout for the iframe path.
  useEffect(() => {
    setLoaded(false);
    setErrored(false);
    setTimedOut(false);
    if (!blobUrl || unsupported) return;
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => setTimedOut(true), LOAD_TIMEOUT_MS);
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [blobUrl, unsupported]);

  if (!blobUrl) return null;

  const showBlankHint = errored || (timedOut && !loaded);

  // A persistent escape hatch — rendered in EVERY branch. A `target="_blank"`
  // navigation to a blob: is a top-level navigation and works even when the
  // inline frame is blocked or blanks.
  const fallbackRow = (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border bg-white px-3 py-2 text-xs">
      <a
        href={blobUrl}
        target="_blank"
        rel="noreferrer"
        aria-label={`Abrir ${fileName ?? "el PDF"} en una pestaña nueva`}
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

      {unsupported ? (
        // Known-blank environment (iOS / in-app webview): lead with the
        // open/download card instead of a blank frame.
        <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
          <Eye className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">
            Tu navegador no puede mostrar el PDF aquí mismo. Ábrelo en una
            pestaña nueva para revisarlo.
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
      ) : (
        <>
          {showBlankHint ? (
            <div className="flex items-start gap-2 border-b border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              <Warning
                className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-700"
                aria-hidden="true"
              />
              <span>
                Si no ves el documento, ábrelo en una pestaña nueva con el
                enlace de abajo.
              </span>
            </div>
          ) : null}
          <iframe
            src={blobUrl}
            title={title}
            className={`block bg-white ${className}`}
            onLoad={() => setLoaded(true)}
            onError={() => setErrored(true)}
          />
        </>
      )}

      {fallbackRow}
    </div>
  );
}

export default PdfPreview;
