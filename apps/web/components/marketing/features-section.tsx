"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Archive,
  Buildings,
  ChartLineUp,
  ClipboardText,
  Gavel,
  Sparkle,
  type Icon,
} from "@phosphor-icons/react";

import { EASE_ENTER, Reveal } from "./motion-helpers";
import { useMotionPreference } from "./motion-preference";

type Role = {
  id: string;
  label: string;
  icon: Icon;
  headline: string;
  body: string;
  image: string;
  chrome: string;
  bullets: ReadonlyArray<string>;
  pillar: {
    label: string;
    value: string;
  };
};

const ROLES: ReadonlyArray<Role> = [
  {
    id: "provider",
    label: "Proveedor",
    icon: ClipboardText,
    headline: "Workspace propio con la próxima acción a la vista",
    body: "Cada proveedor entra a un espacio precargado con cliente, RFC y contacto. El copilot Wise responde dudas del expediente sin abrir otra pestaña.",
    image: "/marketing/product/portal-dashboard.png",
    chrome: "Portal proveedor · dashboard",
    bullets: [
      "Cumplimiento, faltantes y vencimientos en una sola vista",
      "Carga guiada con requisito, periodo e institución",
      "Wise · copilot LLM para resolver dudas del expediente",
    ],
    pillar: { label: "Surface", value: "/portal/dashboard" },
  },
  {
    id: "client",
    label: "Cliente",
    icon: Buildings,
    headline: "Portafolio en semáforo, sin pedir cortes manuales",
    body: "Operación cliente con riesgo, faltantes y proveedores listos para ser auditados. La vista cliente vive en su propio dominio, no es un subdash del admin.",
    image: "/marketing/product/client-dashboard.png",
    chrome: "Portal cliente · resumen",
    bullets: [
      "Proveedores en verde, amarillo o rojo según evidencia",
      "Faltantes obligatorios y próximas renovaciones",
      "Acceso de auditor con paquete descargable",
    ],
    pillar: { label: "Surface", value: "/client/dashboard" },
  },
  {
    id: "legalshelf",
    label: "Legal Shelf",
    icon: Gavel,
    headline: "Cola priorizada de revisión humana, no automatización ciega",
    body: "Los documentos críticos pasan por Ada Reyes y el equipo legal. Cada decisión deja firma, motivo y diff antes de aprobar o rechazar.",
    image: "/marketing/product/admin-reviewer-queue.png",
    chrome: "Bandeja Legal Shelf · documentos por revisar",
    bullets: [
      "FIFO por edad del documento, con desempate humano",
      "Estado por inconsistencia, aclaración o decisión",
      "Cada acción firma el audit log inmediatamente",
    ],
    pillar: { label: "Surface", value: "/admin/reviewer" },
  },
  {
    id: "reports",
    label: "Reportes",
    icon: ChartLineUp,
    headline: "Editor de reportes con copilot LLM y exportación nativa",
    body: "El reporte ejecutivo se redacta, regenera y exporta en el mismo canvas. Bloques editables, versiones, IA explicativa, y descarga en PDF, Excel o HTML.",
    image: "/marketing/product/admin-report-editor.png",
    chrome: "Reporte · Mi estado de cumplimiento",
    bullets: [
      "Generar · Copiloto · Refrescar datos · Vista previa",
      "Versiones con borrador, publicado y firmado",
      "Exportación PDF, Excel, HTML y vista para impresión",
    ],
    pillar: { label: "Surface", value: "/admin/reports" },
  },
  {
    id: "audit",
    label: "Auditoría",
    icon: Archive,
    headline: "Paquete listo para auditor, filtrado por periodo e institución",
    body: "Llega un inspector y CheckWise arma el ZIP exacto: documentos filtrados, índice firmado y audit log de toda la operación.",
    image: "/marketing/product/client-auditoria.png",
    chrome: "Paquete para auditoría · constructor",
    bullets: [
      "Filtros por periodo (mes, trimestre, año fiscal)",
      "Selección por institución y proveedor",
      "ÍNDICE.pdf firmado más audit log exportable",
    ],
    pillar: { label: "Surface", value: "/client/auditoria" },
  },
];

const CYCLE_MS = 5200;

/**
 * Role switcher — replaces the previous 6-card grid.
 *
 * Left rail lists the five product personas. The right side renders the
 * active role's screenshot at full width with a chromed frame, a stack
 * of inline chips for proof bullets, and a small surface identifier
 * (route + icon).
 *
 * The active role auto-cycles every CYCLE_MS, paused on hover so users
 * can read. Click or focus to override.
 */
export function FeaturesSection() {
  const { reduced: reduce } = useMotionPreference();
  const [activeId, setActiveId] = useState<string>(ROLES[0].id);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (reduce || paused) return;
    const id = window.setInterval(() => {
      setActiveId((current) => {
        const idx = ROLES.findIndex((r) => r.id === current);
        return ROLES[(idx + 1) % ROLES.length].id;
      });
    }, CYCLE_MS);
    return () => window.clearInterval(id);
  }, [reduce, paused]);

  const active = ROLES.find((r) => r.id === activeId) ?? ROLES[0];

  return (
    <section
      id="features"
      className="relative bg-[color:var(--surface-raised)]"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div className="mx-auto max-w-[1320px] px-5 py-20 lg:py-28">
        {/* Section header — small, deliberate. The product carries the page. */}
        <Reveal className="grid gap-6 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] md:items-end">
          <div>
            <p className="cw-eyebrow text-[color:var(--text-teal)]">
              El sistema, por rol
            </p>
            <h2
              className="mt-3 font-semibold tracking-[-0.022em] text-[color:var(--text-primary)] [text-wrap:balance]"
              style={{
                fontSize: "clamp(1.9rem, 3vw, 2.65rem)",
                lineHeight: 1.04,
              }}
            >
              Una superficie para cada persona, un mismo expediente debajo.
            </h2>
          </div>
          <p className="text-[14px] leading-[1.65] text-[color:var(--text-secondary)] md:text-right">
            Recorre las cinco superficies que conforman la operación REPSE
            completa de CheckWise.
          </p>
        </Reveal>

        {/* Stage — left rail + right canvas. */}
        <div className="mt-12 grid grid-cols-1 gap-10 lg:mt-16 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)] lg:gap-12 xl:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
          <RoleRail
            roles={ROLES}
            activeId={active.id}
            onSelect={setActiveId}
            paused={paused}
          />
          <RoleCanvas active={active} reduce={reduce} />
        </div>
      </div>
    </section>
  );
}

function RoleRail({
  roles,
  activeId,
  onSelect,
  paused,
}: {
  roles: ReadonlyArray<Role>;
  activeId: string;
  onSelect: (id: string) => void;
  paused: boolean;
}) {
  return (
    <div className="flex flex-col">
      <p className="cw-eyebrow">Roles del sistema</p>
      <ul className="mt-3 flex flex-col divide-y divide-[color:var(--border-subtle)] overflow-hidden rounded-[10px] border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]">
        {roles.map((role) => {
          const Icon = role.icon;
          const active = role.id === activeId;
          return (
            <li key={role.id}>
              <button
                type="button"
                aria-pressed={active}
                onClick={() => onSelect(role.id)}
                className={`group relative flex w-full items-center gap-3 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40 ${
                  active
                    ? "bg-[color:var(--surface-raised)]"
                    : "hover:bg-[color:var(--surface-raised)]/60"
                }`}
              >
                <span
                  aria-hidden="true"
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md transition-colors ${
                    active
                      ? "bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                      : "bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]"
                  }`}
                >
                  <Icon className="h-4 w-4" weight="duotone" />
                </span>
                <div className="min-w-0 flex-1">
                  <p
                    className={`text-[14.5px] font-semibold leading-tight transition-colors ${
                      active
                        ? "text-[color:var(--text-primary)]"
                        : "text-[color:var(--text-secondary)] group-hover:text-[color:var(--text-primary)]"
                    }`}
                  >
                    {role.label}
                  </p>
                  <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-tertiary)]">
                    {role.pillar.value}
                  </p>
                </div>
                {/* Right edge: active progress slice, otherwise a quiet caret. */}
                {active ? (
                  <span
                    aria-hidden="true"
                    className="ml-2 inline-flex items-center gap-1.5"
                  >
                    <span
                      className={`inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)] ${
                        paused ? "" : "cw-pulse-soft"
                      }`}
                    />
                  </span>
                ) : (
                  <span
                    aria-hidden="true"
                    className="ml-2 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-tertiary)] opacity-0 group-hover:opacity-100"
                  >
                    ↵
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>

      <p className="mt-5 font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
        {paused ? "En pausa · hover" : "Avance automático cada 5 s"}
      </p>
    </div>
  );
}

function RoleCanvas({ active, reduce }: { active: Role; reduce: boolean }) {
  return (
    <div className="relative">
      <AnimatePresence mode="wait">
        <motion.div
          key={active.id}
          initial={reduce ? false : { opacity: 0, y: 14 }}
          animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
          exit={reduce ? { opacity: 0 } : { opacity: 0, y: -8 }}
          transition={{ duration: 0.55, ease: EASE_ENTER }}
          className="flex flex-col gap-6"
        >
          {/* Headline + body — short, sharp. */}
          <div>
            <h3
              className="font-semibold tracking-[-0.018em] text-[color:var(--text-primary)] [text-wrap:balance]"
              style={{
                fontSize: "clamp(1.4rem, 2.1vw, 1.85rem)",
                lineHeight: 1.12,
              }}
            >
              {active.headline}
            </h3>
            <p className="mt-3 max-w-[58ch] text-[14.5px] leading-[1.6] text-[color:var(--text-secondary)]">
              {active.body}
            </p>
          </div>

          {/* The product canvas — single large screenshot, no decorative
              card frame around it. */}
          <div className="relative overflow-hidden rounded-[12px] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-[0_38px_90px_-44px_hsl(var(--brand-navy)/0.45),0_14px_28px_-18px_hsl(var(--brand-navy)/0.18)]">
            <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]/85 px-3 py-2">
              <span className="flex gap-1.5" aria-hidden="true">
                <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/70" />
                <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/45" />
                <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/30" />
              </span>
              <span className="ml-1 truncate font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                {active.chrome}
              </span>
              <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-teal)]">
                <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
                En vivo
              </span>
            </div>
            <div className="relative aspect-[16/9.2] w-full">
              <Image
                src={active.image}
                alt={`Captura del sistema CheckWise mostrando ${active.label.toLowerCase()}.`}
                fill
                sizes="(min-width: 1024px) 60vw, 92vw"
                className="object-cover object-top"
                priority={active.id === ROLES[0].id}
              />
            </div>
          </div>

          {/* Proof bullets as a chip strip, not as cards. */}
          <ul className="grid grid-cols-1 gap-2 md:grid-cols-3">
            {active.bullets.map((bullet, idx) => (
              <li
                key={bullet}
                className="flex items-start gap-2.5 border-t border-[color:var(--border-subtle)] pt-3"
              >
                <span
                  aria-hidden="true"
                  className="mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[color:var(--text-teal)]"
                />
                <p className="text-[13px] leading-[1.55] text-[color:var(--text-primary)]">
                  <span className="mr-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-tertiary)]">
                    {String(idx + 1).padStart(2, "0")}
                  </span>
                  {bullet}
                </p>
              </li>
            ))}
          </ul>

          {/* Bottom strip — gentle proof of what surface this is. */}
          <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 border-t border-[color:var(--border-subtle)] pt-4">
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">
              {active.pillar.label}
            </span>
            <span className="font-mono text-[11px] font-semibold tracking-[0.04em] text-[color:var(--text-primary)]">
              {active.pillar.value}
            </span>
            <span aria-hidden="true" className="text-[color:var(--border-default)]">
              ·
            </span>
            <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-teal)]">
              <Sparkle className="h-3 w-3" weight="fill" aria-hidden="true" />
              Pantalla real del sistema
            </span>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
