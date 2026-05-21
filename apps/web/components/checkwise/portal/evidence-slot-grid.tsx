import * as React from "react";
import { Files } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";
import type { DocumentStateCode } from "@/lib/types";

import {
  EvidenceSlotCard,
  type EvidenceSlotCardProps,
} from "./evidence-slot-card";

/**
 * EvidenceSlotGrid — composition that lays out a set of evidence slots
 * as a state-grouped lattice.
 *
 * Replaces the generic "list of attention items" pattern with the
 * doctrine's evidence-slot lattice: groups roll up by SlotState
 * (rejected/needs_review/in_review/approved/...), each section header
 * surfaces the count, and each card carries its own state-colored
 * bar. The wall reads as an operational state map at a glance.
 *
 * Spec: docs/design-system/VISUAL_REDESIGN_DOCTRINE.md §"Evidence Slot Grid".
 */

type SlotItem = EvidenceSlotCardProps;

interface EvidenceSlotGridProps {
  items: SlotItem[];
  /** Section header text. */
  title?: React.ReactNode;
  /** Optional supporting line under the header. */
  description?: React.ReactNode;
  /** "state" groups by DocumentStateCode (preserves urgency order);
   *  null renders a flat grid. */
  groupBy?: "state" | null;
  /** Header icon. Defaults to Files. */
  icon?: React.ReactNode;
  /** Empty-state copy. */
  emptyState?: { title: string; description?: string };
  className?: string;
}

// Order matters — controls top-to-bottom group rendering. Urgency
// first (red/amber), then in-flight, then settled.
const STATE_GROUP_ORDER: DocumentStateCode[] = [
  "rejected",
  "expired",
  "needs_review",
  "in_review",
  "uploaded",
  "pending",
  "approved",
  "empty",
];

const STATE_GROUP_LABEL: Record<DocumentStateCode, string> = {
  rejected: "Rechazados",
  expired: "Vencidos",
  needs_review: "Requieren tu atención",
  in_review: "En revisión",
  uploaded: "Recibidos",
  pending: "Pendientes",
  approved: "Aprobados",
  empty: "Sin estado",
};

const STATE_GROUP_DOT: Record<DocumentStateCode, string> = {
  rejected: "bg-[color:var(--doc-rejected-text)]",
  expired: "bg-[color:var(--doc-expired-text)]",
  needs_review: "bg-[color:var(--doc-needs-review-text)]",
  in_review: "bg-[color:var(--doc-in-review-border)]",
  uploaded: "bg-[color:var(--doc-uploaded-border)]",
  pending: "bg-[color:var(--doc-pending-border)]",
  approved: "bg-[color:var(--doc-approved-text)]",
  empty: "bg-[color:var(--doc-empty-border)]",
};

export function EvidenceSlotGrid({
  items,
  title,
  description,
  groupBy = "state",
  icon,
  emptyState,
  className,
}: EvidenceSlotGridProps) {
  const headerIcon = icon ?? (
    <Files
      className="h-4 w-4 text-[color:var(--text-brand)]"
      weight="duotone"
      aria-hidden="true"
    />
  );

  const sections = React.useMemo(() => {
    if (groupBy !== "state") {
      return [{ key: "all", label: "", items }];
    }
    const buckets = new Map<DocumentStateCode, SlotItem[]>();
    for (const item of items) {
      const list = buckets.get(item.state) ?? [];
      list.push(item);
      buckets.set(item.state, list);
    }
    return STATE_GROUP_ORDER.filter((state) => buckets.has(state)).map((state) => ({
      key: state,
      label: STATE_GROUP_LABEL[state],
      state,
      items: buckets.get(state)!,
    }));
  }, [items, groupBy]);

  if (items.length === 0 && emptyState) {
    return (
      <section
        className={cn(
          "rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-xs",
          className,
        )}
      >
        {title ? (
          <header className="mb-4 flex items-center gap-2">
            {headerIcon}
            <h2 className="text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
              {title}
            </h2>
          </header>
        ) : null}
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <Files
            className="h-10 w-10 text-[color:var(--text-tertiary)]"
            weight="duotone"
            aria-hidden="true"
          />
          <h3 className="mt-3 text-sm font-medium text-[color:var(--text-primary)]">
            {emptyState.title}
          </h3>
          {emptyState.description ? (
            <p className="mt-1 max-w-xs text-xs text-[color:var(--text-secondary)]">
              {emptyState.description}
            </p>
          ) : null}
        </div>
      </section>
    );
  }

  if (items.length === 0) return null;

  return (
    <section
      className={cn(
        "rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs",
        className,
      )}
      aria-label={typeof title === "string" ? title : undefined}
    >
      {title ? (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[color:var(--border-subtle)] px-5 py-3">
          <div className="flex items-center gap-2">
            {headerIcon}
            <h2 className="text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
              {title}
            </h2>
          </div>
          {description ? (
            <p className="text-xs text-[color:var(--text-secondary)]">{description}</p>
          ) : null}
        </header>
      ) : null}

      <div className="flex flex-col gap-5 p-5">
        {sections.map((section) => (
          <div key={section.key}>
            {section.label ? (
              <div className="mb-2.5 flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className={cn(
                    "h-2 w-2 rounded-full",
                    STATE_GROUP_DOT[(section as { state: DocumentStateCode }).state],
                  )}
                />
                <h3 className="text-[11px] font-semibold uppercase tracking-wide text-[color:var(--text-secondary)]">
                  {section.label}
                </h3>
                <span className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
                  {section.items.length}
                </span>
              </div>
            ) : null}
            <ul className="cw-stagger grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {section.items.map((item, idx) => (
                <li key={item.id} className="contents">
                  <EvidenceSlotCard {...item} index={idx} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

export type { SlotItem };
