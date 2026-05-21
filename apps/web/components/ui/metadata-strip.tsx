import { type ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * MetadataStrip — V2.x signature pattern (Phase 2 lock).
 *
 * Renders the canonical `LABEL_MONO_CAPS · value · LABEL · value`
 * horizontal strip used in every page header, detail surface, and
 * right-rail panel. Backed by the `.cw-metadata-strip` + `.cw-eyebrow`
 * utilities defined in globals.css.
 *
 *   <MetadataStrip
 *     items={[
 *       { label: "RFC",      value: "AID010101AB1", mono: true },
 *       { label: "Por atender", value: "3" },
 *     ]}
 *   />
 */

export type MetadataItem = {
  label: string;
  value: ReactNode;
  mono?: boolean;
  tone?: "default" | "teal" | "warning";
};

const TONE_CLASS: Record<NonNullable<MetadataItem["tone"]>, string> = {
  default: "text-[color:var(--text-primary)]",
  teal: "text-[color:var(--text-teal)]",
  warning: "text-[color:var(--status-warning-text)]",
};

export function MetadataStrip({
  items,
  bordered = true,
  className,
}: {
  items: MetadataItem[];
  bordered?: boolean;
  className?: string;
}) {
  if (items.length === 0) return null;
  return (
    <div
      className={cn(
        "cw-metadata-strip cw-fade-up py-3",
        bordered &&
          "border-t border-b border-[color:var(--border-subtle)]",
        className,
      )}
    >
      {items.map((item, idx) => (
        <div key={`${item.label}-${idx}`} className="flex items-baseline gap-2">
          <span className="cw-eyebrow">{item.label}</span>
          <span
            className={cn(
              "text-[13px]",
              item.mono && "font-mono tabular-nums",
              TONE_CLASS[item.tone ?? "default"],
            )}
          >
            {item.value}
          </span>
        </div>
      ))}
    </div>
  );
}
