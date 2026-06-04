"use client";

import {
  ArrowsClockwise,
  ChatCircle,
  ClipboardText,
  IdentificationCard,
  ListNumbers,
  MagnifyingGlass,
} from "@phosphor-icons/react";
import type { Icon as PhosphorIcon } from "@phosphor-icons/react";

import { FreshnessLabel } from "@/components/checkwise/reports/freshness-label";
import type { BlockDefinition, BlockProps } from "@/lib/reports/registry";

/**
 * prioritized_actions block (P1.5).
 *
 * Numbered, vendor-facing action cards that close a provider report.
 * Each card carries:
 *
 *  - A big numeric badge (1, 2, 3 …).
 *  - A type icon matching the action type (reupload / clarify /
 *    verify / complete_onboarding / upcoming).
 *  - A priority chip — high / medium / low — color-coded.
 *  - A canonical title + body, both pulled verbatim from
 *    ``build_suggested_actions_for_vendor`` on the backend. No LLM
 *    in the body — the renderer never invents copy.
 *  - A period chip when the slot is bound to a period.
 *  - A single CTA button that opens ``/portal/upload?…`` with the
 *    pre-computed ``replaces=`` if applicable.
 *
 * The component degrades cleanly for print: chips and icons keep
 * their semantic labels, the CTA becomes a static
 * "Acción: subir / aclarar / verificar (URL)" line.
 *
 * This block is the structured replacement for ``ai_recommendation``
 * in vendor_facing reports. ``ai_recommendation`` stays available
 * for internal / client_facing reports.
 */

type ActionType =
  | "reupload"
  | "clarify"
  | "verify_mismatch"
  | "complete_onboarding"
  | "upcoming";

type Priority = "high" | "medium" | "low";

interface PrioritizedAction {
  id: string;
  type: ActionType;
  title: string;
  body: string;
  priority: Priority;
  href: string;
  requirement_code?: string | null;
  period_key?: string | null;
}

interface PrioritizedActionsConfig {
  max_actions?: number;
  filter?: {
    priorities?: Priority[];
    types?: ActionType[];
  };
}

interface PrioritizedActionsData {
  items: PrioritizedAction[];
  workspace_id: string | null;
  fetched_at: string | null;
  as_of: string | null;
  filter_applied: { priorities?: Priority[]; types?: ActionType[] };
  max_actions: number;
  total_before_filter: number;
}

const TYPE_META: Record<
  ActionType,
  { label: string; icon: PhosphorIcon }
> = {
  reupload: { label: "Resubir", icon: ArrowsClockwise },
  clarify: { label: "Aclarar", icon: ChatCircle },
  verify_mismatch: { label: "Verificar", icon: MagnifyingGlass },
  complete_onboarding: { label: "Onboarding", icon: IdentificationCard },
  upcoming: { label: "Próximo", icon: ClipboardText },
};

const PRIORITY_META: Record<
  Priority,
  { label: string; tone: "red" | "orange" | "gray"; print: string }
> = {
  high: { label: "Alta", tone: "red", print: "[Alta]" },
  medium: { label: "Media", tone: "orange", print: "[Media]" },
  low: { label: "Baja", tone: "gray", print: "[Baja]" },
};

const TONE_CHIP: Record<"red" | "orange" | "gray", string> = {
  red: "bg-[color:var(--state-red,#fee2e2)] text-[color:var(--state-red-fg,#991b1b)] border-[color:var(--state-red-border,#fca5a5)]",
  orange:
    "bg-[color:var(--state-orange,#ffedd5)] text-[color:var(--state-orange-fg,#9a3412)] border-[color:var(--state-orange-border,#fdba74)]",
  gray: "bg-[color:var(--surface-muted,#f1f5f9)] text-[color:var(--text-secondary)] border-[color:var(--border-subtle)]",
};

const TYPE_CTA: Record<ActionType, string> = {
  reupload: "Subir versión corregida",
  clarify: "Atender observación",
  verify_mismatch: "Verificar archivo",
  complete_onboarding: "Completar expediente",
  upcoming: "Subir documento",
};

export const prioritizedActionsDefinition: Omit<
  BlockDefinition<PrioritizedActionsConfig, PrioritizedActionsData>,
  "Component"
> = {
  type: "prioritized_actions",
  label: "Acciones priorizadas",
  icon: ListNumbers,
  description:
    "Tarjetas numeradas con prioridad, motivo y botón para subir o aclarar cada documento.",
  defaultConfig: { max_actions: 3 },
};

export function PrioritizedActionsBlock({
  block,
  interactive = true,
}: BlockProps<PrioritizedActionsConfig, PrioritizedActionsData>) {
  const data = block.data;

  if (!data) {
    return (
      <section className="space-y-2 py-2">
        <div className="border-y border-[color:var(--border-subtle)] py-3 text-[13px] text-[color:var(--text-tertiary)]">
          Cargando acciones priorizadas…
        </div>
      </section>
    );
  }

  const items = data.items ?? [];
  const filterChips = renderFilterChips(data.filter_applied ?? {});

  if (items.length === 0) {
    return (
      <section
        className="space-y-2 py-2"
        data-block-type="prioritized_actions"
      >
        <div className="border-y border-[color:var(--border-subtle)] px-1 py-6 text-center">
          <p className="text-[14px] font-medium text-[color:var(--text-primary)]">
            No hay acciones pendientes.
          </p>
          <p className="mt-1 text-[12px] text-[color:var(--text-tertiary)]">
            {data.total_before_filter > 0
              ? "Ninguna acción coincide con el filtro aplicado."
              : "Tu equipo de LegalShelf no ha sugerido acciones para este proveedor."}
          </p>
          {filterChips}
        </div>
      </section>
    );
  }

  return (
    <section
      className="space-y-3 py-3"
      data-block-type="prioritized_actions"
    >
      {filterChips}
      <ol className="divide-y divide-[color:var(--border-subtle)] border-y border-[color:var(--border-subtle)]">
        {items.map((item, idx) => (
          <ActionCard
            key={item.id}
            item={item}
            index={idx + 1}
            interactive={interactive}
          />
        ))}
      </ol>
      <p className="text-[11px] text-[color:var(--text-tertiary)]">
        {items.length} de {data.total_before_filter} acciones
      </p>
      <FreshnessLabel fetchedAt={data.fetched_at} asOf={data.as_of} />
    </section>
  );
}

function ActionCard({
  item,
  index,
  interactive = true,
}: {
  item: PrioritizedAction;
  index: number;
  interactive?: boolean;
}) {
  const priorityMeta = PRIORITY_META[item.priority] ?? PRIORITY_META.low;
  const typeMeta = TYPE_META[item.type] ?? TYPE_META.reupload;
  const Icon = typeMeta.icon;
  const ctaLabel = TYPE_CTA[item.type] ?? "Atender";
  return (
    <li className="relative flex flex-col gap-3 py-4 first:pt-1 sm:flex-row sm:items-stretch sm:gap-4">
      {/* Numbered badge — navy fill carries the brand into the document. */}
      <div
        aria-hidden="true"
        className="hidden h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-brand)] font-mono text-[13px] font-semibold tabular-nums text-white sm:flex"
        style={{ printColorAdjust: "exact", WebkitPrintColorAdjust: "exact" }}
      >
        {index}
      </div>

      {/* Body */}
      <div className="min-w-0 flex-1 space-y-1">
        {/* Header row: type + priority + period */}
        <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.04em] text-[color:var(--text-tertiary)]">
          <span className="flex items-center gap-1 text-[color:var(--text-secondary)]">
            <Icon className="h-3.5 w-3.5" />
            <span>{typeMeta.label}</span>
          </span>
          <span
            className={`inline-flex items-center rounded-sm border px-1.5 py-[1px] font-medium ${TONE_CHIP[priorityMeta.tone]} print:hidden`}
          >
            Prioridad {priorityMeta.label}
          </span>
          <span className="sr-only print:not-sr-only print:mr-1">
            Prioridad {priorityMeta.print}
          </span>
          {item.period_key && (
            <span className="inline-flex items-center rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-muted,transparent)] px-1.5 py-[1px] font-mono text-[10px] font-medium tabular-nums text-[color:var(--text-secondary)]">
              {item.period_key}
            </span>
          )}
          {item.requirement_code && (
            <span className="ml-auto hidden font-mono text-[10px] text-[color:var(--text-tertiary)] sm:inline">
              {item.requirement_code}
            </span>
          )}
        </div>

        {/* Title */}
        <p className="text-[14px] font-semibold leading-snug text-[color:var(--text-primary)]">
          <span className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full border border-[color:var(--border-subtle)] font-mono text-[10px] font-semibold tabular-nums text-[color:var(--text-secondary)] sm:hidden">
            {index}
          </span>
          {item.title}
        </p>

        {/* Body */}
        {item.body && (
          <p className="text-[13px] leading-snug text-[color:var(--text-secondary)]">
            {item.body}
          </p>
        )}

        {/* CTA — only for the provider's own copy (``interactive``).
            Other audiences read this as a prioritized findings list to
            forward, not a set of buttons they can act on. */}
        {interactive ? (
          <div className="flex items-center gap-2 pt-1">
            <a
              href={item.href}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 rounded-sm border border-[color:var(--border-strong,var(--border-subtle))] bg-[color:var(--surface,#fff)] px-2.5 py-1 text-[12px] font-medium text-[color:var(--text-primary)] hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ring)] print:hidden"
            >
              {ctaLabel}
            </a>
            <span className="sr-only print:not-sr-only print:text-[11px] print:text-[color:var(--text-tertiary)]">
              Acción: {ctaLabel} ({item.href})
            </span>
          </div>
        ) : null}
      </div>
    </li>
  );
}

function renderFilterChips(filter: PrioritizedActionsData["filter_applied"]) {
  const chips: string[] = [];
  if (filter.priorities && filter.priorities.length > 0) {
    chips.push(
      `Prioridad: ${filter.priorities
        .map((p) => PRIORITY_META[p]?.label ?? p)
        .join(", ")}`,
    );
  }
  if (filter.types && filter.types.length > 0) {
    chips.push(
      `Tipo: ${filter.types.map((t) => TYPE_META[t]?.label ?? t).join(", ")}`,
    );
  }
  if (chips.length === 0) return null;
  return (
    <p className="text-[11px] text-[color:var(--text-tertiary)]">
      Filtro · {chips.join(" · ")}
    </p>
  );
}
