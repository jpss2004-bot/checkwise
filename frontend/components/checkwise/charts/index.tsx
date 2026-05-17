/**
 * CheckWise inline-SVG chart primitives.
 *
 * Zero external dependencies — every chart is a small functional
 * component that renders SVG bound to the semantic color tokens in
 * globals.css. Designed for dashboard widgets where a heavyweight
 * library like Recharts would be overkill and slow down first paint.
 *
 * Components:
 *   • RadialGauge   — circular progress ring with center label
 *   • Donut         — multi-segment donut with legend
 *   • Sparkline     — tiny trend line for KPI tiles
 *   • MiniBars      — small column chart, animated on mount
 *   • StackedBars   — horizontal stacked bar for proportions
 *   • TrendArrow    — up/down delta indicator
 */

import { useId } from "react";

import { cn } from "@/lib/utils";

// ─── Helpers ──────────────────────────────────────────────────────

const TONE_TO_VAR: Record<ChartTone, string> = {
  brand: "var(--text-brand)",
  teal: "var(--text-teal)",
  success: "var(--status-success-text)",
  warning: "var(--status-warning-text)",
  error: "var(--status-error-text)",
  info: "var(--status-info-text)",
  neutral: "var(--text-tertiary)",
};

export type ChartTone =
  | "brand"
  | "teal"
  | "success"
  | "warning"
  | "error"
  | "info"
  | "neutral";

export type ChartSegment = {
  label: string;
  value: number;
  tone: ChartTone;
};

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

// ─── RadialGauge ──────────────────────────────────────────────────

interface RadialGaugeProps {
  value: number;
  /** Maximum value the gauge measures up to. Defaults to 100. */
  max?: number;
  /** Pixel size of the gauge. */
  size?: number;
  /** Stroke width. */
  thickness?: number;
  /** Color tone. */
  tone?: ChartTone;
  /** Center label override. Defaults to "{value}%". */
  label?: React.ReactNode;
  /** Caption shown beneath the label. */
  caption?: React.ReactNode;
  className?: string;
}

export function RadialGauge({
  value,
  max = 100,
  size = 132,
  thickness = 10,
  tone = "brand",
  label,
  caption,
  className,
}: RadialGaugeProps) {
  const pct = clamp((value / max) * 100, 0, 100);
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;
  const stroke = TONE_TO_VAR[tone];

  return (
    <div
      className={cn("relative inline-flex items-center justify-center", className)}
      style={{ width: size, height: size }}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="-rotate-90"
        aria-hidden="true"
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--border-subtle)"
          strokeWidth={thickness}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={stroke}
          strokeWidth={thickness}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{
            transition:
              "stroke-dashoffset 800ms var(--ease-enter), stroke 200ms ease-out",
          }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className="font-mono text-2xl font-semibold tabular-nums leading-none text-[color:var(--text-primary)]">
          {label ?? `${Math.round(pct)}%`}
        </span>
        {caption ? (
          <span className="mt-1 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {caption}
          </span>
        ) : null}
      </div>
    </div>
  );
}

// ─── Donut ────────────────────────────────────────────────────────

interface DonutProps {
  segments: ChartSegment[];
  size?: number;
  thickness?: number;
  /** Center label. */
  centerLabel?: React.ReactNode;
  centerCaption?: React.ReactNode;
  className?: string;
  showLegend?: boolean;
}

export function Donut({
  segments,
  size = 132,
  thickness = 14,
  centerLabel,
  centerCaption,
  className,
  showLegend = true,
}: DonutProps) {
  const total = segments.reduce((sum, s) => sum + Math.max(0, s.value), 0);
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;

  let accumulated = 0;

  return (
    <div className={cn("flex items-center gap-5", className)}>
      <div
        className="relative inline-flex shrink-0 items-center justify-center"
        style={{ width: size, height: size }}
      >
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="-rotate-90"
          aria-hidden="true"
        >
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="var(--border-subtle)"
            strokeWidth={thickness}
          />
          {total > 0 &&
            segments.map((seg, idx) => {
              const value = Math.max(0, seg.value);
              if (value === 0) return null;
              const fraction = value / total;
              const length = circumference * fraction;
              const dashArray = `${length} ${circumference - length}`;
              const dashOffset = -((accumulated / total) * circumference);
              accumulated += value;
              return (
                <circle
                  key={`${seg.label}-${idx}`}
                  cx={size / 2}
                  cy={size / 2}
                  r={radius}
                  fill="none"
                  stroke={TONE_TO_VAR[seg.tone]}
                  strokeWidth={thickness}
                  strokeDasharray={dashArray}
                  strokeDashoffset={dashOffset}
                  style={{
                    transition:
                      "stroke-dasharray 600ms var(--ease-enter), stroke-dashoffset 600ms var(--ease-enter)",
                  }}
                />
              );
            })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="font-mono text-xl font-semibold tabular-nums leading-none text-[color:var(--text-primary)]">
            {centerLabel ?? total}
          </span>
          {centerCaption ? (
            <span className="mt-0.5 font-mono text-[9px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              {centerCaption}
            </span>
          ) : null}
        </div>
      </div>
      {showLegend ? (
        <ul className="grid min-w-0 flex-1 grid-cols-1 gap-1.5 text-xs">
          {segments.map((seg) => (
            <li key={seg.label} className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-2 truncate text-[color:var(--text-secondary)]">
                <span
                  aria-hidden="true"
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: TONE_TO_VAR[seg.tone] }}
                />
                <span className="truncate">{seg.label}</span>
              </span>
              <span className="font-mono text-[12px] tabular-nums text-[color:var(--text-primary)]">
                {seg.value}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

// ─── Sparkline ────────────────────────────────────────────────────

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  tone?: ChartTone;
  /** Fill the area below the curve. */
  filled?: boolean;
  className?: string;
}

export function Sparkline({
  data,
  width = 96,
  height = 28,
  tone = "teal",
  filled = true,
  className,
}: SparklineProps) {
  // React.useId — SSR-safe deterministic id; avoids hydration mismatches
  // that Math.random() would produce. Called unconditionally to respect
  // the rules of hooks (the early return below cannot precede it).
  const reactId = useId();
  if (data.length < 2) {
    return (
      <div
        className={cn("h-7 w-24 rounded bg-[color:var(--surface-sunken)]", className)}
        aria-hidden="true"
      />
    );
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const stepX = width / (data.length - 1);
  const points = data.map((v, i) => {
    const x = i * stepX;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return [x, y] as const;
  });
  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p[0].toFixed(2)} ${p[1].toFixed(2)}`)
    .join(" ");
  const areaPath = `${path} L ${width} ${height} L 0 ${height} Z`;
  const color = TONE_TO_VAR[tone];
  const gradientId = `spark-${reactId.replace(/[:]/g, "_")}`;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      aria-hidden="true"
    >
      {filled ? (
        <>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.25} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <path d={areaPath} fill={`url(#${gradientId})`} />
        </>
      ) : null}
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {points.length > 0 ? (
        <circle
          cx={points[points.length - 1][0]}
          cy={points[points.length - 1][1]}
          r={2.4}
          fill={color}
        />
      ) : null}
    </svg>
  );
}

// ─── MiniBars ─────────────────────────────────────────────────────

interface MiniBarsProps {
  data: { label: string; value: number; tone?: ChartTone }[];
  height?: number;
  /** Show value labels above each bar. */
  showValues?: boolean;
  /** Color tone applied to bars without an explicit tone. */
  tone?: ChartTone;
  className?: string;
}

export function MiniBars({
  data,
  height = 100,
  showValues = false,
  tone = "brand",
  className,
}: MiniBarsProps) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className={cn("flex h-full w-full flex-col gap-2", className)}>
      <div
        className="flex w-full items-end gap-1.5"
        style={{ height }}
        role="img"
        aria-label="Distribución mensual"
      >
        {data.map((d, idx) => {
          const pct = d.value === 0 ? 0 : (d.value / max) * 100;
          const color = TONE_TO_VAR[d.tone ?? tone];
          return (
            <div
              key={`${d.label}-${idx}`}
              className="flex flex-1 flex-col items-center justify-end gap-1"
              style={{ height }}
            >
              {showValues ? (
                <span className="font-mono text-[9px] tabular-nums text-[color:var(--text-tertiary)]">
                  {d.value}
                </span>
              ) : null}
              <div
                className="w-full rounded-t-sm transition-[height] duration-700 ease-out"
                style={{
                  height: `${pct}%`,
                  minHeight: d.value === 0 ? 2 : undefined,
                  background:
                    d.value === 0 ? "var(--surface-sunken)" : color,
                  opacity: d.value === 0 ? 0.4 : 1,
                  animationDelay: `${idx * 30}ms`,
                }}
                title={`${d.label}: ${d.value}`}
              />
            </div>
          );
        })}
      </div>
      <div className="flex w-full justify-between font-mono text-[9px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {data.map((d) => (
          <span key={`label-${d.label}`} className="flex-1 text-center">
            {d.label}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─── StackedBars ──────────────────────────────────────────────────

interface StackedBarsProps {
  segments: ChartSegment[];
  className?: string;
  /** Show inline legend underneath. */
  showLegend?: boolean;
  /** Height of the bar in pixels. */
  height?: number;
}

export function StackedBars({
  segments,
  className,
  showLegend = true,
  height = 14,
}: StackedBarsProps) {
  const total = segments.reduce((sum, s) => sum + Math.max(0, s.value), 0);
  return (
    <div className={cn("space-y-2", className)}>
      <div
        className="flex w-full overflow-hidden rounded-full bg-[color:var(--surface-sunken)]"
        style={{ height }}
        role="img"
        aria-label="Distribución"
      >
        {total > 0
          ? segments.map((seg) => {
              const value = Math.max(0, seg.value);
              if (value === 0) return null;
              const pct = (value / total) * 100;
              return (
                <div
                  key={seg.label}
                  className="h-full transition-[width] duration-700 ease-out"
                  style={{
                    width: `${pct}%`,
                    background: TONE_TO_VAR[seg.tone],
                  }}
                  title={`${seg.label}: ${seg.value}`}
                />
              );
            })
          : null}
      </div>
      {showLegend ? (
        <ul className="flex flex-wrap gap-3 font-mono text-[10px] uppercase tracking-wide">
          {segments.map((seg) => (
            <li
              key={seg.label}
              className="flex items-center gap-1.5 text-[color:var(--text-tertiary)]"
            >
              <span
                aria-hidden="true"
                className="h-2 w-2 rounded-full"
                style={{ background: TONE_TO_VAR[seg.tone] }}
              />
              <span>{seg.label}</span>
              <span className="text-[color:var(--text-primary)]">{seg.value}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

// ─── TrendArrow ───────────────────────────────────────────────────

interface TrendArrowProps {
  delta: number;
  /** What the delta unit means — appended after the number. */
  unit?: string;
  /** Inverts color semantics (down is good, up is bad). */
  inverse?: boolean;
  className?: string;
}

export function TrendArrow({
  delta,
  unit = "",
  inverse = false,
  className,
}: TrendArrowProps) {
  if (delta === 0) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-full bg-[color:var(--surface-sunken)] px-1.5 py-0.5 font-mono text-[10px] text-[color:var(--text-tertiary)]",
          className,
        )}
      >
        <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true">
          <line x1="1" y1="4" x2="7" y2="4" stroke="currentColor" strokeWidth="1.5" />
        </svg>
        {Math.abs(delta)}
        {unit}
      </span>
    );
  }
  const positive = delta > 0;
  const isGood = inverse ? !positive : positive;
  const tone = isGood
    ? "bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]"
    : "bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 font-mono text-[10px]",
        tone,
        className,
      )}
    >
      <svg
        width="8"
        height="8"
        viewBox="0 0 8 8"
        aria-hidden="true"
        className={positive ? "" : "rotate-180"}
      >
        <path d="M4 1.5 L7 5.5 H1 Z" fill="currentColor" />
      </svg>
      <span className="tabular-nums">
        {positive ? "+" : "−"}
        {Math.abs(delta)}
        {unit}
      </span>
    </span>
  );
}
