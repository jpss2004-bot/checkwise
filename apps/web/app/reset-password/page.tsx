"use client";

import {
  Suspense,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle,
  ShieldCheck,
} from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { PasswordInput } from "@/components/ui/password-input";
import { Skeleton } from "@/components/ui/skeleton";
import { AuthApiError, resetPassword } from "@/lib/api/auth";
import { evaluatePassword } from "@/lib/email-inference";
import { clearAdminSession } from "@/lib/session/admin";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<ResetSkeleton />}>
      <ResetPasswordInner />
    </Suspense>
  );
}

function ResetPasswordInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams?.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  const rules = useMemo(() => evaluatePassword(password), [password]);
  const allRulesPassed = rules.every((rule) => rule.passed);
  const passwordsMatch = password.length > 0 && password === confirm;
  const canSubmit = Boolean(token) && allRulesPassed && passwordsMatch;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    if (!passwordsMatch) {
      setConfirmError("Las contraseñas no coinciden.");
      return;
    }
    setConfirmError(null);
    setError(null);
    setSubmitting(true);
    try {
      await resetPassword(token, password);
      clearAdminSession();
      setSuccess(true);
      setTimeout(() => router.replace("/login"), 1400);
    } catch (err) {
      if (err instanceof AuthApiError && err.status === 400) {
        setError("El enlace ya venció o no es válido. Solicita uno nuevo.");
      } else if (err instanceof AuthApiError && err.status === 422) {
        setError("La contraseña no cumple los requisitos mínimos.");
      } else {
        setError("No pudimos restablecer la contraseña. Intenta de nuevo.");
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
      <div className="relative mx-auto flex min-h-[100dvh] max-w-2xl flex-col gap-8 px-5 py-10 lg:py-14">
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
              Nueva contraseña
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
              Define tu nueva contraseña
            </h1>
            <p className="text-[15px] leading-relaxed text-[color:var(--text-secondary)]">
              Usa una contraseña distinta a la anterior. Al guardar, tendrás que
              iniciar sesión de nuevo.
            </p>
          </div>

          {!token && (
            <Alert variant="error">
              <AlertTitle>Enlace incompleto</AlertTitle>
              <AlertDescription>
                Solicita un nuevo enlace desde la pantalla de recuperación.
              </AlertDescription>
            </Alert>
          )}

          <section className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-[var(--shadow-sm)]">
            {success ? (
              <SuccessStep />
            ) : (
              <form onSubmit={onSubmit} className="flex flex-col gap-5" noValidate>
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--surface-teal-muted)]">
                    <ShieldCheck
                      className="h-5 w-5 text-[color:var(--text-teal)]"
                      weight="duotone"
                      aria-hidden="true"
                    />
                  </span>
                  <div>
                    <h2 className="text-lg font-semibold text-[color:var(--text-primary)]">
                      Restablecer acceso
                    </h2>
                    <p className="text-[13px] text-[color:var(--text-secondary)]">
                      Mínimo 12 caracteres con mayúscula, minúscula y número.
                    </p>
                  </div>
                </div>

                {error && (
                  <Alert variant="error">
                    <AlertTitle>No pudimos completar el cambio</AlertTitle>
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}

                <Field label="Nueva contraseña" htmlFor="reset-password" required>
                  <PasswordInput
                    id="reset-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                    autoFocus
                    disabled={!token}
                  />
                </Field>

                <ul
                  className="grid gap-2 sm:grid-cols-2"
                  aria-label="Requisitos de la contraseña"
                >
                  {rules.map(({ rule, passed }) => (
                    <li
                      key={rule.label}
                      className={
                        "flex items-center gap-2 rounded-sm border px-3 py-2 text-xs " +
                        (passed
                          ? "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]"
                          : "border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)]")
                      }
                    >
                      {passed ? (
                        <Check className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                      ) : (
                        <span
                          className="h-3.5 w-3.5 rounded-full border border-current opacity-50"
                          aria-hidden="true"
                        />
                      )}
                      <span>{rule.label}</span>
                    </li>
                  ))}
                </ul>

                <Field
                  label="Confirma tu contraseña"
                  htmlFor="reset-confirm-password"
                  required
                  error={confirmError}
                >
                  <PasswordInput
                    id="reset-confirm-password"
                    value={confirm}
                    onChange={(e) => {
                      setConfirm(e.target.value);
                      setConfirmError(null);
                    }}
                    autoComplete="new-password"
                    disabled={!token}
                  />
                </Field>

                <Button
                  type="submit"
                  loading={submitting}
                  size="lg"
                  disabled={!canSubmit && !submitting}
                >
                  <span>{submitting ? "Guardando…" : "Guardar contraseña"}</span>
                  {!submitting && (
                    <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
                  )}
                </Button>
              </form>
            )}
          </section>
        </section>
      </div>
    </main>
  );
}

function SuccessStep() {
  return (
    <div className="flex flex-col items-center gap-4 py-6 text-center">
      <span
        className="cw-success-ring flex h-16 w-16 items-center justify-center rounded-full bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]"
        aria-hidden="true"
      >
        <CheckCircle className="h-9 w-9" weight="fill" />
      </span>
      <div>
        <h2 className="text-xl font-semibold text-[color:var(--text-primary)]">
          Contraseña restablecida
        </h2>
        <p className="mt-1 text-[13px] text-[color:var(--text-secondary)]">
          Te llevamos a iniciar sesión…
        </p>
      </div>
    </div>
  );
}

function ResetSkeleton() {
  return (
    <main className="mx-auto max-w-2xl px-5 py-16">
      <Skeleton className="h-8 w-32" />
      <Skeleton className="mt-6 h-[520px] w-full rounded-xl" />
    </main>
  );
}
