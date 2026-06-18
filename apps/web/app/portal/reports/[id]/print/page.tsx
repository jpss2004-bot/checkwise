"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { ArrowLeft, Printer, WarningCircle } from "@phosphor-icons/react";

import { Canvas } from "@/components/checkwise/reports/canvas";
import { ReportMasthead } from "@/components/checkwise/reports/report-masthead";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  REPORT_AUDIENCE_LABEL,
  REPORT_STATUS_LABEL,
} from "@/lib/reports/constants";
import {
  ReportsApiError,
  getReport,
  type ReportBlock,
  type ReportContent,
  type ReportRead,
} from "@/lib/api/reports";

/**
 * Print mode — executive-grade PDF via browser print.
 *
 * P1.8: open in a new tab and either click "Imprimir / Guardar como PDF"
 * or land here from "Descargar PDF" (?autoprint=1) which fires
 * window.print() on first paint. No server-side renderer.
 *
 * The Canvas is mounted WITHOUT ReportActionsContext, so per-block
 * FreshnessLabel components correctly drop their interactive
 * "Actualizar" chip — the "Datos al …" text remains as paper-safe
 * static content.
 */

export default function PrintPage() {
  const params = useParams();
  const search = useSearchParams();
  const reportId = typeof params?.id === "string" ? params.id : "";
  const autoprint = search?.get("autoprint") === "1";

  const [report, setReport] = useState<ReportRead | null>(null);
  const [content, setContent] = useState<ReportContent | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getReport(reportId)
      .then((r) => {
        if (cancelled) return;
        setReport(r);
        setContent(
          r.current_version?.content_json ?? {
            schema_version: 1,
            blocks: [],
            global: {},
          },
        );
      })
      .catch((e: ReportsApiError) => {
        if (cancelled) return;
        setError(
          e.status === 404 ? "Reporte no encontrado." : e.message ?? "Error.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [reportId]);

  // ?autoprint=1 → trigger window.print() after the canvas has mounted
  // and a paint has happened, so the print dialog sees fully-rendered
  // content. One-shot per page-load via a ref guard.
  const printReady = report !== null && content !== null && !error;
  useEffect(() => {
    if (!autoprint || !printReady) return;
    let cancelled = false;
    const id = window.setTimeout(() => {
      if (!cancelled) window.print();
    }, 350);
    return () => {
      cancelled = true;
      window.clearTimeout(id);
    };
  }, [autoprint, printReady]);

  const sealedAt = useMemo(
    () => firstFreshness(content?.blocks ?? []),
    [content],
  );

  if (error) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-12">
        <Alert variant="warning">
          <AlertTitle className="flex items-center gap-2">
            <WarningCircle className="h-4 w-4" weight="bold" aria-hidden="true" />
            Reporte no disponible
          </AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
        <Button asChild variant="outline" size="sm" className="mt-4">
          <Link href="/portal/reports">
            <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
            Volver
          </Link>
        </Button>
      </main>
    );
  }

  if (!report || !content) {
    return (
      <main className="mx-auto flex max-w-2xl items-center gap-3 px-6 py-12 text-sm text-[color:var(--text-secondary)]">
        <Spinner label="Preparando el reporte para imprimir…" />
        <span>Preparando el reporte para imprimir…</span>
      </main>
    );
  }

  const generatedAtLabel = new Date().toLocaleDateString("es-MX", {
    dateStyle: "long",
  });
  const sealLabel = sealedAt
    ? new Date(sealedAt).toLocaleDateString("es-MX", {
        dateStyle: "long",
      })
    : null;

  return (
    <>
      <PrintStyles
        runningTitle={report.title}
        runningAudience={REPORT_AUDIENCE_LABEL[report.audience]}
        runningVersion={`v${report.current_version?.version_number ?? "—"}`}
      />
      {/* Screen-only toolbar; hidden on @media print. */}
      <div className="cw-print-toolbar sticky top-0 z-10 flex items-center justify-between border-b border-[color:var(--border-default)] bg-[color:var(--surface-page)] px-6 py-3">
        <Button asChild variant="ghost" size="sm">
          <Link href={`/portal/reports/${reportId}`}>
            <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
            Volver al editor
          </Link>
        </Button>
        <Button
          variant="default"
          size="sm"
          onClick={() => window.print()}
          title="Imprimir o guardar como PDF"
        >
          <Printer className="h-4 w-4" weight="bold" aria-hidden="true" />
          Imprimir
        </Button>
      </div>

      <main className="cw-print-document mx-auto max-w-3xl px-6 py-8">
        {/* Cover — shares the branded ReportMasthead with the on-screen
            StoryView so the printed PDF and the auditor view open with the
            same navy/teal document cover. */}
        <header className="cw-print-cover mb-8">
          <ReportMasthead
            title={report.title}
            description={report.description}
            meta={[
              // 2026-06-05: Audiencia / Estado / Versión are internal
              // document-management fields — kept on internal_only
              // covers, dropped for client/vendor/external deliverables
              // (matches StoryView). External covers carry only dates.
              ...(report.audience === "internal_only"
                ? [
                    {
                      label: "Audiencia",
                      value: REPORT_AUDIENCE_LABEL[report.audience],
                    },
                    { label: "Estado", value: REPORT_STATUS_LABEL[report.status] },
                    {
                      label: "Versión",
                      value: `v${report.current_version?.version_number ?? "—"}`,
                    },
                  ]
                : []),
              { label: "Generado", value: generatedAtLabel },
              {
                label: "Datos al",
                value:
                  sealLabel && sealLabel !== generatedAtLabel ? sealLabel : null,
              },
            ]}
          />
          {/* F5 (2026-05-19): the old boxed `cw-print-seal` paragraph was
              dropped; the "Generado" / "Datos al" stamps now live in the
              masthead meta row above. */}
        </header>

        <Canvas
          content={content}
          editable={false}
          onChange={() => {}}
          /* All AI / regenerate / explain hooks omitted — print is read-only. */
        />

        <footer className="cw-print-footer mt-12 border-t border-[color:var(--border-default)] pt-4 text-[10px] text-[color:var(--text-tertiary)]">
          <p>
            CheckWise · {report.title} · v
            {report.current_version?.version_number ?? "—"}
            {" · "}Generado el{" "}
            {new Date().toLocaleDateString("es-MX", { dateStyle: "long" })}
            {" · "}Plataforma de cumplimiento REPSE
          </p>
          <p className="mt-1">
            Las secciones marcadas con el ícono de IA fueron generadas
            automáticamente y deben verificarse antes de su distribución.
          </p>
        </footer>
      </main>
    </>
  );
}

/**
 * Pull the first available `data.fetched_at` from the report's
 * blocks. This becomes the "Datos al …" seal so a printed copy
 * carries the data-as-of stamp on page 1, independent of the
 * generated-at timestamp.
 */
function firstFreshness(blocks: ReportBlock[]): string | null {
  for (const b of blocks) {
    const data = (b as { data?: { fetched_at?: string | null } }).data;
    if (data?.fetched_at) return data.fetched_at;
  }
  return null;
}

/**
 * Print-specific CSS. Pulls the toolbar out of the printed output,
 * tightens margins, forces page-break-inside avoidance per block,
 * promotes executive_summary into a cover when it's first, and
 * special-cases prioritized_actions onto its own page so the
 * decision section opens fresh.
 *
 * Running header/footer pull from CSS env via JS-injected props so
 * each page reasserts the report's identity. Page numbers via
 * @page counter (`counter(page)` / `counter(pages)`).
 */
function PrintStyles({
  runningTitle,
  runningAudience,
  runningVersion,
}: {
  runningTitle: string;
  runningAudience: string;
  runningVersion: string;
}) {
  // Escape quotes so injected strings don't break the CSS content() value.
  const safeTitle = runningTitle.replace(/"/g, '\\"');
  const safeMeta = `${runningAudience} · ${runningVersion}`.replace(/"/g, '\\"');

  return (
    <style jsx global>{`
      @media print {
        @page {
          size: Letter;
          margin: 0.75in 0.75in 0.9in 0.75in;

          @top-left {
            content: "${safeTitle}";
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
              sans-serif;
            font-size: 9pt;
            color: #6b7280;
          }
          @top-right {
            content: "${safeMeta}";
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
              sans-serif;
            font-size: 9pt;
            color: #6b7280;
          }
          @bottom-right {
            content: "Página " counter(page) " de " counter(pages);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
              sans-serif;
            font-size: 9pt;
            color: #6b7280;
          }
          @bottom-left {
            content: "CheckWise · Plataforma de cumplimiento REPSE";
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
              sans-serif;
            font-size: 9pt;
            color: #9ca3af;
          }
        }

        /* The first @page suppresses running header — the cover speaks for itself. */
        @page :first {
          @top-left {
            content: "";
          }
          @top-right {
            content: "";
          }
        }

        html,
        body {
          background: white !important;
          color: #111827 !important;
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
        }

        /* Toolbar + any element opted-out via .cw-print-hidden. */
        .cw-print-toolbar,
        .cw-print-hidden {
          display: none !important;
        }

        .cw-print-document {
          max-width: none;
          padding: 0;
        }
        .cw-print-cover {
          page-break-after: avoid;
        }

        /* Every block: never split mid-block, give them air. */
        article[data-block-id] {
          page-break-inside: avoid;
          break-inside: avoid;
          margin-top: 0.4in;
        }
        article[data-block-id]:first-of-type {
          margin-top: 0;
        }

        /* Per-block-type page-break controls. */
        article[data-block-type="executive_summary"]:first-of-type {
          page-break-after: always;
        }
        article[data-block-type="prioritized_actions"] {
          page-break-before: always;
        }
        article[data-block-type="vendor_risk_matrix"] {
          page-break-inside: auto; /* allow long tables to flow */
        }
        article[data-block-type="vendor_risk_matrix"] tr,
        article[data-block-type="upcoming_deadlines"] tr {
          page-break-inside: avoid;
        }

        /* Drop hover-only chrome that escaped print:hidden. */
        button {
          display: none !important;
        }
        /* Preserve interactive-looking <a>/<details> shells but neutralize hover. */
        a {
          color: inherit !important;
          text-decoration: none !important;
        }

        .cw-print-footer {
          page-break-before: avoid;
        }
        .cw-print-seal {
          background: white !important;
        }

        /* Card surfaces shouldn't look hollow against a white sheet. */
        [class*="bg-[color:var(--surface-elevated"],
        [class*="bg-[color:var(--surface-muted"],
        [class*="bg-[color:var(--status-ai-bg"] {
          background: transparent !important;
        }

        /* Hide internal type code labels in the block header. */
        .cw-print-meta-code {
          display: none !important;
        }
      }
    `}</style>
  );
}
