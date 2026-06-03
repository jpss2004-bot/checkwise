"use client";

import { GridFour } from "@phosphor-icons/react";

import { FreshnessLabel } from "@/components/checkwise/reports/freshness-label";
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
  /** P1.7: ISO8601 stamp from the backend fetcher. */
  fetched_at?: string | null;
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

/**
 * F2 (2026-05-19 visual audit): semantic color token for a metric value.
 * Lets the headline number convey "safe / at-risk / blocked" without
 * forcing the author to pick a color. Conservative defaults: most
 * metrics stay neutral; only compliance %, at-risk counts, and overdue
 * counts trigger colored output. Returns a CSS var name (caller wraps
 * it in `color:var(...)`).
 */
function semanticToneFor(
  metricKey: MetricKey,
  value: number | null,
): string {
  if (value === null) return "var(--text-primary)";
  switch (metricKey) {
    case "completion_pct":
    case "approved_pct":
      if (value >= 80) return "var(--status-success-text)";
      if (value >= 60) return "var(--status-warning-text)";
      return "var(--status-error-text)";
    case "vendors_at_risk":
    case "overdue_count":
      if (value === 0) return "var(--status-success-text)";
      if (value <= 2) return "var(--status-warning-text)";
      return "var(--status-error-text)";
    case "days_to_next_deadline":
      if (value > 14) return "var(--text-primary)";
      if (value > 7) return "var(--status-warning-text)";
      return "var(--status-error-text)";
    default:
      return "var(--text-primary)";
  }
}

export function KpiStripBlock({
  block,
  editable,
}: BlockProps<KpiStripConfig, KpiStripData>) {
  const { metrics } = block.config;
  const resolved = block.data?.resolved ?? [];
  const valueFor = (key: MetricKey): number | null =>
    resolved.find((r) => r.metric_key === key)?.value ?? null;

  return (
    <section
      className="space-y-2 py-2 print:break-inside-avoid"
      data-block-type="kpi_strip"
    >
      <div className="border-t border-b border-[color:var(--border-subtle)] py-3">
        <div className="cw-metadata-strip">
          {/* F2 (2026-05-19 visual audit): first metric gets hero treatment
              (larger type, optional color). Secondaries keep the strip
              row pattern but values pick up a semantic color from the
              metric_key so the eye anchors on what matters.
              Same data, sharper hierarchy. */}
          {metrics.map((m, i) => {
            const value = valueFor(m.metric_key);
            const tone = semanticToneFor(m.metric_key, value);
            const isPrimary = i === 0;
            return (
              <div key={`${m.metric_key}-${m.label}`}>
                <span className="cw-eyebrow">{m.label}</span>
                <span
                  className={
                    isPrimary
                      ? "font-mono text-[22px] font-semibold leading-none tabular-nums"
                      : "font-mono text-[14px] font-semibold tabular-nums"
                  }
                  style={{ color: tone }}
                >
                  {formatValue(value, m.format)}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {editable && (
        <p className="text-[11px] text-[color:var(--text-tertiary)] print:hidden">
          {metrics.length} métrica{metrics.length === 1 ? "" : "s"}.
        </p>
      )}

      <FreshnessLabel fetchedAt={block.data?.fetched_at} />
    </section>
  );
}
