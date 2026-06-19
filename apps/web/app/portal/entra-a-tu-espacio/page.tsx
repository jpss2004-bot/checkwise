"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CalendarBlank,
  CheckCircle,
  ClipboardText,
  IdentificationCard,
  ShieldCheck,
  Sparkle,
  UserCircle,
  type Icon,
} from "@phosphor-icons/react";

import { CorrectionRequestForm } from "@/components/checkwise/workspace/correction-request-form";
import { WorkspaceIdentityCard } from "@/components/checkwise/workspace/workspace-identity-card";
import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { acceptLegalConsent } from "@/lib/api/portal-session";
import { buildWorkspaceContext } from "@/lib/workspace/resolver";
import type { WorkspaceContext } from "@/lib/workspace/types";
import {
  legalConsentRequired,
  withPortalSession,
} from "@/lib/session/with-portal-session";
import {
  setCachedPortalSession,
  type ExpedienteStatus,
  type PortalSession,
} from "@/lib/session/portal";

/**
 * /portal/entra-a-tu-espacio
 *
 * Workspace entry / preview surface. Shows tenant identity, the
 * locked RFC + razón social, the expediente status, and a primary
 * "Entrar a mi espacio" CTA plus a secondary "Mi perfil" CTA.
 *
 * The editable profile form lives on ``/portal/perfil`` after the
 * 2026-05-25 UX pass — splitting the two intents avoids the
 * mixed-purpose page the brief flagged. Legal-consent acceptance
 * remains inline here on first visit (it's a tenant-identity decision,
 * not a profile-edit one). Correction requests still live in the
 * dialog below.
 */
function EntraATuEspacioInner({ session }: { session: PortalSession }) {
  const router = useRouter();

  const [liveSession, setLiveSession] = useState<PortalSession>(session);
  const isFirstVisit = liveSession.profile_confirmed_at === null;
  // Single source of truth for the consent gate — shared with the
  // session HOC so the page and the guard can never drift apart.
  const needsLegalConsent = legalConsentRequired(liveSession);

  const workspace = useMemo<WorkspaceContext>(
    () => buildWorkspaceContext(liveSession),
    [liveSession],
  );

  const [legalConsentAccepted, setLegalConsentAccepted] = useState(false);
  const [acceptingConsent, setAcceptingConsent] = useState(false);
  const [consentError, setConsentError] = useState<string | null>(null);
  const consentCheckboxRef = useRef<HTMLButtonElement>(null);

  const [correctionOpen, setCorrectionOpen] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.location.hash === "#correccion") {
      setCorrectionOpen(true);
      window.history.replaceState(
        null,
        "",
        window.location.pathname + window.location.search,
      );
    }
  }, []);

  // Route per the existing first-visit logic: providers mid-onboarding
  // land on /onboarding so they pick up where they left off; completed
  // expedientes open their working surface — the compliance calendar —
  // rather than the dashboard, so "Entrar a mi espacio" lands the provider
  // where they actually act, instead of an overview screen that read as a
  // name/action mismatch (Portal Proveedor, 2ª revisión, Mi Espacio #15).
  const nextRouteAfterEntry =
    liveSession.expediente_status === "complete"
      ? "/portal/calendar"
      : "/portal/onboarding";

  // §4.7 — when the provider arrives here straight from login
  // (``?continue=1``) and legal consent is already accepted, skip this
  // gate entirely and forward to their real landing surface — no extra
  // "Entrar a mi espacio" click. Navigating here intentionally via the
  // "Mi espacio" nav (no param) keeps the identity view, and a pending
  // consent still renders the form below (the gate has a job to do).
  //
  // Resolve the intent synchronously in the useState initializer
  // (SSR-guarded) so autoForwarding is already true on the first render
  // — that keeps the gate content from painting then vanishing while the
  // replace navigation lands. The actual router.replace stays in the
  // effect below (navigation is a side effect, never run during render).
  const [autoForwarding, setAutoForwarding] = useState(() => {
    if (typeof window === "undefined") return false;
    const params = new URLSearchParams(window.location.search);
    return params.get("continue") === "1" && !needsLegalConsent;
  });
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("continue") === "1" && !needsLegalConsent) {
      setAutoForwarding(true);
      router.replace(nextRouteAfterEntry);
    }
  }, [router, needsLegalConsent, nextRouteAfterEntry]);

  async function handleEnter() {
    if (needsLegalConsent) {
      if (!legalConsentAccepted) {
        setConsentError(
          "Marca la casilla para confirmar que aceptas los avisos legales.",
        );
        consentCheckboxRef.current?.focus();
        return;
      }
      setAcceptingConsent(true);
      setConsentError(null);
      const consent = await acceptLegalConsent(
        workspace.protected.workspace_id,
      );
      setAcceptingConsent(false);
      if (!consent) {
        setConsentError(
          "No pudimos registrar tu aceptación. Intenta de nuevo en unos segundos.",
        );
        return;
      }
      // Merge the consent timestamp + version into the cached session
      // so the gate flips off without a full /me round-trip. The
      // backend's LegalConsentResponse is intentionally narrow (just
      // the consent fields); everything else on the session stays as
      // it was when this page loaded.
      const refreshed: PortalSession = {
        ...liveSession,
        legal_consent_accepted_at: consent.legal_consent_accepted_at,
        legal_consent_version: consent.legal_consent_version,
      };
      setLiveSession(refreshed);
      setCachedPortalSession(refreshed);
    }
    router.push(nextRouteAfterEntry);
  }

  // Forwarding straight through to the dashboard/onboarding (§4.7) —
  // render nothing while the replace navigation lands.
  if (autoForwarding) return null;

  return (
    <PortalAppShell session={liveSession}>
      <main className="relative min-h-[calc(100dvh-3.5rem)] bg-[color:var(--surface-page)]">
        <div className="mx-auto flex max-w-4xl flex-col gap-6 px-5 py-10 lg:py-14">
          <header className="cw-fade-up flex flex-col gap-2">
            <Badge variant="teal" className="self-start rounded-full px-3 py-1">
              <Sparkle className="h-3 w-3" weight="fill" aria-hidden="true" />
              {isFirstVisit ? "Bienvenida a tu espacio" : "Mi espacio"}
            </Badge>
            <h1 className="text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
              {isFirstVisit ? "Entra a tu espacio" : "Tu espacio en CheckWise"}
            </h1>
            <p className="max-w-prose text-[15px] text-[color:var(--text-secondary)]">
              Esta es la entrada a tu workspace en CheckWise. Revisa tu
              identidad de proveedor y entra a tu expediente. Si necesitas
              corregir datos de contacto, abre &quot;Mi perfil&quot;.
            </p>
          </header>

          <WorkspaceIdentityCard
            workspace={workspace}
            showCorrectionLink={false}
            hideExpedienteLink
          />

          <section
            aria-labelledby="entry-status-heading"
            className="cw-fade-up rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-sm sm:p-8"
          >
            <header className="mb-4 flex items-center gap-3">
              <span
                className="flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)]"
                aria-hidden="true"
              >
                <ClipboardText
                  className="h-5 w-5 text-[color:var(--text-brand)]"
                  weight="duotone"
                />
              </span>
              <div className="min-w-0">
                <h2
                  id="entry-status-heading"
                  className="text-base font-semibold text-[color:var(--text-primary)]"
                >
                  Estado de tu expediente
                </h2>
                <p className="text-xs text-[color:var(--text-secondary)]">
                  Lo que verás cuando entres a tu workspace.
                </p>
              </div>
            </header>
            <ExpedienteStatusSummary
              status={liveSession.expediente_status}
              workspace={workspace}
            />
          </section>

          {needsLegalConsent ? (
            <section
              aria-labelledby="legal-consent-title"
              className="cw-fade-up rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-sunken)] p-5"
            >
              <h2
                id="legal-consent-title"
                className="text-sm font-semibold text-[color:var(--text-primary)]"
              >
                Avisos legales
              </h2>
              <p className="mt-1 text-xs text-[color:var(--text-secondary)]">
                Antes de entrar a tu espacio necesitamos que confirmes que
                leíste y aceptas estos tres documentos. Tu aceptación queda
                registrada para auditoría.
              </p>
              <label className="mt-4 flex items-start gap-3 text-sm text-[color:var(--text-primary)]">
                <Checkbox
                  ref={consentCheckboxRef}
                  id="legal-consent-checkbox"
                  checked={legalConsentAccepted}
                  onCheckedChange={(value) => {
                    const accepted = value === true;
                    setLegalConsentAccepted(accepted);
                    if (accepted) setConsentError(null);
                  }}
                  aria-describedby="legal-consent-links"
                  aria-invalid={consentError !== null}
                />
                <span>
                  Acepto el{" "}
                  <Link
                    href="/legal/privacidad"
                    target="_blank"
                    rel="noopener"
                    className="font-medium text-[color:var(--text-brand)] hover:underline"
                  >
                    aviso de privacidad
                  </Link>
                  , los{" "}
                  <Link
                    href="/legal/terminos"
                    target="_blank"
                    rel="noopener"
                    className="font-medium text-[color:var(--text-brand)] hover:underline"
                  >
                    términos de uso
                  </Link>
                  {" y el "}
                  <Link
                    href="/legal/consentimiento"
                    target="_blank"
                    rel="noopener"
                    className="font-medium text-[color:var(--text-brand)] hover:underline"
                  >
                    aviso de consentimiento
                  </Link>
                  {" de CheckWise."}
                </span>
              </label>
              <p
                id="legal-consent-links"
                className="mt-3 text-[11px] text-[color:var(--text-tertiary)]"
              >
                Cada enlace abre el documento en una pestaña nueva.
                {liveSession.current_legal_consent_version ? (
                  <>
                    {" "}
                    Versión vigente{" "}
                    <code className="font-mono">
                      {liveSession.current_legal_consent_version}
                    </code>
                    .
                  </>
                ) : null}
              </p>
              {consentError ? (
                <Alert variant="error" className="mt-4">
                  <AlertTitle>No pudimos continuar</AlertTitle>
                  <AlertDescription>{consentError}</AlertDescription>
                </Alert>
              ) : null}
            </section>
          ) : null}

          <footer className="cw-fade-up flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] p-4 shadow-sm">
            <p className="max-w-md text-xs text-[color:var(--text-secondary)]">
              RFC y razón social se quedan bloqueados al alta. Para
              corregirlos, usa &quot;Solicitar cambio&quot;.
            </p>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Button asChild variant="outline" size="sm">
                <Link href="/portal/perfil">
                  <UserCircle
                    className="h-4 w-4"
                    weight="bold"
                    aria-hidden="true"
                  />
                  <span>Mi perfil</span>
                </Link>
              </Button>
              <Button
                type="button"
                size="lg"
                loading={acceptingConsent}
                onClick={handleEnter}
              >
                <span>
                  {needsLegalConsent ? "Aceptar y entrar" : "Entrar a mi espacio"}
                </span>
                <ArrowRight
                  className="h-4 w-4"
                  weight="bold"
                  aria-hidden="true"
                />
              </Button>
            </div>
          </footer>

          {/* Restacked (Portal Proveedor, 2ª revisión, Mi Espacio #16): the
              old justify-between row pinned the button to the far edge and
              capped the copy at ~55ch, leaving a dead gap across the middle.
              Title + action now share the top row and the description spans
              the full width below, so the space reads as intentional. */}
          <section
            id="correccion"
            className="cw-fade-up rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-sm sm:p-6"
            aria-label="Solicitar corrección de un dato de contacto"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
                ¿Necesitas corregir un dato?
              </h2>
              <Button
                type="button"
                variant="outline"
                onClick={() => setCorrectionOpen(true)}
                aria-haspopup="dialog"
              >
                <IdentificationCard
                  className="h-4 w-4"
                  weight="bold"
                  aria-hidden="true"
                />
                <span>Solicitar cambio</span>
              </Button>
            </div>
            <p className="mt-2 text-xs text-[color:var(--text-secondary)]">
              Para corregir RFC, razón social o tu correo registrado, pide la
              actualización aquí. Cada solicitud entra a revisión antes de
              aplicarse.
            </p>
          </section>

          {isFirstVisit ? (
            <Alert variant="info">
              <AlertTitle className="flex items-center gap-2">
                <ShieldCheck
                  className="h-4 w-4"
                  weight="bold"
                  aria-hidden="true"
                />
                ¿Por qué pedimos esto?
              </AlertTitle>
              <AlertDescription>
                CheckWise opera tu expediente REPSE y debe garantizar que
                los documentos se asignen a la empresa correcta. Esta
                pantalla es la salvaguarda contra accesos cruzados.
              </AlertDescription>
            </Alert>
          ) : null}
        </div>
      </main>

      <Dialog open={correctionOpen} onOpenChange={setCorrectionOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Solicitar corrección de un dato</DialogTitle>
            <DialogDescription>
              Captura el dato que deseas corregir y una razón breve. Cada
              solicitud entra a revisión antes de aplicarse — te avisamos
              por correo cuando se aplique o si necesitamos más
              información.
            </DialogDescription>
          </DialogHeader>
          <CorrectionRequestForm
            workspace_id={workspace.protected.workspace_id}
            initialField="contact_email"
            initialCurrentValue={workspace.protected.email ?? ""}
          />
        </DialogContent>
      </Dialog>
    </PortalAppShell>
  );
}

export default withPortalSession(EntraATuEspacioInner);

// ─── Expediente status summary ──────────────────────────────────

type StepState = "primary" | "default" | "done";
type Step = { icon: Icon; title: string; body: string; state: StepState };

function buildSteps(expedienteStatus: ExpedienteStatus): Step[] {
  const yearLabel = `Calendario REPSE ${new Date().getFullYear()}: SAT mensual, IMSS bimestral, INFONAVIT, acuses STPS.`;
  const dashboard: Step = {
    icon: CheckCircle,
    title: "Revisar dashboard",
    body: "Tu semáforo de cumplimiento, acciones sugeridas y atención del día — todo en una vista.",
    state: "default",
  };
  const calendar: Step = {
    icon: CalendarBlank,
    title: "Ver próximos vencimientos",
    body: yearLabel,
    state: "default",
  };

  if (expedienteStatus === "complete") {
    // "Entrar a mi espacio" lands a completed provider on the calendar, so
    // the highlighted next step is the calendar (matches the landing); the
    // dashboard follows as an overview they can reach from the nav.
    return [
      {
        icon: ClipboardText,
        title: "Expediente completo",
        body: "Ya entregaste los documentos iniciales. Puedes seguir cargando los recurrentes desde el calendario.",
        state: "done",
      },
      { ...calendar, state: "primary" },
      dashboard,
    ];
  }

  const expediente: Step =
    expedienteStatus === "in_progress"
      ? {
          icon: ClipboardText,
          title: "Continúa tu expediente",
          body: "Te faltan algunos documentos iniciales. La checklist guiada te lleva paso a paso.",
          state: "primary",
        }
      : {
          icon: ClipboardText,
          title: "Empieza tu expediente",
          body: "Una checklist guiada con cada documento que necesitas para arrancar tu alta REPSE.",
          state: "primary",
        };
  return [expediente, dashboard, calendar];
}

function ExpedienteStatusSummary({
  status,
  workspace,
}: {
  status: ExpedienteStatus;
  workspace: WorkspaceContext;
}) {
  const items = buildSteps(status);
  return (
    <div>
      <p className="cw-eyebrow mb-3 text-[color:var(--text-teal)]">
        {workspace.editable.first_name
          ? `Próximo paso, ${workspace.editable.first_name}`
          : "Próximo paso"}
      </p>
      <ol className="border-t border-b border-[color:var(--border-subtle)] divide-y divide-[color:var(--border-subtle)]">
        {items.map(({ icon: IconComponent, title, body, state }, idx) => {
          const badgeClass =
            state === "done"
              ? "bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]"
              : state === "primary"
                ? "bg-[color:var(--text-teal)] text-white"
                : "bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]";
          return (
            <li
              key={title}
              className={
                state === "done"
                  ? "flex items-start gap-4 py-3 opacity-70"
                  : "flex items-start gap-4 py-3"
              }
            >
              <span
                className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full font-mono text-[11px] font-semibold ${badgeClass}`}
                aria-hidden="true"
              >
                {state === "done" ? (
                  <CheckCircle className="h-4 w-4" weight="fill" />
                ) : (
                  idx + 1
                )}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <IconComponent
                    className="h-3.5 w-3.5 text-[color:var(--text-tertiary)]"
                    weight="regular"
                    aria-hidden="true"
                  />
                  <p className="text-[13px] font-semibold text-[color:var(--text-primary)]">
                    {title}
                  </p>
                </div>
                <p className="mt-1 text-[12px] leading-relaxed text-[color:var(--text-secondary)]">
                  {body}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
