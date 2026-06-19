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
  /** Hard cap so the popover never spills past the viewport edge — the caller
   *  applies it with ``overflow-y: auto`` so a tall list scrolls internally
   *  instead of being clipped off-screen with no way to reach the bottom. */
  maxHeight: number;
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

  // Space available in each direction. Open downward if the popover fits there
  // OR there is at least as much room below as above; otherwise flip up. Either
  // way the popover is capped to the space in its chosen direction (and made
  // scrollable by the caller), so a list taller than the viewport — common on
  // short laptop screens — is never clipped with its bottom unreachable.
  const spaceBelow = window.innerHeight - VIEWPORT_MARGIN - (triggerRect.bottom + GAP);
  const spaceAbove = triggerRect.top - GAP - VIEWPORT_MARGIN;

  let top: number;
  let placement: PopoverPlacement;
  let maxHeight: number;
  if (height <= spaceBelow || spaceBelow >= spaceAbove) {
    placement = "below";
    top = triggerRect.bottom + GAP;
    maxHeight = spaceBelow;
  } else {
    placement = "above";
    maxHeight = spaceAbove;
    top = triggerRect.top - GAP - Math.min(height, spaceAbove);
  }
  return { top, left, placement, maxHeight: Math.max(80, maxHeight) };
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

  // Re-place using the popover's REAL height once it has rendered. The pass
  // above runs before the popover exists, so it uses ``estimatedHeight``; if the
  // real content is taller (common — the estimate is a lower bound), an "above"
  // placement computed from the estimate sits too low and its bottom spills off
  // the bottom edge. Measuring after mount corrects the placement; the >1px
  // guard stops it after it converges (no commit loop).
  useLayoutEffect(() => {
    if (!open || !position || !triggerRef.current || !popoverRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const next = computePosition(rect, width, popoverRef.current.offsetHeight, align);
    if (
      Math.abs(next.top - position.top) > 1 ||
      Math.abs(next.maxHeight - position.maxHeight) > 1 ||
      next.placement !== position.placement
    ) {
      setPosition(next);
    }
  }, [open, position, triggerRef, width, align]);

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
