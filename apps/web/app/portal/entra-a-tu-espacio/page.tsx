"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CalendarBlank,
  ChartLineUp,
  CheckCircle,
  ClipboardText,
  IdentificationCard,
  ShieldCheck,
  Sparkle,
  type Icon,
} from "@phosphor-icons/react";

import { CorrectionRequestForm } from "@/components/checkwise/workspace/correction-request-form";
import { WorkspaceIdentityCard } from "@/components/checkwise/workspace/workspace-identity-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  readEditableProfile,
  saveEditableProfile,
} from "@/lib/workspace/profile-local";
import { buildWorkspaceContext } from "@/lib/workspace/resolver";
import type {
  EditableProfileFields,
  WorkspaceContext,
} from "@/lib/workspace/types";
import { withPortalSession } from "@/lib/session/with-portal-session";
import type {
  ExpedienteStatus,
  PortalSession,
} from "@/lib/session/portal";

/**
 * /portal/entra-a-tu-espacio
 *
 * Post-auth workspace confirmation step. The user reviews:
 *   - Tenant identity (role + company + RFC + workspace_id) — locked
 *   - Editable profile (name, phone, job title, contact preference)
 *   - Next-step preview that depends on expediente state
 *
 * Before continuing the user must press the "Entrar a mi espacio"
 * primary CTA. That action persists the editable profile and the
 * "confirmed_at" timestamp, then routes via the same routing helper
 * that powers /login and /activate.
 *
 * Spec: docs/CHECKWISE_1_6.md §2, §3, §4.
 *
 * TODO[security-backend]: every value rendered here must be re-fetched
 * from a backend endpoint that derives them from the authenticated
 * session — never trusting the localStorage portal session.
 */
function EntraATuEspacioInner({ session }: { session: PortalSession }) {
  const router = useRouter();

  // Workspace snapshot comes from the authenticated session
  // (cookie-backed /portal/me). No more mock invitations — the user is
  // already inside their assigned workspace by the time this page renders.
  const workspace = useMemo<WorkspaceContext>(
    () => buildWorkspaceContext(session),
    [session],
  );

  const storedProfile = useMemo(
    () => readEditableProfile(workspace.protected.workspace_id),
    [workspace.protected.workspace_id],
  );

  const [profile, setProfile] = useState<EditableProfileFields>({
    first_name: storedProfile.first_name ?? workspace.editable.first_name,
    last_name: storedProfile.last_name ?? workspace.editable.last_name,
    phone: storedProfile.phone ?? workspace.editable.phone,
    job_title: storedProfile.job_title ?? workspace.editable.job_title,
    contact_preference:
      storedProfile.contact_preference ?? workspace.editable.contact_preference,
  });
  const [submitting, setSubmitting] = useState(false);

  // Correction-request modal state. The dashboard's
  // <WorkspaceIdentityCard /> footer link still routes here with
  // ``#correccion`` so existing deep-links don't break; on arrival we
  // auto-open the dialog and clear the fragment so the URL stays clean
  // when the user closes it.
  const [correctionOpen, setCorrectionOpen] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.location.hash === "#correccion") {
      setCorrectionOpen(true);
      // Clear the fragment without scrolling so a second back-and-forth
      // doesn't keep reopening the dialog.
      window.history.replaceState(
        null,
        "",
        window.location.pathname + window.location.search,
      );
    }
  }, []);

  // Inline confirmation that the form persisted before we navigate
  // away. Without it the button label flipped straight from "Entrar a
  // mi espacio" to a route change, which felt like the form had been
  // ignored. ``justSaved`` flips on for ~700ms so the user sees a
  // "Guardado" affordance before the redirect fires.
  const [justSaved, setJustSaved] = useState(false);

  async function handleConfirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    // Profile fields persist locally only today — see lib/workspace/
    // profile-local.ts. The "confirmed_at" timestamp was previously
    // also written to localStorage but nothing read it back, so the
    // dead-state write was dropped during the audit. Real backend
    // persistence is tracked as a follow-up (E in the audit punch list).
    await saveEditableProfile(workspace.protected.workspace_id, profile);
    setSubmitting(false);
    setJustSaved(true);
    // Onboarding gate: a brand-new provider must finish their initial
    // expediente before the dashboard becomes available. The session's
    // expediente_status comes from the backend (single source of truth).
    const next =
      session.expediente_status === "complete"
        ? "/portal/dashboard"
        : "/portal/onboarding";
    // Brief pause so the saved affordance is visible before nav.
    window.setTimeout(() => router.push(next), 700);
  }

  // Lenient MX phone-format check. Empty is fine (phone is optional);
  // anything with at least 10 digits passes, anything else is flagged
  // inline. We do NOT block submit on this — the field is optional and
  // we don't want to wedge the welcome flow over a format quibble.
  const phoneError = (() => {
    if (!profile.phone) return null;
    const digits = profile.phone.replace(/\D+/g, "");
    if (digits.length < 10) {
      return "Captura al menos 10 dígitos (puedes incluir +52).";
    }
    return null;
  })();

  return (
    <main className="relative min-h-[100dvh] overflow-hidden bg-[color:var(--surface-page)]">
      <div className="relative mx-auto flex max-w-4xl flex-col gap-6 px-5 py-10 lg:py-14">
        <header className="cw-fade-up flex flex-col gap-2">
          <Badge variant="teal" className="self-start rounded-full px-3 py-1">
            <Sparkle className="h-3 w-3" weight="fill" aria-hidden="true" />
            Confirmación de espacio
          </Badge>
          <h1 className="text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
            Entra a tu espacio
          </h1>
          <p className="max-w-prose text-[15px] text-[color:var(--text-secondary)]">
            Confirma que esta información es correcta antes de continuar.
            Usamos estos datos para proteger tu expediente y evitar que los
            documentos se asignen a la empresa incorrecta.
          </p>
        </header>

        <WorkspaceIdentityCard
          workspace={workspace}
          showCorrectionLink={false}
          hideExpedienteLink
        />

        <form
          onSubmit={handleConfirm}
          className="cw-fade-up rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-sm sm:p-8"
        >
          <header className="mb-5 flex items-center gap-3">
            <span
              className="flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--surface-teal-muted)]"
              aria-hidden="true"
            >
              <ShieldCheck
                className="h-5 w-5 text-[color:var(--text-teal)]"
                weight="duotone"
              />
            </span>
            <div>
              <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
                Confirma tus datos de contacto
              </h2>
              <p className="text-xs text-[color:var(--text-secondary)]">
                Edita estos campos cuando quieras. Para corregir RFC,
                razón social o tu correo registrado, usa "Solicitar
                cambio".
              </p>
            </div>
          </header>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Nombre" htmlFor="ws-first-name" required>
              <Input
                id="ws-first-name"
                value={profile.first_name}
                onChange={(e) => setProfile({ ...profile, first_name: e.target.value })}
                autoComplete="given-name"
              />
            </Field>
            <Field label="Apellido" htmlFor="ws-last-name" required>
              <Input
                id="ws-last-name"
                value={profile.last_name}
                onChange={(e) => setProfile({ ...profile, last_name: e.target.value })}
                autoComplete="family-name"
              />
            </Field>
            <Field
              label="Teléfono"
              htmlFor="ws-phone"
              helper={
                phoneError ?? "Opcional, para recordatorios."
              }
            >
              <Input
                id="ws-phone"
                value={profile.phone ?? ""}
                onChange={(e) =>
                  setProfile({
                    ...profile,
                    phone: e.target.value || null,
                  })
                }
                autoComplete="tel"
                inputMode="tel"
                placeholder="+52 55 1234 5678"
                aria-invalid={phoneError ? true : undefined}
              />
            </Field>
            <Field label="Cargo o puesto" htmlFor="ws-job-title">
              <Input
                id="ws-job-title"
                value={profile.job_title ?? ""}
                onChange={(e) => setProfile({ ...profile, job_title: e.target.value || null })}
                autoComplete="organization-title"
                placeholder="Responsable de cumplimiento"
              />
            </Field>
            <Field
              label="Canal preferido"
              htmlFor="ws-contact-preference"
              helper="¿Por dónde quieres recibir avisos?"
              className="sm:col-span-2"
            >
              <Select
                id="ws-contact-preference"
                value={profile.contact_preference}
                onChange={(e) =>
                  setProfile({
                    ...profile,
                    contact_preference: e.target.value as EditableProfileFields["contact_preference"],
                  })
                }
              >
                <option value="email">Correo</option>
                <option value="whatsapp">WhatsApp</option>
                <option value="both">Correo + WhatsApp</option>
              </Select>
            </Field>
          </div>

          <NextStepPreview
            workspace={workspace}
            expedienteStatus={session.expediente_status}
          />

          <footer className="mt-6 flex items-center justify-end gap-3 border-t border-[color:var(--border-subtle)] pt-4">
            {justSaved ? (
              <p
                className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[color:var(--status-success-text)]"
                role="status"
              >
                <CheckCircle
                  className="h-4 w-4"
                  weight="fill"
                  aria-hidden="true"
                />
                Guardado
              </p>
            ) : null}
            <Button
              type="submit"
              loading={submitting}
              disabled={justSaved}
              size="lg"
            >
              <span>{justSaved ? "Continuando…" : "Entrar a mi espacio"}</span>
              {!submitting && !justSaved && (
                <ArrowRight
                  className="h-4 w-4"
                  weight="bold"
                  aria-hidden="true"
                />
              )}
            </Button>
          </footer>
        </form>

        <Alert variant="info">
          <AlertTitle className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" weight="bold" aria-hidden="true" />
            ¿Por qué pedimos esto?
          </AlertTitle>
          <AlertDescription>
            CheckWise opera tu expediente REPSE y debe garantizar que los
            documentos se asignen a la empresa correcta. Esta pantalla es la
            salvaguarda contra accesos cruzados.
          </AlertDescription>
        </Alert>

        {/* Stage 2.7-a — provider workspace correction-request entry point.
            The form covers only the locked Tier B fields
            (contact_email / contact_phone / contact_name). Everything
            else routes to support per the locked decision in §18 of
            the experience plan.

            The form now lives inside a Dialog so the page stays focused
            on the welcome flow. ``id="correccion"`` is the anchor
            target referenced by <WorkspaceIdentityCard /> on the
            dashboard; arriving with that fragment auto-opens the
            dialog via the useEffect at the top of this component. */}
        <section
          id="correccion"
          className="cw-fade-up flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-sm sm:p-6"
          aria-label="Solicitar corrección de un dato de contacto"
        >
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
              ¿Necesitas corregir un dato?
            </h2>
            <p className="mt-1 max-w-prose text-xs text-[color:var(--text-secondary)]">
              Pide la actualización de tu correo, teléfono o nombre de
              contacto. Cada solicitud entra a revisión antes de aplicarse.
            </p>
          </div>
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
        </section>
      </div>

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
    </main>
  );
}

export default withPortalSession(EntraATuEspacioInner);

// ─── Next-step preview ──────────────────────────────────────────

type StepState = "primary" | "default" | "done";
type Step = { icon: Icon; title: string; body: string; state: StepState };

function buildSteps(expedienteStatus: ExpedienteStatus): Step[] {
  // Stage 2.7 (audit follow-up G, 2026-05-22) — the rail used to render
  // the same 4 items in the same order regardless of state, so a user
  // with a complete expediente saw "Completar expediente inicial" as
  // step 1 and the system looked like it had forgotten what they did.
  // Now the lead item adapts:
  //   not_started → "Empieza tu expediente" (primary)
  //   in_progress → "Continúa tu expediente" (primary)
  //   complete    → "Expediente completo" (done) with dashboard first
  const yearLabel = `Calendario REPSE ${new Date().getFullYear()}: SAT mensual, IMSS bimestral, INFONAVIT, acuses STPS.`;
  const dashboard: Step = {
    icon: CheckCircle,
    title: "Revisar dashboard",
    body:
      "Tu semáforo de cumplimiento, acciones sugeridas y atención del día — todo en una vista.",
    state: "default",
  };
  const calendar: Step = {
    icon: CalendarBlank,
    title: "Ver próximos vencimientos",
    body: yearLabel,
    state: "default",
  };
  const reports: Step = {
    icon: ChartLineUp,
    title: "Revisar reportes",
    body: "Reportes ejecutivos por periodo, proveedor, faltantes y riesgos.",
    state: "default",
  };

  if (expedienteStatus === "complete") {
    return [
      {
        icon: ClipboardText,
        title: "Expediente completo",
        body: "Ya entregaste los documentos iniciales. Puedes seguir cargando los recurrentes desde el calendario.",
        state: "done",
      },
      { ...dashboard, state: "primary" },
      calendar,
      reports,
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
  return [expediente, dashboard, calendar, reports];
}

function NextStepPreview({
  workspace,
  expedienteStatus,
}: {
  workspace: WorkspaceContext;
  expedienteStatus: ExpedienteStatus;
}) {
  const items = buildSteps(expedienteStatus);

  // V2.x: replaces the previous 2×2 tile grid with a numbered
  // vertical rail. The audit (AUDIT_2_X.md §"Provider portal") flagged
  // the 4 tiles as at risk of being an identical-card-grid anti-
  // pattern. The vertical rail keeps the same content but turns it
  // into an ordered "what happens next" sequence, which is closer to
  // the operator's mental model.
  return (
    <section className="mt-6">
      <p className="cw-eyebrow mb-3 text-[color:var(--text-teal)]">
        {workspace.editable.first_name
          ? `Tu próximo paso, ${workspace.editable.first_name}`
          : "Tu próximo paso"}
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
    </section>
  );
}

// V2.x: BackgroundOrnaments removed. The previous radial-blob
// gradients (navy + teal) violated §"Color strategy — Restrained".
// The page now uses the standard --surface-page background; if more
// texture is needed in a future polish, add cw-grid-pattern instead.

