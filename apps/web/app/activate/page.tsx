"use client";

import {
  Suspense,
  useCallback,
  useEffect,
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
import { evaluatePassword } from "@/lib/email-inference";
import { AuthApiError, setPassword } from "@/lib/api/auth";
import {
  clearAdminSession,
  readAdminSession,
  setAdminAccessToken,
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
  // useSearchParams() forces client-side rendering; Next.js requires
  // it to live inside a Suspense boundary or the static generator
  // bails out (NEXT_NOT_FOUND / missing-suspense-with-csr-bailout).
  // Wrapping ActivateInner in <Suspense> keeps the prerender path
  // clean and falls back to the skeleton during hydration.
  return (
    <Suspense fallback={<ActivateSkeleton />}>
      <ActivateInner />
    </Suspense>
  );
}

function ActivateInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [bootChecked, setBootChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [invalidLink, setInvalidLink] = useState(false);

  const [password, setPasswordValue] = useState("");
  const [confirm, setConfirm] = useState("");
  const [confirmError, setConfirmError] = useState<string | null>(null);

  const session = useMemo(() => (bootChecked ? readAdminSession() : null), [
    bootChecked,
  ]);

  useEffect(() => {
    const stored = readAdminSession();
    if (!stored) {
      // V2.x: surface an explicit invalid-link state when the user
      // landed via an old-style /activate?token=... URL but isn't
      // authenticated. Previously the page silently redirected, which
      // the audit flagged as confusing — the user couldn't tell
      // whether their token was bad or the page was broken.
      const token = searchParams?.get("token");
      if (token) {
        setInvalidLink(true);
        setBootChecked(true);
        return;
      }
      router.replace("/login");
      return;
    }
    setBootChecked(true);
  }, [router, searchParams]);

  const rules = useMemo(() => evaluatePassword(password), [password]);
  const allRulesPassed = rules.every((rule) => rule.passed);
  const passwordsMatch = password.length > 0 && password === confirm;
  const canSubmit = allRulesPassed && passwordsMatch;

  // Audit-finding #9 — surface a soft expiry warning before the JWT
  // dies so the user doesn't type a full password only to have the
  // request bounce them to /login. Buckets:
  //   * "expiring" (< 2 min remaining) → yellow alert above the form
  //     so the user knows to hurry / can save and re-log if needed.
  //   * "expired" (already past) → hard-redirect to /login with a
  //     reason param the login page surfaces ("Tu sesión expiró").
  // ``"healthy"`` means we keep quiet.
  const [sessionState, setSessionState] = useState<
    "healthy" | "expiring" | "expired"
  >("healthy");
  useEffect(() => {
    if (!session) return;
    const expiresAtMs = Date.parse(session.expires_at);
    if (Number.isNaN(expiresAtMs)) return;
    const tick = () => {
      const remaining = expiresAtMs - Date.now();
      if (remaining <= 0) {
        clearAdminSession();
        router.replace("/login?reason=session_expired");
        setSessionState("expired");
      } else if (remaining < 2 * 60 * 1000) {
        setSessionState("expiring");
      } else {
        setSessionState("healthy");
      }
    };
    tick();
    const interval = setInterval(tick, 30_000);
    return () => clearInterval(interval);
  }, [session, router]);

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
        const result = await setPassword(password);
        // CW-AUTH-002 — set-password invalidates the old token (session
        // epoch bump) and returns a freshly-minted one (and a refreshed
        // cookie). Adopt the new token into the in-memory store and persist
        // the new expiry + cleared must-change-password flag, so the
        // post-activation redirect doesn't 401 on a now-stale token.
        setAdminAccessToken(result.access_token);
        writeAdminSession({
          ...stored,
          expires_at: result.expires_at,
          user: {
            ...stored.user,
            ...result.user,
          },
        });
        setSuccess(true);
        // Item 8 v2 — route a freshly-activated client_admin straight
        // to /client/onboarding (their "create client account" page
        // per the spec) instead of /client/dashboard. The first save
        // there sets ``onboarding_completed_at`` and bounces them to
        // the dashboard; subsequent visits to /activate (e.g., forced
        // password rotation later) land on the dashboard directly.
        const dest =
          stored.roles.includes("operations_admin") ||
          stored.roles.includes("platform_admin")
            ? "/admin/dashboard"
            : stored.roles.includes("client_admin") ||
                stored.roles.includes("client_viewer")
              ? "/client/onboarding"
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

  if (!bootChecked) return <ActivateSkeleton />;

  if (invalidLink) {
    return <InvalidLinkState />;
  }

  if (!session) return <ActivateSkeleton />;

  return (
    <main className="min-h-[100dvh] bg-[color:var(--surface-page)]">
      <div className="mx-auto flex min-h-[100dvh] max-w-3xl flex-col gap-8 px-5 py-10 lg:py-14">
        <header className="flex items-center justify-between">
          <Link href="/" aria-label="Volver al inicio">
            <BrandLogo size="md" />
          </Link>
          <button
            type="button"
            onClick={() => {
              // Security fix (CW-AUD-P1-01): clear the temp-password
              // JWT before bouncing to /login. Otherwise /login's boot
              // effect would read the stored session and route the user
              // back into the portal — bypassing the forced password
              // change. Confirmed via the Codex audit in
              // docs/codex-route-workflow-audit/.
              clearAdminSession();
              router.replace("/login");
            }}
            className="inline-flex cursor-pointer items-center gap-1.5 text-xs font-medium text-[color:var(--text-link)] hover:underline"
          >
            <ArrowLeft className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            Cancelar e iniciar sesión de nuevo
          </button>
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

        {sessionState === "expiring" ? (
          <Alert variant="warning">
            <AlertTitle>Tu sesión está por expirar</AlertTitle>
            <AlertDescription>
              Guarda tu nueva contraseña en los próximos dos minutos. Si la
              sesión expira antes de enviar, te llevaremos a iniciar sesión
              de nuevo con tu contraseña temporal y podrás continuar desde
              aquí.
            </AlertDescription>
          </Alert>
        ) : null}

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
                <PasswordInput
                  id="new-password"
                  value={password}
                  onChange={(e) => setPasswordValue(e.target.value)}
                  autoComplete="new-password"
                  autoFocus
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
                htmlFor="confirm-password"
                required
                error={confirmError}
              >
                <PasswordInput
                  id="confirm-password"
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

function InvalidLinkState() {
  return (
    <main className="relative min-h-[100dvh] overflow-hidden bg-[color:var(--surface-page)]">
      <div
        aria-hidden="true"
        className="cw-grid-pattern pointer-events-none absolute inset-0 -z-10"
      />
      <div className="mx-auto flex min-h-[100dvh] max-w-md flex-col gap-8 px-5 py-10 lg:py-14">
        <header className="cw-fade-up flex items-center justify-between">
          <Link href="/" aria-label="Volver al inicio">
            <BrandLogo size="md" poweredBy />
          </Link>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[color:var(--text-link)] hover:underline"
          >
            <ArrowLeft className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            Volver al inicio
          </Link>
        </header>

        <section className="cw-fade-up space-y-6" style={{ animationDelay: "60ms" }}>
          <div className="space-y-2">
            <p className="cw-eyebrow text-[color:var(--text-tertiary)]">
              Enlace de activación
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
              Este enlace ya no es válido.
            </h1>
            <p className="text-[15px] leading-relaxed text-[color:var(--text-secondary)]">
              CheckWise 1.8 reemplazó el flujo anterior. Ahora la activación
              ocurre directamente desde el inicio de sesión: usa el correo y la
              contraseña temporal que te enviamos, y te pediremos cambiarla en
              el siguiente paso.
            </p>
          </div>

          <div className="cw-metadata-strip border-t border-b border-[color:var(--border-subtle)] py-3">
            <div>
              <span className="cw-eyebrow">Motivo</span>
              <span className="text-[12px] text-[color:var(--text-primary)]">
                Formato anterior
              </span>
            </div>
            <div>
              <span className="cw-eyebrow">Siguiente paso</span>
              <span className="text-[12px] text-[color:var(--text-primary)]">
                Iniciar sesión
              </span>
            </div>
          </div>

          <Button asChild size="lg" className="w-full">
            <Link href="/login">
              Ir a iniciar sesión
              <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
            </Link>
          </Button>

          <p className="text-center text-xs text-[color:var(--text-tertiary)]">
            ¿No recibiste credenciales?{" "}
            <a
              href="mailto:soporte@legalshelf.mx"
              className="text-[color:var(--text-link)] hover:underline"
            >
              Contacta soporte.
            </a>
          </p>
        </section>
      </div>
    </main>
  );
}
