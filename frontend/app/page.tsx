"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ClockCounterClockwise,
  Files,
  Scales,
  ShieldCheck,
  type Icon,
} from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { ProviderAccessForm } from "@/components/checkwise/portal/provider-access-form";
import { Skeleton } from "@/components/ui/skeleton";
import { readPortalSession } from "@/lib/session/portal";

interface ReassuranceItem {
  icon: Icon;
  title: string;
  body: string;
}

const REASSURANCE: ReassuranceItem[] = [
  {
    icon: ShieldCheck,
    title: "Acceso seguro",
    body: "Tu sesión vive en este dispositivo y se cierra cuando termines.",
  },
  {
    icon: Files,
    title: "Proceso guiado",
    body: "Te decimos qué falta y por qué, paso a paso. Sin formularios crípticos.",
  },
  {
    icon: Scales,
    title: "Cumplimiento REPSE",
    body: "Calendario completo: SAT, IMSS, INFONAVIT, acuses y renovaciones.",
  },
  {
    icon: ClockCounterClockwise,
    title: "Trazabilidad",
    body: "Cada documento queda registrado con hash, periodo, revisor y resultado.",
  },
];

export default function HomePage() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const existing = readPortalSession();
    if (existing) {
      router.replace("/portal/onboarding");
      return;
    }
    setChecked(true);
  }, [router]);

  if (!checked) {
    return <LandingSkeleton />;
  }

  return (
    <main className="relative min-h-[100dvh] overflow-hidden">
      <BackgroundOrnaments />

      <div className="relative mx-auto flex min-h-[100dvh] max-w-6xl flex-col gap-12 px-5 py-10 lg:py-16">
        <header className="flex items-center justify-between cw-fade-up">
          <BrandLogo size="md" poweredBy />
          <p className="hidden text-xs font-mono uppercase tracking-wide text-[color:var(--text-tertiary)] sm:block">
            Acceso de proveedor · Demo
          </p>
        </header>

        <section className="grid flex-1 items-start gap-10 lg:grid-cols-[1.05fr_minmax(0,440px)] lg:gap-16">
          {/* Left — invitation copy + reassurance */}
          <div className="cw-fade-up space-y-8" style={{ animationDelay: "60ms" }}>
            <div className="space-y-3">
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-teal)]">
                Bienvenido a CheckWise
              </p>
              <h1 className="text-[2rem] font-semibold leading-[1.1] tracking-tight text-[color:var(--text-primary)] sm:text-[2.4rem]">
                Tu espacio para mantener
                <br />
                tu expediente REPSE en regla.
              </h1>
              <p className="max-w-[44ch] text-[15px] leading-relaxed text-[color:var(--text-secondary)]">
                Fuiste invitado a completar tu cumplimiento documental con un
                cliente. Aquí te guiamos paso a paso, desde tu expediente
                inicial hasta el calendario recurrente, sin sorpresas.
              </p>
            </div>

            <ul className="cw-stagger grid gap-4 sm:grid-cols-2" aria-label="Beneficios">
              {REASSURANCE.map(({ icon: IconComponent, title, body }) => (
                <li
                  key={title}
                  className="flex gap-3 rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] p-4 shadow-xs"
                >
                  <span
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-teal-muted)]"
                    aria-hidden="true"
                  >
                    <IconComponent
                      className="h-5 w-5 text-[color:var(--text-teal)]"
                      weight="duotone"
                    />
                  </span>
                  <div className="min-w-0">
                    <p className="text-[13px] font-semibold leading-5 text-[color:var(--text-primary)]">
                      {title}
                    </p>
                    <p className="mt-0.5 text-xs leading-5 text-[color:var(--text-secondary)]">
                      {body}
                    </p>
                  </div>
                </li>
              ))}
            </ul>

            <p className="text-xs text-[color:var(--text-tertiary)]">
              Si recibiste credenciales temporales por correo, úsalas en el
              formulario.{" "}
              <a
                className="text-[color:var(--text-link)] underline-offset-4 hover:underline"
                href="mailto:soporte@legalshelf.mx"
              >
                ¿Aún no las recibes? Escríbenos.
              </a>
            </p>
          </div>

          {/* Right — access form card */}
          <div
            className="cw-fade-up rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-md sm:p-8"
            style={{ animationDelay: "120ms" }}
          >
            <ProviderAccessForm />
          </div>
        </section>

        <footer className="cw-fade-in flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--border-subtle)] pt-6 text-xs text-[color:var(--text-tertiary)]">
          <p>
            CheckWise no firma legalmente documentos. La revisión humana es
            obligatoria para el cumplimiento REPSE.
          </p>
          <p className="font-mono uppercase tracking-wide">v1.4 · Powered by Legal Shelf</p>
        </footer>
      </div>
    </main>
  );
}

/**
 * Decorative background — soft navy + teal radial blooms.
 * Pure CSS, no motion, no images, no layout shift.
 */
function BackgroundOrnaments() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute -top-32 -left-24 h-[480px] w-[480px] rounded-full opacity-[0.18] blur-3xl"
        style={{ background: "radial-gradient(circle, hsl(var(--brand-navy)/0.55) 0%, transparent 70%)" }}
      />
      <div
        className="absolute -bottom-40 -right-24 h-[520px] w-[520px] rounded-full opacity-[0.14] blur-3xl"
        style={{ background: "radial-gradient(circle, hsl(var(--brand-teal)/0.6) 0%, transparent 70%)" }}
      />
    </div>
  );
}

function LandingSkeleton() {
  return (
    <main className="mx-auto max-w-6xl px-5 py-16">
      <Skeleton className="h-8 w-32" />
      <div className="mt-12 grid gap-10 lg:grid-cols-[1.05fr_minmax(0,440px)]">
        <div className="space-y-4">
          <Skeleton className="h-4 w-44" />
          <Skeleton className="h-10 w-3/4" />
          <Skeleton className="h-10 w-2/3" />
          <Skeleton className="h-20 w-full" />
        </div>
        <Skeleton className="h-[420px] w-full rounded-xl" />
      </div>
    </main>
  );
}
