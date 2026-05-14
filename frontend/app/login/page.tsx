"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ShieldCheck } from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { ProviderAccessForm } from "@/components/checkwise/portal/provider-access-form";
import { Skeleton } from "@/components/ui/skeleton";
import { readPortalSession } from "@/lib/session/portal";

/**
 * Login / access page.
 *
 * This was previously the home route; CheckWise 1.5 reframes `/` as a
 * public marketing page and moves the credential-based entry here.
 *
 * Role-based UX (Phase 2 of CheckWise 1.5):
 *  - Provider / Cliente paths share this access form (current backend
 *    contract uses opaque workspace tokens — no real password yet).
 *  - Admin path lives at /admin/login (kept untouched in this phase).
 *
 * TODO[backend-integration]: Replace the form with a real email +
 * password login once the backend exposes user-level credentials.
 */
export default function LoginPage() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const existing = readPortalSession();
    if (existing) {
      router.replace("/portal/onboarding");
      return;
    }
    setChecked(true);
  }, [router]);

  if (!checked) {
    return <LoginSkeleton />;
  }

  return (
    <main className="relative min-h-[100dvh] overflow-hidden">
      <BackgroundOrnaments />

      <div className="relative mx-auto flex min-h-[100dvh] max-w-3xl flex-col gap-8 px-5 py-10 lg:py-14">
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

        <section
          className="cw-fade-up rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-md sm:p-8"
          style={{ animationDelay: "60ms" }}
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
              <h1 className="text-xl font-semibold text-[color:var(--text-primary)]">
                Iniciar sesión en CheckWise
              </h1>
              <p className="text-[13px] text-[color:var(--text-secondary)]">
                Ingresa al portal de cumplimiento documental REPSE.
              </p>
            </div>
          </div>
          <ProviderAccessForm />
        </section>

        <p className="text-center text-xs text-[color:var(--text-tertiary)]">
          ¿No tienes acceso aún?{" "}
          <a
            href="mailto:soporte@legalshelf.mx"
            className="text-[color:var(--text-link)] hover:underline"
          >
            Pídelo a tu cliente o contacta soporte.
          </a>
        </p>
      </div>
    </main>
  );
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
    <main className="mx-auto max-w-3xl px-5 py-16">
      <Skeleton className="h-8 w-32" />
      <Skeleton className="mt-12 h-[480px] w-full rounded-xl" />
    </main>
  );
}
