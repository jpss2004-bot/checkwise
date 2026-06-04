"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, List, X } from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Button } from "@/components/ui/button";

const NAV_ITEMS = [
  { href: "#sistema", label: "Sistema" },
  { href: "#evidencia", label: "Evidencia" },
  { href: "#ai-revision", label: "AI + revisión" },
] as const;

/**
 * Sticky marketing nav. Picks up a subtle elevation + tighter padding
 * once the user scrolls past the hero's first viewport, which is a
 * small detail that makes the page feel premium without being noisy.
 *
 * Action priority — one primary CTA. "Solicitar demo" is the only
 * commercial conversion path; "Iniciar sesión" stays as a quiet utility
 * link for existing users.
 *
 * Below `md`, the section anchors collapse into a disclosure menu
 * (previously they simply disappeared with no replacement, so the page
 * had no in-page navigation on phones). The hamburger and the two CTA
 * buttons are sized ≥44px tall for comfortable touch targets.
 */
export function MarketingNav() {
  const [elevated, setElevated] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setElevated(window.scrollY > 16);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Lock body scroll while the mobile sheet is open.
  useEffect(() => {
    if (!menuOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [menuOpen]);

  return (
    <header
      className={`sticky top-0 z-30 border-b backdrop-blur transition-[background,border-color,box-shadow] duration-300 ${
        elevated || menuOpen
          ? "border-[color:var(--border-default)] bg-[color:var(--surface-raised)]/92 shadow-[0_8px_24px_-18px_hsl(var(--brand-navy)/0.35)]"
          : "border-transparent bg-[color:var(--surface-page)]/70"
      }`}
    >
      <div
        className={`mx-auto flex max-w-[1320px] items-center justify-between gap-3 px-5 transition-[padding] duration-300 ${
          elevated ? "py-2.5" : "py-3"
        }`}
      >
        <Link
          href="/"
          aria-label="CheckWise inicio"
          className="flex items-center gap-2.5"
          onClick={() => setMenuOpen(false)}
        >
          <BrandLogo size="md" />
          {/* Endorsement — discreet, on the parent legal-services brand.
              Hidden on the smallest widths to protect the logo. */}
          <span className="hidden border-l border-[color:var(--border-default)] pl-2.5 font-mono text-[9px] uppercase leading-tight tracking-[0.14em] text-[color:var(--text-tertiary)] lg:inline-block">
            Una solución de
            <br />
            <span className="text-[color:var(--text-secondary)]">Legal Shelf</span>
          </span>
        </Link>

        <nav
          aria-label="Navegación principal"
          className="hidden items-center gap-7 text-[13px] md:flex"
        >
          {NAV_ITEMS.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="relative text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
            >
              {item.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <Button
            asChild
            variant="ghost"
            size="sm"
            className="hidden h-11 text-[color:var(--text-secondary)] sm:inline-flex md:h-8"
          >
            <Link href="/login">Iniciar sesión</Link>
          </Button>
          <Button asChild size="sm" className="h-11 rounded-full md:h-8">
            <Link href="#contacto" onClick={() => setMenuOpen(false)}>
              <span className="sm:hidden">Demo</span>
              <span className="hidden sm:inline">Solicitar demo</span>
              <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            </Link>
          </Button>

          {/* Mobile disclosure trigger */}
          <button
            type="button"
            aria-label={menuOpen ? "Cerrar menú" : "Abrir menú"}
            aria-expanded={menuOpen}
            aria-controls="marketing-mobile-menu"
            onClick={() => setMenuOpen((open) => !open)}
            className="inline-flex h-11 w-11 items-center justify-center rounded-md text-[color:var(--text-primary)] transition-colors hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/45 md:hidden"
          >
            {menuOpen ? (
              <X className="h-5 w-5" weight="bold" aria-hidden="true" />
            ) : (
              <List className="h-5 w-5" weight="bold" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      {/* Mobile menu sheet */}
      {menuOpen ? (
        <nav
          id="marketing-mobile-menu"
          aria-label="Navegación móvil"
          className="border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-5 pb-6 pt-2 md:hidden"
        >
          <ul className="flex flex-col">
            {NAV_ITEMS.map((item) => (
              <li key={item.href}>
                <a
                  href={item.href}
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center justify-between border-b border-[color:var(--border-subtle)] py-3.5 text-[15px] text-[color:var(--text-primary)]"
                >
                  {item.label}
                  <ArrowRight
                    className="h-4 w-4 text-[color:var(--text-tertiary)]"
                    weight="bold"
                    aria-hidden="true"
                  />
                </a>
              </li>
            ))}
            <li>
              <Link
                href="/login"
                onClick={() => setMenuOpen(false)}
                className="flex items-center justify-between py-3.5 text-[15px] text-[color:var(--text-secondary)]"
              >
                Iniciar sesión
                <ArrowRight
                  className="h-4 w-4 text-[color:var(--text-tertiary)]"
                  weight="bold"
                  aria-hidden="true"
                />
              </Link>
            </li>
          </ul>
        </nav>
      ) : null}
    </header>
  );
}
