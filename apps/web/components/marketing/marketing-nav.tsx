"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight } from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Button } from "@/components/ui/button";

const NAV_ITEMS = [
  { href: "#features", label: "Cómo funciona" },
  { href: "#producto", label: "Recorrido" },
  { href: "#legal-shelf", label: "Legal Shelf" },
] as const;

/**
 * Sticky marketing nav. Picks up a subtle elevation + tighter padding
 * once the user scrolls past the hero's first viewport, which is a
 * small detail that makes the page feel premium without being noisy.
 *
 * Action priority — one primary CTA. "Solicitar demo" is the only
 * commercial conversion path; "Iniciar sesión" stays as a quiet utility
 * link for existing users.
 */
export function MarketingNav() {
  const [elevated, setElevated] = useState(false);

  useEffect(() => {
    const onScroll = () => setElevated(window.scrollY > 16);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-30 border-b backdrop-blur transition-[background,border-color,box-shadow] duration-300 ${
        elevated
          ? "border-[color:var(--border-default)] bg-[color:var(--surface-raised)]/92 shadow-[0_8px_24px_-18px_hsl(var(--brand-navy)/0.35)]"
          : "border-transparent bg-[color:var(--surface-page)]/70"
      }`}
    >
      <div
        className={`mx-auto flex max-w-[1320px] items-center justify-between gap-3 px-5 transition-[padding] duration-300 ${
          elevated ? "py-2.5" : "py-3"
        }`}
      >
        <Link href="/" aria-label="CheckWise inicio">
          <BrandLogo size="md" />
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
            className="hidden text-[color:var(--text-secondary)] sm:inline-flex"
          >
            <Link href="/login">Iniciar sesión</Link>
          </Button>
          <Button asChild size="sm" className="rounded-full">
            <Link href="#contacto">
              <span className="sm:hidden">Demo</span>
              <span className="hidden sm:inline">Solicitar demo</span>
              <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            </Link>
          </Button>
        </div>
      </div>
    </header>
  );
}
