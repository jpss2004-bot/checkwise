import Link from "next/link";
import { ArrowUpRight } from "@phosphor-icons/react/dist/ssr";

import { BrandLogo } from "@/components/checkwise/brand-logo";

import { Container } from "./_shared";

const COLS = [
  {
    title: "Producto",
    links: [
      { label: "Sistema", href: "#sistema" },
      { label: "Prevención", href: "#prevencion" },
      { label: "IA + revisión", href: "#ia" },
      { label: "Solicitar demo", href: "#contacto" },
      { label: "Iniciar sesión", href: "/login" },
    ],
  },
  {
    title: "Recursos REPSE",
    links: [
      { label: "Qué es el REPSE", href: "/repse" },
      { label: "Software de cumplimiento REPSE", href: "/software-repse" },
      { label: "ICSOE", href: "/repse" },
      { label: "SISUB", href: "/repse" },
      { label: "Responsabilidad solidaria", href: "/repse" },
    ],
  },
  {
    title: "Empresa",
    links: [
      { label: "Sobre CheckWise", href: "/sobre-checkwise" },
      { label: "Seguridad", href: "/seguridad" },
      { label: "Legal Shelf", href: "https://legalshelf.mx" },
      { label: "Aviso de privacidad", href: "/legal/privacidad" },
      { label: "Términos", href: "/legal/terminos" },
    ],
  },
] as const;

export function V2Footer() {
  return (
    <footer className="border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]">
      <Container className="py-16">
        <div className="grid gap-10 md:grid-cols-[1.5fr_1fr_1fr_1fr] md:gap-12">
          <div className="max-w-[34ch]">
            <BrandLogo size="sm" />
            <p className="mt-4 text-[13px] leading-[1.6] text-[color:var(--text-secondary)]">
              Cumplimiento y prevención REPSE: monitorea a tus proveedores, evita
              multas y responsabilidad solidaria, y llega a cada auditoría con el
              expediente listo.
            </p>
            <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
              Una solución de{" "}
              <span className="text-[color:var(--text-secondary)]">Legal Shelf</span>
            </p>
          </div>
          {COLS.map((col) => (
            <div key={col.title}>
              <p className="font-mono text-[10px] font-medium uppercase tracking-[0.2em] text-[color:var(--text-secondary)]">
                {col.title}
              </p>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((link) => {
                  const external = link.href.startsWith("http");
                  return (
                    <li key={`${col.title}-${link.label}`}>
                      <Link
                        href={link.href}
                        target={external ? "_blank" : undefined}
                        rel={external ? "noreferrer noopener" : undefined}
                        className="group inline-flex items-center gap-1.5 text-[13px] text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
                      >
                        <span>{link.label}</span>
                        <ArrowUpRight
                          className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100"
                          weight="bold"
                          aria-hidden="true"
                        />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-12 flex flex-col gap-2 border-t border-[color:var(--border-subtle)] pt-6 text-[12px] text-[color:var(--text-tertiary)] sm:flex-row sm:items-center sm:justify-between">
          <span>© 2026 CheckWise · Hecho en Ciudad de México</span>
          <span>Respaldado por Legal Shelf</span>
        </div>
      </Container>
    </footer>
  );
}
