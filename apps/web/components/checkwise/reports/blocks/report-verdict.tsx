"use client";

import { Gauge, TrendDown, TrendUp } from "@phosphor-icons/react";

import type { BlockDefinition, BlockProps } from "@/lib/reports/registry";

/**
 * Report verdict — the synthesized "so what" that opens an insight-first
 * report. A semáforo-coloured hero: level chip + headline + subhead + the one
 * metric that matters. Data comes from the deterministic insight engine
 * (services/reports/insights.py) via the report_verdict fetcher.
 */

type Level = "green" | "yellow" | "red";

interface VerdictData {
  verdict?: {
    level: Level;
    headline: string;
    subhead: string;
    metric: { value: number; label: string; format: string };
    /** Month-over-month approval-rate change in points; null = no signal. */
    trend?: number | null;
  };
}

export const reportVerdictDefinition: Omit<
  BlockDefinition<Record<string, never>, VerdictData>,
  "Component"
> = {
  type: "report_verdict",
  label: "Veredicto",
  icon: Gauge,
  description: "Síntesis del estado: semáforo, titular y métrica clave.",
  defaultConfig: {},
};

const LEVEL: Record<Level, { bar: string; chip: string; print: string }> = {
  red: { bar: "var(--state-red,#dc2626)", chip: "Riesgo", print: "[Rojo]" },
  yellow: { bar: "var(--state-yellow,#d97706)", chip: "Atención", print: "[Amarillo]" },
  green: { bar: "var(--state-green,#16a34a)", chip: "En regla", print: "[Verde]" },
};

export function ReportVerdictBlock({
  block,
}: BlockProps<Record<string, never>, VerdictData>) {
  const v = block.data?.verdict;
  if (!v) return null;
  const c = LEVEL[v.level] ?? LEVEL.yellow;
  const metricText =
    v.metric.format === "percent" ? `${v.metric.value}%` : `${v.metric.value}`;

  return (
    <div className="relative overflow-hidden rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-[var(--shadow-sm)]">
      <div
        className="absolute inset-y-0 left-0 w-1.5"
        style={{ background: c.bar }}
        aria-hidden="true"
      />
      <div className="flex flex-wrap items-center justify-between gap-4 py-5 pl-6 pr-5">
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2">
            <span
              className="inline-block h-3 w-3 rounded-full print:hidden"
              style={{ background: c.bar }}
              aria-hidden="true"
            />
            <span className="hidden font-mono text-[11px] print:inline">
              {c.print}
            </span>
            <span
              className="text-[11px] font-semibold uppercase tracking-[0.1em]"
              style={{ color: c.bar }}
            >
              {c.chip}
            </span>
          </div>
          <h2 className="text-[20px] font-semibold leading-tight tracking-tight text-[color:var(--text-primary)]">
            {v.headline}
          </h2>
          <p className="text-[13px] leading-snug text-[color:var(--text-secondary)]">
            {v.subhead}
          </p>
        </div>
        <div className="text-right">
          <div className="font-mono text-[34px] font-semibold leading-none tabular-nums text-[color:var(--text-primary)]">
            {metricText}
          </div>
          <div className="mt-1 text-[10px] uppercase tracking-[0.1em] text-[color:var(--text-tertiary)]">
            {v.metric.label}
          </div>
          {typeof v.trend === "number" && v.trend !== 0 ? (
            <div
              className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-semibold"
              style={{
                color:
                  v.trend > 0
                    ? "var(--state-green,#16a34a)"
                    : "var(--state-red,#dc2626)",
              }}
              title="Cambio en la tasa de aprobación mensual respecto al mes anterior"
            >
              {v.trend > 0 ? (
                <TrendUp className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
              ) : (
                <TrendDown className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
              )}
              {v.trend > 0 ? "+" : ""}
              {v.trend} pts
              <span className="font-normal text-[color:var(--text-tertiary)]">
                vs. mes ant.
              </span>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
