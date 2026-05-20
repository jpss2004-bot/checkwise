"use client";

import { motion } from "motion/react";

import { Reveal, Stagger, STAGGER_ITEM_VARIANTS, EASE_ENTER } from "./motion-helpers";
import { useMotionPreference } from "./motion-preference";

const STEPS = [
  {
    number: "01",
    title: "Invita a tu proveedor o cliente",
    body:
      "Envías un correo con su acceso temporal desde el panel de CheckWise. Listo en menos de un minuto.",
  },
  {
    number: "02",
    title: "Activa la cuenta",
    body:
      "El proveedor ingresa con su código, crea contraseña y completa sus datos. Dos minutos guiados.",
  },
  {
    number: "03",
    title: "Completa el expediente inicial",
    body:
      "Checklist guiada con documentos, formato esperado y siguientes pasos para desbloquear el calendario.",
  },
  {
    number: "04",
    title: "Sube los documentos recurrentes",
    body:
      "Calendario REPSE integrado: SAT, IMSS, INFONAVIT y STPS con sus periodos correctos.",
  },
  {
    number: "05",
    title: "Revisa estados y deadlines",
    body:
      "Semáforo de cumplimiento, acciones sugeridas y revisor humano cuando hace falta criterio legal.",
  },
  {
    number: "06",
    title: "Genera reportes para tu cliente",
    body:
      "Mensuales, por proveedor, por riesgo. Listos para enviar a dirección o auditoría con un clic.",
  },
] as const;

export function HowItWorksSection() {
  const { reduced: reduce } = useMotionPreference();
  return (
    <section id="como-funciona" className="bg-[color:var(--surface-page)]">
      <div className="mx-auto max-w-[1320px] px-5 py-20 lg:py-28">
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)] lg:gap-16">
          {/* Sticky intro */}
          <div>
            <div className="lg:sticky lg:top-24">
              <Reveal>
                <p className="cw-eyebrow text-[color:var(--text-teal)]">
                  Cómo funciona
                </p>
                <h2
                  className="mt-3 font-semibold tracking-[-0.02em] text-[color:var(--text-primary)]"
                  style={{
                    fontSize: "clamp(1.75rem, 2.6vw, 2.25rem)",
                    lineHeight: 1.1,
                  }}
                >
                  De la invitación al reporte ejecutivo, sin spreadsheets de por medio.
                </h2>
                <p className="mt-4 max-w-[44ch] text-[14.5px] leading-[1.65] text-[color:var(--text-secondary)]">
                  Seis pasos para que un proveedor pase de cero a expediente
                  completo, y tu equipo gane visibilidad operativa real.
                </p>
              </Reveal>
            </div>
          </div>

          {/* Steps rail */}
          <Stagger className="relative space-y-0">
            {/* Vertical connector */}
            <div
              aria-hidden="true"
              className="absolute left-[18px] top-2 bottom-2 hidden w-px bg-[color:var(--border-default)] sm:block"
            />
            {STEPS.map((step, idx) => (
              <motion.li
                key={step.number}
                variants={reduce ? undefined : STAGGER_ITEM_VARIANTS}
                transition={reduce ? undefined : { duration: 0.5, ease: EASE_ENTER }}
                className="relative flex gap-4 py-5 sm:gap-5"
              >
                <span
                  aria-hidden="true"
                  className={`relative z-10 mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border bg-[color:var(--surface-raised)] font-mono text-[11px] font-semibold tabular-nums ${
                    idx === 0
                      ? "border-[color:var(--border-brand)] text-[color:var(--text-brand)]"
                      : "border-[color:var(--border-default)] text-[color:var(--text-secondary)]"
                  }`}
                >
                  {step.number}
                </span>
                <div className="min-w-0 flex-1 border-b border-[color:var(--border-subtle)] pb-5">
                  <h3 className="text-[15.5px] font-semibold leading-snug text-[color:var(--text-primary)]">
                    {step.title}
                  </h3>
                  <p className="mt-1.5 max-w-[58ch] text-[13.5px] leading-[1.6] text-[color:var(--text-secondary)]">
                    {step.body}
                  </p>
                </div>
              </motion.li>
            ))}
          </Stagger>
        </div>
      </div>
    </section>
  );
}
