"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, List, X } from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Button } from "@/components/ui/button";

const NAV_ITEMS = [
  { href: "#sistema", label: "Sistema" },
  { href: "#prevencion", label: "Prevención" },
  { href: "#ia", label: "IA + revisión" },
  { href: "#recursos", label: "Recursos" },
] as const;

export function V2Nav() {
  const [elevated, setElevated] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setElevated(window.scrollY > 16);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  return (
    <header
      className={`sticky top-0 z-40 border-b backdrop-blur-xl backdrop-saturate-150 transition-[background-color,border-color,box-shadow] duration-300 ${
        elevated || open
          ? "border-[hsl(var(--navy-200)/0.55)] bg-[hsl(var(--navy-50)/0.85)] shadow-[0_10px_30px_-18px_hsl(var(--brand-navy)/0.4)]"
          : "border-[hsl(var(--navy-100)/0.5)] bg-[hsl(var(--navy-50)/0.6)]"
      }`}
    >
      <div
        className={`mx-auto flex max-w-[1200px] items-center justify-between gap-3 px-6 transition-[padding] duration-300 md:px-10 ${
          elevated ? "py-2.5" : "py-3.5"
        }`}
      >
        <Link
          href="/"
          aria-label="CheckWise inicio"
          className="flex items-center gap-2.5"
          onClick={() => setOpen(false)}
        >
          <BrandLogo size="md" />
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
              className="text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
            >
              {item.label}
            </a>
          ))}
          <a
            href="/repse"
            className="text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
          >
            Guía REPSE
          </a>
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
            <Link href="#contacto" onClick={() => setOpen(false)}>
              <span className="sm:hidden">Demo</span>
              <span className="hidden sm:inline">Solicitar demo</span>
              <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            </Link>
          </Button>

          <button
            type="button"
            aria-label={open ? "Cerrar menú" : "Abrir menú"}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
            className="inline-flex h-11 w-11 items-center justify-center rounded-md text-[color:var(--text-primary)] transition-colors hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/45 md:hidden"
          >
            {open ? (
              <X className="h-5 w-5" weight="bold" aria-hidden="true" />
            ) : (
              <List className="h-5 w-5" weight="bold" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      {open ? (
        <nav
          aria-label="Navegación móvil"
          className="border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-6 pb-6 pt-2 md:hidden"
        >
          <ul className="flex flex-col">
            {[...NAV_ITEMS, { href: "/repse", label: "Guía REPSE" }].map((item) => (
              <li key={item.href}>
                <a
                  href={item.href}
                  onClick={() => setOpen(false)}
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
                onClick={() => setOpen(false)}
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
