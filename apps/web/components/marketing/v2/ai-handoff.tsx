"use client";

import { useEffect, useState } from "react";
import { useReducedMotion } from "motion/react";
import { SealCheck, Sparkle, UserCheck } from "@phosphor-icons/react";

/**
 * AI → Human → Signed hand-off. Meaning: a document passing from the AI's
 * proposal, to the human's decision, to a signed/traceable record. The
 * active highlight cycles through the chain. Isolated client island,
 * single interval, reduced-motion → all lit static.
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
    <div className="grid gap-4 md:grid-cols-3">
      {NODES.map((n, i) => {
        const Icon = n.icon;
        const on = i === active || reduced;
        const signed = i === 2;
        return (
          <div
            key={n.tag}
            className={`rounded-3xl border p-7 transition-[transform,border-color,background-color] duration-500 ${
              on
                ? signed
                  ? "border-[hsl(var(--teal-400))]/50 bg-[hsl(var(--teal-500))]/[0.12] lg:-translate-y-1"
                  : "border-white/25 bg-white/[0.07] lg:-translate-y-1"
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
  );
}
