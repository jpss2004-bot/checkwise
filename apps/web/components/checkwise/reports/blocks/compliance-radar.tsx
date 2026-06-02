"use client";

import Link from "next/link";
import { Compass } from "@phosphor-icons/react";

import { FreshnessLabel } from "@/components/checkwise/reports/freshness-label";
import { cn } from "@/lib/utils";
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

const SEMAPHORE_COLOR = {
  green: "var(--status-success-text)",
  yellow: "var(--status-warning-text)",
  red: "var(--status-danger-text)",
} as const;

const SEMAPHORE_LABEL = {
  green: "Verde",
  yellow: "Amarillo",
  red: "Rojo",
} as const;

export function ComplianceRadarBlock({
  block,
}: BlockProps<ComplianceRadarConfig, ComplianceRadarData>) {
  const data = block.data ?? {};
  const semaphore = data.semaphore_counts ?? { green: 0, yellow: 0, red: 0 };
  const overall = data.overall_compliance_pct ?? 0;
  const topVendors = data.top_vendors ?? [];
  const history = data.history_6mo ?? [];
  const total =
    (semaphore.green ?? 0) + (semaphore.yellow ?? 0) + (semaphore.red ?? 0);

  return (
    <section className="cw-compliance-radar rounded-2xl border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] p-6">
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

      <div className="grid grid-cols-1 gap-6 md:grid-cols-[200px_1fr]">
        {/* Donut */}
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

        {/* Ranked vendor list */}
        <div className="min-w-0">
          <p className="cw-eyebrow mb-2">Atención prioritaria</p>
          {topVendors.length === 0 ? (
            <p className="text-[13px] text-[color:var(--text-tertiary)]">
              El portafolio aún no tiene proveedores con workspace activo.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {topVendors.map((v) => (
                <li key={v.vendor_id}>
                  <Link
                    href={`/client/vendors/${v.vendor_id}`}
                    className="group flex items-center justify-between gap-3 rounded-md border border-transparent px-2.5 py-1.5 hover:border-[color:var(--border-subtle)] hover:bg-[color:var(--surface-2)]"
                  >
                    <div className="flex min-w-0 items-center gap-2.5">
                      <SemaphoreDot level={v.semaphore_level} />
                      <div className="min-w-0">
                        <p className="truncate text-[13px] font-medium text-[color:var(--text-primary)]">
                          {v.vendor_name}
                        </p>
                        <p className="truncate font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                          {v.vendor_rfc ?? "sin RFC"} ·{" "}
                          {SEMAPHORE_LABEL[v.semaphore_level] ?? v.semaphore_level} ·{" "}
                          faltan {v.missing_required_count}, en revisión{" "}
                          {v.pending_reviews_count}
                        </p>
                      </div>
                    </div>
                    <span
                      className={cn(
                        "shrink-0 font-mono text-[14px] tabular-nums",
                        "text-[color:var(--text-primary)]",
                      )}
                    >
                      {v.compliance_pct}%
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Optional 6-month sparkline (M5 will populate). */}
      {history.length > 0 ? (
        <div className="mt-6 border-t border-[color:var(--border-subtle)] pt-4">
          <p className="cw-eyebrow mb-2">Tendencia · últimos 6 meses</p>
          <ComplianceSparkline points={history} />
        </div>
      ) : null}
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
        Verde · {green}
      </li>
      <li className="flex items-center gap-2">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: `color-mix(in oklab, ${SEMAPHORE_COLOR.yellow} 95%, transparent)` }}
          aria-hidden="true"
        />
        Amarillo · {yellow}
      </li>
      <li className="flex items-center gap-2">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: `color-mix(in oklab, ${SEMAPHORE_COLOR.red} 95%, transparent)` }}
          aria-hidden="true"
        />
        Rojo · {red}
      </li>
    </ul>
  );
}

// ─── Per-vendor row marker ────────────────────────────────────────

function SemaphoreDot({ level }: { level: "green" | "yellow" | "red" }) {
  return (
    <span
      aria-label={SEMAPHORE_LABEL[level] ?? level}
      className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
      style={{
        backgroundColor: `color-mix(in oklab, ${SEMAPHORE_COLOR[level]} 95%, transparent)`,
      }}
    />
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
