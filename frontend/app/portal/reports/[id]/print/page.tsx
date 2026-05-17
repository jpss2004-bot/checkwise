"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Printer, Sparkle, WarningCircle } from "@phosphor-icons/react";

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
  type ReportContent,
  type ReportRead,
} from "@/lib/api/reports";

/**
 * Print mode — executive-grade PDF via browser print.
 *
 * Phase 3.3c ships this as the "multi-format output" v1: open in a
 * new tab, hit Cmd+P (or click Imprimir), get a paginated PDF
 * without any server-side renderer.
 *
 * Server-rendered PDF / DOCX defer to the production-polish track —
 * print mode is enough for the executive-share use case the brief
 * named.
 */

export default function PrintPage() {
  const params = useParams();
  const reportId = typeof params?.id === "string" ? params.id : "";

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

  return (
    <>
      <PrintStyles />
      {/* Print-only screen toolbar: hidden on @media print. */}
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
          title="Imprimir / Guardar como PDF"
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
                {new Date().toLocaleString("es-MX", {
                  dateStyle: "long",
                  timeStyle: "short",
                })}
              </span>
            </div>
          </div>
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
 * Print-specific CSS. Pulls the toolbar out of the printed output,
 * tightens margins, forces section breaks between top-level blocks
 * so big tables don't split mid-row.
 */
function PrintStyles() {
  return (
    <style jsx global>{`
      @media print {
        @page {
          size: Letter;
          margin: 0.75in;
        }
        .cw-print-toolbar {
          display: none !important;
        }
        body {
          background: white !important;
        }
        .cw-print-document {
          max-width: none;
          padding: 0;
        }
        .cw-print-cover {
          page-break-after: avoid;
        }
        article[data-block-id] {
          page-break-inside: avoid;
        }
        .cw-print-footer {
          page-break-before: avoid;
        }
        /* Drop hover / interactive chrome we don't want on paper. */
        button {
          display: none !important;
        }
      }
    `}</style>
  );
}
