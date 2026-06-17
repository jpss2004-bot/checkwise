"use client";

import { useState } from "react";
import { CaretRight } from "@phosphor-icons/react";

import type {
  ClientCalendarItem,
  ClientCalendarProvider,
  ClientCalendarRisk,
} from "@/lib/api/client";

import {
  CLIENT_RISK_ORDER,
  RISK_ICON,
  SEMAPHORE_DOT,
  formatLongDate,
} from "./client-calendar-shared";
import { ObligationBlock } from "./obligation-block";

// Detailed obligations grouped by what needs attention first. Only groups
// with items render; the calm "Al día" group sits last for a complete
// systematic review without dominating the card.
const GROUPS: { risk: ClientCalendarRisk; label: string }[] = [
  { risk: "overdue", label: "Vencidas" },
  { risk: "action_required", label: "Por corregir" },
  { risk: "due_soon", label: "Vencen pronto" },
  { risk: "in_review", label: "En revisión" },
  { risk: "upcoming", label: "Próximas" },
  { risk: "on_track", label: "Al día" },
];

const GROUP_CAP = 5;

export function ProviderReviewCard({
  provider,
  items,
  today,
  returnToHref,
  open,
  onToggle,
}: {
  provider: ClientCalendarProvider;
  items: ClientCalendarItem[];
  today: Date;
  returnToHref: string;
  open: boolean;
  onToggle: () => void;
}) {
  const overdue = items.filter((i) => i.risk_level === "overdue").length;
  const dueSoon = items.filter((i) => i.risk_level === "due_soon").length;
  const correction = items.filter(
    (i) => i.risk_level === "action_required",
  ).length;

  const grouped = GROUPS.map((g) => ({
    ...g,
    items: items
      .filter((i) => i.risk_level === g.risk)
      .sort((a, b) => a.deadline_iso.localeCompare(b.deadline_iso)),
  })).filter((g) => g.items.length > 0);

  return (
    <article
      id={`provider-card-${provider.vendor_id}`}
      className={
        "scroll-mt-4 overflow-hidden rounded-xl border bg-[color:var(--surface-raised)] " +
        (provider.semaphore_level === "red"
          ? "border-[color:var(--status-error-border)]"
          : "border-[color:var(--border-default)]")
      }
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-start gap-3 px-5 py-4 text-left transition-colors hover:bg-[color:var(--surface-hover)]"
      >
        <CaretRight
          className={
            "mt-1 h-4 w-4 shrink-0 text-[color:var(--text-tertiary)] transition-transform " +
            (open ? "rotate-90" : "")
          }
          weight="bold"
          aria-hidden="true"
        />
        <span
          aria-hidden="true"
          className={
            "mt-1 h-3 w-3 shrink-0 rounded-full " +
            SEMAPHORE_DOT[provider.semaphore_level]
          }
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h3 className="text-base font-semibold text-[color:var(--text-primary)]">
              {provider.vendor_name}
            </h3>
            <span className="font-mono text-xs tabular-nums text-[color:var(--text-tertiary)]">
              {provider.compliance_pct}% al día
            </span>
          </div>
          <div className="mt-2 h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-[color:var(--surface-sunken)]">
            <div
              className={
                "h-full rounded-full " +
                (provider.semaphore_level === "red"
                  ? "bg-[color:var(--status-error-text)]"
                  : provider.semaphore_level === "yellow"
                    ? "bg-[color:var(--status-warning-text)]"
                    : "bg-[color:var(--status-success-text)]")
              }
              style={{ width: `${Math.max(provider.compliance_pct, 2)}%` }}
            />
          </div>
          <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs">
            <SummaryChip n={overdue} label="vencidas" tone="error" />
            <SummaryChip n={correction} label="por corregir" tone="error" />
            <SummaryChip n={dueSoon} label="por vencer" tone="warning" />
            {provider.next_deadline_iso ? (
              <span className="text-[color:var(--text-tertiary)]">
                Próximo: {formatLongDate(provider.next_deadline_iso)}
              </span>
            ) : null}
          </div>
        </div>
      </button>

      {open ? (
        <div className="space-y-5 border-t border-[color:var(--border-subtle)] px-5 py-4">
          {grouped.length === 0 ? (
            <p className="text-sm text-[color:var(--text-secondary)]">
              Sin obligaciones registradas para este proveedor en el año.
            </p>
          ) : (
            grouped.map((g) => (
              <ObligationGroup
                key={g.risk}
                label={g.label}
                risk={g.risk}
                items={g.items}
                today={today}
                returnToHref={returnToHref}
              />
            ))
          )}
        </div>
      ) : null}
    </article>
  );
}

function SummaryChip({
  n,
  label,
  tone,
}: {
  n: number;
  label: string;
  tone: "error" | "warning";
}) {
  if (n === 0) return null;
  return (
    <span
      className={
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium " +
        (tone === "error"
          ? "border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]"
          : "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]")
      }
    >
      <span className="font-mono tabular-nums">{n}</span>
      {label}
    </span>
  );
}

function ObligationGroup({
  label,
  risk,
  items,
  today,
  returnToHref,
}: {
  label: string;
  risk: ClientCalendarRisk;
  items: ClientCalendarItem[];
  today: Date;
  returnToHref: string;
}) {
  const [showAll, setShowAll] = useState(false);
  const GroupIcon = RISK_ICON[risk];
  const visible = showAll ? items : items.slice(0, GROUP_CAP);
  const hidden = items.length - visible.length;
  const severe = CLIENT_RISK_ORDER[risk] <= CLIENT_RISK_ORDER.action_required;
  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <GroupIcon
          className={
            "h-4 w-4 " +
            (severe
              ? "text-[color:var(--status-error-text)]"
              : "text-[color:var(--text-secondary)]")
          }
          weight="fill"
          aria-hidden="true"
        />
        <h4 className="text-sm font-semibold text-[color:var(--text-primary)]">
          {label}
        </h4>
        <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]">
          {items.length}
        </span>
      </div>
      <ul className="space-y-2.5">
        {visible.map((item) => (
          <ObligationBlock
            key={`${item.requirement_code ?? item.requirement_name}-${item.period_key ?? ""}`}
            item={item}
            today={today}
            returnToHref={returnToHref}
          />
        ))}
      </ul>
      {hidden > 0 ? (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="mt-2 text-xs font-medium text-[color:var(--text-brand)] hover:underline"
        >
          Ver {hidden} más
        </button>
      ) : showAll && items.length > GROUP_CAP ? (
        <button
          type="button"
          onClick={() => setShowAll(false)}
          className="mt-2 text-xs font-medium text-[color:var(--text-brand)] hover:underline"
        >
          Ver menos
        </button>
      ) : null}
    </section>
  );
}
