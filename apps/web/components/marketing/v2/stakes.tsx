import {
  CurrencyDollar,
  Gavel,
  PauseCircle,
  Scales,
  ShieldWarning,
  Warning,
} from "@phosphor-icons/react/dist/ssr";

import { Container, Eyebrow } from "./_shared";

/**
 * Section 02 — Stakes · Por qué importa. The "cadena de responsabilidad":
 * a provider's incumplimiento travels the chain — proveedor → STPS/IMSS →
 * TÚ — and a red liability signal marches toward you, where responsabilidad
 * solidaria lands as concrete consequences. Makes the liability transfer
 * literal instead of three text cards. CSS-animated, reduced-motion safe.
 */
const STAGES = [
  { key: "prov", icon: Warning, label: "Tu proveedor incumple", sub: "Falta un documento o vence un requisito." },
  { key: "aut", icon: Gavel, label: "STPS · IMSS revisa", sub: "Una inspección encuentra el hueco." },
] as const;

const FALLOUT = [
  { icon: Scales, tone: "red", title: "Responsabilidad solidaria" },
  { icon: CurrencyDollar, tone: "amber", title: "Multas STPS e IMSS" },
  { icon: PauseCircle, tone: "red", title: "Operación detenida" },
] as const;

const VB_W = 1060;
const VB_H = 190;
const NX = [150, 530, 910] as const; // proveedor, autoridad, tú
const NY = 66;

export function V2Stakes() {
  return (
    <section
      id="riesgo"
      className="relative overflow-hidden bg-[#031019] text-white"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-[12%] right-[6%] -z-0 h-[560px] w-[560px] rounded-full opacity-25 blur-[150px] [background:radial-gradient(circle,#e5484d,transparent_62%)]"
      />
      <Container className="relative py-[clamp(4.5rem,9vw,8rem)]">
        <div className="mx-auto max-w-[46ch] text-center">
          <Eyebrow tone="onNavy">Responsabilidad solidaria</Eyebrow>
          <h2 className="font-display mx-auto mt-4 max-w-[18ch] text-[clamp(2.4rem,4.4vw,3.9rem)] font-bold leading-[1.03] tracking-[-0.02em] [text-wrap:balance]">
            El incumplimiento de un proveedor es{" "}
            <span className="text-[#ff7a7a]">tu riesgo</span>.
          </h2>
          <p className="mx-auto mt-6 max-w-[54ch] text-[18px] leading-[1.6] text-[hsl(var(--navy-200))] md:text-[20px]">
            Controlar tu propio cumplimiento no alcanza. Si un proveedor tuyo
            incumple sus obligaciones REPSE, la autoridad puede voltear a verte
            a ti — eso es la responsabilidad solidaria.
          </p>
        </div>

        {/* Desktop: the liability chain — a red signal marches proveedor → STPS/IMSS → TÚ */}
        <div className="relative mx-auto mt-16 hidden w-full max-w-[1000px] lg:block">
          <div className="relative" style={{ aspectRatio: `${VB_W} / ${VB_H}` }}>
            <svg
              viewBox={`0 0 ${VB_W} ${VB_H}`}
              fill="none"
              aria-hidden="true"
              preserveAspectRatio="xMidYMid meet"
              className="absolute inset-0 h-full w-full overflow-visible"
            >
              <path
                d={`M${NX[0]},${NY} L${NX[2]},${NY}`}
                stroke="hsl(var(--red-500) / 0.35)"
                strokeWidth={2.5}
                strokeLinecap="round"
                strokeDasharray="2 11"
              />
              <path
                d={`M${NX[0]},${NY} L${NX[2]},${NY}`}
                pathLength={100}
                stroke="#ff5a5f"
                strokeWidth={4}
                strokeLinecap="round"
                strokeDasharray="13 87"
                className="cw-flow-signal"
                style={{ filter: "drop-shadow(0 0 6px rgba(229,72,77,0.9))" }}
              />
              <path d="M0,-9 L14,0 L0,9 Z" transform={`translate(${NX[1] - 52} ${NY})`} fill="#ff5a5f" />
              <path d="M0,-9 L15,0 L0,9 Z" transform={`translate(${NX[2] - 66} ${NY})`} fill="#ff5a5f" />
            </svg>

            {STAGES.map((s, i) => {
              const Icon = s.icon;
              return (
                <div
                  key={s.key}
                  className="absolute -translate-x-1/2 -translate-y-1/2"
                  style={{ left: `${(NX[i] / VB_W) * 100}%`, top: `${(NY / VB_H) * 100}%` }}
                >
                  <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-white/15 bg-white/[0.06] text-white backdrop-blur">
                    <Icon className="h-7 w-7" weight="duotone" aria-hidden="true" />
                  </div>
                  <div className="absolute left-1/2 top-[calc(100%+0.7rem)] w-[210px] -translate-x-1/2 text-center">
                    <p className="text-[15px] font-semibold text-white">{s.label}</p>
                    <p className="mt-0.5 text-[12.5px] leading-[1.4] text-[hsl(var(--navy-200))]">{s.sub}</p>
                  </div>
                </div>
              );
            })}

            {/* TÚ — the emphasized endpoint */}
            <div
              className="absolute -translate-x-1/2 -translate-y-1/2"
              style={{ left: `${(NX[2] / VB_W) * 100}%`, top: `${(NY / VB_H) * 100}%` }}
            >
              <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-2xl border-2 border-[#ff7a7a]/60 bg-[#e5484d]/[0.18] text-[#ff7a7a] shadow-[0_0_46px_rgba(229,72,77,0.45)]">
                <ShieldWarning className="h-9 w-9" weight="duotone" aria-hidden="true" />
              </div>
              <div className="absolute left-1/2 top-[calc(100%+0.7rem)] w-[210px] -translate-x-1/2 text-center">
                <p className="font-display text-[18px] font-bold text-[#ff7a7a]">
                  Respondes tú
                </p>
                <p className="mt-0.5 text-[12.5px] leading-[1.4] text-[hsl(var(--navy-200))]">
                  La empresa contratante.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Mobile: vertical liability chain */}
        <ol className="mx-auto mt-12 flex max-w-[26rem] flex-col lg:hidden">
          {[
            ...STAGES,
            { key: "tu", icon: ShieldWarning, label: "Respondes tú", sub: "La empresa contratante.", em: true },
          ].map((s, i, arr) => {
            const Icon = s.icon;
            const em = "em" in s && s.em;
            return (
              <li key={s.key}>
                <div className="flex items-start gap-4">
                  <div
                    className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl ${
                      em
                        ? "border-2 border-[#ff7a7a]/60 bg-[#e5484d]/[0.18] text-[#ff7a7a]"
                        : "border border-white/15 bg-white/[0.06] text-white"
                    }`}
                  >
                    <Icon className="h-6 w-6" weight="duotone" aria-hidden="true" />
                  </div>
                  <div className="pt-1.5">
                    <p className={`text-[16px] font-semibold ${em ? "text-[#ff7a7a]" : "text-white"}`}>
                      {s.label}
                    </p>
                    <p className="mt-0.5 text-[13.5px] text-[hsl(var(--navy-200))]">
                      {s.sub}
                    </p>
                  </div>
                </div>
                {i < arr.length - 1 ? (
                  <div aria-hidden="true" className="my-1.5 ml-7 flex">
                    <svg viewBox="0 0 12 26" className="h-6 w-3 text-[#ff5a5f]" fill="none">
                      <path d="M6,0 V18" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 3" />
                      <path d="M1.5,13 L6,20 L10.5,13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>

        {/* Fallout — the compact impact that lands on you */}
        <div className="mt-14 flex flex-col items-center gap-4">
          <p className="font-mono text-[11.5px] uppercase tracking-[0.16em] text-[#ff9a9a]">
            Lo que cae sobre ti
          </p>
          <div className="flex flex-wrap items-center justify-center gap-2.5">
            {FALLOUT.map((f) => {
              const Icon = f.icon;
              const red = f.tone === "red";
              return (
                <span
                  key={f.title}
                  className={`inline-flex items-center gap-2 rounded-full border px-4 py-2 text-[14px] font-medium ${
                    red
                      ? "border-[#ff7a7a]/35 bg-[#e5484d]/[0.12] text-[#ffb3b3]"
                      : "border-[#f5a623]/35 bg-[#f5a623]/[0.12] text-[#f7c66b]"
                  }`}
                >
                  <Icon className="h-4 w-4" weight="duotone" aria-hidden="true" />
                  {f.title}
                </span>
              );
            })}
          </div>
        </div>
      </Container>
    </section>
  );
}
