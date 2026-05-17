"use client";

import { GridFour } from "@phosphor-icons/react";

import type { BlockDefinition, BlockProps } from "@/lib/reports/registry";

/**
 * KPI strip block — the metadata-strip pattern from V2.x, in block
 * form. Four to six metrics rendered as a horizontal label/value row
 * with mono values. Replaces the equal-card-grid anti-pattern.
 *
 * Phase 3.2 ships with placeholder values; Phase 3.3 wires the
 * server-side data_fetcher that resolves metric_key → live value.
 */

type MetricKey =
  | "completion_pct"
  | "vendors_total"
  | "vendors_at_risk"
  | "submissions_period"
  | "overdue_count"
  | "in_review_count"
  | "approved_pct"
  | "avg_review_hours"
  | "days_to_next_deadline";

type MetricFormat = "percent" | "number" | "duration_days" | "duration_hours";

interface KpiMetric {
  label: string;
  metric_key: MetricKey;
  format: MetricFormat;
}

interface KpiStripConfig {
  metrics: KpiMetric[];
  period?: string;
}

interface KpiStripData {
  resolved: Array<{
    metric_key: MetricKey;
    value: number | null;
    trend_pct_vs_prior: number | null;
  }>;
}

const METRIC_LABEL: Record<MetricKey, string> = {
  completion_pct: "Cumplimiento",
  vendors_total: "Proveedores",
  vendors_at_risk: "En riesgo",
  submissions_period: "Envíos",
  overdue_count: "Vencidos",
  in_review_count: "En revisión",
  approved_pct: "Aprobados",
  avg_review_hours: "Revisión prom.",
  days_to_next_deadline: "Próximo en",
};

export const kpiStripDefinition: Omit<
  BlockDefinition<KpiStripConfig, KpiStripData>,
  "Component"
> = {
  type: "kpi_strip",
  label: "Tira de KPIs",
  icon: GridFour,
  description: "Cuatro a seis métricas en una línea con valores en mono.",
  defaultConfig: {
    metrics: [
      { label: METRIC_LABEL.completion_pct, metric_key: "completion_pct", format: "percent" },
      { label: METRIC_LABEL.vendors_at_risk, metric_key: "vendors_at_risk", format: "number" },
      { label: METRIC_LABEL.in_review_count, metric_key: "in_review_count", format: "number" },
      { label: METRIC_LABEL.days_to_next_deadline, metric_key: "days_to_next_deadline", format: "duration_days" },
    ],
  },
};

function formatValue(
  value: number | null | undefined,
  format: MetricFormat,
): string {
  if (value === null || value === undefined) return "—";
  switch (format) {
    case "percent":
      return `${Math.round(value)}%`;
    case "number":
      return value.toLocaleString("es-MX");
    case "duration_days":
      return `${Math.round(value)}d`;
    case "duration_hours":
      return `${Math.round(value)}h`;
  }
}

export function KpiStripBlock({
  block,
  editable,
  onPatch,
}: BlockProps<KpiStripConfig, KpiStripData>) {
  const { metrics } = block.config;
  const resolved = block.data?.resolved ?? [];
  const valueFor = (key: MetricKey): number | null =>
    resolved.find((r) => r.metric_key === key)?.value ?? null;

  return (
    <section className="space-y-2 py-2">
      <div className="border-t border-b border-[color:var(--border-subtle)] py-3">
        <div className="cw-metadata-strip">
          {metrics.map((m) => {
            const value = valueFor(m.metric_key);
            return (
              <div key={`${m.metric_key}-${m.label}`}>
                <span className="cw-eyebrow">{m.label}</span>
                <span className="font-mono text-[14px] font-semibold tabular-nums text-[color:var(--text-primary)]">
                  {formatValue(value, m.format)}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {editable && (
        <div className="flex items-center justify-between text-[11px] text-[color:var(--text-tertiary)]">
          <span>
            {metrics.length} métrica{metrics.length === 1 ? "" : "s"}. Configurable
            desde el inspector.
          </span>
          <button
            type="button"
            onClick={() => {
              // Light hand-edit: cycle the first metric's format as a
              // quick demonstration the block is wired. Real config
              // editing happens in the right-rail Inspector in 3.5.
              if (metrics.length === 0) return;
              const cycle: Record<MetricFormat, MetricFormat> = {
                percent: "number",
                number: "duration_days",
                duration_days: "duration_hours",
                duration_hours: "percent",
              };
              const next: KpiMetric[] = [...metrics];
              next[0] = { ...next[0], format: cycle[next[0].format] };
              onPatch({ config: { ...block.config, metrics: next } });
            }}
            className="rounded-sm border border-[color:var(--border-subtle)] px-2 py-0.5 text-[color:var(--text-tertiary)] hover:bg-[color:var(--surface-hover)]"
          >
            Cambiar formato
          </button>
        </div>
      )}
    </section>
  );
}
