"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Icon } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";

/**
 * SettingsNav — the sub-navigation for a per-surface "Configuración"
 * hub (audit Move 2). Each tab is its own route under its own shell, so
 * this is a row of <Link>s (not Radix Tabs, which is single-page); the
 * active tab is picked by pathname.
 *
 * Callers pass fully-formed hrefs. Client hrefs carry ``?client_id=`` —
 * we compare only the path portion so the active state is unaffected by
 * the query string. Role-gating happens in the caller (it knows the
 * session): a ``client_viewer`` simply isn't handed the management tabs
 * it can't use, and the server enforces the boundary regardless.
 */

export type SettingsTab = {
  href: string;
  label: string;
  icon?: Icon;
};

export function SettingsNav({ tabs }: { tabs: readonly SettingsTab[] }) {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Configuración"
      className="-mx-1 mb-1 flex gap-1 overflow-x-auto px-1 pb-1"
    >
      {tabs.map((tab) => {
        const tabPath = tab.href.split("?")[0];
        const isActive = pathname === tabPath;
        const IconComponent = tab.icon;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "inline-flex shrink-0 items-center gap-1.5 rounded-md border px-3 py-1.5 text-[13px] font-medium transition-colors duration-fast",
              isActive
                ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)] shadow-xs"
                : "border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]",
            )}
          >
            {IconComponent ? (
              <IconComponent
                className="h-4 w-4"
                weight={isActive ? "fill" : "bold"}
                aria-hidden="true"
              />
            ) : null}
            <span>{tab.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
