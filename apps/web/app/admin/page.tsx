"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Books,
  CalendarBlank,
  ChartLineUp,
  ClipboardText,
  IdentificationCard,
  ListMagnifyingGlass,
  Storefront,
  type Icon,
} from "@phosphor-icons/react";

import { AdminShell } from "./_shell";
import {
  type AdminSession,
  readAdminSession,
} from "@/lib/session/admin";

const REVIEWER_ROLES = ["platform_admin", "operations_admin"] as const;

type Surface = {
  href: string;
  icon: Icon;
  label: string;
  helper: string;
};

/** Surfaces every internal_admin can open. Mirrors the shell nav so the
 *  hub doubles as a guided launcher with one-line context per surface. */
const ADMIN_SURFACES: Surface[] = [
  { href: "/admin/dashboard", icon: ChartLineUp, label: "Resumen operativo", helper: "Conteos del día y prioridades." },
  { href: "/admin/clients", icon: IdentificationCard, label: "Clientes", helper: "Alta, edición y estatus." },
  { href: "/admin/vendors", icon: Storefront, label: "Proveedores", helper: "Registro, contacto y persona." },
  { href: "/admin/requirements", icon: Books, label: "Requisitos", helper: "Catálogo regulatorio REPSE." },
  { href: "/admin/calendar", icon: CalendarBlank, label: "Calendario", helper: "Periodos y obligaciones." },
  { href: "/admin/reports", icon: ChartLineUp, label: "Reportes", helper: "Genera y consulta reportes." },
  { href: "/platform/audit-log", icon: ListMagnifyingGlass, label: "Bitácora de auditoría", helper: "Eventos del sistema." },
];

export default function AdminHomePage() {
  const router = useRouter();
  const [session, setSession] = useState<AdminSession | null>(null);

  useEffect(() => {
    const current = readAdminSession();
    if (!current) {
      router.replace("/login");
      return;
    }
    setSession(current);
  }, [router]);

  if (!session) return null;

  const canReview = session.roles.some((r) =>
    (REVIEWER_ROLES as readonly string[]).includes(r),
  );
  const isAdmin =
    session.roles.includes("platform_admin") ||
    session.roles.includes("operations_admin");

  return (
    <AdminShell
      title={`Hola, ${firstName(session.user.full_name)}`}
      description="Este es tu centro de operaciones. Elige una superficie para empezar; cada cambio queda firmado en la bitácora de auditoría."
    >
      <div className="space-y-5">
        {canReview ? (
          <Link
            href="/admin/reviewer"
            className="cw-fade-up flex items-start gap-3 rounded-lg border border-[color:var(--border-brand)] bg-[color:var(--surface-brand-muted)] p-5 transition-colors hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40"
          >
            <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]">
              <ClipboardText className="h-4 w-4" weight="bold" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="flex items-center justify-between gap-2 text-sm font-semibold text-[color:var(--text-primary)]">
                Documentos por revisar
                <ArrowRight className="h-4 w-4 text-[color:var(--text-brand)]" weight="bold" aria-hidden="true" />
              </p>
              <p className="mt-0.5 text-xs text-[color:var(--text-secondary)]">
                Cola de documentos esperando una decisión humana: aprobar,
                solicitar corrección, pedir aclaración o aprobar con nota legal.
              </p>
            </div>
          </Link>
        ) : null}

        {isAdmin ? (
          <section
            aria-label="Superficies operativas"
            className="cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
          >
            <header className="border-b border-[color:var(--border-subtle)] px-5 py-3">
              <p className="cw-eyebrow">Superficies operativas</p>
              <p className="text-sm font-semibold text-[color:var(--text-primary)]">
                Gestión de clientes, proveedores y cumplimiento
              </p>
            </header>
            <ul className="grid gap-px bg-[color:var(--border-subtle)] sm:grid-cols-2">
              {ADMIN_SURFACES.map((item) => (
                <li key={item.href} className="bg-[color:var(--surface-raised)]">
                  <Link
                    href={item.href}
                    className="flex items-center gap-3 px-5 py-3.5 transition-colors hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--border-focus)]/40"
                  >
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]">
                      <item.icon className="h-4 w-4" weight="bold" aria-hidden="true" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-semibold text-[color:var(--text-primary)]">
                        {item.label}
                      </p>
                      <p className="text-[11px] text-[color:var(--text-tertiary)]">
                        {item.helper}
                      </p>
                    </div>
                    <ArrowRight
                      className="h-4 w-4 shrink-0 text-[color:var(--text-tertiary)]"
                      weight="bold"
                      aria-hidden="true"
                    />
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {!canReview && !isAdmin ? (
          <div className="cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 text-sm text-[color:var(--text-secondary)]">
            Tu cuenta no tiene superficies de operación asignadas todavía.
            Contacta al administrador interno para que habilite tu rol.
          </div>
        ) : null}
      </div>
    </AdminShell>
  );
}

function firstName(fullName: string): string {
  return fullName.split(" ")[0] ?? fullName;
}
