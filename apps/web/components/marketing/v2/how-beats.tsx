"use client";

import type { Icon as PhosphorIcon } from "@phosphor-icons/react";

/**
 * How-it-works beats — presentational + controlled by the parent
 * (how-it-works.tsx), which owns the active index, the slow auto-cycle and
 * the matching screenshot. Each beat is a button: clicking it jumps the
 * whole section (highlight + image) to that step.
 */
export type Beat = {
  n: string;
  title: string;
  body: string;
  icon: PhosphorIcon;
};

export function HowBeats({
  beats,
  active,
  onSelect,
}: {
  beats: readonly Beat[];
  active: number;
  onSelect: (i: number) => void;
}) {
  return (
    <ol className="flex flex-col gap-2.5">
      {beats.map((b, i) => {
        const Icon = b.icon;
        const on = i === active;
        return (
          <li key={b.n}>
            <button
              type="button"
              onClick={() => onSelect(i)}
              aria-pressed={on}
              className={`flex w-full items-start gap-4 rounded-2xl border p-4 text-left transition-[background-color,border-color,transform] duration-300 ${
                on
                  ? "border-[color:var(--border-ai)] bg-[color:var(--surface-teal-muted)] lg:translate-x-1"
                  : "border-transparent hover:border-[color:var(--border-default)] hover:bg-[color:var(--surface-page)]"
              }`}
            >
              <span
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors duration-300 ${
                  on
                    ? "bg-[color:var(--interactive-secondary)] text-white"
                    : "bg-[color:var(--surface-sunken)] text-[color:var(--text-teal)]"
                }`}
              >
                <Icon className="h-5 w-5" weight="duotone" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <div className="flex items-baseline gap-2">
                  <h3 className="text-[16px] font-semibold text-[color:var(--text-primary)]">
                    {b.title}
                  </h3>
                  <span className="font-mono text-[11px] text-[color:var(--text-tertiary)]">
                    {b.n}
                  </span>
                </div>
                <p className="mt-0.5 text-[13.5px] leading-[1.5] text-[color:var(--text-secondary)]">
                  {b.body}
                </p>
              </div>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
