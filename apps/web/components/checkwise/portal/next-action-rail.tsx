import * as React from "react";
import Link from "next/link";
import { ArrowRight, Lightning } from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * NextActionRail — the operational "what should I do next" surface.
 *
 * Renders the highest-priority suggested actions as a horizontal rail
 * of action cards. Replaces a passive "list of suggestions" with a
 * dominant first-viewport surface that answers the doctrine's
 * "who owns the next action" question without scrolling.
 *
 * Spec: docs/design-system/VISUAL_REDESIGN_DOCTRINE.md §"Next-action rail".
 */

export type NextActionPriority = "high" | "medium" | "low";

export interface NextActionItem {
  id: string;
  title: string;
  body: string;
  priority: NextActionPriority;
  ctaLabel: string;
  ctaHref: string;
  /** Free-form metadata chip rendered above the title — e.g. requirement code or period. */
  meta?: string;
}

interface NextActionRailProps {
  actions: NextActionItem[];
  emptyState?: { title: string; description?: string };
  className?: string;
}

const PRIORITY_DOT: Record<NextActionPriority, string> = {
  high: "bg-[color:var(--status-error-text)]",
  medium: "bg-[color:var(--status-warning-text)]",
  low: "bg-[color:var(--status-info-text)]",
};

const PRIORITY_LABEL: Record<NextActionPriority, string> = {
  high: "Prioridad alta",
  medium: "Prioridad media",
  low: "Prioridad baja",
};

export function NextActionRail({ actions, emptyState, className }: NextActionRailProps) {
  if (actions.length === 0) {
    if (!emptyState) return null;
    return (
      <section
        className={cn(
          "cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs",
          className,
        )}
        aria-label="Sin acciones pendientes"
      >
        <div className="flex items-center gap-3">
          <span
            aria-hidden="true"
            className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]"
          >
            <Lightning className="h-5 w-5" weight="fill" aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-[color:var(--text-primary)]">
              {emptyState.title}
            </h2>
            {emptyState.description ? (
              <p className="text-xs text-[color:var(--text-secondary)]">
                {emptyState.description}
              </p>
            ) : null}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section
      aria-label="Próximas acciones recomendadas"
      className={cn(
        "rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs",
        className,
      )}
    >
      <header className="flex items-center justify-between gap-3 border-b border-[color:var(--border-subtle)] px-5 py-3">
        <div className="flex items-center gap-2">
          <Lightning
            className="h-4 w-4 text-[color:var(--text-brand)]"
            weight="fill"
            aria-hidden="true"
          />
          <h2 className="text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
            Tu siguiente acción
          </h2>
        </div>
        <span className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
          {actions.length} {actions.length === 1 ? "tarea" : "tareas"}
        </span>
      </header>

      <ul className="cw-stagger flex snap-x snap-mandatory gap-3 overflow-x-auto p-5 sm:grid sm:snap-none sm:grid-cols-2 sm:overflow-visible lg:grid-cols-3">
        {actions.map((action, idx) => (
          <li
            key={action.id}
            className={cn(
              "cw-fade-up cw-hover-lift flex min-w-[260px] flex-1 snap-start flex-col gap-3 rounded-md p-4",
              "border border-[color:var(--border-default)] bg-[color:var(--surface-page)]",
            )}
            style={{ "--cw-index": idx } as React.CSSProperties}
            aria-label={`${PRIORITY_LABEL[action.priority]}: ${action.title}`}
          >
            <div className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className={cn("h-2 w-2 rounded-full", PRIORITY_DOT[action.priority])}
              />
              <span className="font-mono text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                {action.meta ?? PRIORITY_LABEL[action.priority]}
              </span>
            </div>

            <div className="min-w-0 space-y-1">
              <h3 className="line-clamp-2 text-[14px] font-semibold leading-snug text-[color:var(--text-primary)]">
                {action.title}
              </h3>
              <p className="line-clamp-2 text-xs leading-[1.5] text-[color:var(--text-secondary)]">
                {action.body}
              </p>
            </div>

            <Button
              asChild
              size="sm"
              variant={action.priority === "high" ? "default" : "outline"}
              className="mt-auto self-start"
            >
              <Link href={action.ctaHref}>
                <span>{action.ctaLabel}</span>
                <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
              </Link>
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
