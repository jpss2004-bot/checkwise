import { Question, Sparkle, Warning, type Icon } from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";
import type { ConfidenceLevel } from "@/lib/types";

/**
 * Confidence badge. Plain-language Spanish labels per the design
 * system's confidence buckets.
 *
 * Stage 2.6 (BL-T9, 2026-05-20): the "Sin extracción" label was
 * engineer dialect — "extraction" is an internal pipeline concept
 * that providers do not need to see. Replaced with the user-facing
 * meaning ("Sin información detectada").
 *
 * Spec: docs/DESIGN_SYSTEM.md §6.5
 */
export const CONFIDENCE_LABELS: Record<ConfidenceLevel, string> = {
  high: "Confianza alta",
  medium: "Confianza media",
  low: "Confianza baja",
  none: "Sin información detectada",
};

const CONFIDENCE_ICON: Record<ConfidenceLevel, Icon> = {
  high: Sparkle,
  medium: Sparkle,
  low: Warning,
  none: Question,
};

const CONFIDENCE_VARIANT: Record<
  ConfidenceLevel,
  "confidence-high" | "confidence-medium" | "confidence-low" | "confidence-none"
> = {
  high: "confidence-high",
  medium: "confidence-medium",
  low: "confidence-low",
  none: "confidence-none",
};

interface ConfidenceBadgeProps {
  level: ConfidenceLevel;
  /** Percentage 0–100. Renders next to the label when provided. */
  percent?: number;
  className?: string;
}

/**
 * Format the bucket from a 0–100 number. The thresholds match
 * DESIGN_SYSTEM.md §6.5.
 */
export function confidenceLevelFromPercent(percent: number): ConfidenceLevel {
  if (percent >= 95) return "high";
  if (percent >= 70) return "medium";
  if (percent >= 50) return "low";
  return "none";
}

export function ConfidenceBadge({ level, percent, className }: ConfidenceBadgeProps) {
  const IconComponent = CONFIDENCE_ICON[level];
  const weight = level === "high" ? "fill" : "bold";
  return (
    <Badge variant={CONFIDENCE_VARIANT[level]} className={className}>
      <IconComponent className="h-3.5 w-3.5" weight={weight} aria-hidden="true" />
      <span>{CONFIDENCE_LABELS[level]}</span>
      {percent !== undefined && (
        <span className="font-mono text-[10px] opacity-80">{Math.round(percent)}%</span>
      )}
    </Badge>
  );
}
