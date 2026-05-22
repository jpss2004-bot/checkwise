import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowLeft, WarningCircle } from "@phosphor-icons/react/dist/ssr";

/**
 * Shared shell for the three legal documents under ``/legal/*``.
 *
 * Phase 1 / Slice 1A — these documents ship as DRAFTS pending review
 * by Paco/Beko. The shell renders a prominent banner so neither the
 * provider nor an auditor can mistake the content for final legal
 * copy. The ``version`` prop is the same canonical string the backend
 * stores on the workspace row at acceptance time.
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
    <main className="bg-[color:var(--surface-page)]">
      <div className="mx-auto flex max-w-3xl flex-col gap-8 px-5 py-12 lg:py-16">
        <Link
          href="/portal/entra-a-tu-espacio"
          className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]"
        >
          <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
          Regresar
        </Link>

        <div
          role="note"
          className="flex items-start gap-3 rounded-md border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] px-4 py-3"
        >
          <WarningCircle
            className="mt-0.5 h-5 w-5 shrink-0 text-[color:var(--status-warning-text)]"
            weight="fill"
            aria-hidden="true"
          />
          <div className="text-sm text-[color:var(--text-primary)]">
            <p className="font-semibold">
              BORRADOR — pendiente de revisión legal
            </p>
            <p className="mt-1 text-[color:var(--text-secondary)]">
              Este documento se publicó como referencia inicial. La
              versión definitiva debe ser validada por el equipo legal
              de LegalShelf antes de operar en producción. La versión
              que estás aceptando es <code className="font-mono">{version}</code>.
            </p>
          </div>
        </div>

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
            . LegalShelf opera CheckWise como responsable del tratamiento
            de datos en cumplimiento con la Ley Federal de Protección de
            Datos Personales en Posesión de los Particulares (LFPDPPP).
          </p>
        </footer>
      </div>
    </main>
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
