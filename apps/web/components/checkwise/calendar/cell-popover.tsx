"use client";

import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";

import { DOC_STATE_LABELS } from "@/components/checkwise/doc-state-badge";
import { MONTH_LABELS_ES } from "@/lib/api/portal";
import type { DocumentStateCode } from "@/lib/types";

import type { CalendarEntry } from "./types";

const MAX_VISIBLE = 6;
const POPOVER_WIDTH = 300;
const VIEWPORT_MARGIN = 8;
const GAP = 6;

const STATE_DOT: Record<DocumentStateCode, string> = {
  approved:     "bg-[color:var(--doc-approved-bg)]     ring-[color:var(--doc-approved-border)]",
  in_review:    "bg-[color:var(--doc-in-review-bg)]    ring-[color:var(--doc-in-review-border)]",
  uploaded:     "bg-[color:var(--doc-uploaded-bg)]     ring-[color:var(--doc-uploaded-border)]",
  rejected:     "bg-[color:var(--doc-rejected-bg)]     ring-[color:var(--doc-rejected-border)]",
  expired:      "bg-[color:var(--doc-expired-bg)]      ring-[color:var(--doc-expired-border)]",
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

type Position = {
  top: number;
  left: number;
  placement: "below" | "above";
};

function computePosition(
  triggerRect: DOMRect,
  popoverHeight: number,
): Position {
  let left = triggerRect.left + triggerRect.width / 2 - POPOVER_WIDTH / 2;
  if (left < VIEWPORT_MARGIN) left = VIEWPORT_MARGIN;
  if (left + POPOVER_WIDTH > window.innerWidth - VIEWPORT_MARGIN) {
    left = window.innerWidth - POPOVER_WIDTH - VIEWPORT_MARGIN;
  }

  let top = triggerRect.bottom + GAP;
  let placement: Position["placement"] = "below";
  if (top + popoverHeight > window.innerHeight - VIEWPORT_MARGIN) {
    const aboveTop = triggerRect.top - popoverHeight - GAP;
    if (aboveTop >= VIEWPORT_MARGIN) {
      top = aboveTop;
      placement = "above";
    }
  }

  return { top, left, placement };
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
  const popoverRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<Position | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) {
      setPosition(null);
      return;
    }
    const triggerRect = triggerRef.current.getBoundingClientRect();
    const estimatedHeight =
      36 + Math.min(events.length, MAX_VISIBLE) * 32 + (events.length > MAX_VISIBLE ? 28 : 0);
    setPosition(computePosition(triggerRect, estimatedHeight));
  }, [open, triggerRef, events.length]);

  useEffect(() => {
    if (!open) return;
    const handleScroll = () => {
      if (!triggerRef.current || !popoverRef.current) return;
      const triggerRect = triggerRef.current.getBoundingClientRect();
      setPosition(computePosition(triggerRect, popoverRef.current.offsetHeight));
    };
    window.addEventListener("scroll", handleScroll, true);
    window.addEventListener("resize", handleScroll);
    return () => {
      window.removeEventListener("scroll", handleScroll, true);
      window.removeEventListener("resize", handleScroll);
    };
  }, [open, triggerRef]);

  if (!mounted || !open || !position) return null;

  const visible = events.slice(0, MAX_VISIBLE);
  const overflow = events.length - visible.length;

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
      {overflow > 0 && (
        <p className="border-t border-[color:var(--border-subtle)] px-2 pb-1 pt-1.5 text-[11px] text-[color:var(--text-tertiary)]">
          + {overflow} más en esta celda
        </p>
      )}
    </div>,
    document.body,
  );
}
