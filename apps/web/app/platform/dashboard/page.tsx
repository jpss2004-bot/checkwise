"use client";

import Link from "next/link";
import {
  ArrowRight,
  Bug,
  ListMagnifyingGlass,
  UserPlus,
} from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Button } from "@/components/ui/button";

import { PlatformShell } from "../_shell";

/**
 * /platform/dashboard — system view (V1).
 *
 * Lightweight landing for the Platform shell. Surfaces the four
 * primary platform actions as cards so an operator who just
 * switched from Operaciones can pick up the IT job they came here
 * to do. Future iterations layer SMTP/WhatsApp health, recent
 * deploy info, and aggregate error counters.
 */

const ACTIONS: {
  href: string;
  title: string;
  description: string;
  icon: typeof UserPlus;
  cta: string;
}[] = [
  {
    href: "/platform/users/new",
    title: "Nuevo usuario",
    description:
      "Da de alta un cliente o proveedor. El sistema genera la contraseña temporal y la manda por correo automáticamente.",
    icon: UserPlus,
    cta: "Crear cuenta",
  },
  {
    href: "/platform/audit-log",
    title: "Audit log",
    description:
      "Trazabilidad completa del sistema: descargas, decisiones del revisor, cambios de perfil, accesos, provisionamiento.",
    icon: ListMagnifyingGlass,
    cta: "Abrir explorador",
  },
  {
    href: "/platform/feedback-reports",
    title: "Reportes de feedback",
    description:
      "Bugs e ideas que los usuarios reportan desde el launcher en la app. Triaje + ack al usuario.",
    icon: Bug,
    cta: "Ver bandeja",
  },
];

export default function PlatformDashboardPage() {
  return (
    <PlatformShell
      title="Resumen de plataforma"
      description="Surfaces internas para el equipo de TI: alta de usuarios, trazabilidad y feedback de la app."
    >
      <div className="grid gap-4 sm:grid-cols-2">
        {ACTIONS.map((action) => {
          const Icon = action.icon;
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
              <p className="text-xs text-[color:var(--text-tertiary)]">
                {action.href}
              </p>
            </Surface>
          );
        })}
      </div>
    </PlatformShell>
  );
}
