import {
  BellRinging,
  MagnifyingGlass,
  SealCheck,
  ShieldCheck,
} from "@phosphor-icons/react/dist/ssr";

import { Eyebrow, Section, SectionTitle } from "./_shared";

/**
 * Section 03 — Shift · Reactivo → Preventivo.
 *
 * Meaning: "a compliance signal travels detect → prove." The four steps sit
 * on a curved wave (non-linear, playful), joined by directional arrows, and
 * a single teal comet runs the whole path 01→04 (CSS .cw-flow-signal,
 * reduced-motion safe). Light band = relief after the two dark risk scenes.
 */
const STEPS = [
  { n: "01", icon: MagnifyingGlass, title: "Detecta", body: "Faltantes y vencimientos por requisito." },
  { n: "02", icon: ShieldCheck, title: "Valida", body: "Verificación con IA y revisión humana." },
  { n: "03", icon: BellRinging, title: "Anticipa", body: "Recordatorios antes de cada vencimiento." },
  { n: "04", icon: SealCheck, title: "Demuestra", body: "Expediente auditable, siempre listo." },
] as const;

// Node centres inside the SVG viewBox. A gentle wave (high, low, high, low)
// so the flow swoops between steps instead of reading as a flat line.
const VB_W = 1040;
const VB_H = 360;
const NODES = [
  { cx: 100, cy: 122, high: true },
  { cx: 385, cy: 248, high: false },
  { cx: 655, cy: 122, high: true },
  { cx: 940, cy: 248, high: false },
] as const;

// One continuous wave through the four centres (smooth cubic S-curves, with
// horizontal tangents at each node so the arrowheads point cleanly forward).
const FLOW_PATH =
  "M100,122 C235,122 250,248 385,248 C520,248 540,122 655,122 C800,122 805,248 940,248";

export function V2Shift() {
  return (
    <Section id="prevencion" band="soft">
      <div className="max-w-[44ch]">
        <Eyebrow>Prevención REPSE</Eyebrow>
        <SectionTitle accent="a la prevención del riesgo." className="mt-4">
          Del seguimiento reactivo
        </SectionTitle>
      </div>

      {/* Desktop: the curved wave with directional arrows + traveling comet. */}
      <div className="relative mx-auto mt-14 hidden w-full max-w-[1040px] lg:block">
        <div className="relative" style={{ aspectRatio: `${VB_W} / ${VB_H}` }}>
          <svg
            viewBox={`0 0 ${VB_W} ${VB_H}`}
            fill="none"
            aria-hidden="true"
            preserveAspectRatio="xMidYMid meet"
            className="absolute inset-0 h-full w-full overflow-visible"
          >
            {/* faint dotted rail */}
            <path
              d={FLOW_PATH}
              stroke="hsl(var(--teal-500) / 0.30)"
              strokeWidth={2}
              strokeLinecap="round"
              strokeDasharray="1.5 9"
            />
            {/* traveling comet — spans all four nodes */}
            <path
              d={FLOW_PATH}
              pathLength={100}
              stroke="hsl(var(--teal-400))"
              strokeWidth={3.5}
              strokeLinecap="round"
              strokeDasharray="12 88"
              className="cw-flow-signal"
              style={{ filter: "drop-shadow(0 0 5px hsl(var(--teal-400) / 0.85))" }}
            />
            {/* directional arrowheads approaching nodes 02, 03, 04 (flow → right) */}
            {NODES.slice(1).map((nd) => (
              <path
                key={nd.cx}
                d="M0,-7 L11,0 L0,7 Z"
                transform={`translate(${nd.cx - 44} ${nd.cy})`}
                fill="hsl(var(--teal-500))"
              />
            ))}
          </svg>

          {/* nodes (HTML, centred on each path point) */}
          {NODES.map((nd, i) => {
            const s = STEPS[i];
            const Icon = s.icon;
            return (
              <div
                key={s.n}
                className="absolute -translate-x-1/2 -translate-y-1/2"
                style={{
                  left: `${(nd.cx / VB_W) * 100}%`,
                  top: `${(nd.cy / VB_H) * 100}%`,
                }}
              >
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-teal)] shadow-[var(--shadow-md)]">
                  <Icon className="h-6 w-6" weight="duotone" aria-hidden="true" />
                </div>
                <div
                  className={`absolute left-1/2 w-[190px] -translate-x-1/2 text-center ${
                    nd.high
                      ? "top-[calc(100%+0.7rem)]"
                      : "bottom-[calc(100%+0.7rem)]"
                  }`}
                >
                  <div className="flex items-center justify-center gap-2">
                    <h3 className="font-display text-[19px] font-bold tracking-[-0.01em] text-[color:var(--text-primary)]">
                      {s.title}
                    </h3>
                    <span className="font-mono text-[12px] text-[color:var(--text-tertiary)]">
                      {s.n}
                    </span>
                  </div>
                  <p className="mt-1 text-[13.5px] leading-[1.5] text-[color:var(--text-secondary)]">
                    {s.body}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Mobile / tablet: a vertical flow with down-arrows between steps. */}
      <ol className="mt-12 flex flex-col lg:hidden">
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          return (
            <li key={s.n}>
              <div className="flex items-start gap-4">
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-teal)] shadow-[var(--shadow-sm)]">
                  <Icon className="h-6 w-6" weight="duotone" aria-hidden="true" />
                </div>
                <div className="pt-1.5">
                  <div className="flex items-center gap-2">
                    <h3 className="font-display text-[19px] font-bold tracking-[-0.01em] text-[color:var(--text-primary)]">
                      {s.title}
                    </h3>
                    <span className="font-mono text-[12px] text-[color:var(--text-tertiary)]">
                      {s.n}
                    </span>
                  </div>
                  <p className="mt-1 max-w-[34ch] text-[14px] leading-[1.5] text-[color:var(--text-secondary)]">
                    {s.body}
                  </p>
                </div>
              </div>
              {i < STEPS.length - 1 ? (
                <div aria-hidden="true" className="my-2 ml-7 flex">
                  <svg viewBox="0 0 12 30" className="h-7 w-3 text-[hsl(var(--teal-500))]" fill="none">
                    <path d="M6,0 V23" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 3" />
                    <path d="M1.5,18 L6,25 L10.5,18" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
    </Section>
  );
}
