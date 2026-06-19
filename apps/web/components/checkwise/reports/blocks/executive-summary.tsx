"use client";

import { Sparkle } from "@phosphor-icons/react";

import { FreshnessLabel } from "@/components/checkwise/reports/freshness-label";
import { semaphoreLabel, slotStateLabel } from "@/lib/constants/statuses";
import type { BlockDefinition, BlockProps } from "@/lib/reports/registry";

/**
 * Executive summary block — the cover paragraph that opens a report.
 *
 * Composition: small eyebrow + period/scope label + a short paragraph,
 * optionally followed by a metric strip. Render is intentionally calm
 * — the strongest typographic anchor on the report, not a card.
 *
 * Data is fetched server-side in Phase 3.3+; until then the block
 * just renders config (the human-authored / placeholder copy).
 */

type ExecutiveSummaryFocus = "compliance" | "risk" | "expediente" | "audit" | "custom";

interface ExecutiveSummaryConfig {
  focus: ExecutiveSummaryFocus;
  custom_prompt?: string;
  include_metrics: boolean;
  period_label?: string;
  scope_label?: string;
  body?: string;
}

interface MetricRow {
  label: string;
  value: string;
}

interface ExecutiveSummaryData {
  period_label?: string;
  scope_label?: string;
  /** Deterministic, templated factual recap (no LLM). The cover lead. */
  summary?: string;
  headline_metrics?: {
    completion_pct?: number;
    vendors_at_risk?: number;
    submissions_in_review?: number;
    next_critical_deadline?: string | null;
  };
  /** P1.7: ISO8601 stamp from the backend fetcher. */
  fetched_at?: string | null;
}

export const executiveSummaryDefinition: Omit<
  BlockDefinition<ExecutiveSummaryConfig, ExecutiveSummaryData>,
  "Component"
> = {
  type: "executive_summary",
  label: "Resumen ejecutivo",
  icon: Sparkle,
  description: "Apertura del reporte. Período, alcance y titular.",
  defaultConfig: {
    focus: "compliance",
    include_metrics: true,
  },
};

function formatPct(value: number | undefined): string {
  if (value === undefined || value === null) return "—";
  return `${Math.round(value)}%`;
}

function formatCount(value: number | undefined): string {
  if (value === undefined || value === null) return "—";
  return value.toString();
}

export function ExecutiveSummaryBlock({
  block,
  editable,
  onPatch,
}: BlockProps<ExecutiveSummaryConfig, ExecutiveSummaryData>) {
  const { config, data } = block;
  // The opening paragraph is DETERMINISTIC: a manually-authored
  // `config.body` wins; otherwise the templated `data.summary` (computed
  // server-side from the metrics — no LLM, so the factual headline can't
  // be hallucinated). The AI prose, if any, is demoted to a clearly
  // labelled subordinate caption below (`aiText`), never the headline.
  const aiText = block.ai_summary?.text ?? "";
  const deterministicSummary = data?.summary ?? "";
  const bodyText =
    config.body && config.body.trim() ? config.body : deterministicSummary;
  const period = data?.period_label ?? config.period_label ?? "—";
  const scope = data?.scope_label ?? config.scope_label ?? "Alcance por definir";
  // State-bearing labels are sourced from the canonical helpers so they
  // read the same word as everywhere else: "En riesgo" (semáforo red) and
  // "En revisión" (in-review item). "Cumplimiento" and "Próximo" are
  // bespoke cover-metric names with no state analogue and stay as-is.
  const metrics: MetricRow[] = [
    { label: "Cumplimiento", value: formatPct(data?.headline_metrics?.completion_pct) },
    { label: semaphoreLabel("red"), value: formatCount(data?.headline_metrics?.vendors_at_risk) },
    { label: slotStateLabel("in_review"), value: formatCount(data?.headline_metrics?.submissions_in_review) },
    {
      label: "Próximo",
      value: data?.headline_metrics?.next_critical_deadline ?? "—",
    },
  ];

  return (
    <section
      className="space-y-4 py-2 print:break-inside-avoid"
      data-block-type="executive_summary"
    >
      <div className="space-y-2">
        <div className="cw-metadata-strip">
          <div>
            <span className="cw-eyebrow">Centro de cumplimiento</span>
            <span className="text-[13px] text-[color:var(--text-primary)]">{scope}</span>
          </div>
          <div>
            <span className="cw-eyebrow">Período</span>
            <span className="font-mono text-[13px] text-[color:var(--text-primary)]">
              {period}
            </span>
          </div>
          {editable ? (
            <div>
              <span className="cw-eyebrow">Enfoque</span>
              <span className="text-[13px] text-[color:var(--text-primary)]">
                {labelForFocus(config.focus)}
              </span>
            </div>
          ) : null}
        </div>

        {editable ? (
          <textarea
            placeholder="Resumen automático; edítalo para personalizarlo."
            value={config.body ?? deterministicSummary}
            onChange={(e) =>
              onPatch({ config: { ...config, body: e.target.value } })
            }
            rows={Math.max(
              2,
              (config.body ?? deterministicSummary).split("\n").length + 1,
            )}
            className="cw-prose w-full resize-none border-0 bg-transparent p-0 text-[15px] leading-relaxed text-[color:var(--text-primary)] outline-none placeholder:text-[color:var(--text-tertiary)] focus:ring-0"
          />
        ) : bodyText ? (
          <p className="cw-prose text-[15px] leading-relaxed text-[color:var(--text-primary)]">
            {bodyText}
          </p>
        ) : (
          <p className="text-[14px] italic leading-relaxed text-[color:var(--text-tertiary)]">
            Sin resumen para este periodo.
          </p>
        )}

        {/* AI prose is demoted to a subordinate, clearly-labelled
            "lectura del equipo" caption below the deterministic recap —
            it can elaborate but never replaces the computed facts above.
            Shown only when an author hasn't overridden the body with
            their own text (so we don't stack two prose paragraphs). */}
        {aiText && !(config.body && config.body.trim()) ? (
          <div className="mt-3 rounded-md bg-[color:var(--surface-ai-muted)] px-3 py-2">
            <p className="mb-1 flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.06em] text-[color:var(--text-ai)]">
              <Sparkle className="h-3 w-3" weight="fill" aria-hidden="true" />
              Lectura del equipo · IA · verificar
            </p>
            <p className="text-[13px] leading-relaxed text-[color:var(--text-secondary)]">
              {aiText}
            </p>
          </div>
        ) : null}
      </div>

      {config.include_metrics && (
        <div className="border-t border-b border-[color:var(--border-subtle)] py-3">
          <div className="cw-metadata-strip">
            {metrics.map((m) => (
              <div key={m.label}>
                <span className="cw-eyebrow">{m.label}</span>
                <span className="font-mono text-[14px] font-semibold tabular-nums text-[color:var(--text-primary)]">
                  {m.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <FreshnessLabel fetchedAt={data?.fetched_at} />
    </section>
  );
}

function labelForFocus(focus: ExecutiveSummaryFocus): string {
  switch (focus) {
    case "compliance":
      return "Cumplimiento";
    case "risk":
      return "Riesgo";
    case "expediente":
      return "Expediente";
    case "audit":
      return "Auditoría";
    case "custom":
      return "Personalizado";
  }
}
