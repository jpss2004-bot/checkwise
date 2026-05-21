"use client";

import { ListChecks } from "@phosphor-icons/react";

import { FreshnessLabel } from "@/components/checkwise/reports/freshness-label";
import type { BlockDefinition, BlockProps } from "@/lib/reports/registry";

/**
 * attention_list block (P1.3).
 *
 * Provider-facing actionable list — every row is one obligation the
 * provider must address: state chip + institution chip + title + days-
 * to-deadline + a single-click CTA that opens ``/portal/upload?...``
 * with ``replaces=<submission_id>`` when applicable.
 *
 * Data comes verbatim from the backend ``build_attention_items_for_vendor``
 * (which mirrors the canonical provider dashboard's attention_today
 * list). The href is computed by the backend from authoritative slot
 * state — never authored by the LLM and never edited client-side.
 *
 * Print parity: chips degrade to bracketed labels, the CTA degrades to
 * plain text "Acción: subir ..." with the href URL inline. The on-
 * screen and printed shapes carry the same information.
 */

type SlotState =
  | "rejected"
  | "needs_correction"
  | "possible_mismatch"
  | "expired"
  | "missing"
  | "in_review"
  | "uploaded"
  | "approved"
  | "exception"
  | "not_applicable";

type Institution =
  | "sat"
  | "imss"
  | "infonavit"
  | "stps_repse"
  | "interno_cliente"
  | string; // tolerate unknowns

interface AttentionItem {
  id: string;
  title: string;
  institution: Institution;
  state: SlotState;
  due_in_days: number | null;
  href: string;
  requirement_code?: string | null;
  period_key?: string | null;
  current_submission_id?: string | null;
}

interface AttentionListFilter {
  states?: SlotState[];
  institutions?: Institution[];
  only_due_within_days?: number;
}

interface AttentionListConfig {
  filter?: AttentionListFilter;
  max_rows?: number;
}

interface AttentionListData {
  items: AttentionItem[];
  workspace_id: string | null;
  fetched_at: string | null;
  filter_applied: AttentionListFilter;
  max_rows: number;
  total_before_filter: number;
}

// Severity buckets for the visual chip + the print-fallback label.
// Mirrors WORKFLOW_STATE_MACHINE.md semantics.
const STATE_META: Record<
  SlotState,
  {
    label: string;
    print: string;
    tone: "red" | "orange" | "yellow" | "blue" | "gray";
  }
> = {
  rejected: { label: "Rechazado", print: "[Rechazado]", tone: "red" },
  needs_correction: { label: "Por aclarar", print: "[Por aclarar]", tone: "red" },
  possible_mismatch: {
    label: "Posible mismatch",
    print: "[Posible mismatch]",
    tone: "orange",
  },
  expired: { label: "Vencido", print: "[Vencido]", tone: "orange" },
  missing: { label: "Pendiente", print: "[Pendiente]", tone: "yellow" },
  in_review: { label: "En revisión", print: "[En revisión]", tone: "blue" },
  uploaded: { label: "Subido", print: "[Subido]", tone: "blue" },
  approved: { label: "Aprobado", print: "[Aprobado]", tone: "gray" },
  exception: { label: "Excepción", print: "[Excepción]", tone: "gray" },
  not_applicable: { label: "No aplica", print: "[No aplica]", tone: "gray" },
};

const TONE_CLASS: Record<
  "red" | "orange" | "yellow" | "blue" | "gray",
  string
> = {
  red: "bg-[color:var(--state-red,#fee2e2)] text-[color:var(--state-red-fg,#991b1b)] border-[color:var(--state-red-border,#fca5a5)]",
  orange:
    "bg-[color:var(--state-orange,#ffedd5)] text-[color:var(--state-orange-fg,#9a3412)] border-[color:var(--state-orange-border,#fdba74)]",
  yellow:
    "bg-[color:var(--state-yellow,#fef3c7)] text-[color:var(--state-yellow-fg,#92400e)] border-[color:var(--state-yellow-border,#fcd34d)]",
  blue: "bg-[color:var(--state-blue,#dbeafe)] text-[color:var(--state-blue-fg,#1e40af)] border-[color:var(--state-blue-border,#93c5fd)]",
  gray: "bg-[color:var(--surface-muted,#f1f5f9)] text-[color:var(--text-secondary)] border-[color:var(--border-subtle)]",
};

const INSTITUTION_LABEL: Record<string, string> = {
  sat: "SAT",
  imss: "IMSS",
  infonavit: "INFONAVIT",
  stps_repse: "STPS · REPSE",
  interno_cliente: "Interno",
};

const STATE_CTA: Record<SlotState, string> = {
  rejected: "Subir versión corregida",
  needs_correction: "Atender observación",
  possible_mismatch: "Verificar archivo",
  expired: "Subir versión vigente",
  missing: "Subir documento",
  in_review: "Reemplazar",
  uploaded: "Reemplazar",
  approved: "Subir nueva versión",
  exception: "Subir nueva versión",
  not_applicable: "Subir",
};

function formatDue(due: number | null): { label: string; tone: "red" | "yellow" | "gray" } {
  if (due === null || due === undefined) return { label: "—", tone: "gray" };
  if (due < 0) return { label: `${Math.abs(due)} días vencido`, tone: "red" };
  if (due === 0) return { label: "hoy", tone: "red" };
  if (due <= 5) return { label: `en ${due} días`, tone: "yellow" };
  return { label: `en ${due} días`, tone: "gray" };
}

export const attentionListDefinition: Omit<
  BlockDefinition<AttentionListConfig, AttentionListData>,
  "Component"
> = {
  type: "attention_list",
  label: "Atención inmediata",
  icon: ListChecks,
  description:
    "Lista de documentos rechazados, en aclaración o por vencer, con botón para subir.",
  defaultConfig: { max_rows: 10 },
};

export function AttentionListBlock({
  block,
}: BlockProps<AttentionListConfig, AttentionListData>) {
  const data = block.data;

  if (!data) {
    return (
      <section className="space-y-2 py-2">
        <div className="border-y border-[color:var(--border-subtle)] py-3 text-[13px] text-[color:var(--text-tertiary)]">
          Cargando documentos por atender…
        </div>
      </section>
    );
  }

  const items = data.items ?? [];
  const filterChips = renderFilterChips(data.filter_applied ?? {});

  if (items.length === 0) {
    return (
      <section className="space-y-2 py-2" data-block-type="attention_list">
        <div className="rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-elevated,transparent)] px-4 py-6 text-center">
          <p className="text-[14px] font-medium text-[color:var(--text-primary)]">
            No hay documentos por atender ahora.
          </p>
          <p className="mt-1 text-[12px] text-[color:var(--text-tertiary)]">
            {data.total_before_filter > 0
              ? "Ningún elemento coincide con el filtro aplicado."
              : "Todo lo obligatorio está al día o ya está en revisión humana."}
          </p>
          {filterChips}
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-2 py-2" data-block-type="attention_list">
      {filterChips}
      <ul className="divide-y divide-[color:var(--border-subtle)] border-y border-[color:var(--border-subtle)]">
        {items.map((item) => {
          const meta = STATE_META[item.state] ?? STATE_META.missing;
          const dueInfo = formatDue(item.due_in_days);
          const dueClass =
            dueInfo.tone === "red"
              ? "text-[color:var(--state-red-fg,#991b1b)]"
              : dueInfo.tone === "yellow"
              ? "text-[color:var(--state-orange-fg,#9a3412)]"
              : "text-[color:var(--text-tertiary)]";
          const inst = INSTITUTION_LABEL[item.institution] ?? item.institution;
          return (
            <li
              key={item.id}
              className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`inline-flex items-center rounded-sm border px-1.5 py-[1px] text-[11px] font-medium uppercase tracking-[0.04em] ${TONE_CLASS[meta.tone]} print:hidden`}
                >
                  {meta.label}
                </span>
                <span className="sr-only print:not-sr-only print:mr-1">
                  {meta.print}
                </span>
                <span className="inline-flex items-center rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-muted,transparent)] px-1.5 py-[1px] text-[11px] font-medium uppercase tracking-[0.04em] text-[color:var(--text-secondary)]">
                  {inst}
                </span>
                <span className="text-[13px] font-medium text-[color:var(--text-primary)]">
                  {item.title}
                </span>
                <span className={`text-[12px] tabular-nums ${dueClass}`}>
                  · {dueInfo.label}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <a
                  href={item.href}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-sm border border-[color:var(--border-strong,var(--border-subtle))] px-2 py-1 text-[12px] font-medium text-[color:var(--text-primary)] hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ring)] print:hidden"
                >
                  {STATE_CTA[item.state] ?? "Subir"}
                </a>
                <span className="sr-only print:not-sr-only print:text-[11px] print:text-[color:var(--text-tertiary)]">
                  Acción: {STATE_CTA[item.state] ?? "Subir"} ({item.href})
                </span>
              </div>
            </li>
          );
        })}
      </ul>
      <p className="text-[11px] text-[color:var(--text-tertiary)]">
        {items.length} de {data.total_before_filter} elementos
      </p>
      <FreshnessLabel fetchedAt={data.fetched_at} />
    </section>
  );
}

function renderFilterChips(filter: AttentionListFilter) {
  const chips: string[] = [];
  if (filter.states && filter.states.length > 0) {
    chips.push(
      `Estados: ${filter.states
        .map((s) => STATE_META[s]?.label ?? s)
        .join(", ")}`,
    );
  }
  if (filter.institutions && filter.institutions.length > 0) {
    chips.push(
      `Instituciones: ${filter.institutions
        .map((i) => INSTITUTION_LABEL[i] ?? i)
        .join(", ")}`,
    );
  }
  if (filter.only_due_within_days !== undefined) {
    chips.push(`Próximos ${filter.only_due_within_days} días`);
  }
  if (chips.length === 0) return null;
  return (
    <p className="text-[11px] text-[color:var(--text-tertiary)]">
      Filtro · {chips.join(" · ")}
    </p>
  );
}
