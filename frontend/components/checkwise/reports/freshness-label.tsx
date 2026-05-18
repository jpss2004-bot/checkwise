"use client";

import { createContext, useContext } from "react";
import { ArrowsClockwise, Clock } from "@phosphor-icons/react";

/**
 * P1.7 — per-block freshness label + inline "Actualizar con datos
 * de hoy" affordance.
 *
 * The four provider blocks (compliance_state, attention_list,
 * upcoming_deadlines, prioritized_actions) embed <FreshnessLabel />
 * sourced from their own `data.fetched_at` / `data.as_of`. The
 * component also surfaces the global refresh handler from
 * <ReportActionsContext> so each block can trigger a whole-report
 * refresh without taking a prop dependency on the editor — refresh
 * is always a report-level action that writes a single new version.
 */

export interface ReportActions {
  onRefreshData: () => void;
  refreshingData: boolean;
}

export const ReportActionsContext = createContext<ReportActions | null>(null);

export function useReportActions(): ReportActions | null {
  return useContext(ReportActionsContext);
}

const STALE_AFTER_HOURS = 24;

function parseTimestamp(value: string | null | undefined): Date | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatAbsolute(d: Date): string {
  return d.toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" });
}

function formatRelative(d: Date): string {
  const diffMs = Date.now() - d.getTime();
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) return "ahora mismo";
  if (diffMin < 60) return `hace ${diffMin} min`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `hace ${diffHr} h`;
  const diffDay = Math.round(diffHr / 24);
  return `hace ${diffDay} día${diffDay === 1 ? "" : "s"}`;
}

export interface FreshnessLabelProps {
  /** ISO8601 timestamp of when the data payload was fetched. */
  fetchedAt: string | null | undefined;
  /** Optional 'as_of' date (e.g. the date passed to the deterministic
   *  builder). Shown alongside `fetchedAt` when present. */
  asOf?: string | null | undefined;
  /** Override the inline refresh button visibility. Default: shown
   *  when the context provides an `onRefreshData` handler. */
  showRefresh?: boolean;
}

export function FreshnessLabel({
  fetchedAt,
  asOf,
  showRefresh,
}: FreshnessLabelProps) {
  const actions = useReportActions();
  const fetched = parseTimestamp(fetchedAt);

  if (!fetched) {
    return (
      <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wide text-[color:var(--text-tertiary)]">
        <Clock className="h-3 w-3" weight="regular" aria-hidden="true" />
        Sin sello de actualización
      </div>
    );
  }

  const ageHours = (Date.now() - fetched.getTime()) / 36e5;
  const isStale = ageHours >= STALE_AFTER_HOURS;
  const shouldShowRefresh =
    (showRefresh ?? actions !== null) && actions !== null;

  return (
    <div
      className={`flex flex-wrap items-center gap-2 text-[10px] font-mono uppercase tracking-wide ${
        isStale
          ? "text-[color:var(--status-warning-text)]"
          : "text-[color:var(--text-tertiary)]"
      }`}
    >
      <Clock className="h-3 w-3" weight="regular" aria-hidden="true" />
      <span title={formatAbsolute(fetched)}>
        Datos al {formatAbsolute(fetched)} · {formatRelative(fetched)}
      </span>
      {asOf ? (
        <span className="text-[color:var(--text-tertiary)]">· corte {asOf}</span>
      ) : null}
      {isStale ? (
        <span className="rounded-sm bg-[color:var(--status-warning-bg)] px-1.5 py-0.5 text-[color:var(--status-warning-text)] normal-case tracking-normal">
          Desactualizado
        </span>
      ) : null}
      {shouldShowRefresh ? (
        <button
          type="button"
          onClick={actions!.onRefreshData}
          disabled={actions!.refreshingData}
          className="inline-flex items-center gap-1 rounded-sm border border-[color:var(--border-subtle)] px-1.5 py-0.5 normal-case tracking-normal text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)] disabled:opacity-50"
          aria-label="Actualizar con datos de hoy"
          title="Actualizar este bloque con datos de hoy (refresca todo el reporte)"
        >
          <ArrowsClockwise
            className={`h-3 w-3 ${actions!.refreshingData ? "animate-spin" : ""}`}
            weight="bold"
            aria-hidden="true"
          />
          {actions!.refreshingData ? "Actualizando…" : "Actualizar"}
        </button>
      ) : null}
    </div>
  );
}
