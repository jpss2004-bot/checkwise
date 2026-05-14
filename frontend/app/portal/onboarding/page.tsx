"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle,
  Files,
  Lightbulb,
  LockKey,
  ShieldCheck,
} from "@phosphor-icons/react";

import { ExpedienteCard } from "@/components/checkwise/portal/expediente-card";
import { ProviderContextBar } from "@/components/checkwise/portal/provider-context-bar";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  MOCK_EXPEDIENTE,
  countExpediente,
  type ExpedienteRequirement,
} from "@/lib/mock/expediente";
import { decidePostLoginRoute } from "@/lib/routing/post-login";
import { withPortalSession } from "@/lib/session/with-portal-session";
import type { PortalSession } from "@/lib/session/portal";

/**
 * Initial expediente gate.
 *
 * Mock data lives in lib/mock/expediente.ts. Once the backend grows
 * a richer onboarding contract (per-requirement why/format/next_action)
 * we can drop the mock and consume the real API.
 *
 * TODO[backend-integration]: Replace MOCK_EXPEDIENTE with a fetch
 * from /api/v1/portal/onboarding once the API returns the enriched
 * shape (currently it only returns the bare requirement names).
 */
function OnboardingInner({ session }: { session: PortalSession }) {
  const [requirements] = useState<ExpedienteRequirement[]>(MOCK_EXPEDIENTE);
  const counts = useMemo(() => countExpediente(requirements), [requirements]);
  const decision = useMemo(() => decidePostLoginRoute(requirements), [requirements]);

  const needsAction = requirements.filter((r) =>
    ["pending", "empty", "rejected", "expired", "needs_review"].includes(r.state),
  );
  const inProgress = requirements.filter((r) =>
    ["uploaded", "in_review"].includes(r.state),
  );
  const completed = requirements.filter((r) => r.state === "approved");

  return (
    <>
      <ProviderContextBar session={session} />
      <main className="mx-auto max-w-6xl space-y-8 px-5 py-8">
        <GateHero counts={counts} banner={decision.banner} />

        {needsAction.length > 0 && (
          <ExpedienteSection
            title="Necesitan tu atención"
            description="Estos documentos te están bloqueando. Atiéndelos primero."
            tone="attention"
            count={needsAction.length}
          >
            <div className="grid gap-4 lg:grid-cols-2">
              {needsAction.map((req) => (
                <ExpedienteCard key={req.id} requirement={req} />
              ))}
            </div>
          </ExpedienteSection>
        )}

        {inProgress.length > 0 && (
          <ExpedienteSection
            title="En revisión humana"
            description="Recibimos tu carga. No necesitas hacer nada — te avisamos por correo."
            tone="info"
            count={inProgress.length}
          >
            <div className="grid gap-4 lg:grid-cols-2">
              {inProgress.map((req) => (
                <ExpedienteCard key={req.id} requirement={req} />
              ))}
            </div>
          </ExpedienteSection>
        )}

        {completed.length > 0 && (
          <ExpedienteSection
            title="Aprobados"
            description="Estos documentos ya quedaron en regla. Los revisaremos por vigencia."
            tone="success"
            count={completed.length}
            collapsible
          >
            <div className="grid gap-4 lg:grid-cols-2">
              {completed.map((req) => (
                <ExpedienteCard key={req.id} requirement={req} />
              ))}
            </div>
          </ExpedienteSection>
        )}
      </main>
    </>
  );
}

export default withPortalSession(OnboardingInner);

// ─── Hero ────────────────────────────────────────────────────────

function GateHero({
  counts,
  banner,
}: {
  counts: ReturnType<typeof countExpediente>;
  banner: "none" | "provisional_access" | "expediente_blocked";
}) {
  if (counts.is_gate_satisfied) {
    const isProvisional = banner === "provisional_access";
    return (
      <section
        className={`cw-fade-up rounded-xl border p-6 shadow-sm sm:p-8 ${
          isProvisional
            ? "border-[color:var(--status-info-border)] bg-[color:var(--status-info-bg)]"
            : "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)]"
        }`}
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:gap-6">
          <span
            className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-white ${
              isProvisional
                ? "bg-[color:var(--status-info-text)]"
                : "bg-[color:var(--status-success-text)]"
            }`}
            aria-hidden="true"
          >
            <CheckCircle className="h-7 w-7" weight="fill" />
          </span>
          <div className="flex-1">
            <p
              className={`font-mono text-[11px] uppercase tracking-wide ${
                isProvisional
                  ? "text-[color:var(--status-info-text)]"
                  : "text-[color:var(--status-success-text)]"
              }`}
            >
              {isProvisional ? "Acceso provisional habilitado" : "Expediente inicial listo"}
            </p>
            <h1 className="mt-1 text-xl font-semibold text-[color:var(--text-primary)]">
              {isProvisional
                ? "Puedes entrar al dashboard mientras revisamos tus documentos"
                : "Ya puedes entrar al dashboard"}
            </h1>
            <p className="mt-2 text-[13px] leading-5 text-[color:var(--text-secondary)]">
              {isProvisional ? (
                <>
                  Tus documentos obligatorios están en revisión humana. Mientras
                  tanto tienes acceso provisional al dashboard — te avisaremos
                  por correo cuando todo quede aprobado.
                </>
              ) : (
                <>
                  Cumpliste todos los documentos requeridos para tu alta. A
                  partir de aquí, sigue tu calendario REPSE recurrente.
                </>
              )}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button asChild size="lg">
                <Link href="/portal/dashboard">
                  <span>Entrar al dashboard</span>
                  <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
                </Link>
              </Button>
            </div>
          </div>
          <CountsSummary counts={counts} stacked />
        </div>
      </section>
    );
  }

  return (
    <section className="cw-fade-up rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-sm sm:p-8">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
        <div className="flex-1 space-y-4">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)]">
              <ShieldCheck
                className="h-5 w-5 text-[color:var(--text-brand)]"
                weight="duotone"
                aria-hidden="true"
              />
            </span>
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-teal)]">
                Tu expediente inicial
              </p>
              <h1 className="text-xl font-semibold text-[color:var(--text-primary)]">
                Completa tu alta REPSE para activar tu dashboard
              </h1>
            </div>
          </div>
          <p className="max-w-prose text-[13px] leading-5 text-[color:var(--text-secondary)]">
            Te pedimos {counts.total_required} documentos obligatorios. Una vez
            que los hayas enviado, tu cliente puede contratar tus servicios
            especializados y empezamos a darle seguimiento mensual a tus
            obligaciones REPSE.
          </p>

          <Progress
            value={counts.completion_pct}
            label={`${counts.completed + counts.in_review} de ${counts.total_required} documentos avanzados`}
            showValue
            tone="brand"
            className="max-w-xl"
          />

          {counts.needs_action > 0 && (
            <Alert variant="warning">
              <AlertTitle>
                {counts.needs_action === 1
                  ? "Tienes 1 documento por atender"
                  : `Tienes ${counts.needs_action} documentos por atender`}
              </AlertTitle>
              <AlertDescription>
                Mientras estos documentos no estén en revisión o aprobados, el
                dashboard se queda bloqueado.{" "}
                <span className="inline-flex items-center gap-1 font-medium">
                  <LockKey className="h-3 w-3" weight="bold" aria-hidden="true" />
                  Gate activo
                </span>
              </AlertDescription>
            </Alert>
          )}
        </div>

        <CountsSummary counts={counts} />
      </div>
    </section>
  );
}

function CountsSummary({
  counts,
  stacked = false,
}: {
  counts: ReturnType<typeof countExpediente>;
  stacked?: boolean;
}) {
  return (
    <dl
      className={
        stacked
          ? "grid grid-cols-3 gap-3 text-center sm:grid-cols-3"
          : "grid w-full grid-cols-3 gap-3 text-center lg:w-auto lg:min-w-[260px] lg:grid-cols-1 lg:text-left"
      }
    >
      <Stat label="Aprobados" value={counts.completed} tone="success" />
      <Stat label="En revisión" value={counts.in_review} tone="info" />
      <Stat label="Por atender" value={counts.needs_action} tone="warning" />
    </dl>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "success" | "info" | "warning";
}) {
  const accent =
    tone === "success"
      ? "text-[color:var(--status-success-text)]"
      : tone === "info"
        ? "text-[color:var(--status-info-text)]"
        : "text-[color:var(--status-warning-text)]";
  return (
    <div className="rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-3 py-3">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {label}
      </dt>
      <dd className={`font-mono text-2xl font-semibold tabular-nums ${accent}`}>
        {value}
      </dd>
    </div>
  );
}

// ─── Section ─────────────────────────────────────────────────────

interface SectionProps {
  title: string;
  description: string;
  tone: "attention" | "info" | "success";
  count: number;
  children: React.ReactNode;
  collapsible?: boolean;
}

function ExpedienteSection({
  title,
  description,
  tone,
  count,
  children,
  collapsible = false,
}: SectionProps) {
  const [open, setOpen] = useState(!collapsible);
  const IconComponent =
    tone === "success" ? CheckCircle : tone === "attention" ? Lightbulb : Files;
  const iconClass =
    tone === "success"
      ? "text-[color:var(--status-success-text)]"
      : tone === "attention"
        ? "text-[color:var(--status-warning-text)]"
        : "text-[color:var(--status-info-text)]";
  const badgeVariant =
    tone === "success" ? "success" : tone === "attention" ? "warning" : "info";

  return (
    <section aria-labelledby={`section-${title}`} className="cw-fade-up">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <IconComponent
            className={`h-5 w-5 ${iconClass}`}
            weight="duotone"
            aria-hidden="true"
          />
          <h2
            id={`section-${title}`}
            className="text-[15px] font-semibold text-[color:var(--text-primary)]"
          >
            {title}
          </h2>
          <Badge variant={badgeVariant}>{count}</Badge>
        </div>
        <div className="flex items-center gap-3">
          <p className="hidden text-xs text-[color:var(--text-secondary)] sm:block">
            {description}
          </p>
          {collapsible && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setOpen((v) => !v)}
              aria-expanded={open}
            >
              {open ? "Ocultar" : "Ver"}
            </Button>
          )}
        </div>
      </header>
      {open && children}
    </section>
  );
}
