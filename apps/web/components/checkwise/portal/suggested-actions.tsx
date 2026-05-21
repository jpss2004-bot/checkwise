import Link from "next/link";
import { ArrowRight, Lightbulb, type Icon } from "@phosphor-icons/react";

import { DocStateBadge } from "@/components/checkwise/doc-state-badge";
import { Button } from "@/components/ui/button";
import type { ActionPriority, SuggestedAction } from "@/lib/types";

const PRIORITY_RAIL: Record<ActionPriority, string> = {
  high: "before:bg-[color:var(--status-error-text)]",
  medium: "before:bg-[color:var(--status-warning-text)]",
  low: "before:bg-[color:var(--status-info-text)]",
};

const PRIORITY_LABEL: Record<ActionPriority, string> = {
  high: "Urgente",
  medium: "Importante",
  low: "Sugerido",
};

interface SuggestedActionsProps {
  actions: SuggestedAction[];
  /** Override the section title. */
  title?: string;
  /** Override the section icon. */
  Icon?: Icon;
}

export function SuggestedActions({
  actions,
  title = "Sugerencias para ti",
  Icon: TitleIcon = Lightbulb,
}: SuggestedActionsProps) {
  if (actions.length === 0) {
    return (
      <section className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 text-center">
        <p className="text-sm text-[color:var(--text-secondary)]">
          Sin acciones sugeridas por ahora. Te avisaremos cuando algo necesite tu
          atención.
        </p>
      </section>
    );
  }

  return (
    <section className="cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs">
      <header className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] px-5 py-3">
        <TitleIcon
          className="h-4 w-4 text-[color:var(--text-teal)]"
          weight="duotone"
          aria-hidden="true"
        />
        <h2 className="text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
          {title}
        </h2>
        <span className="ml-auto font-mono text-xs text-[color:var(--text-tertiary)]">
          {actions.length}
        </span>
      </header>
      <ul className="cw-stagger divide-y divide-[color:var(--border-subtle)]">
        {actions.map((action) => (
          <li
            key={action.id}
            className={`group relative flex flex-col gap-3 px-5 py-4 transition-colors hover:bg-[color:var(--surface-hover)] sm:flex-row sm:items-center sm:justify-between before:absolute before:left-0 before:top-2 before:bottom-2 before:w-1 before:rounded-r-full ${PRIORITY_RAIL[action.priority]}`}
          >
            <div className="min-w-0 flex-1 pl-2 sm:pl-3">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  {PRIORITY_LABEL[action.priority]}
                </p>
                {action.deadline_iso && (
                  <p className="font-mono text-[10px] text-[color:var(--text-tertiary)]">
                    · Vence {formatDeadline(action.deadline_iso)}
                  </p>
                )}
                {action.status_badge && (
                  <DocStateBadge state={action.status_badge} withIcon={false} />
                )}
              </div>
              <p className="mt-1 text-sm font-medium leading-5 text-[color:var(--text-primary)]">
                {action.title}
              </p>
              <p className="mt-0.5 text-xs leading-5 text-[color:var(--text-secondary)]">
                {action.description}
              </p>
            </div>
            <Button asChild size="sm" variant="outline" className="shrink-0 self-start sm:self-center">
              <Link href={action.cta_href}>
                <span>{action.cta_label}</span>
                <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
              </Link>
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function formatDeadline(iso: string): string {
  try {
    const date = new Date(iso);
    return date.toLocaleDateString("es-MX", {
      day: "2-digit",
      month: "short",
    });
  } catch {
    return iso;
  }
}
