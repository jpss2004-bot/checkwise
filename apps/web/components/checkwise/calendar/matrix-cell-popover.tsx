"use client";

import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";

import {
  RISK_ICON,
  RISK_LABEL,
  SEMAPHORE_DOT,
  type CalendarRisk,
} from "./calendar-shared";

/**
 * A lightweight hover/focus preview for one matrix cell — lists the
 * obligations sitting inside a provider-month so the client can scan a busy
 * cell without the click + scroll-to-detail round-trip. Read-only: clicking
 * the cell itself still drives the detail panel below; this is preview only.
 *
 * Positioning mirrors the provider calendar's ``cell-popover`` (fixed-position
 * portal, flips above when it would overflow the viewport bottom), but speaks
 * the client's worst-first risk vocabulary instead of provider doc-states.
 */

export type CellPreviewItem = {
  key: string;
  /** The obligation / requirement name. */
  label: string;
  /** Drives the leading dot + the risk word; worst-first vocabulary. */
  risk: CalendarRisk;
  /** Short relative/absolute deadline string, right-aligned. */
  deadline?: string;
  /** Muted second line, e.g. "IMSS · 1er bimestre". */
  sublabel?: string;
};

const MAX_VISIBLE = 6;
const POPOVER_WIDTH = 280;
const VIEWPORT_MARGIN = 8;
const GAP = 6;

// Worst-risk → semaphore dot tone, so the preview dots match the cell color
// language the rest of the calendar uses.
const RISK_DOT: Record<CalendarRisk, string> = {
  overdue: SEMAPHORE_DOT.red,
  action_required: SEMAPHORE_DOT.red,
  due_soon: SEMAPHORE_DOT.yellow,
  in_review: SEMAPHORE_DOT.yellow,
  upcoming: SEMAPHORE_DOT.yellow,
  on_track: SEMAPHORE_DOT.green,
};

type Position = { top: number; left: number; placement: "below" | "above" };

function computePosition(triggerRect: DOMRect, popoverHeight: number): Position {
  // Left-align to the cell (extends rightward) rather than centering on it.
  // Centering made the popover for the left-edge month cells spill left OVER
  // the sticky provider-name column — which read as the popover "covering the
  // names". Anchoring to the cell's left edge keeps it clear of that column;
  // the viewport clamp below still pulls it in for the right-edge months.
  let left = triggerRect.left;
  if (left + POPOVER_WIDTH > window.innerWidth - VIEWPORT_MARGIN) {
    left = window.innerWidth - POPOVER_WIDTH - VIEWPORT_MARGIN;
  }
  if (left < VIEWPORT_MARGIN) left = VIEWPORT_MARGIN;
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

export function MatrixCellPopover({
  triggerRef,
  items,
  title,
  open,
  onEnter,
  onLeave,
}: {
  triggerRef: RefObject<HTMLElement | null>;
  items: CellPreviewItem[];
  title: string;
  open: boolean;
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
    const rect = triggerRef.current.getBoundingClientRect();
    const estimatedHeight =
      36 + Math.min(items.length, MAX_VISIBLE) * 38 + (items.length > MAX_VISIBLE ? 28 : 0);
    setPosition(computePosition(rect, estimatedHeight));
  }, [open, triggerRef, items.length]);

  useEffect(() => {
    if (!open) return;
    const reposition = () => {
      if (!triggerRef.current || !popoverRef.current) return;
      const rect = triggerRef.current.getBoundingClientRect();
      setPosition(computePosition(rect, popoverRef.current.offsetHeight));
    };
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    return () => {
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
    };
  }, [open, triggerRef]);

  if (!mounted || !open || !position || items.length === 0) return null;

  const visible = items.slice(0, MAX_VISIBLE);
  const overflow = items.length - visible.length;

  return createPortal(
    <div
      ref={popoverRef}
      role="tooltip"
      aria-label={title}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      style={{ position: "fixed", top: position.top, left: position.left, width: POPOVER_WIDTH, zIndex: 50 }}
      className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-overlay)] p-2 shadow-lg cw-fade-up"
      data-placement={position.placement}
    >
      <p className="px-2 pb-1.5 pt-1 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {title}
      </p>
      <ul className="space-y-px">
        {visible.map((item) => {
          const Icon = RISK_ICON[item.risk];
          return (
            <li
              key={item.key}
              className="flex items-start gap-2 rounded-md px-2 py-1.5"
              title={`${RISK_LABEL[item.risk]}${item.deadline ? ` · ${item.deadline}` : ""}`}
            >
              <span
                aria-hidden="true"
                className={"mt-1 h-2 w-2 shrink-0 rounded-full " + RISK_DOT[item.risk]}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12px] text-[color:var(--text-primary)]">
                  {item.label}
                </span>
                {item.sublabel ? (
                  <span className="block truncate text-[10px] text-[color:var(--text-secondary)]">
                    {item.sublabel}
                  </span>
                ) : null}
              </span>
              <span className="mt-0.5 inline-flex shrink-0 items-center gap-1 font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
                <Icon className="h-3 w-3" weight="bold" aria-hidden="true" />
                {item.deadline ?? ""}
              </span>
            </li>
          );
        })}
      </ul>
      {overflow > 0 ? (
        <p className="border-t border-[color:var(--border-subtle)] px-2 pb-1 pt-1.5 text-[11px] text-[color:var(--text-tertiary)]">
          + {overflow} más en esta celda
        </p>
      ) : null}
    </div>,
    document.body,
  );
}
