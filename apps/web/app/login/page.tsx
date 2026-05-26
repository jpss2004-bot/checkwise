"use client";

import { Suspense, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, SignIn, Warning } from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Skeleton } from "@/components/ui/skeleton";
import { AuthApiError, login } from "@/lib/api/auth";
import {
  clearAdminSession,
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
 *   2. role contains internal_admin → /admin/dashboard
 *   3. role contains reviewer → /admin/reviewer
 *   4. role contains client_admin → /client/dashboard
 *   5. otherwise → /portal/entra-a-tu-espacio
 */
export default function LoginPage() {
  // Next 15 requires any component reading useSearchParams to live
  // under a Suspense boundary so the page can be statically prerendered
  // without bailing out to client-side rendering. The boundary
  // bridges the prerender — the boot effect inside LoginInner still
  // gates on bootChecked, so users won't see the form flash either
  // way.
  return (
    <Suspense fallback={<LoginSkeleton />}>
      <LoginInner />
    </Suspense>
  );
}

function LoginInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextParam = sanitizeNext(searchParams?.get("next"));
  const reasonParam = searchParams?.get("reason");
  const [bootChecked, setBootChecked] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (reasonParam === "portal_session_unavailable") {
      clearAdminSession();
      setError(
        "Tu sesión del portal no pudo iniciar. Vuelve a entrar; si se repite, el API todavía no terminó de desplegarse.",
      );
      setBootChecked(true);
      return;
    }

    const session = readAdminSession();
    if (session) {
      // Security fix (CW-AUD-P1-01): honor must_change_password on
      // the stored session. Previously the boot effect always passed
      // `false`, so a user who had a temp-password JWT and then
      // cancelled out of /activate could re-enter the portal via the
      // boot redirect — bypassing the forced password change.
      const mustChange = session.user?.must_change_password ?? false;
      router.replace(decideDestination(session, mustChange, nextParam));
      return;
    }
    setBootChecked(true);
  }, [router, nextParam, reasonParam]);

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
      router.replace(
        decideDestination(result, result.must_change_password, nextParam),
      );
    } catch (err) {
      if (err instanceof AuthApiError && err.status === 401) {
        setError("Correo o contraseña incorrectos.");
      } else if (err instanceof AuthApiError && err.status === 422) {
        setError("Formato de correo inválido.");
      } else if (err instanceof AuthApiError && err.status === 429) {
        // Audit-finding #6 — distinguish the rate-limit hit from a
        // generic failure. The backend per-(IP, email) bucket caps
        // bad-password floods; telling the user to "intenta de nuevo"
        // is misleading because the next attempt would also 429.
        setError(
          "Demasiados intentos. Espera unos minutos antes de volver a intentar.",
        );
      } else {
        setError("No pudimos iniciar sesión. Intenta de nuevo.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (!bootChecked) return <LoginSkeleton />;

  return (
    <main className="relative min-h-[100dvh] overflow-hidden bg-[color:var(--surface-page)]">
      {/* V2.x ornament: the grid-pattern texture from globals.css.
          Replaces the previous radial-blob gradients which violated
          the locked direction (§"Color strategy — Restrained"). */}
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
            href="/"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[color:var(--text-link)] hover:underline"
          >
            <ArrowLeft className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            Volver al inicio
          </Link>
        </header>

        <section className="cw-fade-up space-y-6" style={{ animationDelay: "60ms" }}>
          <div className="space-y-2">
            <p className="cw-eyebrow text-[color:var(--text-teal)]">
              Iniciar sesión
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
              Bienvenido a CheckWise
            </h1>
            <p className="text-[15px] leading-relaxed text-[color:var(--text-secondary)]">
              Usa tus credenciales (reales o temporales) para entrar. Si recibiste
              acceso temporal, te pediremos cambiar la contraseña en el siguiente
              paso.
            </p>
          </div>

          <form
            onSubmit={onSubmit}
            className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-[var(--shadow-sm)]"
            noValidate
          >
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
                <PasswordInput
                  id="login-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                />
              </Field>
              <div className="-mt-2 flex justify-end">
                <Link
                  href="/forgot-password"
                  className="text-xs font-medium text-[color:var(--text-link)] hover:underline"
                >
                  Olvidé mi contraseña
                </Link>
              </div>
            </div>

            <Button
              type="submit"
              loading={submitting}
              size="lg"
              className="mt-6 w-full"
              // Audit-finding #7 — the form was ``noValidate`` and
              // accepted empty submits, which then surfaced as the
              // backend's 422 "Formato de correo inválido" — confusing
              // because the real problem was nothing was typed. Disable
              // up front so the user gets the obvious "fill the fields"
              // visual signal instead.
              disabled={!email.trim() || !password || submitting}
            >
              {!submitting && (
                <SignIn className="h-4 w-4" weight="bold" aria-hidden="true" />
              )}
              <span>{submitting ? "Verificando…" : "Entrar"}</span>
            </Button>
          </form>

          {/* CheckWise-grounding metadata strip. Addresses the audit
              note that /login feels like generic SaaS chrome — the
              mono labels + Spanish copy declare this is a compliance
              product. */}
          <div className="cw-metadata-strip border-t border-b border-[color:var(--border-subtle)] py-3">
            <div>
              <span className="cw-eyebrow">Plataforma</span>
              <span className="text-[12px] text-[color:var(--text-primary)]">
                Cumplimiento REPSE
              </span>
            </div>
            <div>
              <span className="cw-eyebrow">Operado por</span>
              <span className="text-[12px] text-[color:var(--text-primary)]">
                Legal Shelf · México
              </span>
            </div>
            <div>
              <span className="cw-eyebrow">Revisión</span>
              <span className="text-[12px] text-[color:var(--text-primary)]">
                Humana obligatoria
              </span>
            </div>
          </div>

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
  next: string | null,
): string {
  if (mustChangePassword) return "/activate";
  // Honor the ``next`` query param only when it matches the role the
  // user actually has — a provider should not be able to coerce a
  // login redirect into ``/admin/...`` and a client_admin shouldn't be
  // bounced into ``/portal/...`` by a hand-crafted link. We keep the
  // role's default destination as the fallback.
  const defaultDest = defaultDestination(session);
  if (next && allowedForRoles(next, session.roles)) return next;
  return defaultDest;
}

function defaultDestination(session: { roles: string[] }): string {
  if (session.roles.includes("internal_admin")) return "/admin/dashboard";
  if (session.roles.includes("reviewer")) return "/admin/reviewer";
  if (session.roles.includes("client_admin")) return "/client/dashboard";
  return "/portal/entra-a-tu-espacio";
}

/**
 * Restrict ``next`` to relative paths whose role-prefix matches the
 * authenticated user's roles. Open-redirect protection already lives
 * in ``sanitizeNext``; this is the authorization layer on top.
 */
function allowedForRoles(next: string, roles: string[]): boolean {
  if (next.startsWith("/portal/")) return true;
  if (next.startsWith("/admin/")) {
    return roles.includes("internal_admin") || roles.includes("reviewer");
  }
  if (next.startsWith("/client/")) {
    return roles.includes("client_admin");
  }
  // Non-app routes ("/", "/activate", marketing pages, etc.) are fine
  // for any authenticated user — but those aren't where with-portal-
  // session redirects from, so this branch is mostly defensive.
  return !next.startsWith("/admin/") && !next.startsWith("/client/");
}

/**
 * Treat ``next`` as untrusted input. We only accept relative same-
 * origin paths and reject protocol-relative URLs, absolute URLs,
 * ``javascript:`` schemes, and anything with a backslash that browsers
 * sometimes treat as a scheme separator.
 */
function sanitizeNext(raw: string | null | undefined): string | null {
  if (!raw) return null;
  if (!raw.startsWith("/")) return null;
  if (raw.startsWith("//")) return null;
  if (raw.startsWith("/\\")) return null;
  if (raw.includes("\\")) return null;
  // Schemes like "/javascript:..." would already fail the startsWith
  // check above, but be explicit about colons in the first segment.
  const firstSegmentEnd = raw.indexOf("/", 1);
  const firstSegment = firstSegmentEnd === -1 ? raw : raw.slice(0, firstSegmentEnd);
  if (firstSegment.includes(":")) return null;
  return raw;
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
