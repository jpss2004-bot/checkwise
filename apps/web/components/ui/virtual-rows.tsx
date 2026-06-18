"use client";

import {
  cloneElement,
  isValidElement,
  useEffect,
  useRef,
  useState,
  type ReactElement,
} from "react";
import { useWindowVirtualizer } from "@tanstack/react-virtual";

/**
 * VirtualTableBody — a windowed `<tbody>` for long tables.
 *
 * Renders only the rows near the viewport (plus an overscan buffer), so a table
 * holding thousands of loaded rows mounts a few dozen `<tr>` nodes instead of
 * all of them. This is what stops a big Bandeja / vendor / client list from
 * pinning the main thread and feeling frozen while it paints and on every
 * scroll/re-render.
 *
 * Design choices:
 *  - WINDOW virtualizer (the page scrolls as normal; no inner scroll container)
 *    so existing full-page list layouts keep their feel and their sticky page
 *    chrome. `scrollMargin` is measured from the document so positions stay
 *    correct under positioned ancestors (the admin shell has them).
 *  - Rows stay normal in-flow `<tr>` elements bracketed by two spacer rows, so
 *    native table column sizing keeps working — no `table-layout: fixed` or
 *    hand-authored column widths required.
 *  - Below `threshold` rows it renders everything and never touches the
 *    virtualizer, so the common small-table case pays nothing and behaves
 *    exactly as before (and stays fully accessible to screen readers).
 *
 * Contract: `renderRow` must return a SINGLE element that forwards `ref` and
 * arbitrary props to its underlying `<tr>` (e.g. the shared {@link
 * "@/components/ui/table".TableRow}, or any `forwardRef` wrapper that spreads
 * the rest onto it). Do not set your own `ref` or `key` on that element — this
 * component injects them so the virtualizer can measure real row heights.
 */
export function VirtualTableBody<T>({
  items,
  renderRow,
  getRowKey,
  columnCount,
  estimateRowHeight = 64,
  overscan = 10,
  threshold = 60,
  className,
}: {
  items: T[];
  renderRow: (item: T, index: number) => ReactElement;
  getRowKey: (item: T, index: number) => string;
  /** Total columns (including any trailing action column) for the spacer cells. */
  columnCount: number;
  estimateRowHeight?: number;
  overscan?: number;
  /** Render everything (skip virtualization) at or below this row count. */
  threshold?: number;
  className?: string;
}) {
  const bodyRef = useRef<HTMLTableSectionElement>(null);
  const [scrollMargin, setScrollMargin] = useState(0);

  const shouldVirtualize = items.length > threshold;

  // Distance from the top of the document to the start of this <tbody>. The
  // window virtualizer needs it to map item positions onto page-scroll offsets.
  // Re-measured on resize; getBoundingClientRect + scrollY is stable across
  // scrolling, unlike offsetTop under positioned ancestors.
  useEffect(() => {
    if (!shouldVirtualize) return;
    const el = bodyRef.current;
    if (!el) return;
    const measure = () => {
      const rect = el.getBoundingClientRect();
      setScrollMargin(rect.top + window.scrollY);
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [shouldVirtualize]);

  const virtualizer = useWindowVirtualizer({
    count: items.length,
    estimateSize: () => estimateRowHeight,
    overscan,
    scrollMargin,
    getItemKey: (index) => getRowKey(items[index], index),
  });

  if (!shouldVirtualize) {
    return (
      <tbody ref={bodyRef} className={className}>
        {items.map((item, index) => {
          const row = renderRow(item, index);
          return isValidElement(row)
            ? cloneElement(row, { key: getRowKey(item, index) })
            : row;
        })}
      </tbody>
    );
  }

  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();
  const paddingTop =
    virtualItems.length > 0 ? virtualItems[0].start - scrollMargin : 0;
  const paddingBottom =
    virtualItems.length > 0
      ? totalSize - (virtualItems[virtualItems.length - 1].end - scrollMargin)
      : 0;

  return (
    <tbody ref={bodyRef} className={className}>
      {paddingTop > 0 ? (
        <tr aria-hidden>
          <td
            colSpan={columnCount}
            style={{ height: paddingTop, padding: 0, border: 0 }}
          />
        </tr>
      ) : null}
      {virtualItems.map((vi) => {
        const item = items[vi.index];
        const row = renderRow(item, vi.index);
        if (!isValidElement(row)) return row;
        return cloneElement(row, {
          key: vi.key,
          "data-index": vi.index,
          ref: virtualizer.measureElement,
        } as Record<string, unknown>);
      })}
      {paddingBottom > 0 ? (
        <tr aria-hidden>
          <td
            colSpan={columnCount}
            style={{ height: paddingBottom, padding: 0, border: 0 }}
          />
        </tr>
      ) : null}
    </tbody>
  );
}
