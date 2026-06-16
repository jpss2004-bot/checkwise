"use client";

import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import {
  ChartLineUp,
  Gavel,
  ShieldCheck,
  Truck,
  UserCircle,
} from "@phosphor-icons/react";

import { ProductFrame } from "../product-frame";

/**
 * Roles switcher — "cinco vistas, un expediente." Tabs sit in a visible
 * segmented group so the chosen view is remarcada (filled pill, shared
 * layoutId) while the others stay present (not eliminated). The content
 * area crossfades a two-column block: the view's copy + a real screenshot
 * of that view. All previews are mounted (opacity-stacked) so switching
 * never flashes. Reduced motion → instant.
 */
const EASE = [0.16, 1, 0.3, 1] as const;

const ROLES = [
  {
    key: "cliente",
    icon: UserCircle,
    name: "Cliente",
    line: "Tu portafolio en semáforo: qué falta, qué vence y qué está en riesgo.",
    view: "78% al día · 3 en riesgo",
    img: "/marketing/product/client-dashboard.png",
    chrome: "Cliente · resumen del portafolio",
    alt: "Vista cliente: portafolio de proveedores en semáforo.",
  },
  {
    key: "proveedor",
    icon: Truck,
    name: "Proveedor",
    line: "Carga su evidencia por requisito, sin correos sueltos.",
    view: "5 pasos · 2 pendientes",
    img: "/marketing/product/portal-upload.png",
    chrome: "Proveedor · carga de evidencia",
    alt: "Vista proveedor: carga guiada de evidencia por requisito.",
  },
  {
    key: "checkwise",
    icon: ShieldCheck,
    name: "CheckWise",
    line: "El equipo revisa, valida y firma cada decisión documental.",
    view: "12 en revisión",
    img: "/marketing/product/admin-reviewer-queue.png",
    chrome: "CheckWise · cola de revisión",
    alt: "Consola CheckWise: cola de revisión y validación documental.",
  },
  {
    key: "reportes",
    icon: ChartLineUp,
    name: "Reportes",
    line: "Exporta el estado del portafolio para dirección y auditoría.",
    view: "PDF · Excel · HTML",
    img: "/marketing/product/client-reports.png",
    chrome: "Reportes · exportación",
    alt: "Reportes CheckWise: estado del portafolio para dirección y auditoría.",
  },
  {
    key: "auditoria",
    icon: Gavel,
    name: "Auditoría",
    line: "Acceso de auditor con el expediente completo y trazable.",
    view: "Expediente firmado",
    img: "/marketing/product/client-auditoria.png",
    chrome: "Auditoría · expediente",
    alt: "Vista de auditoría: expediente completo y trazable.",
  },
] as const;

export function RolesSwitcher() {
  const reduced = useReducedMotion();
  const [active, setActive] = useState(0);

  return (
    <div>
      <div className="inline-flex max-w-full flex-wrap gap-1 rounded-2xl border border-[color:var(--border-default)] bg-[color:var(--surface-page)] p-1">
        {ROLES.map((r, i) => {
          const on = i === active;
          return (
            <button
              key={r.key}
              type="button"
              onClick={() => setActive(i)}
              aria-pressed={on}
              className={`relative rounded-xl px-4 py-2 text-[14px] font-medium transition-colors ${
                on
                  ? "text-white"
                  : "text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]"
              }`}
            >
              {on ? (
                <motion.span
                  layoutId="role-pill"
                  className="absolute inset-0 -z-10 rounded-xl bg-[color:var(--interactive-primary)]"
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                />
              ) : null}
              {r.name}
            </button>
          );
        })}
      </div>

      <div className="mt-8 grid">
        {ROLES.map((r, i) => {
          const on = i === active;
          const Icon = r.icon;
          return (
            <motion.div
              key={r.key}
              aria-hidden={!on}
              initial={false}
              animate={{ opacity: on ? 1 : 0 }}
              transition={{ duration: reduced ? 0 : 0.4, ease: EASE }}
              className={`col-start-1 row-start-1 grid items-center gap-8 lg:grid-cols-[0.8fr_1.2fr] ${
                on ? "" : "pointer-events-none"
              }`}
            >
              <div>
                <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]">
                  <Icon className="h-7 w-7" weight="duotone" aria-hidden="true" />
                </span>
                <h3 className="font-display mt-5 text-[26px] font-bold text-[color:var(--text-primary)]">
                  {r.name}
                </h3>
                <p className="mt-2.5 max-w-[40ch] text-[17px] leading-[1.55] text-[color:var(--text-secondary)]">
                  {r.line}
                </p>
                <div className="mt-5 inline-flex items-center gap-2 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-page)] px-3 py-1.5 font-mono text-[12.5px] text-[color:var(--text-primary)]">
                  <span className="cw-pulse-soft h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
                  {r.view}
                </div>
              </div>
              <ProductFrame
                src={r.img}
                alt={r.alt}
                chrome={r.chrome}
                status="Vista en vivo"
                aspect="16/10"
                sizes="(min-width: 1024px) 52vw, 92vw"
                loading="lazy"
              />
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
