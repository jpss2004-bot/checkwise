"use client";

import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

/** Returns the meter tone for a usage percentage. Exported for testing. */
export function usageTone(pct: number): "success" | "warning" | "error" {
  if (pct >= 100) return "error";
  if (pct >= 80) return "warning";
  return "success";
}

/**
 * "X de Y proveedores" usage bar. A null ``limit`` (uncapped legacy/enterprise)
 * renders a plain caption with no bar.
 */
export function UsageMeter({
  used,
  limit,
  className,
}: {
  used: number;
  limit: number | null;
  className?: string;
}) {
  if (limit === null) {
    return (
      <p
        className={cn(
          "text-sm text-[color:var(--text-secondary)]",
          className,
        )}
      >
        {used} proveedores · sin límite
      </p>
    );
  }
  const pct = limit > 0 ? Math.round((used / limit) * 100) : 100;
  return (
    <div className={cn("space-y-1", className)}>
      <Progress
        value={pct}
        label="Proveedores"
        showValue
        tone={usageTone(pct)}
      />
      <p className="text-sm text-[color:var(--text-secondary)]">
        {used} de {limit} proveedores
      </p>
    </div>
  );
}
