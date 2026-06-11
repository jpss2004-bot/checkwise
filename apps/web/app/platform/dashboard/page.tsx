"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bug,
  ListMagnifyingGlass,
  UsersThree,
} from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { PlatformShell } from "../_shell";
import {
  listAuditLog,
  listFeedbackReports,
  listUsers,
} from "@/lib/api/admin";

/**
 * /platform/dashboard — system view (V2).
 *
 * Lightweight landing for the Platform shell. Each card now carries a
 * live count (V1 showed the raw route path) fetched in parallel with
 * ``limit: 1`` — the backend returns the real filtered ``total``
 * regardless of page size, so these are cheap. Individual failures
 * degrade to "—" without blocking the other cards. Future iterations
 * layer SMTP/WhatsApp health, recent deploy info, and aggregate error
 * counters.
 */

type CardKey = "users" | "audit" | "feedback";

const ACTIONS: {
  key: CardKey;
  href: string;
  title: string;
  description: string;
  icon: typeof UsersThree;
  cta: string;
  /** Spanish count line, e.g. "12 usuarios" / "3 nuevos". */
  countLabel: (n: number) => string;
}[] = [
  {
    key: "users",
    href: "/platform/users",
    title: "Usuarios",
    description:
      "Todas las cuentas del sistema: restablece contraseñas, desactiva o reactiva accesos y da de alta usuarios nuevos.",
    icon: UsersThree,
    cta: "Ver usuarios",
    countLabel: (n) => `${n.toLocaleString("es-MX")} ${n === 1 ? "usuario" : "usuarios"}`,
  },
  {
    key: "audit",
    href: "/platform/audit-log",
    title: "Audit log",
    description:
      "Trazabilidad completa del sistema: descargas, decisiones del revisor, cambios de perfil, accesos, provisionamiento.",
    icon: ListMagnifyingGlass,
    cta: "Abrir explorador",
    countLabel: (n) => `${n.toLocaleString("es-MX")} ${n === 1 ? "evento" : "eventos"}`,
  },
  {
    key: "feedback",
    href: "/platform/feedback-reports",
    title: "Reportes de feedback",
    description:
      "Bugs e ideas que los usuarios reportan desde el launcher en la app. Triaje + ack al usuario.",
    icon: Bug,
    cta: "Ver bandeja",
    countLabel: (n) => `${n.toLocaleString("es-MX")} ${n === 1 ? "nuevo" : "nuevos"}`,
  },
];

/** null = the fetch failed (render "—"); undefined = still loading. */
type Counts = Record<CardKey, number | null | undefined>;

export default function PlatformDashboardPage() {
  const [counts, setCounts] = useState<Counts>({
    users: undefined,
    audit: undefined,
    feedback: undefined,
  });

  useEffect(() => {
    let cancelled = false;
    // ``limit: 1`` keeps the payloads tiny — only ``total`` matters.
    Promise.allSettled([
      listUsers({ limit: 1 }),
      listAuditLog({ limit: 1 }),
      listFeedbackReports({ status: "new", limit: 1 }),
    ]).then(([users, audit, feedback]) => {
      if (cancelled) return;
      setCounts({
        users: users.status === "fulfilled" ? users.value.total : null,
        audit: audit.status === "fulfilled" ? audit.value.total : null,
        feedback:
          feedback.status === "fulfilled" ? feedback.value.total : null,
      });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <PlatformShell
      title="Resumen de plataforma"
      description="Surfaces internas para el equipo de TI: gestión de usuarios, trazabilidad y feedback de la app."
    >
      <div className="grid gap-4 sm:grid-cols-2">
        {ACTIONS.map((action) => {
          const Icon = action.icon;
          const count = counts[action.key];
          return (
            <Surface
              key={action.href}
              title={action.title}
              icon={Icon}
              description={action.description}
              actions={
                <Button asChild size="sm">
                  <Link href={action.href}>
                    {action.cta}
                    <ArrowRight
                      className="h-3.5 w-3.5"
                      weight="bold"
                      aria-hidden="true"
                    />
                  </Link>
                </Button>
              }
            >
              {count === undefined ? (
                <Skeleton className="h-5 w-24" />
              ) : count === null ? (
                <p className="text-sm text-[color:var(--text-tertiary)]">—</p>
              ) : (
                <p
                  className={
                    count === 0
                      ? "text-sm text-[color:var(--text-tertiary)]"
                      : "text-sm font-semibold tabular-nums text-[color:var(--text-primary)]"
                  }
                >
                  {action.countLabel(count)}
                </p>
              )}
            </Surface>
          );
        })}
      </div>
    </PlatformShell>
  );
}
