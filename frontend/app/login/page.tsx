"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  CircleNotch,
  ShieldCheck,
  SignIn,
  Warning,
} from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { AuthApiError, login } from "@/lib/api/auth";
import {
  readAdminSession,
  writeAdminSession,
  type AdminSession,
} from "@/lib/session/admin";

/**
 * Single login surface.
 *
 * CheckWise 1.8 collapsed the old 3-role picker into a single
 * email + password form. Anonymous workspace creation has been
 * removed — every user (admin, reviewer, provider) authenticates
 * here. Routing happens after the response based on:
 *
 *   1. ``must_change_password`` → /activate (forced first-login)
 *   2. role contains internal_admin or reviewer → /admin/reviewer
 *   3. otherwise → /portal/entra-a-tu-espacio
 */
export default function LoginPage() {
  const router = useRouter();
  const [bootChecked, setBootChecked] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const session = readAdminSession();
    if (session) {
      router.replace(decideDestination(session, false));
      return;
    }
    setBootChecked(true);
  }, [router]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await login(email, password);
      // Always store the session so /activate or /portal/* can read the JWT.
      writeAdminSession({
        access_token: result.access_token,
        expires_at: result.expires_at,
        user: result.user,
        roles: result.roles,
        organization_ids: result.organization_ids,
      });
      router.replace(decideDestination(result, result.must_change_password));
    } catch (err) {
      if (err instanceof AuthApiError && err.status === 401) {
        setError("Correo o contraseña incorrectos.");
      } else if (err instanceof AuthApiError && err.status === 422) {
        setError("Formato de correo inválido.");
      } else {
        setError("No pudimos iniciar sesión. Intenta de nuevo.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (!bootChecked) return <LoginSkeleton />;

  return (
    <main className="relative min-h-[100dvh] overflow-hidden">
      <BackgroundOrnaments />
      <div className="relative mx-auto flex min-h-[100dvh] max-w-md flex-col gap-8 px-5 py-10 lg:py-14">
        <header className="flex items-center justify-between cw-fade-up">
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
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-teal)]">
              Iniciar sesión
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
              Bienvenido a CheckWise
            </h1>
            <p className="text-[15px] text-[color:var(--text-secondary)]">
              Usa tus credenciales (reales o temporales) para entrar.
            </p>
          </div>

          <form
            onSubmit={onSubmit}
            className="rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-md sm:p-8"
            noValidate
          >
            <div className="mb-5 flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)]">
                <ShieldCheck
                  className="h-5 w-5 text-[color:var(--text-brand)]"
                  weight="duotone"
                  aria-hidden="true"
                />
              </span>
              <div>
                <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
                  Acceso a CheckWise
                </h2>
                <p className="text-xs text-[color:var(--text-secondary)]">
                  Si recibiste credenciales temporales, te pediremos cambiar la
                  contraseña en el siguiente paso.
                </p>
              </div>
            </div>

            {error && (
              <Alert variant="error" className="mb-5">
                <AlertTitle className="flex items-center gap-2">
                  <Warning className="h-4 w-4" weight="bold" aria-hidden="true" />
                  No pudimos iniciar sesión
                </AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="grid gap-4">
              <Field label="Correo electrónico" htmlFor="login-email" required>
                <Input
                  id="login-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  autoFocus
                  placeholder="tu.correo@empresa.com"
                />
              </Field>

              <Field label="Contraseña" htmlFor="login-password" required>
                <Input
                  id="login-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                />
              </Field>
            </div>

            <Button
              type="submit"
              loading={submitting}
              size="lg"
              className="mt-6 w-full"
            >
              {submitting ? (
                <CircleNotch className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <SignIn className="h-4 w-4" weight="bold" aria-hidden="true" />
              )}
              <span>{submitting ? "Verificando…" : "Entrar"}</span>
            </Button>
          </form>

          <p className="text-center text-xs text-[color:var(--text-tertiary)]">
            ¿No tienes acceso aún?{" "}
            <a
              href="mailto:soporte@legalshelf.mx"
              className="text-[color:var(--text-link)] hover:underline"
            >
              Pídelo a tu cliente o contacta soporte.
            </a>
          </p>
        </section>
      </div>
    </main>
  );
}

function decideDestination(
  session: { roles: string[] },
  mustChangePassword: boolean,
): string {
  if (mustChangePassword) return "/activate";
  if (
    session.roles.includes("internal_admin") ||
    session.roles.includes("reviewer")
  ) {
    return "/admin/reviewer";
  }
  return "/portal/entra-a-tu-espacio";
}

function BackgroundOrnaments() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute -top-32 -left-24 h-[480px] w-[480px] rounded-full opacity-[0.18] blur-3xl"
        style={{
          background:
            "radial-gradient(circle, hsl(var(--brand-navy)/0.55) 0%, transparent 70%)",
        }}
      />
      <div
        className="absolute -bottom-40 -right-24 h-[520px] w-[520px] rounded-full opacity-[0.14] blur-3xl"
        style={{
          background:
            "radial-gradient(circle, hsl(var(--brand-teal)/0.6) 0%, transparent 70%)",
        }}
      />
    </div>
  );
}

function LoginSkeleton() {
  return (
    <main className="mx-auto max-w-md px-5 py-16">
      <Skeleton className="h-8 w-32" />
      <Skeleton className="mt-6 h-[420px] w-full rounded-xl" />
    </main>
  );
}

// Re-export the AdminSession type so any direct importers stay typed.
export type { AdminSession };
