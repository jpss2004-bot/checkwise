"use client";

import { Gauge } from "@phosphor-icons/react";

import { FreshnessLabel } from "@/components/checkwise/reports/freshness-label";
import type { BlockDefinition, BlockProps } from "@/lib/reports/registry";

/**
 * compliance_state block (P1.2).
 *
 * Provider compliance pulse — semáforo + reason + compliance % + the
 * eight-bucket document-state counts. Data comes verbatim from the
 * backend ``build_compliance_state_for_vendor`` builder (which mirrors
 * the canonical provider dashboard payload).
 *
 * No AI text. No editable config in v1 (a future ``year`` override is
 * reserved on the catalog schema). The block degrades to a static
 * representation in print: chips render as bracketed labels, the
 * semáforo dot becomes a leading colored character.
 */

type SemaphoreLevel = "green" | "yellow" | "red";

interface Semaphore {
  level: SemaphoreLevel;
  label: string;
  reason: string;
  compliance_pct: number;
  total_tracked: number;
  on_track: number;
}

interface DocumentStateCounts {
  approved: number;
  in_review: number;
  uploaded: number;
  pending: number;
  needs_review: number;
  rejected: number;
  expired: number;
  exception: number;
}

interface ComplianceStateConfig {
  year?: number;
}

interface ComplianceStateData {
  semaphore: Semaphore;
  document_state_counts: DocumentStateCounts;
  workspace_id: string | null;
  persona_type: string | null;
  /** P1.7: ISO8601 of when the backend builder fetched this payload.
   *  Drives the freshness label + "Actualizar" affordance. */
  fetched_at?: string | null;
}

// Ordered for display: actionable buckets first, then in-flight, then resolved.
const BUCKETS: Array<{ key: keyof DocumentStateCounts; label: string }> = [
  { key: "rejected", label: "Rechazados" },
  { key: "needs_review", label: "Por aclarar" },
  { key: "expired", label: "Vencidos" },
  { key: "in_review", label: "En revisión" },
  { key: "uploaded", label: "Subidos" },
  { key: "pending", label: "Pendientes" },
  { key: "approved", label: "Aprobados" },
  { key: "exception", label: "Excepción" },
];

const LEVEL_DOT: Record<SemaphoreLevel, string> = {
  red: "bg-[color:var(--state-red,#dc2626)]",
  yellow: "bg-[color:var(--state-yellow,#d97706)]",
  green: "bg-[color:var(--state-green,#16a34a)]",
};

const LEVEL_PRINT: Record<SemaphoreLevel, string> = {
  red: "[Rojo]",
  yellow: "[Amarillo]",
  green: "[Verde]",
};

export const complianceStateDefinition: Omit<
  BlockDefinition<ComplianceStateConfig, ComplianceStateData>,
  "Component"
> = {
  type: "compliance_state",
  label: "Estado de cumplimiento",
  icon: Gauge,
  description:
    "Semáforo del proveedor, motivo, % de cumplimiento y conteos por estado.",
  defaultConfig: {},
};

export function ComplianceStateBlock({
  block,
}: BlockProps<ComplianceStateConfig, ComplianceStateData>) {
  const data = block.data;

  // No data yet (block just inserted or backend returned null) —
  // render a skeleton that still establishes the visual footprint so
  // the canvas doesn't jump when data arrives.
  if (!data) {
    return (
      <section className="space-y-3 py-3">
        <div className="cw-metadata-strip border-t border-b border-[color:var(--border-subtle)] py-3">
          <div>
            <span className="cw-eyebrow">Semáforo</span>
            <span className="text-[color:var(--text-tertiary)]">Cargando…</span>
          </div>
        </div>
      </section>
    );
  }

  const { semaphore, document_state_counts: counts } = data;

  return (
    <section className="space-y-3 py-3" data-block-type="compliance_state">
      {/* Semáforo + headline */}
      <div className="flex items-start gap-3 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-elevated,transparent)] px-4 py-3">
        <span
          className={`mt-1 inline-block h-3 w-3 rounded-full ${LEVEL_DOT[semaphore.level]} print:hidden`}
          aria-hidden="true"
        />
        <span className="sr-only print:not-sr-only print:mr-1">
          {LEVEL_PRINT[semaphore.level]}
        </span>
        <div className="flex-1 space-y-1">
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="text-[14px] font-semibold text-[color:var(--text-primary)]">
              {semaphore.label}
            </h3>
            <span className="font-mono text-[14px] font-semibold tabular-nums text-[color:var(--text-primary)]">
              {semaphore.compliance_pct}%
            </span>
          </div>
          <p className="text-[13px] leading-snug text-[color:var(--text-secondary)]">
            {semaphore.reason}
          </p>
          <p className="text-[11px] text-[color:var(--text-tertiary)]">
            {semaphore.on_track} de {semaphore.total_tracked} obligaciones al día
          </p>
        </div>
      </div>

      {/* Document-state counts strip */}
      <div className="border-t border-b border-[color:var(--border-subtle)] py-3">
        <div className="cw-metadata-strip">
          {BUCKETS.map((b) => (
            <div key={b.key}>
              <span className="cw-eyebrow">{b.label}</span>
              <span className="font-mono text-[14px] font-semibold tabular-nums text-[color:var(--text-primary)]">
                {counts[b.key]}
              </span>
            </div>
          ))}
        </div>
      </div>

      <FreshnessLabel fetchedAt={data.fetched_at} />
    </section>
  );
}
