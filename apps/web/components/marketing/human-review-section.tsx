"use client";

import Link from "next/link";
import {
  BellRinging,
  ChartLineUp,
  Gavel,
  PaperPlaneTilt,
  ShieldCheck,
  Sparkle,
  Stamp,
  type Icon,
} from "@phosphor-icons/react";
import { motion } from "motion/react";

import { Button } from "@/components/ui/button";

import { EASE_ENTER, Reveal } from "./motion-helpers";
import { useMotionPreference } from "./motion-preference";
import { ProductShot, type ProductShotFocus } from "./product-shot";

const AI_DOES = [
  "Planear el reporte con datos del expediente",
  "Redactar bloques editables para dirección",
  "Asistir al usuario Wise dentro del portal",
] as const;

const AI_DOES_NOT = [
  "Aprobar documentos legales",
  "Sustituir la revisión del equipo CheckWise",
  "Cambiar estados sin registro de auditoría",
] as const;

export function HumanReviewSection() {
  const { reduced: reduce } = useMotionPreference();

  return (
    <section
      id="ai-revision"
      className="relative isolate overflow-hidden bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
    >
      <div
        aria-hidden="true"
        className="cw-band-drift pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, rgba(255,255,255,0.6) 0 1px, transparent 1px 64px)",
        }}
      />

      <div className="relative mx-auto grid max-w-[1320px] grid-cols-1 gap-12 px-5 py-24 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] lg:gap-16 lg:py-28">
        <Reveal className="flex min-w-0 flex-col">
          <p className="cw-eyebrow text-[hsl(var(--brand-teal))]">
            AI + revisión humana
          </p>
          <h2
            className="mt-3 font-semibold tracking-[-0.022em] [text-wrap:balance]"
            style={{
              fontSize: "clamp(1.9rem, 2.9vw, 2.55rem)",
              lineHeight: 1.06,
            }}
          >
            CheckWise acelera el criterio.{" "}
            <span className="text-[hsl(var(--brand-teal))]">
              No lo reemplaza.
            </span>
          </h2>
          <p className="mt-4 max-w-[48ch] text-[15px] leading-[1.6] text-[color:var(--text-inverse-secondary)]">
            La IA ayuda a explicar, redactar y convertir estados en reportes.
            Las decisiones críticas siguen en manos del equipo CheckWise, con actor,
            acción y cambio firmado.
          </p>

          <div className="mt-9 grid grid-cols-1 gap-6 sm:grid-cols-2">
            <TruthList
              label="La IA hace"
              icon={Sparkle}
              items={AI_DOES}
              tone="ai"
            />
            <TruthList
              label="La IA no hace"
              icon={ShieldCheck}
              items={AI_DOES_NOT}
              tone="guardrail"
            />
          </div>

          <ol className="mt-9 space-y-5 border-l border-white/15 pl-5">
            <Statement
              n="01"
              kicker="Revisión"
              body="La cola prioriza documentos; el equipo CheckWise decide aprobar, rechazar, aclarar o exceptuar."
            />
            <Statement
              n="02"
              kicker="Reporte"
              body="El editor compone bloques, versiones y exportaciones con datos del mismo expediente."
            />
            <Statement
              n="03"
              kicker="Notificación"
              body="Los eventos y recordatorios mantienen a proveedor y cliente sincronizados sin perseguir archivos."
            />
          </ol>

          <div className="mt-9 flex flex-wrap gap-3">
            <Button asChild size="lg" variant="secondary" className="rounded-full">
              <Link href="#contacto">
                <PaperPlaneTilt className="h-4 w-4" weight="bold" aria-hidden="true" />
                <span>Contactar a CheckWise</span>
              </Link>
            </Button>
          </div>
        </Reveal>

        <motion.div
          className="min-w-0 self-start"
          initial={reduce ? false : { opacity: 0, y: 22 }}
          whileInView={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.2 }}
          transition={{ duration: 0.75, ease: EASE_ENTER, delay: 0.05 }}
        >
          <div className="grid grid-cols-1 gap-5">
            <ProductProof
              label="Bandeja CheckWise"
              status="Decisión firmada"
              image="/marketing/product/admin-reviewer-queue.png"
              alt="Bandeja de revisión CheckWise con documentos pendientes y estados de revisión."
              icon={Gavel}
              focus={{ position: "top center" }}
            />
            <div className="grid grid-cols-1 gap-5 md:grid-cols-[minmax(0,1fr)_260px]">
              <ProductProof
                compact
                label="Reportes AI"
                status="Bloques editables"
                image="/marketing/product/admin-report-editor.png"
                alt="Editor de reportes CheckWise con asistente AI y bloques editables."
                icon={ChartLineUp}
                focus={{ position: "top center" }}
              />
              <div className="rounded-[12px] border border-white/12 bg-white/[0.04] p-4">
                <p className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-inverse-muted)]">
                  <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[hsl(var(--brand-teal))]" />
                  Auditoría viva
                </p>
                <div className="mt-4 space-y-4">
                  <Signal
                    icon={Stamp}
                    label="Evento"
                    value="Documento aprobado"
                  />
                  <Signal
                    icon={BellRinging}
                    label="Recordatorio"
                    value="Faltante próximo a vencer"
                  />
                  <Signal
                    icon={ShieldCheck}
                    label="Control"
                    value="Cambio registrado"
                  />
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function ProductProof({
  label,
  status,
  image,
  alt,
  icon: Icon,
  focus,
  compact = false,
}: {
  label: string;
  status: string;
  image: string;
  alt: string;
  icon: Icon;
  focus: ProductShotFocus;
  compact?: boolean;
}) {
  return (
    <div className="relative overflow-hidden rounded-[14px] border border-white/12 bg-[color:var(--surface-raised)] shadow-[0_44px_120px_-44px_rgba(0,0,0,0.65),0_18px_36px_-22px_rgba(0,0,0,0.4)]">
      <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]/88 px-3 py-2">
        <span className="flex gap-1.5" aria-hidden="true">
          <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/70" />
          <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/45" />
          <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/30" />
        </span>
        <span className="ml-1 truncate font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
          {label}
        </span>
        <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-teal)]">
          <Icon className="h-3 w-3" weight="fill" aria-hidden="true" />
          {status}
        </span>
      </div>
      <div
        className={`relative bg-[color:var(--surface-page)] ${
          compact ? "aspect-[16/10]" : "aspect-[16/9.8]"
        }`}
      >
        <ProductShot
          src={image}
          alt={alt}
          sizes={compact ? "(min-width: 1024px) 48vw, 150vw" : "(min-width: 1024px) 72vw, 160vw"}
          loading="lazy"
          focus={focus}
        />
      </div>
    </div>
  );
}

function TruthList({
  label,
  icon: Icon,
  items,
  tone,
}: {
  label: string;
  icon: Icon;
  items: ReadonlyArray<string>;
  tone: "ai" | "guardrail";
}) {
  return (
    <div className="border-t border-white/15 pt-4">
      <p className="inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-inverse-muted)]">
        <Icon
          className={`h-3.5 w-3.5 ${
            tone === "ai" ? "text-[hsl(var(--brand-teal))]" : "text-[color:var(--text-inverse-secondary)]"
          }`}
          weight="fill"
          aria-hidden="true"
        />
        {label}
      </p>
      <ul className="mt-4 space-y-2.5">
        {items.map((item) => (
          <li
            key={item}
            className="flex items-start gap-2 text-[13.5px] leading-[1.5] text-[color:var(--text-inverse-secondary)]"
          >
            <span
              aria-hidden="true"
              className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[hsl(var(--brand-teal))]"
            />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Signal({
  icon: Icon,
  label,
  value,
}: {
  icon: Icon;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-white/[0.10] text-[hsl(var(--brand-teal))]">
        <Icon className="h-3.5 w-3.5" weight="fill" aria-hidden="true" />
      </span>
      <div>
        <p className="font-mono text-[9px] uppercase tracking-[0.18em] text-[color:var(--text-inverse-muted)]">
          {label}
        </p>
        <p className="mt-1 text-[13px] font-medium leading-tight text-[color:var(--text-inverse-secondary)]">
          {value}
        </p>
      </div>
    </div>
  );
}

function Statement({
  n,
  kicker,
  body,
}: {
  n: string;
  kicker: string;
  body: string;
}) {
  return (
    <li className="relative">
      <span
        aria-hidden="true"
        className="absolute -left-[1.65rem] top-1 font-mono text-[10px] uppercase tracking-[0.18em] text-[hsl(var(--brand-teal))]"
      >
        {n}
      </span>
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-inverse-muted)]">
        {kicker}
      </p>
      <p className="mt-1.5 max-w-[44ch] text-[14.5px] leading-[1.55] text-[color:var(--text-inverse-secondary)]">
        {body}
      </p>
    </li>
  );
}
