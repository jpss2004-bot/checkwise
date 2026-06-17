"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bug,
  ListMagnifyingGlass,
  UsersThree,
} from "@phosphor-icons/react";

import { Skeleton } from "@/components/ui/skeleton";

import { PlatformShell } from "../_shell";
import {
  listAuditLog,
  listFeedbackReports,
  listUsers,
} from "@/lib/api/admin";

/**
 * /platform/dashboard — system overview (V3).
 *
 * V2 rendered three full launcher cards (icon + description + a CTA button)
 * that simply re-linked to the sidebar destinations — a home that duplicated
 * the nav (P3-11), the same anti-pattern /admin/dashboard already removed.
 * V3 keeps the genuinely useful part (live counts) as a compact stat strip:
 * each tile leads with the number and links through to its surface, but the
 * redundant descriptions and "Ver …" buttons are gone. Counts fetch in
 * parallel with ``limit: 1`` (only ``total`` matters) and degrade to "—"
 * independently. Future iterations layer real IT telemetry here — SMTP /
 * WhatsApp / R2 health, cron + job status, error counters, storage — which is
 * what this section should eventually own.
 */

type CardKey = "users" | "audit" | "feedback";

const STATS: {
  key: CardKey;
  href: string;
  label: string;
  icon: typeof UsersThree;
}[] = [
  {
    key: "users",
    href: "/platform/users",
    label: "Usuarios del sistema",
    icon: UsersThree,
  },
  {
    key: "audit",
    href: "/platform/audit-log",
    label: "Eventos en bitácora",
    icon: ListMagnifyingGlass,
  },
  {
    key: "feedback",
    href: "/platform/feedback-reports",
    label: "Feedback sin triage",
    icon: Bug,
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
      description="Vista de sistema para el equipo de TI. La navegación vive en la barra lateral; aquí solo el estado de un vistazo."
    >
      <div className="grid gap-3 sm:grid-cols-3">
        {STATS.map((stat) => {
          const Icon = stat.icon;
          const count = counts[stat.key];
          return (
            <Link
              key={stat.href}
              href={stat.href}
              className="group flex items-center gap-3 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-4 py-3 shadow-[var(--shadow-sm)] transition-colors hover:bg-[color:var(--surface-hover)]"
            >
              <span
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]"
                aria-hidden="true"
              >
                <Icon className="h-4 w-4" weight="bold" />
              </span>
              <div className="min-w-0">
                {count === undefined ? (
                  <Skeleton className="h-6 w-16" />
                ) : (
                  <p
                    className={
                      count
                        ? "text-[20px] font-semibold tabular-nums leading-none text-[color:var(--text-primary)]"
                        : "text-[20px] font-semibold tabular-nums leading-none text-[color:var(--text-tertiary)]"
                    }
                  >
                    {count === null ? "—" : count.toLocaleString("es-MX")}
                  </p>
                )}
                <p className="mt-1 truncate text-[11px] text-[color:var(--text-secondary)]">
                  {stat.label}
                </p>
              </div>
              <ArrowRight
                className="ml-auto h-4 w-4 shrink-0 text-[color:var(--text-tertiary)] opacity-0 transition-opacity group-hover:opacity-100"
                weight="bold"
                aria-hidden="true"
              />
            </Link>
          );
        })}
      </div>
    </PlatformShell>
  );
}
