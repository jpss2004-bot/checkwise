"use client";

import { useEffect, type RefObject } from "react";
import { createPortal } from "react-dom";

import { DOC_STATE_LABELS } from "@/components/checkwise/doc-state-badge";
import { MONTH_LABELS_ES } from "@/lib/api/portal";
import type { DocumentStateCode } from "@/lib/types";

import { riskRank } from "./calendar-shared";
import type { CalendarEntry } from "./types";
import { useAnchoredPopover } from "./use-anchored-popover";

const MAX_VISIBLE = 6;
const POPOVER_WIDTH = 300;

const STATE_DOT: Record<DocumentStateCode, string> = {
  approved:     "bg-[color:var(--doc-approved-bg)]     ring-[color:var(--doc-approved-border)]",
  in_review:    "bg-[color:var(--doc-in-review-bg)]    ring-[color:var(--doc-in-review-border)]",
  uploaded:     "bg-[color:var(--doc-uploaded-bg)]     ring-[color:var(--doc-uploaded-border)]",
  rejected:     "bg-[color:var(--doc-rejected-bg)]     ring-[color:var(--doc-rejected-border)]",
  expired:      "bg-[color:var(--doc-expired-bg)]      ring-[color:var(--doc-expired-border)]",
  possible_mismatch: "bg-[color:var(--doc-needs-review-bg)] ring-[color:var(--doc-needs-review-border)]",
  needs_review: "bg-[color:var(--doc-needs-review-bg)] ring-[color:var(--doc-needs-review-border)]",
  pending:      "bg-[color:var(--doc-pending-bg)]      ring-[color:var(--doc-pending-border)]",
  empty:        "bg-[color:var(--doc-empty-bg)]        ring-[color:var(--doc-empty-border)]",
};

function formatDay(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("es-MX", {
      day: "2-digit",
      month: "short",
    });
  } catch {
    return "";
  }
}

export function CellPopover({
  triggerRef,
  events,
  month,
  open,
  onSelect,
  onEnter,
  onLeave,
}: {
  triggerRef: RefObject<HTMLElement | null>;
  events: CalendarEntry[];
  month: number;
  open: boolean;
  onSelect: (id: string) => void;
  onEnter: () => void;
  onLeave: () => void;
}) {
  // Provider cell popover anchors centered on its trigger cell.
  const estimatedHeight =
    36 + Math.min(events.length, MAX_VISIBLE) * 32 + (events.length > MAX_VISIBLE ? 28 : 0);
  const { mounted, position, popoverRef } = useAnchoredPopover({
    triggerRef,
    open,
    width: POPOVER_WIDTH,
    align: "center",
    estimatedHeight,
  });

  // Touch/click dismissal. The popover opens on hover for mouse users, but
  // a tapped-open popover (a multi-obligation cell on touch) has no
  // mouseleave to close it. Dismiss on an outside pointer or Escape so the
  // provider is never trapped in an open menu and can reach the grid again
  // (Portal Proveedor, 2ª revisión, Calendario #2).
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node | null;
      if (!target) return;
      if (popoverRef.current?.contains(target)) return;
      if (triggerRef.current?.contains(target)) return;
      onLeave();
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onLeave();
    };
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onLeave, triggerRef, popoverRef]);

  if (!mounted || !open || !position) return null;

  // A6 — most-urgent-first: order by the server risk tier (overdue → … →
  // on_track), deadline as the tiebreak. So a busy month's overdue/rejected
  // obligations lead instead of appearing in catalog order.
  const ordered = [...events].sort(
    (a, b) =>
      riskRank(a.risk_level) - riskRank(b.risk_level) ||
      a.deadline_iso.localeCompare(b.deadline_iso),
  );
  // Render every obligation — the container scrolls within its capped
  // maxHeight. Previously this sliced to MAX_VISIBLE and showed a
  // non-interactive "+N más" line, leaving obligations 7..N with no way to
  // be opened (Portal Proveedor, 2ª revisión, Calendario #2).
  const visible = ordered;

  return createPortal(
    <div
      ref={popoverRef}
      role="menu"
      aria-label={`Obligaciones de ${MONTH_LABELS_ES[month]}`}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      style={{
        position: "fixed",
        top: position.top,
        left: position.left,
        width: POPOVER_WIDTH,
        maxHeight: position.maxHeight,
        overflowY: "auto",
        zIndex: 50,
      }}
      className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-overlay)] p-2 shadow-lg cw-fade-up"
      data-placement={position.placement}
    >
      <p className="px-2 pb-1.5 pt-1 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {MONTH_LABELS_ES[month]} · {events.length}{" "}
        {events.length === 1 ? "obligación" : "obligaciones"}
      </p>
      <ul className="space-y-px">
        {visible.map((event) => {
          // Jorge feedback (2026-05-21) — surface filename + upload
          // date so the cell tooltip gives the provider an actual
          // document anchor, not just the deadline.
          const uploaded = event.submitted_at
            ? formatDay(event.submitted_at)
            : null;
          const tooltipParts = [DOC_STATE_LABELS[event.state]];
          if (event.filename) tooltipParts.push(event.filename);
          if (uploaded) tooltipParts.push(`Cargado ${uploaded}`);
          return (
            <li key={event.id}>
              <button
                type="button"
                role="menuitem"
                onClick={() => onSelect(event.id)}
                title={tooltipParts.join(" · ")}
                className="group flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-[color:var(--surface-hover)] focus:outline-none focus-visible:bg-[color:var(--surface-hover)]"
              >
                <span
                  aria-hidden="true"
                  className={
                    "mt-1 h-2 w-2 shrink-0 rounded-full ring-1 ring-inset " +
                    STATE_DOT[event.state]
                  }
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12px] text-[color:var(--text-primary)]">
                    {event.obligation}
                  </span>
                  {event.period_label ? (
                    <span className="block truncate text-[10px] text-[color:var(--text-secondary)]">
                      Periodo: {event.period_label}
                    </span>
                  ) : null}
                  {event.filename ? (
                    <span className="block truncate text-[10px] text-[color:var(--text-tertiary)]">
                      {event.filename}
                      {uploaded ? ` · ${uploaded}` : ""}
                    </span>
                  ) : null}
                </span>
                <span className="mt-0.5 shrink-0 font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)] group-hover:text-[color:var(--text-secondary)]">
                  {formatDay(event.deadline_iso)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>,
    document.body,
  );
}
