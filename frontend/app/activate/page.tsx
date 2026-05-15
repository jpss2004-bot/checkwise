"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle,
  Eye,
  EyeSlash,
  ShieldCheck,
} from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { evaluatePassword } from "@/lib/email-inference";
import { AuthApiError, setPassword } from "@/lib/api/auth";
import {
  clearAdminSession,
  readAdminSession,
  writeAdminSession,
} from "@/lib/session/admin";

/**
 * /activate
 *
 * Forced first-login screen. Reached when /login responds with
 * ``must_change_password=true``. The user already has a valid JWT
 * stored from /login — this page only collects the new password and
 * posts it to /api/v1/auth/set-password.
 *
 * On success the local session is updated to drop the must-change
 * flag and the user is routed to:
 *   * /admin/reviewer if their roles include admin/reviewer, or
 *   * /portal/entra-a-tu-espacio otherwise.
 */
export default function ActivatePage() {
  const router = useRouter();
  const [bootChecked, setBootChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const [password, setPasswordValue] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  const session = useMemo(() => (bootChecked ? readAdminSession() : null), [
    bootChecked,
  ]);

  useEffect(() => {
    const stored = readAdminSession();
    if (!stored) {
      router.replace("/login");
      return;
    }
    setBootChecked(true);
  }, [router]);

  const rules = useMemo(() => evaluatePassword(password), [password]);
  const allRulesPassed = rules.every((rule) => rule.passed);
  const passwordsMatch = password.length > 0 && password === confirm;
  const canSubmit = allRulesPassed && passwordsMatch;

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const stored = readAdminSession();
      if (!stored) {
        router.replace("/login");
        return;
      }
      if (!passwordsMatch) {
        setConfirmError("Las contraseñas no coinciden.");
        return;
      }
      setConfirmError(null);
      setError(null);
      setSubmitting(true);
      try {
        const result = await setPassword(stored.access_token, password);
        // Refresh local session with the cleared flag so a refresh on
        // any page doesn't bounce the user back to /activate.
        writeAdminSession({
          ...stored,
          user: {
            ...stored.user,
            ...result.user,
          },
        });
        setSuccess(true);
        const dest = stored.roles.includes("internal_admin") ||
          stored.roles.includes("reviewer")
          ? "/admin/reviewer"
          : "/portal/entra-a-tu-espacio";
        setTimeout(() => router.replace(dest), 1200);
      } catch (err) {
        if (err instanceof AuthApiError && err.status === 401) {
          // Token expired or invalid — bounce to login to re-auth.
          clearAdminSession();
          setError("Tu sesión expiró. Vuelve a iniciar sesión.");
          setTimeout(() => router.replace("/login"), 1200);
        } else if (err instanceof AuthApiError && err.status === 422) {
          setError("La contraseña no cumple los requisitos mínimos.");
        } else {
          setError("No pudimos guardar tu nueva contraseña. Intenta de nuevo.");
        }
      } finally {
        setSubmitting(false);
      }
    },
    [password, passwordsMatch, router],
  );

  if (!bootChecked || !session) return <ActivateSkeleton />;

  return (
    <main className="min-h-[100dvh] bg-[color:var(--surface-page)]">
      <div className="mx-auto flex min-h-[100dvh] max-w-3xl flex-col gap-8 px-5 py-10 lg:py-14">
        <header className="flex items-center justify-between">
          <Link href="/" aria-label="Volver al inicio">
            <BrandLogo size="md" />
          </Link>
          <Link
            href="/login"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[color:var(--text-link)] hover:underline"
          >
            <ArrowLeft className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            Cancelar e iniciar sesión de nuevo
          </Link>
        </header>

        <Alert variant="info">
          <AlertTitle className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" weight="bold" aria-hidden="true" />
            Tu contraseña actual es temporal
          </AlertTitle>
          <AlertDescription>
            Antes de entrar a tu espacio necesitamos que definas una contraseña
            permanente para{" "}
            <span className="font-medium text-[color:var(--text-primary)]">
              {session.user.email}
            </span>
            .
          </AlertDescription>
        </Alert>

        <section className="cw-fade-up rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-md sm:p-8">
          {success ? (
            <SuccessStep />
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--surface-teal-muted)]">
                  <ShieldCheck
                    className="h-5 w-5 text-[color:var(--text-teal)]"
                    weight="duotone"
                    aria-hidden="true"
                  />
                </span>
                <div>
                  <h1 className="text-lg font-semibold text-[color:var(--text-primary)]">
                    Define tu contraseña permanente
                  </h1>
                  <p className="text-[13px] text-[color:var(--text-secondary)]">
                    Mínimo 12 caracteres. La usarás en cada inicio de sesión.
                  </p>
                </div>
              </div>

              {error && (
                <Alert variant="error">
                  <AlertTitle>No pudimos completar el cambio</AlertTitle>
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <Field label="Nueva contraseña" htmlFor="new-password" required>
                <div className="relative">
                  <Input
                    id="new-password"
                    type={show ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPasswordValue(e.target.value)}
                    autoComplete="new-password"
                    autoFocus
                    className="pr-12"
                  />
                  <button
                    type="button"
                    onClick={() => setShow((s) => !s)}
                    aria-label={show ? "Ocultar contraseña" : "Mostrar contraseña"}
                    className="absolute inset-y-0 right-0 flex w-12 items-center justify-center text-[color:var(--text-tertiary)] hover:text-[color:var(--text-primary)]"
                  >
                    {show ? (
                      <EyeSlash className="h-4 w-4" weight="bold" aria-hidden="true" />
                    ) : (
                      <Eye className="h-4 w-4" weight="bold" aria-hidden="true" />
                    )}
                  </button>
                </div>
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
                htmlFor="confirm-password"
                required
                error={confirmError}
              >
                <Input
                  id="confirm-password"
                  type={show ? "text" : "password"}
                  value={confirm}
                  onChange={(e) => {
                    setConfirm(e.target.value);
                    setConfirmError(null);
                  }}
                  autoComplete="new-password"
                />
              </Field>

              <Button
                type="submit"
                loading={submitting}
                size="lg"
                disabled={!canSubmit && !submitting}
              >
                <span>Guardar y entrar</span>
                {!submitting && (
                  <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
                )}
              </Button>
            </form>
          )}
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
        <h1 className="text-xl font-semibold text-[color:var(--text-primary)]">
          Contraseña guardada
        </h1>
        <p className="mt-1 text-[13px] text-[color:var(--text-secondary)]">
          Te llevamos a tu espacio…
        </p>
      </div>
    </div>
  );
}

function ActivateSkeleton() {
  return (
    <main className="min-h-[100dvh] bg-[color:var(--surface-page)]">
      <div className="mx-auto flex min-h-[100dvh] max-w-3xl flex-col gap-6 px-5 py-10 lg:py-14">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-[480px] w-full rounded-xl" />
      </div>
    </main>
  );
}
