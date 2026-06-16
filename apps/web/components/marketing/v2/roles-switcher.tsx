"use client";

import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  ChartLineUp,
  Gavel,
  ShieldCheck,
  Truck,
  UserCircle,
} from "@phosphor-icons/react";

/**
 * Roles switcher — meaning: "five views, one truth." A shared-element
 * (layoutId) pill slides between roles; the same operation re-frames per
 * role (the `view` chip). One source of truth, made literal.
 */
const EASE = [0.16, 1, 0.3, 1] as const;

const ROLES = [
  { key: "cliente", icon: UserCircle, name: "Cliente", line: "Tu portafolio en semáforo: qué falta, qué vence y qué está en riesgo.", view: "78% al día · 3 en riesgo" },
  { key: "proveedor", icon: Truck, name: "Proveedor", line: "Carga su evidencia por requisito, sin correos sueltos.", view: "5 pasos · 2 pendientes" },
  { key: "checkwise", icon: ShieldCheck, name: "CheckWise", line: "El equipo revisa, valida y firma cada decisión documental.", view: "12 en revisión" },
  { key: "reportes", icon: ChartLineUp, name: "Reportes", line: "Exporta el estado del portafolio para dirección y auditoría.", view: "PDF · Excel · HTML" },
  { key: "auditoria", icon: Gavel, name: "Auditoría", line: "Acceso de auditor con el expediente completo y trazable.", view: "Expediente firmado" },
] as const;

export function RolesSwitcher() {
  const reduced = useReducedMotion();
  const [active, setActive] = useState(0);
  const role = ROLES[active];
  const Icon = role.icon;

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {ROLES.map((r, i) => {
          const on = i === active;
          return (
            <button
              key={r.key}
              type="button"
              onClick={() => setActive(i)}
              className={`relative rounded-full px-4 py-2 text-[13.5px] font-medium transition-colors ${
                on
                  ? "text-white"
                  : "text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]"
              }`}
            >
              {on ? (
                <motion.span
                  layoutId="role-pill"
                  className="absolute inset-0 -z-10 rounded-full bg-[color:var(--interactive-primary)]"
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                />
              ) : null}
              {r.name}
            </button>
          );
        })}
      </div>

      <div className="mt-8 overflow-hidden rounded-3xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-8 shadow-[var(--shadow-sm)]">
        <AnimatePresence mode="wait">
          <motion.div
            key={role.key}
            initial={reduced ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduced ? { opacity: 1 } : { opacity: 0, y: -10 }}
            transition={{ duration: 0.28, ease: EASE }}
            className="grid items-center gap-6 sm:grid-cols-[auto_1fr]"
          >
            <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]">
              <Icon className="h-8 w-8" weight="duotone" aria-hidden="true" />
            </span>
            <div>
              <h3 className="font-display text-[22px] font-bold text-[color:var(--text-primary)]">
                {role.name}
              </h3>
              <p className="mt-1.5 max-w-[46ch] text-[15px] leading-[1.55] text-[color:var(--text-secondary)]">
                {role.line}
              </p>
              <div className="mt-4 inline-flex items-center gap-2 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-page)] px-3 py-1.5 font-mono text-[12px] text-[color:var(--text-primary)]">
                <span className="cw-pulse-soft h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
                {role.view}
              </div>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
