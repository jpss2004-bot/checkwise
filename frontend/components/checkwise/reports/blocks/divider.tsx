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
