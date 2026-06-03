"use client";

import { ChartBar } from "@phosphor-icons/react";

import { FreshnessLabel } from "@/components/checkwise/reports/freshness-label";
import type { BlockDefinition, BlockProps } from "@/lib/reports/registry";

/**
 * compliance_overview — the deterministic "cover stats" band for the
 * cliente report, modelled on real GRC dashboards (a hero KPI row + a
 * per-provider bar). Every number here is computed server-side from the
 * live expediente and rendered as-is, so the block carries NO AI text
 * and nothing can be hallucinated: the figures ARE the report.
 *
 * Two parts:
 *   1. Hero KPI band — cumplimiento global, proveedores (with semáforo
 *      breakdown), documentos críticos (with a one-line breakdown), and
 *      en revisión.
 *   2. "Cumplimiento por proveedor" — a worst-first horizontal bar
 *      (length = compliance %, colored by semáforo) so the reader sees
 *      at a glance who needs attention. The dense matrix stays below as
 *      the drill-down.
 *
 * Hand-rolled SVG/CSS (no chart library), matching the radar's
 * approach. Vendor names are masked by the backend for vendor_facing /
 * external audiences; we render "Proveedor reservado" for the null case.
 */

type SemaphoreLevel = "green" | "yellow" | "red";

interface ComplianceOverviewConfig {
  top_n_vendors?: number;
}

interface OverviewVendor {
  vendor_id: string;
  vendor_name: string | null;
  vendor_rfc: string | null;
  semaphore_level: SemaphoreLevel;
  compliance_pct: number;
  missing_required_count: number;
  pending_reviews_count: number;
}

interface ComplianceOverviewData {
  client_name?: string;
  overall_compliance_pct?: number;
  vendors_total?: number;
  vendors_semaphore?: { green: number; yellow: number; red: number };
  docs_critical?: number;
  docs_critical_breakdown?: {
    rechazados: number;
    vencidos: number;
    inconsistencias: number;
    aclaracion: number;
  };
  docs_in_review?: number;
  by_vendor?: OverviewVendor[];
  fetched_at?: string | null;
}

export const complianceOverviewDefinition: Omit<
  BlockDefinition<ComplianceOverviewConfig, ComplianceOverviewData>,
  "Component"
> = {
  type: "compliance_overview",
  label: "Cifras clave del portafolio",
  icon: ChartBar,
  description:
    "Banda de KPIs (cumplimiento, proveedores, críticos, en revisión) + barra de cumplimiento por proveedor. Solo datos, sin IA.",
  defaultConfig: { top_n_vendors: 12 },
};

// Solid fills for bars / dots — same semaphore mapping the radar uses.
const SEMAPHORE_FILL: Record<SemaphoreLevel, string> = {
  green: "var(--status-success-text)",
  yellow: "var(--status-warning-text)",
  red: "var(--status-error-text)",
};

function pct(n: number | undefined): number {
  if (n === undefined || n === null || Number.isNaN(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n)));
}

export function ComplianceOverviewBlock({
  block,
}: BlockProps<ComplianceOverviewConfig, ComplianceOverviewData>) {
  const data = block.data;
  const vendors = data?.by_vendor ?? [];
  const sem = data?.vendors_semaphore ?? { green: 0, yellow: 0, red: 0 };
  const crit = data?.docs_critical_breakdown;

  if (!data) {
    return (
      <section className="space-y-2 py-2" data-block-type="compliance_overview">
        <div className="border-y border-[color:var(--border-subtle)] py-6 text-center text-[13px] text-[color:var(--text-tertiary)]">
          Las cifras se generan cuando el reporte se ejecuta sobre el portafolio.
        </div>
      </section>
    );
  }

  const criticalParts: string[] = [];
  if (crit) {
    if (crit.rechazados) criticalParts.push(`${crit.rechazados} rechazados`);
    if (crit.vencidos) criticalParts.push(`${crit.vencidos} vencidos`);
    if (crit.inconsistencias)
      criticalParts.push(`${crit.inconsistencias} con inconsistencia`);
    if (crit.aclaracion) criticalParts.push(`${crit.aclaracion} en aclaración`);
  }
  const docsCritical = data.docs_critical ?? 0;

  return (
    <section
      className="space-y-6 py-2 print:break-inside-avoid"
      data-block-type="compliance_overview"
    >
      {/* ─── Hero KPI band ─────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-6 border-y border-[color:var(--border-default)] py-5 sm:grid-cols-4">
        {/* Cumplimiento global */}
        <Kpi label="Cumplimiento global">
          <span className="font-mono text-[28px] font-semibold leading-none tabular-nums text-[color:var(--text-primary)]">
            {pct(data.overall_compliance_pct)}
            <span className="text-[16px] text-[color:var(--text-tertiary)]">%</span>
          </span>
          <Track className="mt-2">
            <span
              className="block h-full rounded-full"
              style={{
                width: `${pct(data.overall_compliance_pct)}%`,
                backgroundColor: "var(--text-brand)",
              }}
            />
          </Track>
        </Kpi>

        {/* Proveedores + semáforo */}
        <Kpi label="Proveedores">
          <span className="font-mono text-[28px] font-semibold leading-none tabular-nums text-[color:var(--text-primary)]">
            {data.vendors_total ?? 0}
          </span>
          <SemaphoreBar green={sem.green} yellow={sem.yellow} red={sem.red} />
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-[color:var(--text-secondary)]">
            <Legend level="green" label={`${sem.green} al día`} />
            <Legend level="yellow" label={`${sem.yellow} en proceso`} />
            <Legend level="red" label={`${sem.red} en riesgo`} />
          </div>
        </Kpi>

        {/* Documentos críticos */}
        <Kpi label="Documentos críticos">
          <span
            className="font-mono text-[28px] font-semibold leading-none tabular-nums"
            style={{
              color: docsCritical > 0 ? "var(--status-error-text)" : "var(--text-primary)",
            }}
          >
            {docsCritical}
          </span>
          <p className="mt-2 text-[11px] leading-snug text-[color:var(--text-tertiary)]">
            {criticalParts.length > 0
              ? criticalParts.join(" · ")
              : "Sin documentos críticos."}
          </p>
        </Kpi>

        {/* En revisión */}
        <Kpi label="En revisión">
          <span className="font-mono text-[28px] font-semibold leading-none tabular-nums text-[color:var(--text-primary)]">
            {data.docs_in_review ?? 0}
          </span>
          <p className="mt-2 text-[11px] leading-snug text-[color:var(--text-tertiary)]">
            documentos esperando dictamen.
          </p>
        </Kpi>
      </div>

      {/* ─── Cumplimiento por proveedor ────────────────────────── */}
      {vendors.length > 0 ? (
        <div className="space-y-2.5">
          <p className="cw-eyebrow">Cumplimiento por proveedor</p>
          <ul className="space-y-2">
            {vendors.map((v) => (
              <li key={v.vendor_id} className="flex items-center gap-3">
                <div className="w-[34%] min-w-0 shrink-0">
                  <p
                    className={`truncate text-[13px] font-medium ${
                      v.vendor_name
                        ? "text-[color:var(--text-primary)]"
                        : "italic text-[color:var(--text-tertiary)]"
                    }`}
                    title={v.vendor_name ?? undefined}
                  >
                    {v.vendor_name || "Proveedor reservado"}
                  </p>
                  <p className="truncate text-[10px] text-[color:var(--text-tertiary)]">
                    {annotate(v)}
                  </p>
                </div>
                <div className="flex flex-1 items-center gap-2">
                  <Track className="flex-1">
                    <span
                      className="block h-full rounded-full"
                      style={{
                        width: `${pct(v.compliance_pct)}%`,
                        backgroundColor: SEMAPHORE_FILL[v.semaphore_level],
                      }}
                    />
                  </Track>
                  <span className="w-9 shrink-0 text-right font-mono text-[12px] font-semibold tabular-nums text-[color:var(--text-secondary)]">
                    {pct(v.compliance_pct)}%
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <FreshnessLabel fetchedAt={data.fetched_at} />
    </section>
  );
}

// ─── Small presentational helpers ─────────────────────────────────

function Kpi({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="cw-eyebrow mb-1.5">{label}</p>
      {children}
    </div>
  );
}

function Track({
  children,
  className = "",
}: {
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`block h-2 overflow-hidden rounded-full bg-[color:var(--surface-hover)] ${className}`}
    >
      {children}
    </span>
  );
}

function SemaphoreBar({
  green,
  yellow,
  red,
}: {
  green: number;
  yellow: number;
  red: number;
}) {
  const total = green + yellow + red;
  if (total === 0) {
    return <Track className="mt-2" />;
  }
  const seg = (n: number, level: SemaphoreLevel) =>
    n > 0 ? (
      <span
        className="block h-full"
        style={{ width: `${(n / total) * 100}%`, backgroundColor: SEMAPHORE_FILL[level] }}
      />
    ) : null;
  return (
    <span className="mt-2 flex h-2 overflow-hidden rounded-full bg-[color:var(--surface-hover)]">
      {seg(green, "green")}
      {seg(yellow, "yellow")}
      {seg(red, "red")}
    </span>
  );
}

function Legend({ level, label }: { level: SemaphoreLevel; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span
        className="inline-block h-2 w-2 rounded-full"
        style={{ backgroundColor: SEMAPHORE_FILL[level] }}
        aria-hidden="true"
      />
      {label}
    </span>
  );
}

function annotate(v: OverviewVendor): string {
  const parts: string[] = [];
  if (v.missing_required_count > 0) parts.push(`faltan ${v.missing_required_count}`);
  if (v.pending_reviews_count > 0) parts.push(`en revisión ${v.pending_reviews_count}`);
  return parts.length > 0 ? parts.join(" · ") : "al día";
}
