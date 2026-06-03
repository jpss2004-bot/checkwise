"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle,
  DownloadSimple,
  Pencil,
  Printer,
} from "@phosphor-icons/react";

import { Canvas } from "@/components/checkwise/reports/canvas";
import { ReportMasthead } from "@/components/checkwise/reports/report-masthead";
import { ExportButton } from "@/components/checkwise/reports/editor/export-button";
import { ShareDialog } from "@/components/checkwise/reports/editor/share-dialog";
import { Button } from "@/components/ui/button";
import {
  REPORT_AUDIENCE_LABEL,
  REPORT_STATUS_LABEL,
  type ReportAudience,
} from "@/lib/reports/constants";
import type {
  ReportBlock,
  ReportContent,
  ReportRead,
} from "@/lib/api/reports";

/**
 * StoryView — R7 auditor mode.
 *
 * The same content the editor renders, framed as a deliverable rather
 * than an authoring surface. Used when the route carries
 * ``?mode=audit``. Three responsibilities:
 *
 * 1. **Strip every author-facing affordance.** No AI generation
 *    panel, no copilot, no Save button, no toolbar dirty-state, no
 *    block headers (the Canvas already hides them when
 *    ``editable=false`` — same path the print route takes).
 *
 * 2. **Wrap the blocks in narrative scaffolding** that an executive
 *    or external auditor can read top-to-bottom: hero with title +
 *    audience + version + data-as-of, an opening framing paragraph,
 *    the data blocks, and a closing CTA section that promotes the
 *    deliverable artefacts (Descargar PDF + Compartir + Imprimir).
 *
 * 3. **Keep the back-button safe.** The mode is a query param on the
 *    existing editor route, so bookmarking, sharing, and the browser
 *    back-button all work without route-level state.
 *
 * The component is deliberately presentational — it takes a fully
 * loaded report + content from ReportEditor (which owns the fetch
 * lifecycle) and never re-fetches. The only state it owns is the
 * "Volver al editor" callback the parent wires to a router.push.
 */
export interface StoryViewProps {
  report: ReportRead;
  content: ReportContent;
  reportId: string;
  /** Route to the printable PDF surface (existing /portal/reports/{id}/print). */
  printHref: string;
  /** Route the back link points to when the auditor closes the report. */
  backHref: string;
  /** Pushes the URL back to the editor (drops the ?mode=audit flag). */
  onExitToEditor: () => void;
}

export function StoryView({
  report,
  content,
  reportId,
  printHref,
  backHref,
  onExitToEditor,
}: StoryViewProps) {
  // The "Datos al…" seal: first ``data.fetched_at`` we find on the
  // canvas. Same heuristic the print route uses (firstFreshness in
  // app/portal/reports/[id]/print/page.tsx) so the screen story view
  // and the printed PDF cite the same data timestamp.
  const sealedAt = useMemo(
    () => firstFreshness(content.blocks ?? []),
    [content.blocks],
  );
  const audience = report.audience as ReportAudience;
  const audienceFraming = FRAMING_BY_AUDIENCE[audience] ?? FRAMING_BY_AUDIENCE.internal_only;
  const versionLabel = report.current_version
    ? `v${report.current_version.version_number}`
    : "—";
  const updatedAtLabel = report.updated_at
    ? new Date(report.updated_at).toLocaleString("es-MX", {
        dateStyle: "long",
        timeStyle: "short",
      })
    : null;
  const sealedAtLabel = sealedAt
    ? new Date(sealedAt).toLocaleString("es-MX", {
        dateStyle: "long",
        timeStyle: "short",
      })
    : null;

  return (
    <div className="mx-auto max-w-3xl space-y-10 px-5 py-8">
      {/* ─── Top utility row — screen-only, never printed ─── */}
      <div className="flex flex-wrap items-center justify-between gap-2 print:hidden">
        <Button asChild variant="ghost" size="sm">
          <Link href={backHref}>
            <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
            Volver a reportes
          </Link>
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onExitToEditor}
          title="Cambiar a la vista editable"
        >
          <Pencil className="h-4 w-4" weight="bold" aria-hidden="true" />
          Editar este reporte
        </Button>
      </div>

      {/* ─── Masthead — bold, branded document cover ──────── */}
      <ReportMasthead
        title={report.title}
        description={report.description}
        meta={[
          { label: "Audiencia", value: REPORT_AUDIENCE_LABEL[audience] },
          { label: "Estado", value: REPORT_STATUS_LABEL[report.status] },
          { label: "Versión", value: versionLabel },
          { label: "Última edición", value: updatedAtLabel },
          {
            label: "Datos al",
            value:
              sealedAtLabel && sealedAtLabel !== updatedAtLabel
                ? sealedAtLabel
                : null,
          },
        ]}
      />

      {/* ─── Opening framing paragraph ─────────────────── */}
      <section className="cw-fade-up space-y-2">
        <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">
          Por qué este reporte
        </p>
        <p className="max-w-prose text-[14px] leading-relaxed text-[color:var(--text-primary)]">
          {audienceFraming.opening}
        </p>
      </section>

      {/* ─── Body — the same blocks, no edit chrome ───────── */}
      <section className="cw-fade-up space-y-2">
        <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-[color:var(--text-tertiary)]">
          Qué encontramos
        </p>
        <Canvas content={content} editable={false} onChange={() => {}} />
      </section>

      {/* ─── Closing CTA — make the deliverable obvious ───── */}
      <section className="cw-fade-up space-y-3 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 print:hidden">
        <div className="flex items-center gap-2 text-[color:var(--text-ai)]">
          <CheckCircle className="h-4 w-4" weight="fill" aria-hidden="true" />
          <span className="text-[11px] font-medium uppercase tracking-[0.08em]">
            Listo para entregar
          </span>
        </div>
        <h2 className="text-[18px] font-semibold tracking-tight text-[color:var(--text-primary)]">
          {audienceFraming.closingHeading}
        </h2>
        <p className="max-w-prose text-[13px] leading-relaxed text-[color:var(--text-secondary)]">
          {audienceFraming.closingBody}
        </p>
        <div className="flex flex-wrap items-center gap-2 pt-2">
          <Button asChild variant="default" size="sm">
            <Link
              href={`${printHref}?autoprint=1`}
              target="_blank"
              rel="noopener noreferrer"
            >
              <DownloadSimple
                className="h-4 w-4"
                weight="bold"
                aria-hidden="true"
              />
              Descargar PDF
            </Link>
          </Button>
          <ShareDialog reportId={reportId} variant="outline" />
          <ExportButton reportId={reportId} format="xlsx" />
          <Button asChild variant="ghost" size="sm">
            <Link href={printHref} target="_blank" rel="noopener noreferrer">
              <Printer className="h-4 w-4" weight="bold" aria-hidden="true" />
              Imprimir
            </Link>
          </Button>
        </div>
      </section>

      <footer className="border-t border-[color:var(--border-subtle)] pt-4 text-[10px] text-[color:var(--text-tertiary)] print:hidden">
        <p>
          CheckWise · Plataforma de cumplimiento REPSE · Las secciones marcadas
          con el ícono de IA fueron generadas automáticamente y deben
          verificarse antes de su distribución.
        </p>
      </footer>
    </div>
  );
}

// ─── Audience-aware framing copy ─────────────────────────────────
//
// The opening + closing paragraphs are static today — they depend on
// audience but not on the report's data, so we don't need an LLM call
// to produce them. If we later want them to vary per-report
// (mentioning the headline metric, the period, the highest-risk
// vendor) the cleanest move is to derive them from
// ``content.global.story_intro`` / ``story_outro`` strings that the
// planner can populate.

type FramingCopy = {
  opening: string;
  closingHeading: string;
  closingBody: string;
};

const FRAMING_BY_AUDIENCE: Record<ReportAudience, FramingCopy> = {
  internal_only: {
    opening:
      "Este reporte concentra el estado de cumplimiento REPSE del periodo. " +
      "Las cifras vienen del expediente vivo: cualquier documento cargado, " +
      "rechazado o vencido se refleja aquí en cuanto pasa por el ciclo de " +
      "revisión. Úsalo como tablero interno; las observaciones marcadas son " +
      "lo único que requiere acción.",
    closingHeading: "Descarga lo que necesites para archivar o presentar",
    closingBody:
      "Genera un PDF para el archivo del periodo o comparte un enlace " +
      "temporal con dirección. Todo se entrega con la versión y el sello " +
      "de fecha del reporte tal cual se ve aquí.",
  },
  client_facing: {
    opening:
      "Este reporte muestra el estado de cumplimiento de las obligaciones " +
      "REPSE de tus proveedores en el periodo. Las cifras provienen del " +
      "expediente vigente; cualquier observación marcada es una acción " +
      "pendiente que ya está siendo gestionada por nuestro equipo.",
    closingHeading: "Comparte este reporte con quien corresponda",
    closingBody:
      "Descarga el PDF para tu auditor o genera un enlace temporal " +
      "con vigencia limitada. El reporte se entrega con la versión y el " +
      "sello de datos visibles en el encabezado.",
  },
  vendor_facing: {
    opening:
      "Este reporte resume tu cumplimiento REPSE al cierre del periodo. " +
      "Las observaciones marcadas son lo único que requiere tu acción; " +
      "todo lo demás ya está al día o en revisión interna. Si tienes " +
      "dudas, contacta a tu coordinador.",
    closingHeading: "Guarda una copia o compártela con tu equipo",
    closingBody:
      "Puedes descargar el PDF firmado del periodo o enviar un enlace " +
      "interno a tu área administrativa. Las acciones pendientes se " +
      "actualizan en automático cuando subes la versión corregida.",
  },
  external_signed: {
    opening:
      "Reporte firmado de cumplimiento REPSE para la entidad consultora. " +
      "Las cifras corresponden al periodo señalado en el encabezado y " +
      "están firmadas por la versión y el sello de datos visibles arriba. " +
      "Cualquier diferencia con el expediente posterior debe contrastarse " +
      "contra esa versión.",
    closingHeading: "Documentación firmada del periodo",
    closingBody:
      "Descarga el PDF firmado o comparte el enlace de validación. " +
      "Este reporte mantiene su validez hasta el cierre del siguiente " +
      "periodo o hasta que la entidad emita una versión actualizada.",
  },
};

function firstFreshness(blocks: ReportBlock[]): string | null {
  for (const b of blocks) {
    const data = (b as { data?: { fetched_at?: string | null } }).data;
    if (data?.fetched_at) return data.fetched_at;
  }
  return null;
}
