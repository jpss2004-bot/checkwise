"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Clock,
  Printer,
  Sparkle,
  WarningCircle,
} from "@phosphor-icons/react";

import { Canvas } from "@/components/checkwise/reports/canvas";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

  if (error || !report || !content) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-12">
        <Alert variant="warning">
          <AlertTitle className="flex items-center gap-2">
            <WarningCircle className="h-4 w-4" weight="bold" aria-hidden="true" />
            Reporte no disponible
          </AlertTitle>
          <AlertDescription>{error ?? "Cargando…"}</AlertDescription>
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

  const generatedAtLabel = new Date().toLocaleString("es-MX", {
    dateStyle: "long",
    timeStyle: "short",
  });
  const sealLabel = sealedAt
    ? new Date(sealedAt).toLocaleString("es-MX", {
        dateStyle: "long",
        timeStyle: "short",
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
        {/* Cover */}
        <header className="cw-print-cover mb-8 border-b border-[color:var(--border-default)] pb-6">
          <p className="cw-eyebrow text-[color:var(--text-ai)]">
            <Sparkle
              className="-mt-0.5 inline h-3 w-3"
              weight="fill"
              aria-hidden="true"
            />{" "}
            Reporte CheckWise
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
            {report.title}
          </h1>
          {report.description && (
            <p className="mt-2 max-w-prose text-[14px] leading-relaxed text-[color:var(--text-secondary)]">
              {report.description}
            </p>
          )}
          <div className="cw-metadata-strip mt-4">
            <div>
              <span className="cw-eyebrow">Audiencia</span>
              <span className="text-[13px] text-[color:var(--text-primary)]">
                {REPORT_AUDIENCE_LABEL[report.audience]}
              </span>
            </div>
            <div>
              <span className="cw-eyebrow">Estado</span>
              <Badge variant={report.status === "active" ? "success" : "outline"}>
                {REPORT_STATUS_LABEL[report.status]}
              </Badge>
            </div>
            <div>
              <span className="cw-eyebrow">Versión</span>
              <span className="font-mono text-[13px] text-[color:var(--text-primary)]">
                v{report.current_version?.version_number ?? "—"}
              </span>
            </div>
            <div>
              <span className="cw-eyebrow">Generado</span>
              <span className="font-mono text-[11px] text-[color:var(--text-tertiary)]">
                {generatedAtLabel}
              </span>
            </div>
          </div>
          <p className="cw-print-seal mt-3 inline-flex items-center gap-1.5 rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-muted,transparent)] px-2 py-1 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            <Clock className="h-3 w-3" weight="regular" aria-hidden="true" />
            {sealLabel
              ? `Datos al ${sealLabel}`
              : `Generado el ${generatedAtLabel}`}
          </p>
        </header>

        <Canvas
          content={content}
          editable={false}
          onChange={() => {}}
          /* All AI / regenerate / explain hooks omitted — print is read-only. */
        />

        <footer className="cw-print-footer mt-12 border-t border-[color:var(--border-default)] pt-4 text-[10px] text-[color:var(--text-tertiary)]">
          <p>
            CheckWise · {report.title} · v{report.current_version?.version_number}
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
