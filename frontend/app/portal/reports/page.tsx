"use client";

import Link from "next/link";
import {
  ArrowRight,
  CalendarBlank,
  ChartLineUp,
  DownloadSimple,
  Files,
  Lightbulb,
  PaperPlaneTilt,
  ShieldCheck,
  Warning,
  WarningCircle,
  type Icon,
} from "@phosphor-icons/react";

import { DocStateBadge } from "@/components/checkwise/doc-state-badge";
import { ProviderContextBar } from "@/components/checkwise/portal/provider-context-bar";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  MOCK_REPORTS,
  REPORT_STATUS_LABEL,
  REPORT_STATUS_VARIANT,
  REPORT_TYPE_BLURB,
  REPORT_TYPE_LABEL,
  type ReportMeta,
  type ReportType,
} from "@/lib/mock/reports";
import { withPortalSession } from "@/lib/session/with-portal-session";
import type { PortalSession } from "@/lib/session/portal";

const TYPE_ICON: Record<ReportType, Icon> = {
  monthly_compliance: ChartLineUp,
  provider_expediente: ShieldCheck,
  missing_documents: WarningCircle,
  risk_action: Warning,
};

/**
 * Reports scaffold.
 *
 * This is the V1.5 scaffold of CheckWise's reporting surface. The
 * generation pipeline lives behind backend integration TODOs in
 * lib/mock/reports.ts — today the page renders four representative
 * report types with realistic metadata so demos, screenshots, and
 * sales conversations have something to point at.
 *
 * Reports are a CheckWise differentiator: not just exports, but
 * summaries of risk, faltantes, deadlines, responsable parties, and
 * next actions. The tile + drawer pattern here is sized to grow into
 * a real report list with filters + per-report deep dives.
 */
function ReportsInner({ session }: { session: PortalSession }) {
  return (
    <>
      <ProviderContextBar session={session} />
      <main className="mx-auto max-w-7xl space-y-8 px-5 py-8">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div className="space-y-1">
            <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-teal)]">
              Reportes
            </p>
            <h1 className="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">
              Reportes ejecutivos de CheckWise
            </h1>
            <p className="max-w-prose text-[13px] text-[color:var(--text-secondary)]">
              Resúmenes de cumplimiento, faltantes, riesgo y expediente — listos
              para enviar al cliente. Esta vista es la primera versión del
              motor; las acciones avanzadas se habilitan en V1.6.
            </p>
          </div>
          <Button variant="outline" size="sm" disabled>
            <ChartLineUp className="h-4 w-4" weight="bold" aria-hidden="true" />
            <span>Generar reporte personalizado</span>
          </Button>
        </header>

        <Alert variant="info">
          <AlertTitle className="flex items-center gap-2">
            <Lightbulb className="h-4 w-4" weight="bold" aria-hidden="true" />
            Los reportes son un diferenciador clave
          </AlertTitle>
          <AlertDescription>
            No son simples exportaciones: resumen riesgo, faltantes, deadlines
            y responsables, y se conectan con el calendario REPSE y la revisión
            humana. Esta es la base. La generación automática, programación y
            envío a cliente entran como capa siguiente.
          </AlertDescription>
        </Alert>

        <section aria-label="Listado de reportes" className="grid gap-5 lg:grid-cols-2">
          {MOCK_REPORTS.map((report) => (
            <ReportCard key={report.id} report={report} />
          ))}
        </section>

        <ReportsFutureRoadmap />
      </main>
    </>
  );
}

export default withPortalSession(ReportsInner);

// ─── Report card ────────────────────────────────────────────────

function ReportCard({ report }: { report: ReportMeta }) {
  const IconComponent = TYPE_ICON[report.type];
  const isReady = report.status === "ready";

  return (
    <article
      className="cw-hover-lift flex flex-col gap-4 rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs"
      aria-labelledby={`report-${report.id}-title`}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <span
            className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)]"
            aria-hidden="true"
          >
            <IconComponent
              className="h-5 w-5 text-[color:var(--text-brand)]"
              weight="duotone"
            />
          </span>
          <div className="min-w-0">
            <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              {REPORT_TYPE_LABEL[report.type]}
            </p>
            <h3
              id={`report-${report.id}-title`}
              className="mt-1 text-[15px] font-semibold leading-5 text-[color:var(--text-primary)]"
            >
              {report.title}
            </h3>
            <p className="mt-1 text-[12px] leading-5 text-[color:var(--text-secondary)]">
              {report.blurb || REPORT_TYPE_BLURB[report.type]}
            </p>
          </div>
        </div>
        <Badge variant={REPORT_STATUS_VARIANT[report.status]}>
          {REPORT_STATUS_LABEL[report.status]}
        </Badge>
      </header>

      <dl className="grid gap-3 sm:grid-cols-3">
        <Meta label="Periodo" value={report.period} mono />
        <Meta label="Alcance" value={report.scope} />
        <Meta
          label="Generado"
          value={
            report.generated_at_iso ? formatDate(report.generated_at_iso) : "—"
          }
          mono
        />
      </dl>

      {(report.compliance_pct !== null ||
        report.document_coverage_pct !== null) && (
        <div className="grid gap-3 sm:grid-cols-2">
          {report.compliance_pct !== null && (
            <Progress
              value={report.compliance_pct}
              label="Cumplimiento"
              showValue
              tone={report.compliance_pct >= 80 ? "success" : report.compliance_pct >= 60 ? "warning" : "error"}
            />
          )}
          {report.document_coverage_pct !== null && (
            <Progress
              value={report.document_coverage_pct}
              label="Cobertura documental"
              showValue
              tone="brand"
            />
          )}
        </div>
      )}

      {report.highlights.length > 0 && (
        <ul className="space-y-1.5 border-t border-[color:var(--border-subtle)] pt-3">
          {report.highlights.map((h, idx) => (
            <li key={idx} className="flex items-center justify-between gap-2">
              <span className="truncate text-xs text-[color:var(--text-primary)]">
                {h.label}
              </span>
              <DocStateBadge state={h.state} withIcon={false} />
            </li>
          ))}
        </ul>
      )}

      <footer className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--border-subtle)] pt-3">
        <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
          {report.pending_actions > 0
            ? `${report.pending_actions} acciones pendientes`
            : "Sin acciones pendientes"}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={!isReady}
            title={isReady ? undefined : "El reporte aún se está generando."}
          >
            <Files className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            <span>Ver reporte</span>
          </Button>
          <Button size="sm" disabled={!isReady}>
            <DownloadSimple className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            <span>Descargar PDF</span>
          </Button>
        </div>
      </footer>

      {isReady && (
        <p className="text-xs text-[color:var(--text-tertiary)]">
          <button
            type="button"
            disabled
            className="inline-flex items-center gap-1.5 text-[color:var(--text-link)] disabled:cursor-not-allowed disabled:opacity-60"
            title="Se habilita cuando se conecte el envío automático (V1.6)."
          >
            <PaperPlaneTilt className="h-3 w-3" weight="bold" aria-hidden="true" />
            Enviar a cliente
          </button>{" "}
          · disponible en V1.6 cuando se conecte el envío automático.
        </p>
      )}
    </article>
  );
}

function Meta({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {label}
      </dt>
      <dd
        className={
          "truncate text-[13px] text-[color:var(--text-primary)] " +
          (mono ? "font-mono" : "")
        }
      >
        {value}
      </dd>
    </div>
  );
}

function ReportsFutureRoadmap() {
  return (
    <section className="rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] p-5">
      <header className="mb-3 flex items-center gap-2">
        <CalendarBlank
          className="h-4 w-4 text-[color:var(--text-teal)]"
          weight="duotone"
          aria-hidden="true"
        />
        <h2 className="text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
          Próximas funcionalidades
        </h2>
      </header>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          {
            title: "Generación automática",
            body: "Reportes mensuales programados con cierre del periodo + envío al cliente.",
          },
          {
            title: "Plantillas personalizables",
            body: "Por cliente: branding, métricas elegidas, observaciones legales.",
          },
          {
            title: "Comparativos históricos",
            body: "Cumplimiento mes vs. mes, tendencias por proveedor y por institución.",
          },
          {
            title: "Acciones embebidas",
            body: "Que cada faltante / riesgo abra la acción correspondiente en el portal.",
          },
        ].map((item) => (
          <li
            key={item.title}
            className="rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-3"
          >
            <p className="text-[13px] font-semibold text-[color:var(--text-primary)]">
              {item.title}
            </p>
            <p className="mt-1 text-xs leading-5 text-[color:var(--text-secondary)]">
              {item.body}
            </p>
          </li>
        ))}
      </ul>
      <p className="mt-4 flex items-center gap-2 text-xs text-[color:var(--text-tertiary)]">
        <Link
          href="/portal/dashboard"
          className="inline-flex items-center gap-1 text-[color:var(--text-link)] hover:underline"
        >
          <span>Volver al dashboard</span>
          <ArrowRight className="h-3 w-3" weight="bold" aria-hidden="true" />
        </Link>
      </p>
    </section>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("es-MX", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}
