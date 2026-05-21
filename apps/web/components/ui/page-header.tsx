import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * PageHeader — single header pattern reused across every product surface.
 *
 * The doctrine asks every surface to answer "what is this and what should
 * I do next" within the first viewport. PageHeader provides the
 * skeleton: a small mono eyebrow that names the product object (so the
 * user always knows what surface they're on), a tight title in the
 * primary type token, an optional description that frames the user's
 * decision, and an actions slot for primary/secondary CTAs.
 *
 * SectionHeader is the in-page sibling for sub-sections.
 */

interface PageHeaderProps {
  /** Mono uppercase eyebrow — the product object this surface is about. */
  eyebrow?: string;
  /** Title of the surface. Should fit one line on lg+. */
  title: string;
  /** One-sentence framing of the user's decision on this surface. */
  description?: React.ReactNode;
  /** Primary + secondary CTAs. Caller supplies <Button> elements. */
  actions?: React.ReactNode;
  /** Optional badge/status indicator rendered next to the title. */
  trailing?: React.ReactNode;
  className?: string;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  trailing,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        "cw-fade-up flex flex-wrap items-end justify-between gap-4",
        className,
      )}
    >
      <div className="min-w-0 space-y-1.5">
        {eyebrow ? (
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-teal)]">
            {eyebrow}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="text-3xl font-semibold leading-[1.1] tracking-[-0.015em] text-balance text-[color:var(--text-primary)] sm:text-4xl">
            {title}
          </h1>
          {trailing}
        </div>
        {description ? (
          <p className="max-w-prose text-[13px] leading-[1.55] text-[color:var(--text-secondary)]">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </header>
  );
}

interface SectionHeaderProps {
  title: React.ReactNode;
  /** Optional eyebrow for the in-page section. */
  eyebrow?: React.ReactNode;
  description?: React.ReactNode;
  /** Right-aligned filter chips, sort buttons, or inline actions. */
  trailing?: React.ReactNode;
  /** Optional icon rendered to the left of the title. */
  icon?: React.ReactNode;
  className?: string;
}

export function SectionHeader({
  title,
  eyebrow,
  description,
  trailing,
  icon,
  className,
}: SectionHeaderProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-end justify-between gap-3 border-b border-[color:var(--border-subtle)] pb-3",
        className,
      )}
    >
      <div className="min-w-0 space-y-1">
        {eyebrow ? (
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
            {eyebrow}
          </p>
        ) : null}
        <div className="flex items-center gap-2">
          {icon}
          <h2 className="text-[15px] font-semibold leading-snug text-[color:var(--text-primary)]">
            {title}
          </h2>
        </div>
        {description ? (
          <p className="text-xs text-[color:var(--text-secondary)]">{description}</p>
        ) : null}
      </div>
      {trailing}
    </div>
  );
}
