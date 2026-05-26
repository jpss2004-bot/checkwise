"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { ArrowLeft, PaperPlaneTilt } from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { AuthApiError, requestPasswordReset } from "@/lib/api/auth";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await requestPasswordReset(email);
      setSent(true);
    } catch (err) {
      if (err instanceof AuthApiError && err.status === 422) {
        setError("Escribe un correo válido.");
      } else if (err instanceof AuthApiError && err.status === 429) {
        // Audit-finding #6 — surface the rate-limit specifically.
        // Without this branch the user saw a generic "intenta de
        // nuevo" message that told them to do exactly the thing the
        // server is throttling.
        setError(
          "Ya enviamos demasiadas solicitudes para este correo. Espera unos minutos antes de pedir otro enlace.",
        );
      } else {
        setError("No pudimos enviar las instrucciones. Intenta de nuevo.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="relative min-h-[100dvh] overflow-hidden bg-[color:var(--surface-page)]">
      <div
        aria-hidden="true"
        className="cw-grid-pattern pointer-events-none absolute inset-0 -z-10"
      />
      <div className="relative mx-auto flex min-h-[100dvh] max-w-md flex-col gap-8 px-5 py-10 lg:py-14">
        <header className="cw-fade-up flex items-center justify-between">
          <Link href="/" aria-label="Volver al inicio">
            <BrandLogo size="md" poweredBy />
          </Link>
          <Link
            href="/login"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[color:var(--text-link)] hover:underline"
          >
            <ArrowLeft className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            Volver a iniciar sesión
          </Link>
        </header>

        <section className="cw-fade-up space-y-6" style={{ animationDelay: "60ms" }}>
          <div className="space-y-2">
            <p className="cw-eyebrow text-[color:var(--text-teal)]">
              Recuperar acceso
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
              Restablece tu contraseña
            </h1>
            <p className="text-[15px] leading-relaxed text-[color:var(--text-secondary)]">
              Escribe el correo de tu cuenta. Si existe en CheckWise, te enviaremos
              un enlace para definir una contraseña nueva.
            </p>
          </div>

          <form
            onSubmit={onSubmit}
            className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-[var(--shadow-sm)]"
            noValidate
          >
            {sent && (
              <Alert variant="success" className="mb-5">
                <AlertTitle>Revisa tu correo</AlertTitle>
                <AlertDescription>
                  Si encontramos una cuenta con ese correo, enviamos el enlace para
                  restablecer la contraseña.
                </AlertDescription>
              </Alert>
            )}

            {error && (
              <Alert variant="error" className="mb-5">
                <AlertTitle>No pudimos procesar la solicitud</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <Field label="Correo electrónico" htmlFor="forgot-email" required>
              <Input
                id="forgot-email"
                type="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setSent(false);
                }}
                autoComplete="email"
                autoFocus
                placeholder="tu.correo@empresa.com"
              />
            </Field>

            <Button
              type="submit"
              loading={submitting}
              size="lg"
              className="mt-6 w-full"
            >
              {!submitting && (
                <PaperPlaneTilt className="h-4 w-4" weight="bold" aria-hidden="true" />
              )}
              <span>{submitting ? "Enviando…" : "Enviar enlace"}</span>
            </Button>
          </form>
        </section>
      </div>
    </main>
  );
}
