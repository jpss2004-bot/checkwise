"use client";

import { useMemo, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CalendarBlank,
  ChartLineUp,
  CheckCircle,
  ClipboardText,
  ShieldCheck,
  Sparkle,
  type Icon,
} from "@phosphor-icons/react";

import { WorkspaceIdentityCard } from "@/components/checkwise/workspace/workspace-identity-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  readEditableProfile,
  saveEditableProfile,
} from "@/lib/mock/corrections";
import { buildWorkspaceContext } from "@/lib/workspace/resolver";
import type {
  EditableProfileFields,
  WorkspaceContext,
} from "@/lib/workspace/types";
import { withPortalSession } from "@/lib/session/with-portal-session";
import type { PortalSession } from "@/lib/session/portal";

const STORAGE_KEY_CONFIRMED = "checkwise.workspace.confirmed.v1";

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
    () => buildWorkspaceContext(session, null),
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

  async function handleConfirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    await saveEditableProfile(workspace.protected.workspace_id, profile);
    if (typeof window !== "undefined") {
      const confirmed = (() => {
        try {
          const raw = window.localStorage.getItem(STORAGE_KEY_CONFIRMED);
          return raw ? (JSON.parse(raw) as Record<string, string>) : {};
        } catch {
          return {} as Record<string, string>;
        }
      })();
      confirmed[workspace.protected.workspace_id] = new Date().toISOString();
      window.localStorage.setItem(STORAGE_KEY_CONFIRMED, JSON.stringify(confirmed));
    }
    setSubmitting(false);
    // Onboarding gate: a brand-new provider must finish their initial
    // expediente before the dashboard becomes available. The session's
    // expediente_status comes from the backend (single source of truth).
    const next =
      session.expediente_status === "complete"
        ? "/portal/dashboard"
        : "/portal/onboarding";
    router.push(next);
  }

  return (
    <main className="relative min-h-[100dvh] overflow-hidden bg-[color:var(--surface-page)]">
      <BackgroundOrnaments />

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
                Estos campos sí los puedes editar directamente.
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
            <Field label="Teléfono" htmlFor="ws-phone" helper="Opcional, para recordatorios.">
              <Input
                id="ws-phone"
                value={profile.phone ?? ""}
                onChange={(e) => setProfile({ ...profile, phone: e.target.value || null })}
                autoComplete="tel"
                placeholder="+52 55 1234 5678"
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

          <NextStepPreview workspace={workspace} />

          <footer className="mt-6 flex justify-end border-t border-[color:var(--border-subtle)] pt-4">
            <Button
              type="submit"
              loading={submitting}
              size="lg"
            >
              <span>Entrar a mi espacio</span>
              {!submitting && <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />}
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
      </div>
    </main>
  );
}

export default withPortalSession(EntraATuEspacioInner);

// ─── Next-step preview ──────────────────────────────────────────

function NextStepPreview({ workspace }: { workspace: WorkspaceContext }) {
  const items: { icon: Icon; title: string; body: string }[] = [
    {
      icon: ClipboardText,
      title: "Completar expediente inicial",
      body:
        "Una checklist guiada con cada documento que necesitas para arrancar tu alta REPSE.",
    },
    {
      icon: CheckCircle,
      title: "Revisar dashboard",
      body:
        "Tu semáforo de cumplimiento, acciones sugeridas y atención del día — todo en una vista.",
    },
    {
      icon: CalendarBlank,
      title: "Ver próximos vencimientos",
      body:
        "Calendario REPSE 2026: SAT mensual, IMSS bimestral, INFONAVIT, acuses STPS.",
    },
    {
      icon: ChartLineUp,
      title: "Revisar reportes",
      body:
        "Reportes ejecutivos por periodo, proveedor, faltantes y riesgos.",
    },
  ];

  return (
    <section className="mt-6 rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-4">
      <p className="mb-3 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-teal)]">
        Tu próximo paso, {workspace.editable.first_name || "bienvenido"}
      </p>
      <ul className="grid gap-3 sm:grid-cols-2">
        {items.map(({ icon: IconComponent, title, body }) => (
          <li
            key={title}
            className="flex items-start gap-3 rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] p-3"
          >
            <span
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)]"
              aria-hidden="true"
            >
              <IconComponent
                className="h-4 w-4 text-[color:var(--text-brand)]"
                weight="duotone"
              />
            </span>
            <div>
              <p className="text-[13px] font-semibold text-[color:var(--text-primary)]">
                {title}
              </p>
              <p className="mt-0.5 text-xs leading-5 text-[color:var(--text-secondary)]">
                {body}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function BackgroundOrnaments() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute -top-32 left-1/4 h-[480px] w-[480px] rounded-full opacity-[0.14] blur-3xl"
        style={{
          background:
            "radial-gradient(circle, hsl(var(--brand-navy)/0.55) 0%, transparent 70%)",
        }}
      />
      <div
        className="absolute -bottom-40 -right-24 h-[520px] w-[520px] rounded-full opacity-[0.12] blur-3xl"
        style={{
          background:
            "radial-gradient(circle, hsl(var(--brand-teal)/0.6) 0%, transparent 70%)",
        }}
      />
    </div>
  );
}

