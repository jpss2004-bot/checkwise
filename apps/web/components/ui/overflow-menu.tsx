"use client";

import * as React from "react";
import { DotsThreeVertical } from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Minimal click-toggled overflow menu.
 *
 * Used by header chrome that has more actions than fit in the primary
 * action cluster — collapses the long tail into a single ``⋮`` button
 * that opens a list of secondary actions. Click-outside and Esc both
 * collapse the menu; clicking a menu item also collapses (the item's
 * own ``onSelect`` runs first).
 *
 * Deliberately small (~60 lines including a11y wiring) so we don't
 * add ``@radix-ui/react-dropdown-menu`` for one use site. If a second
 * surface needs this we can either keep the lightweight component or
 * swap it for the Radix primitive — call sites use the same API.
 *
 * Accessibility notes:
 *   • Trigger: ``aria-haspopup="menu"`` + ``aria-expanded``.
 *   • Panel: ``role="menu"`` + ``aria-orientation="vertical"``.
 *   • Items: ``role="menuitem"``.
 *   • Esc closes; click-outside closes (mouse + touch).
 *   • Keyboard arrow-key navigation is intentionally NOT implemented
 *     today — the consumer surfaces (M2 Reportes header) have ≤6
 *     items and the actions are all anchored on the same row of the
 *     visible page, so Tab navigation through them is good enough
 *     for the tester round. Bump to arrow-key nav when a screen
 *     reader user reports the gap.
 */

export interface OverflowMenuProps {
  /** Trigger button label for screen readers. */
  triggerAriaLabel: string;
  /** Optional className applied to the trigger button. */
  triggerClassName?: string;
  /** Optional className applied to the floating panel. */
  panelClassName?: string;
  children: React.ReactNode;
}

export function OverflowMenu({
  triggerAriaLabel,
  triggerClassName,
  panelClassName,
  children,
}: OverflowMenuProps) {
  const [open, setOpen] = React.useState(false);
  const rootRef = React.useRef<HTMLDivElement | null>(null);

  // Esc closes.
  React.useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Click-outside closes. Uses ``pointerdown`` so touch + mouse fire
  // the same handler; ``click`` would miss a touch-tap that lifts
  // outside the menu.
  React.useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current) return;
      if (event.target instanceof Node && rootRef.current.contains(event.target)) {
        return;
      }
      setOpen(false);
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  return (
    <div ref={rootRef} className="relative inline-block">
      <Button
        variant="ghost"
        size="sm"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={triggerAriaLabel}
        onClick={() => setOpen((v) => !v)}
        className={cn("px-2", triggerClassName)}
      >
        <DotsThreeVertical className="h-5 w-5" weight="bold" aria-hidden="true" />
      </Button>
      {open ? (
        <ul
          role="menu"
          aria-orientation="vertical"
          aria-label={triggerAriaLabel}
          onClick={() => setOpen(false)}
          className={cn(
            "absolute right-0 top-full z-20 mt-1 min-w-[200px] overflow-hidden rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] py-1 text-[13px] shadow-lg",
            panelClassName,
          )}
        >
          {children}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * One row inside an :class:`OverflowMenu`. Wraps an arbitrary node so
 * the consumer can pass a Button, Link, or plain ``<button>`` — useful
 * for actions that need the ``asChild`` Link pattern (open in new tab,
 * trigger native download, etc.) without the menu component having to
 * know about each variant.
 */
export interface OverflowMenuItemProps {
  children: React.ReactNode;
  className?: string;
}

export function OverflowMenuItem({ children, className }: OverflowMenuItemProps) {
  return (
    <li role="menuitem" className={cn("contents", className)}>
      {children}
    </li>
  );
}
