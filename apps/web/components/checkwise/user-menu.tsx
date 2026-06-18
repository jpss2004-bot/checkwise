"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowsLeftRight,
  CaretDown,
  Gear,
  IdentificationCard,
  SignOut,
  User,
} from "@phosphor-icons/react";

import { cn } from "@/lib/utils";

/**
 * Junta 2026-05-23 — LinkedIn-style profile dropdown shared across
 * the three shells (portal, client, admin). The trigger renders the
 * user's initials in a circle plus their name on >= sm viewports;
 * the menu opens below-right and exposes the profile link the
 * shell passes in plus "Cerrar sesión".
 *
 * Implementation notes:
 *
 * - No new dependency. Built on plain ``useState`` + outside-click
 *   handling so we don't drag in another radix package for one
 *   menu.
 * - The trigger is a real <button>; the menu items are either
 *   <Link>s (profile) or <button>s (logout) for keyboard support.
 * - Escape closes; click-outside closes. ``role="menu"`` +
 *   ``role="menuitem"`` so screen readers announce it properly.
 * - The shell decides the profile destination (provider →
 *   /portal/entra-a-tu-espacio; client_admin → /client/onboarding;
 *   internal_admin → /admin). Pass ``null`` to hide the row.
 */

export type UserMenuProps = {
  name: string;
  email: string;
  /** Optional roles strip rendered under the name in the menu header. */
  roles?: string[];
  /**
   * Destination for "Mi perfil". Pass ``null`` when no profile
   * surface exists yet for this role (e.g. internal_admin).
   */
  profileHref: string | null;
  /** Label for the profile link. Defaults to "Mi perfil". */
  profileLabel?: string;
  /**
   * Extra settings rows below the profile link (e.g. the client shell's
   * "Preferencias de notificaciones") so settings are reachable from the
   * account menu, not just from inside one page (audit P3.19).
   */
  secondaryLinks?: ReadonlyArray<{ href: string; label: string }>;
  /**
   * Shell switcher — when set, renders a "Cambiar a X" row above
   * the sign-out action. Used by the AdminShell ↔ PlatformShell
   * pair so the same internal_admin can flip between the
   * compliance and IT views without leaving the page. ``null``
   * hides the row entirely.
   */
  shellSwitch?: {
    href: string;
    label: string;
  } | null;
  onSignOut: () => void;
  /** Optional className applied to the trigger button. */
  className?: string;
};

export function UserMenu({
  name,
  email,
  roles,
  profileHref,
  profileLabel = "Mi perfil",
  secondaryLinks,
  shellSwitch,
  onSignOut,
  className,
}: UserMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  // Outside-click + Escape close the menu. Same handler covers both
  // surfaces because the menu is small and the listeners are cheap.
  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const initials = computeInitials(name) || computeInitials(email);

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={open ? "Cerrar menú de cuenta" : "Abrir menú de cuenta"}
        className={cn(
          "inline-flex items-center gap-2 rounded-full border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-1.5 py-1 text-xs font-medium text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40",
        )}
      >
        <span
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)] text-[10px] font-semibold uppercase text-[color:var(--text-brand)]"
          aria-hidden="true"
        >
          {initials || <User className="h-3.5 w-3.5" weight="bold" />}
        </span>
        <span className="hidden max-w-[140px] truncate sm:inline">{name}</span>
        <CaretDown
          className={cn(
            "hidden h-3 w-3 shrink-0 text-[color:var(--text-tertiary)] transition-transform sm:block",
            open && "rotate-180",
          )}
          weight="bold"
          aria-hidden="true"
        />
      </button>

      {open ? (
        <div
          role="menu"
          aria-label="Menú de cuenta"
          className="absolute right-0 z-40 mt-2 w-64 origin-top-right overflow-hidden rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-lg ring-1 ring-black/5"
        >
          <div className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-4 py-3">
            <p className="truncate text-sm font-semibold text-[color:var(--text-primary)]">
              {name}
            </p>
            <p className="mt-0.5 truncate font-mono text-[11px] text-[color:var(--text-tertiary)]">
              {email}
            </p>
            {roles && roles.length > 0 ? (
              <p className="mt-1 truncate text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                {roles.map(humanizeRole).join(" · ")}
              </p>
            ) : null}
          </div>
          <ul className="py-1">
            {profileHref ? (
              <li role="none">
                <Link
                  href={profileHref}
                  role="menuitem"
                  className="flex items-center gap-2 px-4 py-2 text-sm text-[color:var(--text-primary)] hover:bg-[color:var(--surface-hover)]"
                  onClick={() => setOpen(false)}
                >
                  <IdentificationCard
                    className="h-4 w-4 text-[color:var(--text-tertiary)]"
                    weight="bold"
                    aria-hidden="true"
                  />
                  {profileLabel}
                </Link>
              </li>
            ) : null}
            {secondaryLinks?.map((link) => (
              <li role="none" key={link.href}>
                <Link
                  href={link.href}
                  role="menuitem"
                  className="flex items-center gap-2 px-4 py-2 text-sm text-[color:var(--text-primary)] hover:bg-[color:var(--surface-hover)]"
                  onClick={() => setOpen(false)}
                >
                  <Gear
                    className="h-4 w-4 text-[color:var(--text-tertiary)]"
                    weight="bold"
                    aria-hidden="true"
                  />
                  {link.label}
                </Link>
              </li>
            ))}
            {shellSwitch ? (
              <li role="none">
                <Link
                  href={shellSwitch.href}
                  role="menuitem"
                  className="flex items-center gap-2 px-4 py-2 text-sm text-[color:var(--text-primary)] hover:bg-[color:var(--surface-hover)]"
                  onClick={() => setOpen(false)}
                >
                  <ArrowsLeftRight
                    className="h-4 w-4 text-[color:var(--text-tertiary)]"
                    weight="bold"
                    aria-hidden="true"
                  />
                  {shellSwitch.label}
                </Link>
              </li>
            ) : null}
            <li role="none">
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  onSignOut();
                }}
                className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-[color:var(--text-primary)] hover:bg-[color:var(--surface-hover)]"
              >
                <SignOut
                  className="h-4 w-4 text-[color:var(--text-tertiary)]"
                  weight="bold"
                  aria-hidden="true"
                />
                Cerrar sesión
              </button>
            </li>
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function computeInitials(value: string | undefined): string {
  if (!value) return "";
  const trimmed = value.trim();
  if (!trimmed) return "";
  const tokens = trimmed
    .replace(/[@._-]+/g, " ")
    .split(/\s+/)
    .filter(Boolean);
  if (tokens.length === 0) return "";
  const first = tokens[0]?.[0] ?? "";
  const second = tokens.length > 1 ? tokens[tokens.length - 1][0] : "";
  return (first + second).toUpperCase();
}

function humanizeRole(role: string): string {
  // Display-friendly role labels. Mirrors the existing copy on the
  // shells ("internal admin", "reviewer", "client admin") but keeps
  // the values stable for any future role-name change.
  return role.replace(/_/g, " ");
}
