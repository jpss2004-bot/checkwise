import { PauseCircle, Scales, Warning } from "@phosphor-icons/react/dist/ssr";

import { Container, Eyebrow } from "./_shared";
import { RiskMeter } from "./stakes-risk-meter";

/**
 * Section 02 — Stakes · Por qué importa.
 *
 * Bold: dark band + a semáforo-red "exposure" glow (color that means risk),
 * an asymmetric bento (not 3 equal cards), and a risk meter that fills
 * green→red (the motion says "your exposure is rising"). Low-text.
 */
export function V2Stakes() {
  return (
    <section
      id="riesgo"
      className="relative overflow-hidden bg-[#031019] text-white"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-[12%] right-[6%] -z-0 h-[540px] w-[540px] rounded-full opacity-25 blur-[150px] [background:radial-gradient(circle,#e5484d,transparent_62%)]"
      />
      <Container className="relative py-[clamp(4.5rem,9vw,8rem)]">
        <Eyebrow tone="onNavy">Por qué importa</Eyebrow>
        <h2 className="font-display mt-4 max-w-[16ch] text-[clamp(2rem,3.6vw,3.2rem)] font-bold leading-[1.05] tracking-[-0.02em] [text-wrap:balance]">
          El incumplimiento de un proveedor es{" "}
          <span className="text-[#ff7a7a]">tu riesgo</span>.
        </h2>
        <p className="mt-5 max-w-[50ch] text-[16px] leading-[1.6] text-[hsl(var(--navy-200))]">
          Si un proveedor incumple sus obligaciones REPSE, la autoridad puede
          voltear a verte a ti.
        </p>

        <div className="mt-12 grid gap-4 md:grid-cols-12">
          {/* Lead tile — responsabilidad solidaria + risk meter */}
          <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-7 md:col-span-7 md:p-9">
            <div className="flex items-center gap-3">
              <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-[#e5484d]/15 text-[#ff7a7a]">
                <Scales className="h-5 w-5" weight="duotone" aria-hidden="true" />
              </span>
              <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-[#ff9a9a]">
                Responsabilidad solidaria
              </span>
            </div>
            <p className="font-display mt-5 max-w-[32ch] text-[22px] font-semibold leading-[1.2] text-white">
              Respondes por las obligaciones laborales y fiscales del proveedor
              incumplido.
            </p>
            <div className="mt-8">
              <RiskMeter />
            </div>
          </div>

          {/* Right column — two stacked tiles */}
          <div className="grid gap-4 md:col-span-5">
            <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-7">
              <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-[#f5a623]/15 text-[#f5a623]">
                <Warning className="h-5 w-5" weight="duotone" aria-hidden="true" />
              </span>
              <h3 className="font-display mt-4 text-[18px] font-semibold text-white">
                Multas de la STPS e IMSS
              </h3>
              <p className="mt-1.5 text-[13.5px] leading-[1.5] text-[hsl(var(--navy-200))]">
                Por contratar servicios sin verificar el cumplimiento documental.
              </p>
            </div>
            <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-7">
              <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-[hsl(var(--teal-500))]/15 text-[hsl(var(--teal-300))]">
                <PauseCircle className="h-5 w-5" weight="duotone" aria-hidden="true" />
              </span>
              <h3 className="font-display mt-4 text-[18px] font-semibold text-white">
                Operación detenida
              </h3>
              <p className="mt-1.5 text-[13.5px] leading-[1.5] text-[hsl(var(--navy-200))]">
                Una inspección sin expediente frena pagos, contratos y
                continuidad.
              </p>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
