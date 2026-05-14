"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Buildings,
  CalendarBlank,
  ChartLineUp,
  CheckCircle,
  ClipboardText,
  Files,
  Gavel,
  Lightbulb,
  Lock,
  PaperPlaneTilt,
  Robot,
  ShieldCheck,
  Sparkle,
  Stamp,
  type Icon,
} from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { DocStateBadge } from "@/components/checkwise/doc-state-badge";
import { ContactForm } from "@/components/marketing/contact-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { readPortalSession } from "@/lib/session/portal";

interface FeatureItem {
  icon: Icon;
  title: string;
  body: string;
}

const FEATURES: FeatureItem[] = [
  {
    icon: ClipboardText,
    title: "Expediente guiado",
    body:
      "Tus proveedores ven exactamente qué subir, por qué y en qué formato. Nada de instrucciones por correo o WhatsApp.",
  },
  {
    icon: CalendarBlank,
    title: "Calendario REPSE",
    body:
      "SAT mensual, IMSS, INFONAVIT bimestral, acuses cuatrimestrales y renovaciones anuales — todo en una vista.",
  },
  {
    icon: Lightbulb,
    title: "Recordatorios automáticos",
    body:
      "Antes del vencimiento, no después. Cada proveedor recibe alertas con la acción exacta que debe ejecutar.",
  },
  {
    icon: Files,
    title: "Trazabilidad documental",
    body:
      "Cada archivo queda registrado con hash, periodo, revisor humano y resultado. Auditable de extremo a extremo.",
  },
  {
    icon: Gavel,
    title: "Revisión humana / legal",
    body:
      "El equipo de Legal Shelf valida lo crítico. CheckWise nunca firma documentos — solo guía la operación.",
  },
  {
    icon: Robot,
    title: "Validación lista para OCR/IA",
    body:
      "Prevalidación determinística hoy. Extracción estructurada con niveles de confianza en camino.",
  },
  {
    icon: ChartLineUp,
    title: "Reportes ejecutivos",
    body:
      "Cumplimiento, faltantes, riesgos y vencimientos. PDF descargable o envío directo al cliente.",
  },
  {
    icon: Buildings,
    title: "Experiencia premium para proveedores",
    body:
      "Portal claro, en español, pensado para usuarios no técnicos. Menos errores, menos roces operativos.",
  },
];

interface StepItem {
  number: number;
  title: string;
  body: string;
}

const STEPS: StepItem[] = [
  {
    number: 1,
    title: "Invita a tu proveedor o cliente",
    body: "Mandas un correo con su acceso temporal desde el panel de CheckWise.",
  },
  {
    number: 2,
    title: "Activa la cuenta",
    body:
      "El proveedor ingresa con su código, crea contraseña y completa sus datos. 2 minutos.",
  },
  {
    number: 3,
    title: "Completa el expediente inicial",
    body:
      "Una checklist guiada con documentos, formato esperado y siguientes pasos.",
  },
  {
    number: 4,
    title: "Sube tus documentos recurrentes",
    body:
      "Calendario REPSE integrado: SAT, IMSS, INFONAVIT, acuses, renovaciones.",
  },
  {
    number: 5,
    title: "Revisa estados y deadlines",
    body:
      "Semáforo de cumplimiento, acciones sugeridas y revisor humano cuando hace falta.",
  },
  {
    number: 6,
    title: "Genera reportes",
    body:
      "Mensuales, por proveedor, por riesgo. Listos para enviar al cliente.",
  },
];

export default function PublicHome() {
  const router = useRouter();
  const [hasSession, setHasSession] = useState(false);

  useEffect(() => {
    setHasSession(!!readPortalSession());
  }, []);

  // If a session already exists, send the user straight to the portal.
  // Public marketing page is for unauthenticated visitors.
  useEffect(() => {
    // CheckWise 1.6: route returning sessions through the workspace
    // confirmation step. Once confirmed it redirects onward.
    if (hasSession) router.replace("/portal/entra-a-tu-espacio");
  }, [hasSession, router]);

  return (
    <main className="min-h-[100dvh] bg-[color:var(--surface-page)]">
      <MarketingNav />
      <Hero />
      <Trust />
      <ProductPreview />
      <Features />
      <HowItWorks />
      <LegalShelfBlock />
      <RequestInformation />
      <MarketingFooter />
    </main>
  );
}

// ─── Nav ─────────────────────────────────────────────────────────

function MarketingNav() {
  return (
    <header className="sticky top-0 z-20 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3">
        <Link href="/" aria-label="CheckWise inicio">
          <BrandLogo size="md" />
        </Link>
        <nav className="hidden items-center gap-6 text-[13px] sm:flex">
          <a
            href="#producto"
            className="text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]"
          >
            Producto
          </a>
          <a
            href="#como-funciona"
            className="text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]"
          >
            Cómo funciona
          </a>
          <a
            href="#contacto"
            className="text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]"
          >
            Contacto
          </a>
        </nav>
        <div className="flex items-center gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link href="/login">Iniciar sesión</Link>
          </Button>
          <Button asChild size="sm">
            <Link href="#contacto">
              <span>Solicitar información</span>
              <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            </Link>
          </Button>
        </div>
      </div>
    </header>
  );
}

// ─── Hero ────────────────────────────────────────────────────────

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <BackgroundOrnaments />
      <div className="relative mx-auto max-w-6xl px-5 py-16 lg:py-24">
        <div className="grid items-center gap-12 lg:grid-cols-[1.1fr_1fr]">
          <div className="cw-fade-up space-y-6">
            <Badge variant="teal" className="rounded-full px-3 py-1">
              <Sparkle className="h-3 w-3" weight="fill" aria-hidden="true" />
              Plataforma de cumplimiento REPSE
            </Badge>
            <h1 className="text-[2.4rem] font-semibold leading-[1.05] tracking-tight text-[color:var(--text-primary)] sm:text-[2.9rem] lg:text-[3.2rem]">
              Cumplimiento documental REPSE
              <br />
              <span className="text-[color:var(--text-teal)]">
                guiado, trazable y accionable.
              </span>
            </h1>
            <p className="max-w-[52ch] text-[15px] leading-relaxed text-[color:var(--text-secondary)] sm:text-base">
              CheckWise ayuda a empresas y proveedores a gestionar documentos
              recurrentes, vencimientos, evidencia, estados de revisión y
              reportes ejecutivos en un solo lugar — sin spreadsheets, sin
              correos perdidos.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button asChild size="lg">
                <Link href="#contacto">
                  <span>Solicitar información</span>
                  <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg">
                <Link href="/login">
                  <Lock className="h-4 w-4" weight="bold" aria-hidden="true" />
                  <span>Iniciar sesión</span>
                </Link>
              </Button>
            </div>
            <p className="text-xs text-[color:var(--text-tertiary)]">
              CheckWise no firma documentos. La revisión humana sigue siendo
              obligatoria para el cumplimiento REPSE.
            </p>
          </div>
          <div className="cw-fade-up" style={{ animationDelay: "120ms" }}>
            <HeroPreviewCard />
          </div>
        </div>
      </div>
    </section>
  );
}

function BackgroundOrnaments() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute -top-32 left-1/4 h-[520px] w-[520px] rounded-full opacity-[0.16] blur-3xl"
        style={{
          background:
            "radial-gradient(circle, hsl(var(--brand-navy)/0.55) 0%, transparent 70%)",
        }}
      />
      <div
        className="absolute -bottom-40 -right-24 h-[560px] w-[560px] rounded-full opacity-[0.13] blur-3xl"
        style={{
          background:
            "radial-gradient(circle, hsl(var(--brand-teal)/0.6) 0%, transparent 70%)",
        }}
      />
    </div>
  );
}

function HeroPreviewCard() {
  return (
    <div className="relative rounded-2xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-lg">
      <div className="flex items-center justify-between">
        <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
          Estado actual · Mayo 2026
        </p>
        <Badge variant="warning">Atención</Badge>
      </div>
      <h3 className="mt-2 text-lg font-semibold text-[color:var(--text-primary)]">
        Distribuidora Nogal SA
      </h3>
      <p className="mt-1 text-[13px] text-[color:var(--text-secondary)]">
        Cumplimiento estable · 2 puntos por atender
      </p>
      <Progress
        value={78}
        showValue
        tone="warning"
        label="11 de 14 obligaciones al día"
        className="mt-4"
      />
      <ul className="mt-4 space-y-2 border-t border-[color:var(--border-subtle)] pt-4">
        <PreviewRow
          label="Opinión SAT · mayo"
          state="pending"
          mono="Vence 18 may"
        />
        <PreviewRow
          label="Acuse ICSOE · Q2"
          state="uploaded"
          mono="En revisión humana"
        />
        <PreviewRow label="Resumen IMSS · marzo" state="approved" mono="Aprobado" />
      </ul>
    </div>
  );
}

function PreviewRow({
  label,
  state,
  mono,
}: {
  label: string;
  state: "approved" | "uploaded" | "pending";
  mono: string;
}) {
  return (
    <li className="flex items-center justify-between gap-3">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-[color:var(--text-primary)]">
          {label}
        </p>
        <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
          {mono}
        </p>
      </div>
      <DocStateBadge state={state} withIcon />
    </li>
  );
}

// ─── Trust strip ─────────────────────────────────────────────────

function Trust() {
  const items = [
    { label: "Trazabilidad", value: "100%" },
    { label: "Estados REPSE", value: "8" },
    { label: "Validación", value: "Humana + IA" },
    { label: "Reportes", value: "PDF · ejecutivos" },
  ];
  return (
    <section className="border-y border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]">
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-3 px-5 py-5 sm:grid-cols-4">
        {items.map((item) => (
          <div key={item.label} className="flex flex-col">
            <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              {item.label}
            </p>
            <p className="text-[15px] font-semibold text-[color:var(--text-primary)]">
              {item.value}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

// ─── Product preview tiles ──────────────────────────────────────

function ProductPreview() {
  return (
    <section id="producto" className="mx-auto max-w-6xl px-5 py-16 lg:py-24">
      <header className="mb-10 max-w-3xl">
        <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-teal)]">
          Vista del producto
        </p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
          Una sola plataforma para todo el ciclo REPSE
        </h2>
        <p className="mt-3 text-[15px] leading-relaxed text-[color:var(--text-secondary)]">
          Desde la primera invitación hasta el reporte ejecutivo mensual —
          CheckWise organiza expediente inicial, calendario recurrente, revisión
          humana, validación documental y reportes en una experiencia guiada.
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-3">
        <PreviewTile
          eyebrow="Expediente inicial"
          title="Checklist guiada por documento"
          body="Cada requisito explica qué subir, por qué se pide y el siguiente paso. Sin formularios crípticos."
        >
          <div className="space-y-3">
            <MiniDoc label="Constancia REPSE" state="in_review" />
            <MiniDoc label="Acta constitutiva" state="approved" />
            <MiniDoc label="RFC del representante" state="rejected" />
          </div>
        </PreviewTile>

        <PreviewTile
          eyebrow="Calendario REPSE"
          title="12 meses, 4 instituciones, un vistazo"
          body="SAT, IMSS, INFONAVIT, STPS · mensual / bimestral / cuatrimestral / anual. Toca cualquier celda para abrir el detalle."
        >
          <div className="grid grid-cols-6 gap-1">
            {Array.from({ length: 12 }).map((_, i) => {
              const tone =
                i < 4
                  ? "bg-[color:var(--doc-approved-bg)] border-[color:var(--doc-approved-border)]"
                  : i === 4
                    ? "bg-[color:var(--surface-brand-muted)] border-[color:var(--border-focus)]/40"
                    : "bg-[color:var(--surface-sunken)] border-[color:var(--border-subtle)]";
              return (
                <div
                  key={i}
                  className={`flex h-8 items-center justify-center rounded-sm border font-mono text-[9px] uppercase ${tone}`}
                >
                  {["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"][i]}
                </div>
              );
            })}
          </div>
          <p className="mt-3 text-xs text-[color:var(--text-secondary)]">
            Mayo es tu mes en curso — 2 obligaciones por completar.
          </p>
        </PreviewTile>

        <PreviewTile
          eyebrow="Reportes ejecutivos"
          title="Más que una exportación"
          body="Cumplimiento, faltantes, riesgos y responsables — listos para enviar al cliente con un clic."
        >
          <div className="space-y-2">
            <MiniReport title="Reporte mensual · mayo 2026" badge="ready" />
            <MiniReport title="Expediente · Distribuidora Nogal" badge="ready" />
            <MiniReport title="Faltantes · 14 proveedores" badge="generating" />
          </div>
        </PreviewTile>
      </div>
    </section>
  );
}

function PreviewTile({
  eyebrow,
  title,
  body,
  children,
}: {
  eyebrow: string;
  title: string;
  body: string;
  children: React.ReactNode;
}) {
  return (
    <article className="cw-hover-lift flex flex-col gap-4 rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-sm">
      <div>
        <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-teal)]">
          {eyebrow}
        </p>
        <h3 className="mt-1 text-[15px] font-semibold text-[color:var(--text-primary)]">
          {title}
        </h3>
        <p className="mt-2 text-[13px] leading-5 text-[color:var(--text-secondary)]">
          {body}
        </p>
      </div>
      <div className="mt-auto rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-3">
        {children}
      </div>
    </article>
  );
}

function MiniDoc({
  label,
  state,
}: {
  label: string;
  state: "approved" | "in_review" | "rejected" | "pending";
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="truncate text-xs text-[color:var(--text-primary)]">{label}</span>
      <DocStateBadge state={state} withIcon={false} />
    </div>
  );
}

function MiniReport({
  title,
  badge,
}: {
  title: string;
  badge: "ready" | "generating" | "needs_review";
}) {
  const badgeMap = {
    ready: { variant: "success" as const, label: "Listo" },
    generating: { variant: "info" as const, label: "Generando…" },
    needs_review: { variant: "warning" as const, label: "Revisar" },
  };
  const cfg = badgeMap[badge];
  return (
    <div className="flex items-center justify-between gap-2 rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-2.5 py-1.5">
      <span className="truncate text-xs text-[color:var(--text-primary)]">{title}</span>
      <Badge variant={cfg.variant}>{cfg.label}</Badge>
    </div>
  );
}

// ─── Features ────────────────────────────────────────────────────

function Features() {
  return (
    <section className="border-y border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]">
      <div className="mx-auto max-w-6xl px-5 py-16 lg:py-24">
        <header className="mb-10 max-w-3xl">
          <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-teal)]">
            Por qué CheckWise
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
            Lo que nos diferencia de un simple repositorio
          </h2>
        </header>
        <ul className="cw-stagger grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map(({ icon: IconComponent, title, body }) => (
            <li
              key={title}
              className="flex flex-col gap-3 rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-4"
            >
              <span
                className="flex h-9 w-9 items-center justify-center rounded-full bg-[color:var(--surface-teal-muted)]"
                aria-hidden="true"
              >
                <IconComponent
                  className="h-5 w-5 text-[color:var(--text-teal)]"
                  weight="duotone"
                />
              </span>
              <h3 className="text-[13px] font-semibold leading-5 text-[color:var(--text-primary)]">
                {title}
              </h3>
              <p className="text-xs leading-5 text-[color:var(--text-secondary)]">
                {body}
              </p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// ─── How it works ────────────────────────────────────────────────

function HowItWorks() {
  return (
    <section id="como-funciona" className="mx-auto max-w-6xl px-5 py-16 lg:py-24">
      <header className="mb-10 max-w-3xl">
        <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-teal)]">
          Cómo funciona
        </p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
          De la invitación al reporte ejecutivo en seis pasos
        </h2>
      </header>
      <ol className="cw-stagger grid gap-4 lg:grid-cols-3">
        {STEPS.map((step) => (
          <li
            key={step.number}
            className="flex gap-4 rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] p-5 shadow-xs"
          >
            <span
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-brand)] font-mono text-sm font-semibold text-[color:var(--text-inverse)]"
              aria-hidden="true"
            >
              {step.number}
            </span>
            <div>
              <h3 className="text-[15px] font-semibold leading-5 text-[color:var(--text-primary)]">
                {step.title}
              </h3>
              <p className="mt-1 text-[13px] leading-5 text-[color:var(--text-secondary)]">
                {step.body}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

// ─── Legal Shelf block ───────────────────────────────────────────

function LegalShelfBlock() {
  return (
    <section className="bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]">
      <div className="mx-auto grid max-w-6xl gap-8 px-5 py-16 lg:grid-cols-[1.1fr_1fr] lg:items-center">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--brand-teal)]">
            Powered by Legal Shelf
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight">
            CheckWise se conecta con flujos de Legal Shelf y Sámano Abogados
          </h2>
          <p className="mt-3 max-w-prose text-[15px] leading-relaxed text-[color:var(--text-inverse)]/80">
            Cuando un documento necesita criterio legal, la revisión humana queda
            en manos del equipo de Legal Shelf. CheckWise nunca firma documentos —
            asegura que cada paso quede trazable y listo para auditoría.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Button asChild size="lg" variant="secondary">
              <Link href="#contacto">
                <PaperPlaneTilt className="h-4 w-4" weight="bold" aria-hidden="true" />
                <span>Hablar con un asesor</span>
              </Link>
            </Button>
          </div>
        </div>
        <ul className="grid gap-3 sm:grid-cols-2">
          {[
            { icon: Gavel, label: "Revisión legal humana" },
            { icon: ShieldCheck, label: "Estándar REPSE 2026" },
            { icon: Stamp, label: "Auditable extremo a extremo" },
            { icon: CheckCircle, label: "Excepciones legales registradas" },
          ].map(({ icon: IconComponent, label }) => (
            <li
              key={label}
              className="flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-3 py-3"
            >
              <IconComponent
                className="h-4 w-4 text-[color:var(--brand-teal)]"
                weight="duotone"
                aria-hidden="true"
              />
              <span className="text-[13px] font-medium">{label}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// ─── Request information ─────────────────────────────────────────

function RequestInformation() {
  return (
    <section id="contacto" className="mx-auto max-w-6xl px-5 py-16 lg:py-24">
      <div className="grid gap-12 lg:grid-cols-[1fr_1.1fr]">
        <div className="space-y-4">
          <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-teal)]">
            Solicita información
          </p>
          <h2 className="text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
            ¿Listo para ver CheckWise en acción?
          </h2>
          <p className="text-[15px] leading-relaxed text-[color:var(--text-secondary)]">
            Cuéntanos qué necesitas y te agendamos una demo personalizada.
            Solemos responder el mismo día hábil.
          </p>
          <ul className="space-y-3 pt-2">
            {[
              "Demo guiada del portal proveedor + cliente",
              "Recorrido por reportes ejecutivos",
              "Mapa de implementación para tu operación",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2 text-[13px]">
                <CheckCircle
                  className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--text-teal)]"
                  weight="fill"
                  aria-hidden="true"
                />
                <span className="text-[color:var(--text-primary)]">{item}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-md sm:p-8">
          <ContactForm />
        </div>
      </div>
    </section>
  );
}

// ─── Footer ──────────────────────────────────────────────────────

function MarketingFooter() {
  return (
    <footer className="border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-8 sm:flex-row sm:items-center sm:justify-between">
        <BrandLogo size="sm" poweredBy />
        <div className="flex flex-wrap items-center gap-4 text-xs text-[color:var(--text-tertiary)]">
          <Link href="/login" className="hover:text-[color:var(--text-primary)]">
            Iniciar sesión
          </Link>
          <a href="#contacto" className="hover:text-[color:var(--text-primary)]">
            Contacto
          </a>
          <span className="font-mono uppercase tracking-wide">v1.5 demo</span>
        </div>
      </div>
    </footer>
  );
}
