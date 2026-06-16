import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowLeft } from "@phosphor-icons/react/dist/ssr";

import { V2Footer } from "@/components/marketing/v2/footer";
import { V2Nav } from "@/components/marketing/v2/nav";

/**
 * Shared shell for the three legal documents under ``/legal/*``.
 *
 * These are public pages reached from the footer, so they carry the full
 * marketing header (logo → home) and footer, and the back link returns to
 * the landing — not the portal login. (The earlier "Regresar" sent visitors
 * to /portal/entra-a-tu-espacio, which read as "regresar te lleva a iniciar
 * sesión".)
 *
 * The ``version`` prop is the same canonical string the backend stores on
 * the workspace row at acceptance time so a forensic reader can recreate the
 * exact copy the provider accepted on any given date.
 */
export function LegalDocShell({
  eyebrow,
  title,
  effectiveDate,
  version,
  children,
}: {
  eyebrow: string;
  title: string;
  effectiveDate: string;
  version: string;
  children: ReactNode;
}) {
  return (
    <>
      <V2Nav />
      <main className="bg-[color:var(--surface-page)]">
        <div className="mx-auto flex max-w-3xl flex-col gap-8 px-5 py-12 lg:py-16">
          <Link
            href="/"
            className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]"
          >
            <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
            Volver al inicio
          </Link>

          <header className="flex flex-col gap-2">
            <p className="font-mono text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              {eyebrow}
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
              {title}
            </h1>
            <p className="text-sm text-[color:var(--text-secondary)]">
              Vigente desde el {effectiveDate} · Versión{" "}
              <code className="font-mono">{version}</code>
            </p>
          </header>

          <article className="legal-doc space-y-6 text-[15px] leading-relaxed text-[color:var(--text-primary)]">
            {children}
          </article>

          <footer className="mt-4 border-t border-[color:var(--border-subtle)] pt-6 text-xs text-[color:var(--text-tertiary)]">
            <p>
              ¿Dudas sobre este documento? Escríbenos a{" "}
              <a
                href="mailto:legal@legalshelf.mx"
                className="font-medium text-[color:var(--text-brand)] hover:underline"
              >
                legal@legalshelf.mx
              </a>
              . LegalShelf opera CheckWise como encargado del tratamiento de
              datos personales por cuenta del responsable, conforme a la Ley
              Federal de Protección de Datos Personales en Posesión de los
              Particulares.
            </p>
          </footer>
        </div>
      </main>
      <V2Footer />
    </>
  );
}

export function LegalSection({
  heading,
  children,
}: {
  heading: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold tracking-tight text-[color:var(--text-primary)]">
        {heading}
      </h2>
      <div className="space-y-3 text-[color:var(--text-secondary)]">
        {children}
      </div>
    </section>
  );
}
