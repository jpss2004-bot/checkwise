import { Check } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";

export interface StepperStep {
  id: string;
  label: string;
}

interface StepperProps {
  steps: StepperStep[];
  /** Zero-based index of the currently active step. */
  currentIndex: number;
  className?: string;
}

/**
 * Horizontal step indicator for multi-step wizards.
 *
 * Spec: docs/DESIGN_SYSTEM.md §6.1 — completed (filled navy + check),
 * active (filled navy + number), upcoming (empty + gray border).
 * Connector line is navy up to current, gray after.
 */
export function Stepper({ steps, currentIndex, className }: StepperProps) {
  return (
    <ol
      className={cn(
        "flex w-full items-center justify-between gap-2",
        className,
      )}
      aria-label="Pasos del proceso"
    >
      {steps.map((step, idx) => {
        const isComplete = idx < currentIndex;
        const isActive = idx === currentIndex;
        const isLast = idx === steps.length - 1;

        const dotClasses = cn(
          "flex h-8 w-8 items-center justify-center rounded-full border-2 text-[12px] font-semibold transition-colors duration-fast",
          isComplete &&
            "border-[color:var(--interactive-primary)] bg-[color:var(--interactive-primary)] text-white",
          isActive &&
            "border-[color:var(--interactive-primary)] bg-[color:var(--interactive-primary)] text-white shadow-sm",
          !isComplete &&
            !isActive &&
            "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-tertiary)]",
        );

        return (
          <li
            key={step.id}
            className="flex flex-1 items-center gap-2 min-w-0"
            aria-current={isActive ? "step" : undefined}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className={dotClasses} aria-hidden="true">
                {isComplete ? <Check className="h-4 w-4" weight="bold" /> : idx + 1}
              </span>
              <span
                className={cn(
                  "truncate text-[13px] font-medium",
                  isActive
                    ? "text-[color:var(--text-primary)]"
                    : isComplete
                      ? "text-[color:var(--text-brand)]"
                      : "text-[color:var(--text-tertiary)]",
                )}
              >
                {step.label}
              </span>
            </div>
            {!isLast && (
              <span
                aria-hidden="true"
                className={cn(
                  "h-px flex-1",
                  isComplete
                    ? "bg-[color:var(--interactive-primary)]"
                    : "bg-[color:var(--border-default)]",
                )}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
