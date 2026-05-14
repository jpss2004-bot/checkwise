"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  CalendarBlank,
  ChartLineUp,
  ClipboardText,
  Files,
  House,
  IdentificationCard,
  SignOut,
  type Icon,
} from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { clearPortalSession, type PortalSession } from "@/lib/session/portal";

type Props = {
  session: PortalSession;
  onboardingPct?: number | null;
};

interface NavLink {
  href: string;
  label: string;
  icon: Icon;
}

const NAV_LINKS: NavLink[] = [
  { href: "/portal/dashboard", label: "Dashboard", icon: House },
  { href: "/portal/onboarding", label: "Expediente", icon: ClipboardText },
  { href: "/portal/calendar", label: "Calendario", icon: CalendarBlank },
  { href: "/portal/reports", label: "Reportes", icon: ChartLineUp },
  { href: "/portal/upload", label: "Subir documento", icon: Files },
  { href: "/portal/entra-a-tu-espacio", label: "Mi espacio", icon: IdentificationCard },
];

export function ProviderContextBar({ session, onboardingPct }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const pct =
    typeof onboardingPct === "number" && Number.isFinite(onboardingPct)
      ? Math.min(100, Math.max(0, Math.round(onboardingPct)))
      : null;
  const isComplete = pct !== null && pct >= 100;

  return (
    <header className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-5 py-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-4">
          <Link href="/portal/dashboard" aria-label="CheckWise dashboard">
            <BrandLogo variant="compact" size="md" />
          </Link>
          <div className="min-w-0 border-l border-[color:var(--border-subtle)] pl-4">
            <p className="text-xs text-[color:var(--text-tertiary)]">Sesión proveedor</p>
            <p className="truncate text-sm font-semibold text-[color:var(--text-primary)]">
              {session.vendor_name}{" "}
              <span className="font-mono text-[color:var(--text-secondary)]">
                · {session.vendor_rfc}
              </span>
            </p>
            <p className="truncate text-xs text-[color:var(--text-secondary)]">
              Cliente: {session.client_name}
              {session.filial_name ? ` / ${session.filial_name}` : ""}
              {session.contract_reference ? ` · ${session.contract_reference}` : ""}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {pct !== null ? (
            <div
              className={cn(
                "flex items-center gap-2 rounded-full border px-3 py-1 text-xs",
                isComplete
                  ? "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]"
                  : "border-[color:var(--border-default)] bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]",
              )}
              role="status"
              aria-label={`Expediente al ${pct} por ciento`}
            >
              <ClipboardText className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="font-medium">Expediente</span>
              <span
                aria-hidden="true"
                className="h-1.5 w-12 overflow-hidden rounded-full bg-white/60"
              >
                <span
                  className={cn(
                    "block h-full rounded-full transition-[width] duration-500 ease-out",
                    isComplete
                      ? "bg-[color:var(--status-success-text)]"
                      : "bg-[color:var(--text-brand)]",
                  )}
                  style={{ width: `${pct}%` }}
                />
              </span>
              <span className="font-mono tabular-nums font-semibold">{pct}%</span>
            </div>
          ) : null}
          <Badge variant="outline">
            {session.persona_type === "moral" ? "Persona Moral" : "Persona Física"}
          </Badge>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              clearPortalSession();
              router.push("/");
            }}
          >
            <SignOut className="h-4 w-4" aria-hidden="true" />
            Cerrar sesión demo
          </Button>
        </div>
      </div>

      <nav
        aria-label="Portal proveedor"
        className="mx-auto flex max-w-7xl items-center gap-1 overflow-x-auto px-5 pb-3"
      >
        {NAV_LINKS.map(({ href, label, icon: IconComponent }) => {
          const isActive = pathname === href || pathname?.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12px] font-medium transition-colors duration-fast",
                isActive
                  ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                  : "border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-[color:var(--text-secondary)] hover:border-[color:var(--border-strong)] hover:text-[color:var(--text-primary)]",
              )}
            >
              <IconComponent className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
