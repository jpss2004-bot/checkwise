import Link from "next/link";
import { ArrowLeft, Compass } from "@phosphor-icons/react/dist/ssr";

/**
 * Branded 404 page (Audit fix I-02, 2026-05-18).
 *
 * Replaces the Next.js default "404 / This page could not be found"
 * which renders English copy with no branding and no way back to the
 * product. CheckWise serves Mexican REPSE customers in Spanish, so a
 * default English error page reads as broken even though the route
 * was simply unknown.
 *
 * Intentionally a Server Component with plain anchor tags — the
 * `Button` component pulls Radix UI's createContext and can't render
 * here. A 404 needs no client interactivity.
 */
export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col items-start justify-center gap-6 px-6 py-12">
      <p className="cw-eyebrow text-[color:var(--text-tertiary)]">Error 404</p>
      <h1 className="text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
        No encontramos esta página.
      </h1>
      <p className="max-w-prose text-[15px] leading-relaxed text-[color:var(--text-secondary)]">
        La dirección que abriste no existe, o requiere una sesión que no
        está activa. Si llegaste aquí desde un enlace dentro de CheckWise,
        avísanos para corregirlo.
      </p>
      <div className="flex flex-wrap items-center gap-3 pt-2">
        <Link
          href="/"
          className="inline-flex items-center gap-2 rounded-md bg-[color:var(--surface-action,#0f172a)] px-3 py-2 text-[13px] font-medium text-white hover:opacity-90"
        >
          <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
          Volver al inicio
        </Link>
        <Link
          href="/login"
          className="inline-flex items-center gap-2 rounded-md border border-[color:var(--border-default)] bg-transparent px-3 py-2 text-[13px] font-medium text-[color:var(--text-primary)] hover:bg-[color:var(--surface-hover)]"
        >
          <Compass className="h-4 w-4" weight="bold" aria-hidden="true" />
          Iniciar sesión
        </Link>
      </div>
    </main>
  );
}
