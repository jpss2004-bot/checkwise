import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type RefObject,
} from "react";

/**
 * Shared positioning for the calendar's two hover/focus cell popovers — the
 * provider grid's ``cell-popover`` and the client/admin matrix's
 * ``matrix-cell-popover``. Both are fixed-position portals that open under their
 * trigger cell, flip above when they would overflow the viewport bottom, and
 * reposition on scroll/resize. The two only differ in horizontal anchoring
 * (``center`` on the trigger vs ``left`` edge — the latter keeps the matrix
 * popover off the sticky name column) and their estimated height; everything
 * else lived as a copy in each file. One hook, one definition.
 */

const VIEWPORT_MARGIN = 8;
const GAP = 6;

export type PopoverPlacement = "below" | "above";

export type PopoverPosition = {
  top: number;
  left: number;
  placement: PopoverPlacement;
};

function computePosition(
  triggerRect: DOMRect,
  width: number,
  height: number,
  align: "center" | "left",
): PopoverPosition {
  let left =
    align === "center"
      ? triggerRect.left + triggerRect.width / 2 - width / 2
      : triggerRect.left;
  // Pull in from the right edge first, then guarantee the left margin — so a
  // popover near either viewport edge stays fully on-screen.
  if (left + width > window.innerWidth - VIEWPORT_MARGIN) {
    left = window.innerWidth - width - VIEWPORT_MARGIN;
  }
  if (left < VIEWPORT_MARGIN) left = VIEWPORT_MARGIN;

  let top = triggerRect.bottom + GAP;
  let placement: PopoverPlacement = "below";
  if (top + height > window.innerHeight - VIEWPORT_MARGIN) {
    const aboveTop = triggerRect.top - height - GAP;
    if (aboveTop >= VIEWPORT_MARGIN) {
      top = aboveTop;
      placement = "above";
    }
  }
  return { top, left, placement };
}

export function useAnchoredPopover({
  triggerRef,
  open,
  width,
  align,
  estimatedHeight,
}: {
  triggerRef: RefObject<HTMLElement | null>;
  open: boolean;
  width: number;
  /** Horizontal anchor: ``center`` on the trigger, or its ``left`` edge. */
  align: "center" | "left";
  /** First-paint height estimate (before the popover is measured); the
   *  reposition pass uses the real measured height. */
  estimatedHeight: number;
}): {
  mounted: boolean;
  position: PopoverPosition | null;
  popoverRef: RefObject<HTMLDivElement | null>;
} {
  const popoverRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<PopoverPosition | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) {
      setPosition(null);
      return;
    }
    const rect = triggerRef.current.getBoundingClientRect();
    setPosition(computePosition(rect, width, estimatedHeight, align));
  }, [open, triggerRef, width, estimatedHeight, align]);

  useEffect(() => {
    if (!open) return;
    const reposition = () => {
      if (!triggerRef.current || !popoverRef.current) return;
      const rect = triggerRef.current.getBoundingClientRect();
      setPosition(
        computePosition(rect, width, popoverRef.current.offsetHeight, align),
      );
    };
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    return () => {
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
    };
  }, [open, triggerRef, width, align]);

  return { mounted, position, popoverRef };
}
