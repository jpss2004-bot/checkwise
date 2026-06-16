import {
  BellRinging,
  MagnifyingGlass,
  SealCheck,
  ShieldCheck,
} from "@phosphor-icons/react/dist/ssr";

import { Eyebrow, Lead, Section, SectionTitle } from "./_shared";

const STEPS = [
  { n: "01", icon: MagnifyingGlass, title: "Detecta", body: "Ve qué falta y qué vence, por proveedor, requisito y periodo." },
  { n: "02", icon: ShieldCheck, title: "Valida", body: "La IA clasifica el documento. El equipo CheckWise firma la decisión." },
  { n: "03", icon: BellRinging, title: "Anticipa", body: "Alertas 30 días antes del vencimiento, por correo y en el semáforo." },
  { n: "04", icon: SealCheck, title: "Demuestra", body: "Exporta el expediente firmado en PDF, Excel o HTML, listo para la inspección." },
] as const;

// Circuit frame — rounded rectangle, nodes at corners, clockwise 01→02→03→04
const VB_W = 1060;
const VB_H = 580;
const FL = 130, FT = 50, FR = 930, FB = 530;
const R = 28;

const FRAME_PATH = [
  `M${FL + R},${FT}`,
  `H${FR - R} Q${FR},${FT} ${FR},${FT + R}`,
  `V${FB - R} Q${FR},${FB} ${FR - R},${FB}`,
  `H${FL + R} Q${FL},${FB} ${FL},${FB - R}`,
  `V${FT + R} Q${FL},${FT} ${FL + R},${FT}`,
].join(" ");

// Clockwise direction arrows at mid-segment of each side
const FLOW_ARROWS = [
  { x: (FL + FR) / 2, y: FT, rot: 0 },
  { x: FR, y: (FT + FB) / 2, rot: 90 },
  { x: (FL + FR) / 2, y: FB, rot: 180 },
  { x: FL, y: (FT + FB) / 2, rot: -90 },
] as const;

// Nodes at the 4 corners (TL=01, TR=02, BR=03, BL=04)
const FRAME_NODES = [
  { step: STEPS[0], x: FL, y: FT, below: true },
  { step: STEPS[1], x: FR, y: FT, below: true },
  { step: STEPS[2], x: FR, y: FB, below: false },
  { step: STEPS[3], x: FL, y: FB, below: false },
] as const;

export function V2Shift() {
  return (
    <Section id="prevencion" band="soft">
      {/* Mobile header */}
      <div className="mx-auto max-w-[44ch] text-center lg:hidden">
        <Eyebrow className="justify-center">Prevención REPSE</Eyebrow>
        <SectionTitle accent="a la prevención del riesgo." className="mx-auto mt-4">
          Del seguimiento reactivo
        </SectionTitle>
        <Lead className="mx-auto mt-6">
          Un solo flujo: detecta, valida, anticipa y demuestra, antes de que
          llegue la inspección.
        </Lead>
      </div>

      {/* Desktop: circuit frame — headline centered inside, steps at corners */}
      <div className="relative mx-auto hidden w-full max-w-[1060px] lg:block">
        <div className="relative" style={{ aspectRatio: `${VB_W} / ${VB_H}` }}>
          <svg
            viewBox={`0 0 ${VB_W} ${VB_H}`}
            fill="none"
            aria-hidden="true"
            preserveAspectRatio="xMidYMid meet"
            className="absolute inset-0 h-full w-full overflow-visible"
          >
            {/* Dashed guide frame */}
            <path
              d={FRAME_PATH}
              stroke="hsl(var(--teal-500) / 0.28)"
              strokeWidth={2.5}
              strokeLinecap="round"
              strokeDasharray="2 11"
            />
            {/* Animated comet */}
            <path
              d={FRAME_PATH}
              pathLength={100}
              stroke="hsl(var(--teal-400))"
              strokeWidth={4}
              strokeLinecap="round"
              strokeDasharray="10 90"
              className="cw-flow-signal"
              style={{ filter: "drop-shadow(0 0 6px hsl(var(--teal-400) / 0.9))" }}
            />
            {/* Mid-segment direction arrows */}
            {FLOW_ARROWS.map((a, i) => (
              <g key={i} transform={`translate(${a.x} ${a.y}) rotate(${a.rot})`}>
                <path d="M-6,-8 L7,0 L-6,8 Z" fill="hsl(var(--teal-500) / 0.7)" />
              </g>
            ))}
          </svg>

          {/* Step nodes at the 4 corners */}
          {FRAME_NODES.map(({ step, x, y, below }) => {
            const Icon = step.icon;
            return (
              <div
                key={step.n}
                className="absolute -translate-x-1/2 -translate-y-1/2"
                style={{ left: `${(x / VB_W) * 100}%`, top: `${(y / VB_H) * 100}%` }}
              >
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-teal)] shadow-[var(--shadow-md)]">
                  <Icon className="h-7 w-7" weight="duotone" aria-hidden="true" />
                </div>
                <div
                  className={`absolute left-1/2 w-[210px] -translate-x-1/2 text-center ${
                    below ? "top-[calc(100%+0.8rem)]" : "bottom-[calc(100%+0.8rem)]"
                  }`}
                >
                  <div className="flex items-center justify-center gap-2">
                    <h3 className="font-display text-[21px] font-bold tracking-[-0.01em] text-[color:var(--text-primary)]">
                      {step.title}
                    </h3>
                    <span className="font-mono text-[12px] text-[color:var(--text-tertiary)]">
                      {step.n}
                    </span>
                  </div>
                  <p className="mt-1 text-[14px] leading-[1.5] text-[color:var(--text-secondary)]">
                    {step.body}
                  </p>
                </div>
              </div>
            );
          })}

          {/* Center headline — inside the circuit */}
          <div
            className="absolute -translate-x-1/2 -translate-y-1/2 w-[310px] text-center"
            style={{
              left: `${(((FL + FR) / 2) / VB_W) * 100}%`,
              top: `${(((FT + FB) / 2) / VB_H) * 100}%`,
            }}
          >
            <Eyebrow className="justify-center">Prevención REPSE</Eyebrow>
            <h2
              className="font-display mt-3 font-bold leading-[1.07] tracking-[-0.02em] [text-wrap:balance] text-[color:var(--text-primary)]"
              style={{ fontSize: "clamp(1.8rem, 2.4vw, 2.6rem)" }}
            >
              Del seguimiento{" "}
              <span className="text-[color:var(--text-teal)]">reactivo</span>
              {" "}a la prevención.
            </h2>
          </div>
        </div>
      </div>

      {/* Mobile / tablet: vertical flow with down-arrows */}
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
