"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { ArrowRight, CheckCircle, PaperPlaneTilt } from "@phosphor-icons/react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  INTEREST_LABELS,
  submitContactRequest,
  type ContactRequestPayload,
  type LeadInterest,
} from "@/lib/api/contact";

const initial: ContactRequestPayload = {
  name: "",
  company: "",
  email: "",
  interest: "exploring",
  message: "",
};

/**
 * Inline contact / demo-request form used on the public landing.
 *
 * Real submission — posts to `POST /api/v1/contact` via `lib/api/contact.ts`.
 * Persisted as a `ContactRequest` row, plus optional Slack delivery when
 * `SLACK_CONTACT_WEBHOOK_URL` is configured on the backend.
 */
export function ContactForm() {
  const [form, setForm] = useState<ContactRequestPayload>(initial);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState<{ request_id: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{
    name?: string;
    email?: string;
  }>({});

  function update<K extends keyof ContactRequestPayload>(
    key: K,
    value: ContactRequestPayload[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
    if (key === "name" || key === "email") {
      setFieldErrors((current) => ({ ...current, [key]: undefined }));
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors: typeof fieldErrors = {};
    if (form.name.trim().length < 2) errors.name = "Captura tu nombre.";
    if (!form.email.trim().includes("@")) errors.email = "Captura un correo válido.";
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    setError(null);
    const result = await submitContactRequest(form);
    setSubmitting(false);
    if (!result.ok) {
      setError(result.error ?? "No pudimos enviar tu solicitud.");
      return;
    }
    setDone({ request_id: result.request_id! });
  }

  if (done) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-xl border border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] px-6 py-8 text-center">
        <span
          className="cw-success-ring flex h-12 w-12 items-center justify-center rounded-full bg-[color:var(--status-success-text)] text-white"
          aria-hidden="true"
        >
          <CheckCircle className="h-7 w-7" weight="fill" />
        </span>
        <div>
          <h3 className="text-lg font-semibold text-[color:var(--text-primary)]">
            ¡Recibimos tu solicitud!
          </h3>
          <p className="mt-1 max-w-prose text-[13px] text-[color:var(--text-secondary)]">
            Te contactaremos en menos de 1 día hábil con los próximos pasos.
          </p>
          <p className="mt-3 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            Folio: {done.request_id}
          </p>
        </div>
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-6"
      noValidate
      aria-label="Formulario de contacto"
    >
      <div className="grid gap-6 sm:grid-cols-2">
        <Field
          label="Nombre"
          htmlFor="contact-name"
          required
          error={fieldErrors.name}
        >
          <Input
            id="contact-name"
            value={form.name}
            onChange={(e) => update("name", e.target.value)}
            placeholder="Juan Pérez"
            autoComplete="name"
          />
        </Field>
        <Field label="Empresa" htmlFor="contact-company">
          <Input
            id="contact-company"
            value={form.company}
            onChange={(e) => update("company", e.target.value)}
            placeholder="Constructora ABC"
            autoComplete="organization"
          />
        </Field>
      </div>

      <Field
        label="Correo de trabajo"
        htmlFor="contact-email"
        required
        error={fieldErrors.email}
      >
        <Input
          id="contact-email"
          type="email"
          value={form.email}
          onChange={(e) => update("email", e.target.value)}
          placeholder="juan.perez@empresa.com"
          autoComplete="email"
        />
      </Field>

      <Field label="¿Cuál es tu rol?" htmlFor="contact-interest">
        <Select
          id="contact-interest"
          value={form.interest}
          onChange={(e) => update("interest", e.target.value as LeadInterest)}
        >
          {Object.entries(INTEREST_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </Field>

      <Field
        label="¿Qué necesitas?"
        htmlFor="contact-message"
        helper="Opcional. Cuéntanos brevemente tu caso."
      >
        <Textarea
          id="contact-message"
          value={form.message}
          onChange={(e) => update("message", e.target.value)}
          rows={4}
          placeholder="Buscamos auditar a 12 proveedores REPSE este trimestre…"
        />
      </Field>

      {error && (
        <Alert variant="error">
          <AlertTitle>No pudimos enviar tu solicitud</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Button type="submit" loading={submitting} size="lg" className="self-start">
        <PaperPlaneTilt className="h-4 w-4" weight="bold" aria-hidden="true" />
        <span>Enviar solicitud</span>
        {!submitting && <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />}
      </Button>
      <p className="text-xs leading-relaxed text-[color:var(--text-secondary)]">
        Al enviar aceptas que te contactemos para coordinar una demo o brindarte
        información. Tratamos tus datos conforme a nuestro{" "}
        <Link
          href="/legal/privacidad"
          className="font-medium text-[color:var(--text-link)] underline-offset-2 hover:underline"
        >
          Aviso de privacidad
        </Link>
        .
      </p>
    </form>
  );
}
