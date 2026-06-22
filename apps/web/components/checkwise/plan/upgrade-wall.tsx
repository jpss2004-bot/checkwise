"use client";

import Link from "next/link";

import { PLAN_CONTACT_HREF } from "@/lib/constants/plan-states";

/**
 * Full-screen demo-expired wall (Phase C3). Shown when a frozen/expired demo
 * client hits the gate (403 trial_expired). Modeled on the shell's
 * consent-error escape hatch: it ALWAYS renders a "Cerrar sesión" button wired
 * to ``onLogout`` so the user is never trapped behind the wall.
 */
export function UpgradeWall({ onLogout }: { onLogout: () => void }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-[color:var(--surface-page)] px-5 text-center">
      <h1 className="text-xl font-semibold text-[color:var(--text-primary)]">
        Tu demo de CheckWise terminó
      </h1>
      <p className="max-w-md text-sm text-[color:var(--text-secondary)]">
        Tu información sigue guardada. Mejora tu plan para reactivar tu portal y
        conservar todo en su lugar — sin perder nada.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <Link
          href={PLAN_CONTACT_HREF}
          className="rounded-md border border-[color:var(--border-brand)] bg-[color:var(--surface-brand)] px-3 py-1.5 text-sm font-medium text-[color:var(--text-inverse)] transition-opacity hover:opacity-90"
        >
          Contactar a CheckWise
        </Link>
        <button
          type="button"
          onClick={onLogout}
          className="rounded-md px-3 py-1.5 text-sm font-medium text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
        >
          Cerrar sesión
        </button>
      </div>
    </div>
  );
}
