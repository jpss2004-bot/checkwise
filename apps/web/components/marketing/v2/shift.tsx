import {
  BellRinging,
  MagnifyingGlass,
  SealCheck,
  ShieldCheck,
} from "@phosphor-icons/react/dist/ssr";

import { Eyebrow, Lead, Section, SectionTitle } from "./_shared";

/**
 * Section 03 — Shift · Reactivo → Preventivo.
 *
 * Meaning: "a compliance signal travels detect → prove." A centered header
 * sits over a bold curved wave through the four steps, joined by directional
 * flow arrows (node arrowheads + mid-segment chevrons), with a teal comet
 * running the whole path 01→04 (CSS .cw-flow-signal, reduced-motion safe).
 * Light band = relief after the two dark risk scenes.
 */
const STEPS = [
  { n: "01", icon: MagnifyingGlass, title: "Detecta", body: "Ve qué falta y qué vence, por proveedor, requisito y periodo." },
  { n: "02", icon: ShieldCheck, title: "Valida", body: "La IA clasifica el documento. El equipo CheckWise firma la decisión." },
  { n: "03", icon: BellRinging, title: "Anticipa", body: "Alertas 30 días antes del vencimiento, por correo y en el semáforo." },
  { n: "04", icon: SealCheck, title: "Demuestra", body: "Exporta el expediente firmado en PDF, Excel o HTML, listo para la inspección." },
] as const;

// Node centres in the SVG viewBox — a pronounced wave (high, low, high, low)
// so the flow fills the band vertically instead of sitting in dead space.
const VB_W = 1060;
const VB_H = 330;
const NODES = [
  { cx: 110, cy: 78, high: true },
  { cx: 390, cy: 252, high: false },
  { cx: 670, cy: 78, high: true },
  { cx: 950, cy: 252, high: false },
] as const;

const FLOW_PATH =
  "M110,78 C250,78 250,252 390,252 C530,252 530,78 670,78 C810,78 810,252 950,252";

// Mid-segment flow arrows, rotated to the curve's mid-tangent (≈ ±51°).
const MID_ARROWS = [
  { x: 250, y: 165, rot: 51 },
  { x: 530, y: 165, rot: -51 },
  { x: 810, y: 165, rot: 51 },
] as const;

export function V2Shift() {
  return (
    <Section id="prevencion" band="soft">
      <div className="mx-auto max-w-[44ch] text-center">
        <Eyebrow className="justify-center">Prevención REPSE</Eyebrow>
        <SectionTitle accent="a la prevención del riesgo." className="mx-auto mt-4">
          Del seguimiento reactivo
        </SectionTitle>
        <Lead className="mx-auto mt-6">
          Un solo flujo: detecta, valida, anticipa y demuestra, antes de que
          llegue la inspección.
        </Lead>
      </div>

      {/* Desktop: the curved wave with directional flow arrows + comet. */}
      <div className="relative mx-auto mt-8 hidden w-full max-w-[1060px] lg:block">
        <div className="relative" style={{ aspectRatio: `${VB_W} / ${VB_H}` }}>
          <svg
            viewBox={`0 0 ${VB_W} ${VB_H}`}
            fill="none"
            aria-hidden="true"
            preserveAspectRatio="xMidYMid meet"
            className="absolute inset-0 h-full w-full overflow-visible"
          >
            <path
              d={FLOW_PATH}
              stroke="hsl(var(--teal-500) / 0.30)"
              strokeWidth={2.5}
              strokeLinecap="round"
              strokeDasharray="1.5 10"
            />
            <path
              d={FLOW_PATH}
              pathLength={100}
              stroke="hsl(var(--teal-400))"
              strokeWidth={4}
              strokeLinecap="round"
              strokeDasharray="13 87"
              className="cw-flow-signal"
              style={{ filter: "drop-shadow(0 0 6px hsl(var(--teal-400) / 0.9))" }}
            />
            {/* bigger arrowheads approaching nodes 02, 03, 04 */}
            {NODES.slice(1).map((nd) => (
              <path
                key={`n${nd.cx}`}
                d="M0,-9 L14,0 L0,9 Z"
                transform={`translate(${nd.cx - 52} ${nd.cy})`}
                fill="hsl(var(--teal-500))"
              />
            ))}
            {/* mid-segment flow arrows (aumentar flechas) */}
            {MID_ARROWS.map((a) => (
              <path
                key={`m${a.x}`}
                d="M0,-7 L11,0 L0,7 Z"
                transform={`translate(${a.x} ${a.y}) rotate(${a.rot})`}
                fill="hsl(var(--teal-500) / 0.7)"
              />
            ))}
          </svg>

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
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-teal)] shadow-[var(--shadow-md)]">
                  <Icon className="h-7 w-7" weight="duotone" aria-hidden="true" />
                </div>
                <div
                  className={`absolute left-1/2 w-[210px] -translate-x-1/2 text-center ${
                    nd.high
                      ? "top-[calc(100%+0.8rem)]"
                      : "bottom-[calc(100%+0.8rem)]"
                  }`}
                >
                  <div className="flex items-center justify-center gap-2">
                    <h3 className="font-display text-[21px] font-bold tracking-[-0.01em] text-[color:var(--text-primary)]">
                      {s.title}
                    </h3>
                    <span className="font-mono text-[12px] text-[color:var(--text-tertiary)]">
                      {s.n}
                    </span>
                  </div>
                  <p className="mt-1 text-[14px] leading-[1.5] text-[color:var(--text-secondary)]">
                    {s.body}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Mobile / tablet: a vertical flow with down-arrows between steps. */}
      <ol className="mx-auto mt-12 flex max-w-[30rem] flex-col lg:hidden">
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          return (
            <li key={s.n}>
              <div className="flex items-start gap-4">
                <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-teal)] shadow-[var(--shadow-sm)]">
                  <Icon className="h-7 w-7" weight="duotone" aria-hidden="true" />
                </div>
                <div className="pt-2">
                  <div className="flex items-center gap-2">
                    <h3 className="font-display text-[20px] font-bold tracking-[-0.01em] text-[color:var(--text-primary)]">
                      {s.title}
                    </h3>
                    <span className="font-mono text-[12px] text-[color:var(--text-tertiary)]">
                      {s.n}
                    </span>
                  </div>
                  <p className="mt-1 max-w-[34ch] text-[15px] leading-[1.5] text-[color:var(--text-secondary)]">
                    {s.body}
                  </p>
                </div>
              </div>
              {i < STEPS.length - 1 ? (
                <div aria-hidden="true" className="my-2 ml-8 flex">
                  <svg viewBox="0 0 12 30" className="h-8 w-3 text-[hsl(var(--teal-500))]" fill="none">
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
