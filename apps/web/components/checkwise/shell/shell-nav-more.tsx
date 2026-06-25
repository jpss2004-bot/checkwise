"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { CaretDown, type Icon } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";

/**
 * ShellNavMore — the "Más" overflow for a console shell's primary nav
 * (audit Move 3 / F10). Collapses occasional/administrative destinations
 * into one labeled, chip-styled dropdown so the day-to-day row stays
 * under ~7 items.
 *
 * Why not ``components/ui/overflow-menu``? That one is an icon-only
 * ``⋮`` trigger with no active state — fine for a Reportes header, wrong
 * for a nav, where the control must (a) read as "Más" and (b) light up
 * when one of its hidden destinations is the current page. The a11y
 * wiring (pointerdown-outside + Esc close, ``role="menu"``) mirrors that
 * primitive. Callers pass fully-formed hrefs (client shells wrap them
 * with ``withClientId``); active state ignores the query string.
 */

export type ShellNavMoreItem = {
  href: string;
  label: string;
  icon: Icon;
};

export function ShellNavMore({
  items,
  label = "Más",
}: {
  items: readonly ShellNavMoreItem[];
  label?: string;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  // Close the menu on route change so it never lingers open across nav.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (
        rootRef.current &&
        event.target instanceof Node &&
        rootRef.current.contains(event.target)
      ) {
        return;
      }
      setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (items.length === 0) return null;

  const isItemActive = (href: string) => {
    const path = href.split("?")[0];
    return pathname === path || pathname?.startsWith(path + "/");
  };
  const groupActive = items.some((item) => isItemActive(item.href));

  return (
    <div ref={rootRef} className="relative inline-block shrink-0">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "inline-flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-[12px] font-medium transition-colors duration-fast",
          groupActive
            ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)] shadow-xs"
            : "border-transparent bg-transparent text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]",
        )}
      >
        <span>{label}</span>
        <CaretDown
          className={cn("h-3 w-3 transition-transform", open && "rotate-180")}
          weight="bold"
          aria-hidden="true"
        />
      </button>
      {open ? (
        <ul
          role="menu"
          aria-label={label}
          className="absolute right-0 top-full z-50 mt-1 min-w-[210px] overflow-hidden rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] py-1 shadow-xl ring-1 ring-black/5"
        >
          {items.map((item) => {
            const active = isItemActive(item.href);
            const IconComponent = item.icon;
            return (
              <li role="none" key={item.href}>
                <Link
                  role="menuitem"
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  onClick={() => setOpen(false)}
                  className={cn(
                    "flex items-center gap-2 px-3 py-2 text-[13px] transition-colors",
                    active
                      ? "bg-[color:var(--surface-brand-muted)] font-medium text-[color:var(--text-brand)]"
                      : "text-[color:var(--text-primary)] hover:bg-[color:var(--surface-hover)]",
                  )}
                >
                  <IconComponent
                    className={cn(
                      "h-4 w-4",
                      active
                        ? "text-[color:var(--text-brand)]"
                        : "text-[color:var(--text-tertiary)]",
                    )}
                    weight="bold"
                    aria-hidden="true"
                  />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
