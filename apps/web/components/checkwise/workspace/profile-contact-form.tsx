"use client";

import { useState, type FormEvent } from "react";
import { ArrowRight, CheckCircle, ShieldCheck } from "@phosphor-icons/react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { patchWorkspaceProfile } from "@/lib/api/portal-session";
import {
  setCachedPortalSession,
  summaryToSession,
  type PortalSession,
} from "@/lib/session/portal";
import { buildWorkspaceContext } from "@/lib/workspace/resolver";
import type {
  EditableProfileFields,
  WorkspaceContext,
} from "@/lib/workspace/types";

/**
 * ProfileContactForm — editable contact / internal fields only.
 *
 * Hosted on ``/portal/perfil``. RFC + razón social + email stay
 * locked (corrections route through the dedicated request flow on
 * ``/portal/entra-a-tu-espacio``). The form persists via
 * ``PATCH /portal/workspaces/{id}/profile``.
 *
 * The CTA is "Guardar y volver a mi espacio" by default. ``onSaved``
 * lets the host page redirect to ``/portal/entra-a-tu-espacio``
 * (or wherever) after the save resolves.
 */
export function ProfileContactForm({
  session,
  onSaved,
  submitLabel = "Guardar y volver a mi espacio",
  showReturnHelper = true,
}: {
  session: PortalSession;
  onSaved?: (next: PortalSession) => void;
  submitLabel?: string;
  showReturnHelper?: boolean;
}) {
  const [liveSession, setLiveSession] = useState<PortalSession>(session);
  const workspace: WorkspaceContext = buildWorkspaceContext(liveSession);

  const [profile, setProfile] = useState<EditableProfileFields>({
    first_name: workspace.editable.first_name,
    last_name: workspace.editable.last_name,
    phone: workspace.editable.phone,
    job_title: workspace.editable.job_title,
    contact_preference: workspace.editable.contact_preference,
  });
  const [submitting, setSubmitting] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);

  const phoneError = (() => {
    if (!profile.phone) return null;
    const digits = profile.phone.replace(/\D+/g, "");
    if (digits.length < 10) {
      return "Captura al menos 10 dígitos (puedes incluir +52).";
    }
    return null;
  })();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (phoneError) {
      setSaveError(phoneError);
      document.getElementById("profile-phone")?.focus();
      return;
    }
    setSubmitting(true);
    setSaveError(null);
    const fullName = `${profile.first_name.trim()} ${profile.last_name.trim()}`
      .trim();
    const updated = await patchWorkspaceProfile(
      workspace.protected.workspace_id,
      {
        full_name: fullName || undefined,
        phone: profile.phone ?? undefined,
        job_title: profile.job_title ?? undefined,
        contact_preference: profile.contact_preference,
      },
    );
    setSubmitting(false);
    if (!updated) {
      setSaveError(
        "No pudimos guardar tus cambios. Verifica tu conexión e intenta de nuevo.",
      );
      return;
    }
    const refreshed = summaryToSession(updated);
    setLiveSession(refreshed);
    setCachedPortalSession(refreshed);
    setJustSaved(true);
    if (onSaved) {
      // Short delay so the "Guardado" affordance is visible before the
      // host routes away. Matches the prior gate behavior.
      window.setTimeout(() => onSaved(refreshed), 700);
    } else {
      window.setTimeout(() => setJustSaved(false), 1800);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
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
            Tus datos de contacto
          </h2>
          <p className="text-xs text-[color:var(--text-secondary)]">
            Edita estos campos cuando quieras. RFC, razón social y tu
            correo registrado se corrigen desde tu espacio.
          </p>
        </div>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Nombre" htmlFor="profile-first-name" required>
          <Input
            id="profile-first-name"
            value={profile.first_name}
            onChange={(e) =>
              setProfile({ ...profile, first_name: e.target.value })
            }
            autoComplete="given-name"
          />
        </Field>
        <Field label="Apellido" htmlFor="profile-last-name" required>
          <Input
            id="profile-last-name"
            value={profile.last_name}
            onChange={(e) =>
              setProfile({ ...profile, last_name: e.target.value })
            }
            autoComplete="family-name"
          />
        </Field>
        <Field
          label="Teléfono"
          htmlFor="profile-phone"
          helper={phoneError ?? "Opcional, para recordatorios."}
        >
          <Input
            id="profile-phone"
            value={profile.phone ?? ""}
            onChange={(e) =>
              setProfile({ ...profile, phone: e.target.value || null })
            }
            autoComplete="tel"
            inputMode="tel"
            placeholder="+52 55 1234 5678"
            aria-invalid={phoneError ? true : undefined}
          />
        </Field>
        <Field label="Cargo o puesto" htmlFor="profile-job-title">
          <Input
            id="profile-job-title"
            value={profile.job_title ?? ""}
            onChange={(e) =>
              setProfile({
                ...profile,
                job_title: e.target.value || null,
              })
            }
            autoComplete="organization-title"
            placeholder="Responsable de cumplimiento"
          />
        </Field>
        <Field
          label="Canal preferido"
          htmlFor="profile-contact-preference"
          helper="¿Por dónde quieres recibir avisos?"
          className="sm:col-span-2"
        >
          <Select
            id="profile-contact-preference"
            value={profile.contact_preference}
            onChange={(e) =>
              setProfile({
                ...profile,
                contact_preference:
                  e.target.value as EditableProfileFields["contact_preference"],
              })
            }
          >
            <option value="email">Correo</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="both">Correo + WhatsApp</option>
          </Select>
        </Field>
      </div>

      {saveError ? (
        <Alert variant="error" className="mt-4">
          <AlertTitle>No pudimos guardar tus cambios</AlertTitle>
          <AlertDescription>{saveError}</AlertDescription>
        </Alert>
      ) : null}

      <footer className="mt-6 flex flex-wrap items-center justify-end gap-3 border-t border-[color:var(--border-subtle)] pt-4">
        {showReturnHelper ? (
          <p className="mr-auto text-[11px] text-[color:var(--text-tertiary)]">
            Al guardar volverás a tu espacio principal.
          </p>
        ) : null}
        {justSaved ? (
          <p
            className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[color:var(--status-success-text)]"
            role="status"
          >
            <CheckCircle className="h-4 w-4" weight="fill" aria-hidden="true" />
            Guardado
          </p>
        ) : null}
        <Button
          type="submit"
          loading={submitting}
          disabled={justSaved || !!phoneError}
          size="lg"
        >
          <span>{justSaved ? "Volviendo…" : submitLabel}</span>
          {!submitting && !justSaved && (
            <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
          )}
        </Button>
      </footer>
    </form>
  );
}
