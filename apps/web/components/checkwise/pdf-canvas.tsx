"use client";

import { useEffect, useRef, useState } from "react";
import { CircleNotch } from "@phosphor-icons/react";

import type {
  PDFDocumentProxy,
  PDFPageProxy,
  RenderTask,
} from "pdfjs-dist";

/**
 * Render a PDF to <canvas> with pdf.js.
 *
 * This is the cross-browser path: unlike a native `<iframe>` PDF (which blanks
 * on iOS/iPadOS WebKit and many in-app webviews), canvas rendering works
 * everywhere. pdf.js parses off the main thread in a web worker served from
 * `/pdf.worker.min.mjs` (copied from the pinned pdfjs-dist by
 * scripts/copy-pdf-worker.mjs, so the worker can never drift from the API).
 *
 * CSP: `isEvalSupported:false` means normal text/vector PDFs render with NO
 * `'unsafe-eval'` and NO WebAssembly — i.e. under the current enforced prod
 * CSP unchanged. The only PDFs that need WASM are JPEG2000 (JPXDecode) /
 * JBIG2 scans; those throw and bubble up to `onFail`, which degrades to the
 * open-in-new-tab card rather than weakening the CSP.
 *
 * Pages are rendered lazily (page 1 eager, the rest as they scroll near the
 * viewport) so a large scanned PDF doesn't rasterize everything at once.
 */

// pdfjs-dist is a sizeable lib; load it only when the canvas path is actually
// used (iOS / webview / iframe escalation), never in the main bundle.
let pdfjsPromise: Promise<typeof import("pdfjs-dist")> | null = null;
async function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import("pdfjs-dist").then((pdfjs) => {
      pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
      return pdfjs;
    });
  }
  return pdfjsPromise;
}

// Cap the device-pixel-ratio we rasterize at. dpr 3 on a tall page can exceed
// mobile Safari's per-canvas pixel limit; 2 is crisp and safe.
const MAX_DPR = 2;
// Cap the fit-to-width scale so an ultra-wide container doesn't blow up canvas
// memory for a small page.
const MAX_SCALE = 1.5;

type PdfCanvasProps = {
  blobUrl: string;
  /** Called on any load/parse/render failure so the parent can fall back. */
  onFail: (error?: unknown) => void;
  /** Optional fixed viewport height; defaults to a tall scroll area. */
  heightClassName?: string;
};

export function PdfCanvas({
  blobUrl,
  onFail,
  heightClassName = "h-[480px]",
}: PdfCanvasProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const canvasRefs = useRef<Map<number, HTMLCanvasElement>>(new Map());
  const renderedRef = useRef<Set<number>>(new Set());
  const docRef = useRef<PDFDocumentProxy | null>(null);
  const baseScaleRef = useRef(1);

  const [ready, setReady] = useState(false);
  // Per-page placeholder dimensions (page-1 aspect ratio; corrected on render).
  const [pages, setPages] = useState<{ num: number; w: number; h: number }[]>([]);

  // Load the document and derive page-1 geometry.
  useEffect(() => {
    let cancelled = false;
    let doc: PDFDocumentProxy | null = null;
    renderedRef.current.clear();
    canvasRefs.current.clear();
    setReady(false);
    setPages([]);

    (async () => {
      try {
        const pdfjs = await loadPdfjs();
        const task = pdfjs.getDocument({
          url: blobUrl,
          isEvalSupported: false,
          standardFontDataUrl: "/standard_fonts/",
        });
        doc = await task.promise;
        if (cancelled) {
          void doc.destroy();
          return;
        }
        docRef.current = doc;

        const containerWidth = scrollRef.current?.clientWidth ?? 800;
        const first = await doc.getPage(1);
        const unit = first.getViewport({ scale: 1 });
        const scale = Math.min(containerWidth / unit.width, MAX_SCALE);
        baseScaleRef.current = scale;
        const w = Math.floor(unit.width * scale);
        const h = Math.floor(unit.height * scale);
        first.cleanup();
        if (cancelled) return;

        // Assume uniform page size for placeholders; each page sets its real
        // height when it renders.
        setPages(
          Array.from({ length: doc.numPages }, (_, i) => ({ num: i + 1, w, h })),
        );
        setReady(true);
      } catch (error) {
        if (!cancelled) onFail(error);
      }
    })();

    return () => {
      cancelled = true;
      const d = docRef.current;
      docRef.current = null;
      if (d) void d.destroy();
    };
    // onFail is stable from the parent (useCallback); blobUrl drives reloads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blobUrl]);

  // Lazily rasterize each page as it nears the viewport.
  useEffect(() => {
    if (!ready || pages.length === 0) return;
    const root = scrollRef.current;
    if (!root) return;

    let cancelled = false;
    const tasks = new Set<RenderTask>();

    async function renderPage(num: number) {
      if (cancelled || renderedRef.current.has(num)) return;
      const doc = docRef.current;
      const canvas = canvasRefs.current.get(num);
      if (!doc || !canvas) return;
      renderedRef.current.add(num);
      let page: PDFPageProxy | null = null;
      try {
        page = await doc.getPage(num);
        if (cancelled) return;
        const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
        const viewport = page.getViewport({ scale: baseScaleRef.current });
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        canvas.width = Math.floor(viewport.width * dpr);
        canvas.height = Math.floor(viewport.height * dpr);
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;
        const task = page.render({
          canvasContext: ctx,
          viewport,
          transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined,
        });
        tasks.add(task);
        await task.promise;
        tasks.delete(task);
      } catch (error) {
        // A cancelled render throws RenderingCancelledException — ignore it.
        const name = (error as { name?: string } | null)?.name;
        if (!cancelled && name !== "RenderingCancelledException") {
          renderedRef.current.delete(num);
          onFail(error);
        }
      } finally {
        page?.cleanup();
      }
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const num = Number((entry.target as HTMLElement).dataset.page);
            if (num) void renderPage(num);
            observer.unobserve(entry.target);
          }
        }
      },
      { root, rootMargin: "400px 0px" },
    );

    const placeholders = root.querySelectorAll<HTMLElement>("[data-page]");
    placeholders.forEach((el) => observer.observe(el));
    // Always render page 1 immediately so the preview isn't empty above the fold.
    void renderPage(1);

    return () => {
      cancelled = true;
      observer.disconnect();
      tasks.forEach((t) => t.cancel());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, pages.length]);

  return (
    <div
      ref={scrollRef}
      className={`relative w-full overflow-auto bg-muted/40 ${heightClassName}`}
    >
      {!ready ? (
        <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground">
          <CircleNotch className="h-4 w-4 animate-spin" aria-hidden="true" />
          Cargando vista previa…
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 py-3">
          {pages.map((p) => (
            <div
              key={p.num}
              data-page={p.num}
              style={{ width: p.w, minHeight: p.h }}
              className="flex items-center justify-center bg-white shadow-sm"
            >
              <canvas
                ref={(el) => {
                  if (el) canvasRefs.current.set(p.num, el);
                  else canvasRefs.current.delete(p.num);
                }}
                className="block"
                aria-label={`Página ${p.num}`}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default PdfCanvas;
