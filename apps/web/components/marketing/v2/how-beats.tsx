"use client";

import { useEffect, useState } from "react";
import { useReducedMotion } from "motion/react";
import {
  CalendarBlank,
  Eye,
  FileText,
  UploadSimple,
} from "@phosphor-icons/react";

/**
 * How-it-works beats with a cycling "active" highlight — the document
 * moving through the loop (calendario → reporte). Isolated client island,
 * single interval, reduced-motion → first beat static.
 */
const BEATS = [
  { n: "01", icon: CalendarBlank, title: "Calendario", body: "151 obligaciones por proveedor, periodo e institución." },
  { n: "02", icon: UploadSimple, title: "Evidencia", body: "Carga guiada en 5 pasos, en su lugar exacto." },
  { n: "03", icon: Eye, title: "Revisión", body: "Verificación con IA y decisión del equipo." },
  { n: "04", icon: FileText, title: "Reporte", body: "Paquete auditable, con trazabilidad firmada." },
] as const;

export function HowBeats() {
  const reduced = useReducedMotion();
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (reduced) return;
    const id = setInterval(() => setActive((a) => (a + 1) % BEATS.length), 2200);
    return () => clearInterval(id);
  }, [reduced]);

  return (
    <ol className="flex flex-col gap-3">
      {BEATS.map((b, i) => {
        const Icon = b.icon;
        const on = i === active;
        return (
          <li
            key={b.n}
            className={`flex items-start gap-4 rounded-2xl border p-4 transition-[background-color,border-color,transform] duration-500 ${
              on
                ? "border-[color:var(--border-ai)] bg-[color:var(--surface-teal-muted)] lg:translate-x-1"
                : "border-transparent bg-transparent"
            }`}
          >
            <span
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors duration-500 ${
                on
                  ? "bg-[color:var(--interactive-secondary)] text-white"
                  : "bg-[color:var(--surface-sunken)] text-[color:var(--text-teal)]"
              }`}
            >
              <Icon className="h-5 w-5" weight="duotone" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <div className="flex items-baseline gap-2">
                <h3 className="text-[16px] font-semibold text-[color:var(--text-primary)]">
                  {b.title}
                </h3>
                <span className="font-mono text-[11px] text-[color:var(--text-tertiary)]">
                  {b.n}
                </span>
              </div>
              <p className="mt-0.5 text-[13.5px] leading-[1.5] text-[color:var(--text-secondary)]">
                {b.body}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
