"use client";

import { CalendarBlank } from "@phosphor-icons/react";

import { FreshnessLabel } from "@/components/checkwise/reports/freshness-label";
import type { BlockDefinition, BlockProps } from "@/lib/reports/registry";

/**
 * upcoming_deadlines block (P1.4).
 *
 * Three stacked surfaces in one block, in order of glance value:
 *
 *  1. Urgency timeline (SVG): a horizontal axis 0–30+ days with
 *     four tinted bands (this week / 2 weeks / month / later) and
 *     one dot per deadline at its due_in_days position. Reads in
 *     under a second.
 *  2. Per-institution cards: 2×N grid showing the next deadline per
 *     institution, with a countdown and a one-click "Subir" link.
 *  3. Compact table: every row, every column. The print-safe
 *     fallback that PDF export will use.
 *
 * Data comes verbatim from the backend builder
 * ``build_upcoming_deadlines_for_vendor``. No client-side data
 * massaging beyond grouping for the institution cards.
 *
 * Print parity:
 * - SVG prints (inline, no external deps).
 * - Cards are static grids.
 * - The table is the canonical printed shape.
 * - Hover/interactive states are explicitly hidden via ``print:``
 *   modifiers — the rendered block looks the same on paper.
 */

type SlotState =
  | "rejected"
  | "needs_correction"
  | "possible_mismatch"
  | "expired"
  | "missing"
  | "in_review"
  | "uploaded"
  | "approved"
  | "exception"
  | "not_applicable";

type Institution = "sat" | "imss" | "infonavit" | "stps_repse" | "interno_cliente" | string;

interface UpcomingItem {
  id: string;
  title: string;
  institution: Institution;
  period_key: string | null;
  due_month: number;
  due_in_days: number;
  state: SlotState;
  href: string;
  requirement_code?: string | null;
}

interface UrgencyBuckets {
  week: number;
  fortnight: number;
  month: number;
  later: number;
}

interface UpcomingDeadlinesConfig {
  top?: number;
  filter?: { institutions?: Institution[] };
}

interface UpcomingDeadlinesData {
  items: UpcomingItem[];
  urgency_buckets: UrgencyBuckets;
  workspace_id: string | null;
  fetched_at: string | null;
  as_of: string | null;
  filter_applied: { institutions?: Institution[] };
  top: number;
  total_before_filter: number;
}

const INSTITUTION_LABEL: Record<string, string> = {
  sat: "SAT",
  imss: "IMSS",
  infonavit: "INFONAVIT",
  stps_repse: "STPS / REPSE",
  interno_cliente: "Interno",
};

// Display order — used for the institution-card grid + the table.
const INSTITUTION_ORDER: Institution[] = [
  "sat",
  "imss",
  "infonavit",
  "stps_repse",
  "interno_cliente",
];

// State chip palette (matches attention_list).
const STATE_LABEL: Record<SlotState, string> = {
  rejected: "Rechazado",
  needs_correction: "Por aclarar",
  possible_mismatch: "Posible inconsistencia",
  expired: "Vencido",
  missing: "Pendiente",
  in_review: "En revisión",
  uploaded: "Subido",
  approved: "Aprobado",
  exception: "Excepción",
  not_applicable: "No aplica",
};

// Band geometry — must agree with backend URGENCY_BANDS.
const BAND_MAX = [7, 14, 30] as const; // last band is unbounded
const TIMELINE_MAX_DAYS = 30; // x-axis cap for the SVG
const SVG_W = 520;
const SVG_H = 80;
const PAD_X = 28;
const PAD_TOP = 28;
const BAND_Y = PAD_TOP + 10;
const BAND_H = 14;

function formatCountdown(days: number): string {
  if (days <= 0) return "hoy";
  if (days === 1) return "mañana";
  return `${days}d`;
}

function urgencyToneFor(days: number): "red" | "orange" | "yellow" | "gray" {
  if (days <= 7) return "red";
  if (days <= 14) return "orange";
  if (days <= 30) return "yellow";
  return "gray";
}

const TONE_FILL: Record<"red" | "orange" | "yellow" | "gray", string> = {
  red: "var(--state-red,#dc2626)",
  orange: "var(--state-orange,#ea580c)",
  yellow: "var(--state-yellow,#d97706)",
  gray: "var(--text-tertiary,#6b7280)",
};

const BAND_TINT: Record<"red" | "orange" | "yellow" | "gray", string> = {
  red: "color-mix(in srgb, var(--state-red,#dc2626) 14%, transparent)",
  orange: "color-mix(in srgb, var(--state-orange,#ea580c) 12%, transparent)",
  yellow: "color-mix(in srgb, var(--state-yellow,#d97706) 10%, transparent)",
  gray: "color-mix(in srgb, var(--text-tertiary,#6b7280) 8%, transparent)",
};

export const upcomingDeadlinesDefinition: Omit<
  BlockDefinition<UpcomingDeadlinesConfig, UpcomingDeadlinesData>,
  "Component"
> = {
  type: "upcoming_deadlines",
  label: "Próximos vencimientos",
  icon: CalendarBlank,
  description:
    "Línea de tiempo + tarjetas por institución + tabla con los próximos vencimientos.",
  defaultConfig: { top: 5 },
};

export function UpcomingDeadlinesBlock({
  block,
  interactive = true,
}: BlockProps<UpcomingDeadlinesConfig, UpcomingDeadlinesData>) {
  const data = block.data;

  if (!data) {
    return (
      <section className="space-y-2 py-2">
        <div className="border-y border-[color:var(--border-subtle)] py-3 text-[13px] text-[color:var(--text-tertiary)]">
          Cargando próximos vencimientos…
        </div>
      </section>
    );
  }

  const items = data.items ?? [];

  if (items.length === 0) {
    return (
      <section className="space-y-2 py-2" data-block-type="upcoming_deadlines">
        <div className="rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-elevated,transparent)] px-4 py-6 text-center">
          <p className="text-[14px] font-medium text-[color:var(--text-primary)]">
            Sin próximos vencimientos.
          </p>
          <p className="mt-1 text-[12px] text-[color:var(--text-tertiary)]">
            No hay obligaciones por vencer en los próximos periodos para este
            proveedor.
          </p>
        </div>
      </section>
    );
  }

  const buckets = data.urgency_buckets ?? {
    week: 0,
    fortnight: 0,
    month: 0,
    later: 0,
  };

  return (
    <section
      className="space-y-4 py-3"
      data-block-type="upcoming_deadlines"
    >
      {/* ── Timeline ── */}
      <TimelineSvg items={items} buckets={buckets} />

      {/* ── Per-institution cards ── */}
      <InstitutionCards items={items} interactive={interactive} />

      {/* ── Compact table (PDF-safe) ── */}
      <DeadlinesTable items={items} interactive={interactive} />

      {/* Footer meta */}
      <p className="text-[11px] text-[color:var(--text-tertiary)]">
        {items.length} de {data.total_before_filter} vencimientos
      </p>
      <FreshnessLabel fetchedAt={data.fetched_at} asOf={data.as_of} />
    </section>
  );
}

// ── Timeline ────────────────────────────────────────────────────

function TimelineSvg({
  items,
  buckets,
}: {
  items: UpcomingItem[];
  buckets: UrgencyBuckets;
}) {
  const innerW = SVG_W - PAD_X * 2;

  // Tick stops at 7, 14, 30 days (band boundaries).
  const ticks = BAND_MAX.map((d) => ({
    x: PAD_X + (d / TIMELINE_MAX_DAYS) * innerW,
    label: `${d}d`,
  }));

  return (
    <figure className="space-y-2">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-2 text-[11px] text-[color:var(--text-tertiary)]">
        <span className="cw-eyebrow">Línea de tiempo · próximos 30 días</span>
        <span className="flex flex-wrap items-center gap-3 font-mono tabular-nums">
          <BucketSwatch tone="red" label="Esta semana" count={buckets.week} />
          <BucketSwatch
            tone="orange"
            label="2 semanas"
            count={buckets.fortnight}
          />
          <BucketSwatch tone="yellow" label="Este mes" count={buckets.month} />
          <BucketSwatch tone="gray" label="Más adelante" count={buckets.later} />
        </span>
      </figcaption>
      <div className="overflow-x-auto rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-elevated,transparent)] p-3">
        <svg
          viewBox={`0 0 ${SVG_W} ${SVG_H}`}
          width="100%"
          height={SVG_H}
          role="img"
          aria-label="Línea de tiempo de vencimientos"
          className="block"
        >
          {/* Bands */}
          <rect
            x={PAD_X}
            y={BAND_Y}
            width={(7 / TIMELINE_MAX_DAYS) * innerW}
            height={BAND_H}
            fill={BAND_TINT.red}
          />
          <rect
            x={PAD_X + (7 / TIMELINE_MAX_DAYS) * innerW}
            y={BAND_Y}
            width={(7 / TIMELINE_MAX_DAYS) * innerW}
            height={BAND_H}
            fill={BAND_TINT.orange}
          />
          <rect
            x={PAD_X + (14 / TIMELINE_MAX_DAYS) * innerW}
            y={BAND_Y}
            width={(16 / TIMELINE_MAX_DAYS) * innerW}
            height={BAND_H}
            fill={BAND_TINT.yellow}
          />
          {/* Axis */}
          <line
            x1={PAD_X}
            x2={PAD_X + innerW}
            y1={BAND_Y + BAND_H}
            y2={BAND_Y + BAND_H}
            stroke="var(--border-subtle,#e5e7eb)"
            strokeWidth={1}
          />
          {ticks.map((t) => (
            <g key={t.label}>
              <line
                x1={t.x}
                x2={t.x}
                y1={BAND_Y}
                y2={BAND_Y + BAND_H + 4}
                stroke="var(--border-subtle,#e5e7eb)"
                strokeWidth={1}
              />
              <text
                x={t.x}
                y={BAND_Y + BAND_H + 16}
                textAnchor="middle"
                fontSize={10}
                fill="var(--text-tertiary,#6b7280)"
              >
                {t.label}
              </text>
            </g>
          ))}
          {/* Now label */}
          <text
            x={PAD_X}
            y={BAND_Y - 6}
            fontSize={10}
            fill="var(--text-tertiary,#6b7280)"
          >
            hoy
          </text>
          <text
            x={PAD_X + innerW}
            y={BAND_Y - 6}
            textAnchor="end"
            fontSize={10}
            fill="var(--text-tertiary,#6b7280)"
          >
            +{TIMELINE_MAX_DAYS}d
          </text>

          {/* Markers (one circle per item, capped at 30d for layout) */}
          {items.map((it) => {
            const clamped = Math.max(0, Math.min(TIMELINE_MAX_DAYS, it.due_in_days));
            const cx = PAD_X + (clamped / TIMELINE_MAX_DAYS) * innerW;
            const cy = BAND_Y + BAND_H / 2;
            const tone = urgencyToneFor(it.due_in_days);
            const inst = INSTITUTION_LABEL[it.institution] ?? it.institution;
            return (
              <g key={it.id}>
                <circle
                  cx={cx}
                  cy={cy}
                  r={5}
                  fill={TONE_FILL[tone]}
                  stroke="white"
                  strokeWidth={1.5}
                >
                  <title>
                    {inst} · {it.title} · {formatCountdown(it.due_in_days)}
                  </title>
                </circle>
              </g>
            );
          })}
        </svg>
      </div>
    </figure>
  );
}

function BucketSwatch({
  tone,
  label,
  count,
}: {
  tone: "red" | "orange" | "yellow" | "gray";
  label: string;
  count: number;
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <span
        aria-hidden="true"
        className="inline-block h-2 w-2 rounded-sm"
        style={{ background: TONE_FILL[tone] }}
      />
      <span className="text-[color:var(--text-secondary)]">{label}</span>
      <span className="font-semibold text-[color:var(--text-primary)]">{count}</span>
    </span>
  );
}

// ── Institution cards ───────────────────────────────────────────

function InstitutionCards({
  items,
  interactive = true,
}: {
  items: UpcomingItem[];
  interactive?: boolean;
}) {
  // Group: keep the SOONEST item per institution. Items are already
  // sorted ascending by due_in_days from the backend.
  const soonestByInst = new Map<Institution, UpcomingItem>();
  for (const it of items) {
    if (!soonestByInst.has(it.institution)) {
      soonestByInst.set(it.institution, it);
    }
  }
  // Render every institution in display order plus any extras that
  // appeared in the data (filter could include institutions not in the
  // canonical set).
  const institutionsInPlay = new Set<Institution>([
    ...INSTITUTION_ORDER,
    ...soonestByInst.keys(),
  ]);
  const ordered = Array.from(institutionsInPlay);

  // De-carded (2026-06): was a 4-up equal-card grid (a banned pattern,
  // and a third redundant representation of the timeline + table). Now a
  // clean hairline list — one row per institution, soonest deadline
  // first, countdown right-aligned.
  return (
    <ul className="divide-y divide-[color:var(--border-subtle)] border-y border-[color:var(--border-subtle)]">
      {ordered.map((inst) => {
        const item = soonestByInst.get(inst);
        if (!item) {
          return (
            <li
              key={inst}
              className="flex items-baseline justify-between gap-3 py-2.5"
            >
              <span className="cw-eyebrow">
                {INSTITUTION_LABEL[inst] ?? inst}
              </span>
              <span className="text-[12px] text-[color:var(--text-tertiary)]">
                Sin pendientes.
              </span>
            </li>
          );
        }
        const tone = urgencyToneFor(item.due_in_days);
        return (
          <li key={inst} className="py-2.5">
            <div className="flex items-baseline justify-between gap-3">
              <span className="cw-eyebrow">
                {INSTITUTION_LABEL[inst] ?? inst}
              </span>
              <span
                className="font-mono text-[12px] font-semibold tabular-nums"
                style={{ color: TONE_FILL[tone] }}
              >
                {formatCountdown(item.due_in_days)}
              </span>
            </div>
            <div className="mt-1 flex items-baseline justify-between gap-3">
              <p className="min-w-0 text-[13px] font-medium text-[color:var(--text-primary)]">
                {item.title}
                <span className="ml-2 font-mono text-[11px] font-normal text-[color:var(--text-tertiary)]">
                  {item.period_key ?? "—"}
                </span>
              </p>
              {/* Upload CTA only for the provider's own copy; other
                  audiences read the countdown as a finding. */}
              {interactive ? (
                <>
                  <a
                    href={item.href}
                    target="_blank"
                    rel="noreferrer"
                    className="shrink-0 rounded-sm border border-[color:var(--border-subtle)] px-2 py-0.5 text-[11px] font-medium text-[color:var(--text-primary)] hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ring)] print:hidden"
                  >
                    Subir documento
                  </a>
                  <span className="sr-only print:not-sr-only print:text-[11px] print:text-[color:var(--text-tertiary)]">
                    Acción: subir documento ({item.href})
                  </span>
                </>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

// ── Table (canonical PDF surface) ───────────────────────────────

function DeadlinesTable({
  items,
  interactive = true,
}: {
  items: UpcomingItem[];
  interactive?: boolean;
}) {
  return (
    <details className="rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-elevated,transparent)] print:open">
      <summary className="cursor-pointer select-none px-3 py-2 text-[12px] text-[color:var(--text-secondary)] print:hidden">
        Tabla detallada ({items.length})
      </summary>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="text-left text-[color:var(--text-tertiary)]">
              <th className="border-y border-[color:var(--border-subtle)] px-3 py-2 font-medium">
                Institución
              </th>
              <th className="border-y border-[color:var(--border-subtle)] px-3 py-2 font-medium">
                Documento
              </th>
              <th className="border-y border-[color:var(--border-subtle)] px-3 py-2 font-medium">
                Periodo
              </th>
              <th className="border-y border-[color:var(--border-subtle)] px-3 py-2 font-medium">
                Estado
              </th>
              <th className="border-y border-[color:var(--border-subtle)] px-3 py-2 text-right font-medium">
                Días
              </th>
              {interactive ? (
                <th className="border-y border-[color:var(--border-subtle)] px-3 py-2 text-right font-medium print:hidden">
                  Acción
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {items.map((it) => {
              const tone = urgencyToneFor(it.due_in_days);
              return (
                <tr
                  key={it.id}
                  className="border-b border-[color:var(--border-subtle)] last:border-b-0"
                >
                  <td className="px-3 py-2 text-[color:var(--text-secondary)]">
                    {INSTITUTION_LABEL[it.institution] ?? it.institution}
                  </td>
                  <td className="px-3 py-2 text-[color:var(--text-primary)]">
                    {it.title}
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]">
                    {it.period_key ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-[color:var(--text-secondary)]">
                    {STATE_LABEL[it.state] ?? it.state}
                  </td>
                  <td
                    className="px-3 py-2 text-right font-mono font-semibold tabular-nums"
                    style={{ color: TONE_FILL[tone] }}
                  >
                    {formatCountdown(it.due_in_days)}
                  </td>
                  {interactive ? (
                    <td className="px-3 py-2 text-right print:hidden">
                      <a
                        href={it.href}
                        target="_blank"
                        rel="noreferrer"
                        className="rounded-sm border border-[color:var(--border-subtle)] px-2 py-0.5 text-[11px] hover:bg-[color:var(--surface-hover)]"
                      >
                        Subir
                      </a>
                    </td>
                  ) : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}
