"use client";

import { Compass } from "@phosphor-icons/react";

import { BlockIntro } from "@/components/checkwise/reports/block-intro";
import { FreshnessLabel } from "@/components/checkwise/reports/freshness-label";
import { SEMAPHORE_DOT_CLASS } from "@/lib/constants/statuses";
import type { BlockDefinition, BlockProps } from "@/lib/reports/registry";

/**
 * Compliance Radar — cliente Resumen ejecutivo hero block.
 *
 * Three visual surfaces in one block:
 *
 *   1. Donut chart of the green/yellow/red semáforo distribution
 *      with the overall ``cumplimiento%`` in the centre — answers
 *      "how is my portfolio doing?" at a glance.
 *   2. A worst-first ranked list of vendors with a traffic-light
 *      pill + compliance %. Drills into ``/client/vendors/<id>`` so
 *      the executive can act on the riskiest row without scrolling.
 *   3. Reserved sparkline slot for the 6-month trend (M5 ships the
 *      historical compute that populates it; today we hide the slot
 *      when ``history_6mo`` is empty).
 *
 * Everything is pure SVG + flex. No chart-library dep, no font from
 * the bundle, so the block stays cheap to render on the print path
 * (Phase 10 chromium export reuses the same component).
 */

interface ComplianceRadarConfig {
  top_n_vendors: number;
  include_history: boolean;
}

interface RadarVendorRow {
  vendor_id: string;
  vendor_name: string;
  vendor_rfc: string | null;
  semaphore_level: "green" | "yellow" | "red";
  compliance_pct: number;
  pending_reviews_count: number;
  missing_required_count: number;
}

interface RadarHistoryPoint {
  month_key: string;
  compliance_pct: number;
}

interface ComplianceRadarData {
  client_name?: string;
  vendor_count?: number;
  semaphore_counts?: { green: number; yellow: number; red: number };
  overall_compliance_pct?: number;
  top_vendors?: RadarVendorRow[];
  history_6mo?: RadarHistoryPoint[];
  fetched_at?: string | null;
}

export const complianceRadarDefinition: Omit<
  BlockDefinition<ComplianceRadarConfig, ComplianceRadarData>,
  "Component"
> = {
  type: "compliance_radar",
  label: "Radar de cumplimiento",
  icon: Compass,
  description:
    "Hero del portafolio: donut del semáforo + ranking de proveedores + tendencia.",
  defaultConfig: {
    top_n_vendors: 8,
    include_history: false,
  },
};

// SVG fill/stroke + color-mix() need a bare ``var(--token)`` value, not a
// Tailwind class, so we can't drop SEMAPHORE_DOT_CLASS in directly here.
// Instead we DERIVE the bare value from the canonical dot-class map
// (statuses.ts) — extracting the ``var(--status-*-text)`` it wraps — so
// the semáforo tokens still come from the single source of truth (no
// inline --status-* re-declaration) while the SVG keeps the exact value
// form it needs. The rendered colour is unchanged.
const semaphoreVar = (level: "green" | "yellow" | "red"): string => {
  const match = SEMAPHORE_DOT_CLASS[level].match(/var\((--[^)]+)\)/);
  return `var(${match?.[1] ?? "--status-success-text"})`;
};

const SEMAPHORE_COLOR = {
  green: semaphoreVar("green"),
  yellow: semaphoreVar("yellow"),
  red: semaphoreVar("red"),
} as const;

export function ComplianceRadarBlock({
  block,
}: BlockProps<ComplianceRadarConfig, ComplianceRadarData>) {
  const data = block.data ?? {};
  const semaphore = data.semaphore_counts ?? { green: 0, yellow: 0, red: 0 };
  const overall = data.overall_compliance_pct ?? 0;
  const history = data.history_6mo ?? [];
  const total =
    (semaphore.green ?? 0) + (semaphore.yellow ?? 0) + (semaphore.red ?? 0);

  return (
    <section className="cw-compliance-radar border-t border-[color:var(--border-default)] pt-5">
      <header className="mb-5 flex items-baseline justify-between gap-3">
        <div>
          <p className="cw-eyebrow">Radar de cumplimiento</p>
          <h3 className="text-[19px] font-semibold leading-tight text-[color:var(--text-primary)]">
            {data.client_name
              ? `Portafolio · ${data.client_name}`
              : "Portafolio del cliente"}
          </h3>
        </div>
        <FreshnessLabel fetchedAt={data.fetched_at ?? null} />
      </header>

      <BlockIntro caption="La salud del portafolio de un vistazo: la dona muestra cómo se reparten los proveedores entre verde, amarillo y rojo, y la línea sigue la tasa de aprobación mes a mes durante los últimos seis meses." />

      {/* 2026-06-03: the radar is now a compact GAUGE + TREND. Its old
          ranked-vendor list duplicated compliance_overview's per-provider
          bars, so it was dropped — the donut (portfolio gauge) and the
          6-month approval sparkline (the only trend in the report) are
          the radar's unique contributions. */}
      <div className="grid grid-cols-1 items-center gap-6 md:grid-cols-[200px_1fr]">
        {/* Donut — portfolio gauge */}
        <div className="flex flex-col items-center gap-3">
          <ComplianceDonut
            green={semaphore.green ?? 0}
            yellow={semaphore.yellow ?? 0}
            red={semaphore.red ?? 0}
            overall={overall}
            size={180}
          />
          <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {total} proveedor{total === 1 ? "" : "es"}
          </p>
          <DonutLegend
            green={semaphore.green ?? 0}
            yellow={semaphore.yellow ?? 0}
            red={semaphore.red ?? 0}
          />
        </div>

        {/* Trend — approval-rate proxy (% of submissions created each
            month that ended ``aprobado``), labelled "Aprobación mensual"
            so the distinction from strict compliance % stays honest. */}
        <div className="min-w-0">
          {history.length > 0 ? (
            <>
              <div className="mb-2 flex items-baseline justify-between gap-3">
                <p className="cw-eyebrow">Aprobación mensual · últimos 6 meses</p>
                <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  {history[0]?.month_key} → {history[history.length - 1]?.month_key}
                </p>
              </div>
              <ComplianceSparkline points={history} />
            </>
          ) : (
            <p className="text-[13px] text-[color:var(--text-tertiary)]">
              La tendencia mensual de aprobación aparece cuando hay actividad
              registrada en varios periodos.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

// ─── Donut ────────────────────────────────────────────────────────

function ComplianceDonut({
  green,
  yellow,
  red,
  overall,
  size,
}: {
  green: number;
  yellow: number;
  red: number;
  overall: number;
  size: number;
}) {
  const total = green + yellow + red;
  const strokeWidth = 18;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const segments =
    total === 0
      ? []
      : [
          { value: green, color: SEMAPHORE_COLOR.green },
          { value: yellow, color: SEMAPHORE_COLOR.yellow },
          { value: red, color: SEMAPHORE_COLOR.red },
        ];
  let offsetAccum = 0;
  const cx = size / 2;
  const cy = size / 2;

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={`Distribución del semáforo: ${green} verdes, ${yellow} amarillos, ${red} rojos.`}
    >
      {/* Background ring — visible when total is 0 too. */}
      <circle
        cx={cx}
        cy={cy}
        r={radius}
        fill="none"
        stroke="color-mix(in oklab, var(--border-subtle) 60%, transparent)"
        strokeWidth={strokeWidth}
      />
      {segments.map((seg, idx) => {
        if (seg.value === 0) return null;
        const length = (seg.value / total) * circumference;
        const dashArray = `${length} ${circumference - length}`;
        const el = (
          <circle
            key={idx}
            cx={cx}
            cy={cy}
            r={radius}
            fill="none"
            stroke={`color-mix(in oklab, ${seg.color} 95%, transparent)`}
            strokeWidth={strokeWidth}
            strokeDasharray={dashArray}
            strokeDashoffset={-offsetAccum}
            strokeLinecap="butt"
            transform={`rotate(-90 ${cx} ${cy})`}
          />
        );
        offsetAccum += length;
        return el;
      })}
      {/* Center labels */}
      <text
        x={cx}
        y={cy - 2}
        textAnchor="middle"
        className="fill-[color:var(--text-primary)]"
        fontSize="28"
        fontWeight="600"
      >
        {overall}%
      </text>
      <text
        x={cx}
        y={cy + 18}
        textAnchor="middle"
        className="fill-[color:var(--text-tertiary)]"
        fontSize="10"
        fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
        letterSpacing="0.05em"
      >
        CUMPLIMIENTO
      </text>
    </svg>
  );
}

function DonutLegend({
  green,
  yellow,
  red,
}: {
  green: number;
  yellow: number;
  red: number;
}) {
  return (
    <ul className="flex flex-col gap-1 text-[12px] text-[color:var(--text-secondary)]">
      <li className="flex items-center gap-2">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: `color-mix(in oklab, ${SEMAPHORE_COLOR.green} 95%, transparent)` }}
          aria-hidden="true"
        />
        Al día · {green}
      </li>
      <li className="flex items-center gap-2">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: `color-mix(in oklab, ${SEMAPHORE_COLOR.yellow} 95%, transparent)` }}
          aria-hidden="true"
        />
        En proceso · {yellow}
      </li>
      <li className="flex items-center gap-2">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: `color-mix(in oklab, ${SEMAPHORE_COLOR.red} 95%, transparent)` }}
          aria-hidden="true"
        />
        En riesgo · {red}
      </li>
    </ul>
  );
}

// ─── Sparkline ────────────────────────────────────────────────────

function ComplianceSparkline({ points }: { points: RadarHistoryPoint[] }) {
  if (points.length === 0) return null;
  const width = 600;
  const height = 64;
  const padX = 4;
  const padY = 8;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;
  const max = 100;
  const min = 0;

  const xStep = points.length > 1 ? innerW / (points.length - 1) : 0;
  const y = (pct: number) => padY + innerH - ((pct - min) / (max - min)) * innerH;

  const path = points
    .map(
      (p, i) =>
        `${i === 0 ? "M" : "L"}${padX + i * xStep},${y(p.compliance_pct)}`,
    )
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`Cumplimiento histórico: ${points
        .map((p) => `${p.month_key} ${p.compliance_pct}%`)
        .join(", ")}`}
      className="block h-16 w-full"
    >
      <path
        d={path}
        fill="none"
        stroke={`color-mix(in oklab, ${SEMAPHORE_COLOR.green} 90%, transparent)`}
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {points.map((p, i) => (
        <circle
          key={p.month_key}
          cx={padX + i * xStep}
          cy={y(p.compliance_pct)}
          r="2"
          fill={`color-mix(in oklab, ${SEMAPHORE_COLOR.green} 95%, transparent)`}
        />
      ))}
    </svg>
  );
}
