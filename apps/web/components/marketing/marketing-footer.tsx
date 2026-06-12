import Link from "next/link";
import { ArrowUpRight } from "@phosphor-icons/react/dist/ssr";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { APP_VERSION, BUILD_SHA } from "@/lib/version";

/**
 * Marketing footer, shared by the landing page and the public REPSE
 * content pages (/repse, /software-repse). Extracted from app/page.tsx
 * so every public page closes with the same crawl paths: section
 * anchors are absolute ("/#sistema") so they resolve correctly from
 * subpages, and the Recursos column gives the content pages permanent
 * internal links with keyword anchor text.
 *
 * Editorial structure is unchanged: brand + signature on the left,
 * nav columns in the middle, version + region stamp on the right, and
 * the legal strip at the bottom. No nested cards; mono captions
 * provide the operational signature.
 */
export function MarketingFooter() {
  return (
    <footer className="border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]">
      <div className="mx-auto grid max-w-[1320px] grid-cols-1 gap-10 px-5 py-12 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] md:gap-12">
        {/* Brand column */}
        <div>
          <BrandLogo size="sm" />
          <p className="mt-4 max-w-[32ch] text-[13px] leading-[1.55] text-[color:var(--text-secondary)]">
            Sistema operativo REPSE para proveedor, cliente y equipo CheckWise,
            sobre un mismo expediente auditable.
          </p>
          <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
            Una solución de{" "}
            <span className="text-[color:var(--text-secondary)]">Legal Shelf</span>
          </p>
        </div>

        {/* Nav column — mirrors the top-nav anchors so labels stay
            consistent across the page. */}
        <FooterColumn
          label="Producto"
          links={[
            { label: "Sistema", href: "/#sistema" },
            { label: "Evidencia", href: "/#evidencia" },
            { label: "AI + revisión", href: "/#ai-revision" },
            { label: "Iniciar sesión", href: "/login" },
            { label: "Solicitar demo", href: "/#contacto" },
          ]}
        />

        {/* Resources column — public REPSE content pages. */}
        <FooterColumn
          label="Recursos REPSE"
          links={[
            { label: "Qué es el REPSE", href: "/repse" },
            { label: "Software de cumplimiento REPSE", href: "/software-repse" },
            { label: "Preguntas frecuentes", href: "/#faq" },
          ]}
        />

        {/* Signature column. Build metadata stays in the title
            attribute for support diagnostics but is no longer visible
            text on the public landing. */}
        <div
          className="flex flex-col gap-3 md:items-end md:text-right"
          title={`CheckWise v${APP_VERSION} · ${BUILD_SHA}`}
        >
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">
            Equipo CheckWise
          </p>
          <p className="text-[13px] text-[color:var(--text-secondary)]">
            Hecho en Ciudad de México.
          </p>
          <p className="text-[12px] text-[color:var(--text-tertiary)]">
            © {new Date().getFullYear()} CheckWise. Todos los derechos reservados.
          </p>
        </div>
      </div>

      {/* Legal strip — required near data collection for a compliance
          product; links to the existing /legal pages. */}
      <div className="border-t border-[color:var(--border-subtle)]">
        <div className="mx-auto flex max-w-[1320px] flex-col gap-3 px-5 py-5 text-[12px] sm:flex-row sm:items-center sm:justify-between">
          <p className="text-[color:var(--text-tertiary)]">
            CheckWise es una plataforma de control documental REPSE. No emite
            resoluciones legales ni garantiza el cumplimiento automático.
          </p>
          <ul className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <li>
              <Link
                href="/legal/privacidad"
                className="text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
              >
                Aviso de privacidad
              </Link>
            </li>
            <li>
              <Link
                href="/legal/terminos"
                className="text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
              >
                Términos
              </Link>
            </li>
          </ul>
        </div>
      </div>
    </footer>
  );
}

function FooterColumn({
  label,
  links,
}: {
  label: string;
  links: ReadonlyArray<{ label: string; href: string }>;
}) {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-secondary)]">
        {label}
      </p>
      <ul className="mt-4 space-y-2.5">
        {links.map((link) => {
          const external = link.href.startsWith("http");
          const hashOnly = link.href.includes("#");
          const className =
            "group inline-flex items-center gap-1.5 text-[13px] text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]";
          if (!external && !hashOnly) {
            return (
              <li key={link.href}>
                <Link href={link.href} className={className}>
                  <span>{link.label}</span>
                  <ArrowUpRight
                    className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100"
                    weight="bold"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            );
          }
          return (
            <li key={link.href}>
              <a
                href={link.href}
                className={className}
                target={external ? "_blank" : undefined}
                rel={external ? "noreferrer noopener" : undefined}
              >
                <span>{link.label}</span>
                <ArrowUpRight
                  className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100"
                  weight="bold"
                  aria-hidden="true"
                />
              </a>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
