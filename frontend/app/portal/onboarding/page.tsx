"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
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
import { Skeleton } from "@/components/ui/skeleton";
import { completeOnboarding, getOnboarding } from "@/lib/api/portal";
import {
  adaptOnboardingToRequirements,
  countRealExpediente,
} from "@/lib/api/portal-adapters";
import { MOCK_EXPEDIENTE, type ExpedienteRequirement } from "@/lib/mock/expediente";
import { withPortalSession } from "@/lib/session/with-portal-session";
import { fetchCurrentSession } from "@/lib/session/portal";
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
  // CheckWise 1.7: real /portal/workspaces/{id}/onboarding. The
  // adapter enriches each item with UX copy (why/format/next_action)
  // that the backend doesn't yet ship — that enrichment will move
  // server-side in P1-1.
  const router = useRouter();
  const [requirements, setRequirements] = useState<ExpedienteRequirement[] | null>(
    null,
  );
  const [loadError, setLoadError] = useState(false);
  const [activating, setActivating] = useState(false);
  const [activateError, setActivateError] = useState<string | null>(null);

  /**
   * Mark the initial expediente as complete and unlock the dashboard.
   *
   * Centralised here so the page has one entry point for completion —
   * called both by the bottom "Activar dashboard" CTA and by the hero
   * button when the gate is already satisfied.
   *
   * Refreshes the in-memory portal session afterwards so
   * ``withOnboardingGate`` sees the new ``expediente_status`` and lets
   * the user into ``/portal/dashboard`` instead of bouncing them back
   * here.
   */
  async function handleActivateDashboard() {
    setActivating(true);
    setActivateError(null);
    try {
      if (session.expediente_status !== "complete") {
        await completeOnboarding(session);
        // Bust the in-memory session cache so the gate sees the new status.
        await fetchCurrentSession();
      }
      router.push("/portal/dashboard");
    } catch {
      setActivateError(
        "No pudimos activar tu dashboard. Revisa tu conexión e intenta de nuevo.",
      );
    } finally {
      setActivating(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    getOnboarding(session)
      .then((payload) => {
        if (cancelled) return;
        const adapted = adaptOnboardingToRequirements(payload);
        // Backend may legitimately return zero items during early
        // setup; the UI shouldn't render an empty gate. Fall back to
        // the mock so demos still work end-to-end.
        setRequirements(adapted.length > 0 ? adapted : MOCK_EXPEDIENTE);
      })
      .catch(() => {
        if (cancelled) return;
        setLoadError(true);
        setRequirements(MOCK_EXPEDIENTE);
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  const counts = useMemo(
    () => countRealExpediente(requirements ?? []),
    [requirements],
  );

  // Local banner decision — replaces the mock-only routing helper for
  // this page's hero. Same semantics, derived from the real counts.
  const banner: "expediente_blocked" | "provisional_access" | "none" = (() => {
    if (!requirements) return "none";
    const blocking = requirements
      .filter((r) => r.required)
      .some((r) =>
        ["empty", "pending", "rejected", "expired", "needs_review"].includes(r.state),
      );
    if (blocking) return "expediente_blocked";
    if (counts.in_review > 0) return "provisional_access";
    return "none";
  })();

  if (!requirements) {
    return (
      <>
        <ProviderContextBar session={session} />
        <main className="mx-auto max-w-6xl space-y-6 px-5 py-8">
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-48 w-full rounded-xl" />
          <Skeleton className="h-48 w-full rounded-xl" />
        </main>
      </>
    );
  }

  const needsAction = requirements.filter((r) =>
    ["pending", "empty", "rejected", "expired", "needs_review"].includes(r.state),
  );
  // Mandatory items unlock the dashboard. Optional items can be done
  // later from the dashboard's settings area. Splitting them into two
  // visually distinct sections is the difference between "10 things to
  // do" (overwhelming) and "5 to unlock + 5 you can defer" (clear).
  const needsActionMandatory = needsAction.filter((r) => r.required);
  const needsActionOptional = needsAction.filter((r) => !r.required);
  const inProgress = requirements.filter((r) =>
    ["uploaded", "in_review"].includes(r.state),
  );
  const completed = requirements.filter((r) => r.state === "approved");

  /**
   * Open the upload wizard pre-filled for a specific expediente
   * requirement. The wizard reads ?requirement=…&institution=… from
   * the URL and locks those fields so the user just picks the file
   * and hits submit. ``load_type=alta_inicial`` because every card on
   * this page belongs to the initial expediente.
   */
  function openUploadFor(req: ExpedienteRequirement) {
    const params = new URLSearchParams();
    params.set("requirement", req.name);
    if (req.requirement_code) params.set("requirement_code", req.requirement_code);
    params.set("institution", req.institution);
    params.set("load_type", "alta_inicial");
    router.push(`/portal/upload?${params.toString()}`);
  }

  return (
    <>
      <ProviderContextBar session={session} />
      <main className="mx-auto max-w-6xl space-y-8 px-5 py-8">
        {loadError && (
          <Alert variant="warning">
            <AlertTitle>Mostramos datos de respaldo</AlertTitle>
            <AlertDescription>
              No pudimos consultar tu expediente al instante. La vista usa
              datos de respaldo mientras se restablece la conexión.
            </AlertDescription>
          </Alert>
        )}
        <GateHero
          counts={counts}
          banner={banner}
          onActivate={handleActivateDashboard}
          activating={activating}
        />

        {needsActionMandatory.length > 0 && (
          <ExpedienteSection
            title="Obligatorios — desbloquean tu dashboard"
            description="Estos documentos te bloquean el dashboard. Atiéndelos primero."
            tone="attention"
            count={needsActionMandatory.length}
          >
            <div className="grid gap-4 lg:grid-cols-2">
              {needsActionMandatory.map((req) => (
                <ExpedienteCard
                  key={req.id}
                  requirement={req}
                  onAction={openUploadFor}
                />
              ))}
            </div>
          </ExpedienteSection>
        )}

        {needsActionOptional.length > 0 && (
          <ExpedienteSection
            title="Opcionales — puedes hacerlos después"
            description="No bloquean tu dashboard. Súbelos cuando aplique a tu caso."
            tone="info"
            count={needsActionOptional.length}
            collapsible
          >
            <div className="grid gap-4 lg:grid-cols-2">
              {needsActionOptional.map((req) => (
                <ExpedienteCard
                  key={req.id}
                  requirement={req}
                  onAction={openUploadFor}
                />
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
                <ExpedienteCard
                  key={req.id}
                  requirement={req}
                  onAction={openUploadFor}
                />
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
                <ExpedienteCard
                  key={req.id}
                  requirement={req}
                  onAction={openUploadFor}
                />
              ))}
            </div>
          </ExpedienteSection>
        )}

        <ActivateDashboardCard
          status={session.expediente_status}
          counts={counts}
          activating={activating}
          error={activateError}
          onActivate={handleActivateDashboard}
        />
      </main>
    </>
  );
}

// ─── Activate-dashboard CTA ─────────────────────────────────────
//
// The single entry point a provider uses to leave the expediente
// flow and unlock /portal/dashboard. Visible always on this page so
// the user is never guessing how to "finish onboarding". The button
// degrades gracefully:
//   * status === "complete"   → "Entrar al dashboard"   (skips API call)
//   * counts gate satisfied   → "Activar dashboard"     (primary CTA)
//   * neither                 → "Activar dashboard sin completar todo"
//                               with a warning explaining the trade-off
//                               (kept for the demo so the seeded user
//                               can reach the dashboard without uploads)

function ActivateDashboardCard({
  status,
  counts,
  activating,
  error,
  onActivate,
}: {
  status: PortalSession["expediente_status"];
  counts: ReturnType<typeof countRealExpediente>;
  activating: boolean;
  error: string | null;
  onActivate: () => void;
}) {
  const alreadyComplete = status === "complete";
  const gateReady = counts.is_gate_satisfied;
  const ctaLabel = alreadyComplete
    ? "Entrar al dashboard"
    : gateReady
      ? "Activar mi dashboard"
      : "Activar mi dashboard de todos modos";

  return (
    <section className="cw-fade-up rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-sm sm:p-8">
      <header className="mb-3 flex items-center gap-3">
        <span
          className="flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)]"
          aria-hidden="true"
        >
          <ShieldCheck
            className="h-5 w-5 text-[color:var(--text-brand)]"
            weight="duotone"
          />
        </span>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-teal)]">
            Activación de dashboard
          </p>
          <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
            {alreadyComplete
              ? "Tu expediente inicial está completo"
              : "Cuando tu expediente esté listo, activa tu dashboard"}
          </h2>
        </div>
      </header>

      <p className="mb-4 max-w-prose text-[13px] leading-5 text-[color:var(--text-secondary)]">
        {alreadyComplete
          ? "Puedes entrar a tu dashboard cuando quieras. Si necesitas actualizar un documento, vuelve aquí desde la sección de configuración."
          : gateReady
            ? "Cumpliste lo necesario para arrancar. Activa tu dashboard para comenzar a darle seguimiento a tus obligaciones recurrentes."
            : "Si quieres revisar tu dashboard antes de terminar de subir documentos, puedes activarlo ahora — los documentos que falten quedarán visibles en tu expediente."}
      </p>

      {error && (
        <Alert variant="warning" className="mb-4">
          <AlertTitle>No se pudo activar</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={onActivate} loading={activating} size="lg">
          <span>{ctaLabel}</span>
          {!activating && (
            <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
          )}
        </Button>
        <p className="text-xs text-[color:var(--text-tertiary)]">
          {alreadyComplete
            ? "El dashboard reemplaza este expediente como tu vista principal."
            : "Una vez activado, podrás regresar aquí cuando necesites actualizar documentos."}
        </p>
      </div>
    </section>
  );
}

export default withPortalSession(OnboardingInner);

// ─── Hero ────────────────────────────────────────────────────────

function GateHero({
  counts,
  banner,
  onActivate,
  activating,
}: {
  counts: ReturnType<typeof countRealExpediente>;
  banner:
    | "none"
    | "provisional_access"
    | "expediente_blocked"
    | "needs_workspace_confirmation";
  onActivate: () => void;
  activating: boolean;
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
              <Button onClick={onActivate} loading={activating} size="lg">
                <span>Entrar al dashboard</span>
                {!activating && (
                  <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
                )}
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
            Solo los <strong>{counts.total_required} documentos obligatorios</strong>{" "}
            desbloquean tu dashboard. Los opcionales puedes subirlos cuando
            apliquen a tu caso. Una vez que envíes los obligatorios, tu cliente
            puede contratar tus servicios especializados y empezamos a darle
            seguimiento mensual a tus obligaciones REPSE.
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
  counts: ReturnType<typeof countRealExpediente>;
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
