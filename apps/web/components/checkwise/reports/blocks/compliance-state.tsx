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
// R4 (user-language taxonomy): labels rewritten for the audience that
// actually reads the report — internal admins and external auditors,
// not the engineers who designed the workflow state machine. The
// ``hint`` is surfaced as a hover tooltip so a power user who knows the
// internal term still recognises the mapping. Order is preserved so the
// auditor sees what needs work first, what's resolved last.
const BUCKETS: Array<{
  key: keyof DocumentStateCounts;
  label: string;
  hint: string;
}> = [
  {
    key: "rejected",
    label: "Con observaciones",
    hint: "Documentos devueltos al proveedor para corrección.",
  },
  {
    key: "needs_review",
    label: "Pendiente aclaración",
    hint: "El proveedor debe atender un comentario antes de avanzar.",
  },
  {
    key: "expired",
    label: "Vencidos",
    hint: "Cuya vigencia ya expiró y deben renovarse.",
  },
  {
    key: "in_review",
    label: "En revisión",
    hint: "Recibidos y siendo validados por el equipo de cumplimiento.",
  },
  {
    key: "uploaded",
    label: "Recibidos",
    hint: "Cargados por el proveedor, aún sin entrar al ciclo de revisión.",
  },
  {
    key: "pending",
    label: "Por entregar",
    hint: "El proveedor todavía no carga el documento.",
  },
  {
    key: "approved",
    label: "Aprobados",
    hint: "Validados; cuentan como cumplimiento del periodo.",
  },
  {
    key: "exception",
    label: "Excepción autorizada",
    hint: "Documento no exigible por decisión documentada del cliente.",
  },
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
      {/* Semáforo + headline — de-carded (2026-06): the boxed headline
          read as app chrome. Now a clean document headline with the
          compliance % promoted as the block's hero figure. */}
      <div className="flex items-start gap-3">
        <span
          className={`mt-1.5 inline-block h-3.5 w-3.5 rounded-full ${LEVEL_DOT[semaphore.level]} print:hidden`}
          aria-hidden="true"
        />
        <span className="sr-only print:not-sr-only print:mr-1">
          {LEVEL_PRINT[semaphore.level]}
        </span>
        <div className="flex-1 space-y-1">
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="text-[15px] font-semibold text-[color:var(--text-primary)]">
              {semaphore.label}
            </h3>
            <span className="font-mono text-[22px] font-semibold leading-none tabular-nums text-[color:var(--text-primary)]">
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

      {/* Document-state counts strip.
          R4: dropped uppercase-mono eyebrows in favour of sentence-case
          sans labels so the strip reads like a report figure ("Por
          entregar: 3") rather than a debug telemetry row. The
          ``title`` attribute exposes the canonical glossary on hover
          for power users who learned the original taxonomy. */}
      <div className="border-t border-b border-[color:var(--border-subtle)] py-3">
        <p className="mb-2 text-[12px] text-[color:var(--text-tertiary)]">
          Documentos del periodo agrupados por estado.
        </p>
        <div className="cw-metadata-strip">
          {BUCKETS.map((b) => (
            <div key={b.key} title={b.hint}>
              <span className="text-[11px] font-medium text-[color:var(--text-tertiary)]">
                {b.label}
              </span>
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
