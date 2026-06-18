/**
 * Shared dashboard primitives used by the vendor, client, and admin
 * dashboards. The original ``Tile`` component was redefined three
 * separate times across these surfaces; consolidating into one
 * component family removes drift and lets every surface inherit the
 * same hover / animation / tone behavior.
 */

import type { ReactNode } from "react";
import { ArrowRight, type Icon } from "@phosphor-icons/react";
import Link from "next/link";

import { Sparkline, type ChartTone } from "@/components/checkwise/charts";
import { cn } from "@/lib/utils";

export type StatTone =
  | "neutral"
  | "brand"
  | "teal"
  | "success"
  | "warning"
  | "error"
  | "info";

const TONE_ACCENT: Record<StatTone, string> = {
  neutral: "text-[color:var(--text-primary)]",
  brand: "text-[color:var(--text-brand)]",
  teal: "text-[color:var(--text-teal)]",
  success: "text-[color:var(--status-success-text)]",
  warning: "text-[color:var(--status-warning-text)]",
  error: "text-[color:var(--status-error-text)]",
  info: "text-[color:var(--status-info-text)]",
};

const TONE_BORDER: Record<StatTone, string> = {
  neutral: "border-[color:var(--border-default)]",
  brand: "border-[color:var(--border-default)]",
  teal: "border-[color:var(--status-ai-border)]",
  success: "border-[color:var(--status-success-border)]",
  warning: "border-[color:var(--status-warning-border)]",
  error: "border-[color:var(--status-error-border)]",
  info: "border-[color:var(--status-info-border)]",
};

const TONE_ICON_BG: Record<StatTone, string> = {
  neutral: "bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)]",
  brand: "bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]",
  teal: "bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]",
  success:
    "bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]",
  warning:
    "bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]",
  error:
    "bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]",
  info: "bg-[color:var(--status-info-bg)] text-[color:var(--status-info-text)]",
};

const TONE_TO_CHART: Record<StatTone, ChartTone> = {
  neutral: "neutral",
  brand: "brand",
  teal: "teal",
  success: "success",
  warning: "warning",
  error: "error",
  info: "info",
};

interface StatCardProps {
  label: string;
  value: number | string;
  /** Short caption below the value. */
  caption?: ReactNode;
  /** Lucide / Phosphor icon component. */
  icon?: Icon;
  tone?: StatTone;
  /** Time-series for a sparkline. */
  trend?: number[];
  /** Optional href — turns the card into a link. */
  href?: string;
  className?: string;
  /** Right-aligned slot (badge, button) shown next to the value. */
  trailing?: ReactNode;
  /** Compact mode — used inside dense KPI strips. */
  compact?: boolean;
}

/**
 * Single statistic card — supports an icon, sparkline trend, optional
 * link, and a tone that colors borders + accents.
 */
export function StatCard({
  label,
  value,
  caption,
  icon: IconComponent,
  tone = "neutral",
  trend,
  href,
  className,
  trailing,
  compact = false,
}: StatCardProps) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          {IconComponent ? (
            <span
              className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-md",
                TONE_ICON_BG[tone],
              )}
              aria-hidden="true"
            >
              <IconComponent className="h-4 w-4" weight="duotone" />
            </span>
          ) : null}
          <p
            className={cn(
              "font-mono uppercase tracking-wide text-[color:var(--text-tertiary)]",
              compact ? "text-[10px]" : "text-[11px]",
            )}
          >
            {label}
          </p>
        </div>
        {trailing ? <div className="shrink-0">{trailing}</div> : null}
      </div>
      <div className={cn("mt-3 flex items-end justify-between gap-3")}>
        <p
          className={cn(
            "font-mono font-semibold tabular-nums leading-none",
            compact ? "text-2xl" : "text-3xl",
            TONE_ACCENT[tone],
          )}
        >
          {value}
        </p>
        {trend && trend.length > 1 ? (
          <Sparkline
            data={trend}
            width={compact ? 64 : 88}
            height={compact ? 22 : 28}
            tone={TONE_TO_CHART[tone]}
          />
        ) : null}
      </div>
      {caption ? (
        <p className="mt-2 text-[12px] leading-snug text-[color:var(--text-secondary)]">
          {caption}
        </p>
      ) : null}
      {href ? (
        <div className="mt-3 flex items-center gap-1 text-[11px] font-medium text-[color:var(--text-link)]">
          <span>Ver detalle</span>
          <ArrowRight className="h-3 w-3" weight="bold" aria-hidden="true" />
        </div>
      ) : null}
    </>
  );

  const baseClassName = cn(
    "block rounded-lg border bg-[color:var(--surface-raised)] p-4 shadow-xs transition-all duration-fast",
    TONE_BORDER[tone],
    href
      ? "cw-hover-lift hover:border-[color:var(--border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40"
      : "",
    compact ? "p-3" : "p-4",
    className,
  );

  if (href) {
    return (
      <Link href={href} className={baseClassName}>
        {body}
      </Link>
    );
  }
  return <div className={baseClassName}>{body}</div>;
}

// ─── StatGroup — labelled grid of cards ───────────────────────────

interface StatGroupProps {
  title?: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  /** Tailwind grid template — defaults to 2/4 column responsive grid. */
  columnsClassName?: string;
  className?: string;
}

export function StatGroup({
  title,
  description,
  children,
  columnsClassName = "grid-cols-2 lg:grid-cols-4",
  className,
}: StatGroupProps) {
  return (
    <section className={cn("space-y-3", className)}>
      {(title || description) && (
        <header className="space-y-0.5">
          {title ? (
            <h2 className="text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
              {title}
            </h2>
          ) : null}
          {description ? (
            <p className="text-xs text-[color:var(--text-secondary)]">
              {description}
            </p>
          ) : null}
        </header>
      )}
      <div className={cn("cw-stagger grid gap-3", columnsClassName)}>
        {children}
      </div>
    </section>
  );
}

// ─── Surface — generic dashboard panel ────────────────────────────

interface SurfaceProps {
  title?: ReactNode;
  description?: ReactNode;
  icon?: Icon;
  /** Right-side actions (e.g. "Ver todo →"). */
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  /** Mute the surface — lighter background, used for subdued panels. */
  muted?: boolean;
  /**
   * Heading level for the panel title. Top-level panels sit directly under
   * the page ``<h1>``, so default to ``h2`` to keep the document outline
   * unbroken (no h1→h3 skip — audit P3.16). Pass 3 for a nested panel.
   */
  headingLevel?: 2 | 3;
}

/**
 * Generic dashboard surface — header with title/icon/actions and a
 * body slot. Replaces the dozen-ish ad-hoc card definitions across the
 * dashboards.
 */
export function Surface({
  title,
  description,
  icon: IconComponent,
  actions,
  children,
  className,
  bodyClassName,
  muted = false,
  headingLevel = 2,
}: SurfaceProps) {
  const HeadingTag = headingLevel === 3 ? "h3" : "h2";
  return (
    <section
      className={cn(
        "rounded-lg border border-[color:var(--border-default)] shadow-xs",
        muted
          ? "bg-[color:var(--surface-page)]"
          : "bg-[color:var(--surface-raised)]",
        className,
      )}
    >
      {(title || description || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-[color:var(--border-subtle)] px-5 py-3.5">
          <div className="min-w-0 space-y-0.5">
            <HeadingTag className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
              {IconComponent ? (
                <IconComponent
                  className="h-4 w-4 text-[color:var(--text-brand)]"
                  weight="duotone"
                  aria-hidden="true"
                />
              ) : null}
              {title}
            </HeadingTag>
            {description ? (
              <p className="text-xs text-[color:var(--text-secondary)]">
                {description}
              </p>
            ) : null}
          </div>
          {actions ? (
            <div className="flex shrink-0 items-center gap-2">{actions}</div>
          ) : null}
        </header>
      )}
      <div className={cn("p-5", bodyClassName)}>{children}</div>
    </section>
  );
}

// ─── EmptyState ──────────────────────────────────────────────────

interface EmptyStateProps {
  icon?: Icon;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({
  icon: IconComponent,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-[color:var(--border-default)] bg-[color:var(--surface-page)] px-4 py-8 text-center",
        className,
      )}
    >
      {IconComponent ? (
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--surface-sunken)] text-[color:var(--text-tertiary)]">
          <IconComponent className="h-5 w-5" weight="duotone" aria-hidden="true" />
        </span>
      ) : null}
      <p className="text-[13px] font-medium text-[color:var(--text-primary)]">
        {title}
      </p>
      {description ? (
        <p className="max-w-prose text-xs text-[color:var(--text-secondary)]">
          {description}
        </p>
      ) : null}
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}
