"use client";

import { Minus } from "@phosphor-icons/react";

import type { BlockDefinition, BlockProps } from "@/lib/reports/registry";

interface DividerConfig {
  label?: string;
}

export const dividerDefinition: Omit<BlockDefinition<DividerConfig>, "Component"> = {
  type: "divider",
  label: "Divisor",
  icon: Minus,
  description: "Línea separadora con etiqueta opcional.",
  defaultConfig: {},
};

export function DividerBlock({ block, editable, onPatch }: BlockProps<DividerConfig>) {
  const { label } = block.config;
  // F8 (2026-05-19 visual audit): a labeled divider IS a section
  // heading on a printed report. Eyebrow chrome (small, all-caps,
  // tracked) made these reads as wireframe labels instead of section
  // breaks. In editor mode keep the inline input. In read-only render
  // the label at section-heading weight, with hairlines flanking it.
  if (!editable && label) {
    return (
      <div className="flex items-center gap-3 py-4 print:break-inside-avoid">
        <span className="h-px flex-1 bg-[color:var(--border-default)]" />
        <h3 className="text-[14px] font-semibold tracking-tight text-[color:var(--text-primary)]">
          {label}
        </h3>
        <span className="h-px flex-1 bg-[color:var(--border-default)]" />
      </div>
    );
  }
  return (
    <div className="flex items-center gap-3 py-3">
      <span className="h-px flex-1 bg-[color:var(--border-default)]" />
      {(label || editable) && (
        <input
          type="text"
          placeholder={editable ? "Etiqueta opcional" : ""}
          value={label ?? ""}
          disabled={!editable}
          onChange={(e) => onPatch({ config: { label: e.target.value } })}
          className="cw-eyebrow border-0 bg-transparent p-0 text-center outline-none focus:ring-0 disabled:cursor-default"
        />
      )}
      <span className="h-px flex-1 bg-[color:var(--border-default)]" />
    </div>
  );
}
