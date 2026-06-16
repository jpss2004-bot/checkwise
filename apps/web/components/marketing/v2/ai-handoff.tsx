"use client";

import { useEffect, useState } from "react";
import { useReducedMotion } from "motion/react";
import { SealCheck, Sparkle, UserCheck } from "@phosphor-icons/react";

/**
 * AI → Human → Signed hand-off. Meaning: a document passing from the AI's
 * proposal, to the human's decision, to a signed/traceable record. The
 * active node lifts toward the viewer through z-space as the focus travels
 * the chain — the hand-off, in depth. Isolated client island, single
 * interval, reduced-motion → all lit, flat, no z.
 */
const NODES = [
  { icon: Sparkle, tag: "La IA propone", sub: "Lee, clasifica y redacta el borrador." },
  { icon: UserCheck, tag: "El humano decide", sub: "El equipo valida cada documento legal." },
  { icon: SealCheck, tag: "Queda firmado", sub: "Actor, acción y fecha. Trazable." },
] as const;

export function AiHandoff() {
  const reduced = useReducedMotion();
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (reduced) return;
    const id = setInterval(() => setActive((a) => (a + 1) % NODES.length), 1800);
    return () => clearInterval(id);
  }, [reduced]);

  return (
    <div style={{ perspective: "1100px" }}>
      <div
        className="grid gap-4 md:grid-cols-3"
        style={{ transformStyle: "preserve-3d" }}
      >
        {NODES.map((n, i) => {
          const Icon = n.icon;
          const on = i === active || reduced;
          const signed = i === 2;
          return (
            <div
              key={n.tag}
              style={{
                transform: reduced
                  ? undefined
                  : on
                    ? "translateZ(40px) translateY(-4px)"
                    : "translateZ(-16px)",
                transition: "transform 600ms cubic-bezier(0.16,1,0.3,1)",
              }}
              className={`rounded-3xl border p-7 transition-[border-color,background-color,box-shadow] duration-500 ${
                on
                  ? signed
                    ? "border-[hsl(var(--teal-400))]/50 bg-[hsl(var(--teal-500))]/[0.12] shadow-[0_30px_70px_-30px_rgba(9,193,176,0.5)]"
                    : "border-white/25 bg-white/[0.07] shadow-[0_30px_70px_-34px_rgba(0,0,0,0.55)]"
                  : "border-white/10 bg-white/[0.03]"
              }`}
            >
              <span
                className={`inline-flex h-12 w-12 items-center justify-center rounded-xl transition-colors duration-500 ${
                  on
                    ? "bg-[hsl(var(--teal-500))]/20 text-[hsl(var(--teal-300))]"
                    : "bg-white/[0.06] text-[hsl(var(--navy-200))]"
                }`}
              >
                <Icon className="h-6 w-6" weight="duotone" aria-hidden="true" />
              </span>
              <p className="mt-5 font-mono text-[10.5px] uppercase tracking-[0.14em] text-[hsl(var(--teal-300))]">
                {n.tag}
              </p>
              <h3 className="font-display mt-1.5 text-[18px] font-semibold text-white">
                {n.sub}
              </h3>
            </div>
          );
        })}
      </div>
    </div>
  );
}
