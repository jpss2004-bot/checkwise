import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowRight, ArrowUpRight } from "@phosphor-icons/react/dist/ssr";

import { Button } from "@/components/ui/button";
import { DEMO_BOOKING_URL } from "@/lib/marketing/booking";
import { SITE_URL } from "@/lib/site";

import { V2Footer } from "./v2/footer";
import { V2Nav } from "./v2/nav";

/**
 * Shell for the public REPSE content pages (/repse, /software-repse).
 * Server component: the whole article — headline, intro, sections —
 * ships in the initial HTML, which is the entire point of these pages.
 *
 * Emits a BreadcrumbList JSON-LD node from the `breadcrumb` prop so
 * search results can show "Inicio › {page}" instead of a bare URL.
 * Visual language mirrors the landing (eyebrow, balance-wrapped
 * headline, mono captions) so the jump from ad/result to demo request
 * feels like one product.
 */
export function MarketingArticleShell({
  eyebrow,
  title,
  intro,
  breadcrumbName,
  path,
  children,
}: {
  eyebrow: string;
  title: ReactNode;
  intro: string;
  breadcrumbName: string;
  path: string;
  children: ReactNode;
}) {
  const breadcrumbLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Inicio", item: SITE_URL },
      {
        "@type": "ListItem",
        position: 2,
        name: breadcrumbName,
        item: `${SITE_URL}${path}`,
      },
    ],
  };

  return (
    <main className="min-h-[100dvh] bg-[color:var(--surface-page)]">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbLd) }}
      />
      <V2Nav />

      <article className="mx-auto max-w-[820px] px-5 pb-24 pt-14 lg:pt-20">
        <header>
          <p className="cw-eyebrow text-[color:var(--text-teal)]">{eyebrow}</p>
          <h1
            className="mt-3 font-semibold tracking-[-0.024em] text-[color:var(--text-primary)] [text-wrap:balance]"
            style={{ fontSize: "clamp(2rem, 4vw, 3.1rem)", lineHeight: 1.02 }}
          >
            {title}
          </h1>
          <p className="mt-5 max-w-[62ch] text-[16px] leading-[1.65] text-[color:var(--text-secondary)] md:text-[17px]">
            {intro}
          </p>
        </header>

        <div className="mt-12 space-y-12">{children}</div>

        <footer className="mt-14 border-t border-[color:var(--border-subtle)] pt-6 text-[12px] leading-[1.6] text-[color:var(--text-tertiary)]">
          <p>
            Este contenido es informativo y de carácter general; no constituye
            asesoría legal ni fiscal. Para tu caso concreto, consulta a tu
            equipo legal o escríbenos — CheckWise es una solución de Legal
            Shelf, firma legal con sede en Ciudad de México.
          </p>
        </footer>
      </article>

      <V2Footer />
    </main>
  );
}

export function ArticleSection({
  id,
  heading,
  children,
}: {
  id?: string;
  heading: string;
  children: ReactNode;
}) {
  return (
    <section id={id}>
      <h2 className="text-[22px] font-semibold tracking-[-0.018em] text-[color:var(--text-primary)] md:text-[24px]">
        {heading}
      </h2>
      <div className="mt-4 space-y-4 text-[15px] leading-[1.7] text-[color:var(--text-secondary)]">
        {children}
      </div>
    </section>
  );
}

/**
 * Demo CTA used at the bottom of each article. Routes to the landing
 * contact section — one conversion path for the whole public site.
 */
export function ArticleCta({
  title,
  body,
}: {
  title: string;
  body: string;
}) {
  return (
    <aside className="rounded-[10px] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-7 py-8 shadow-[0_22px_50px_-32px_hsl(var(--brand-navy)/0.22)]">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-teal)]">
        <span className="cw-pulse-soft mr-2 inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)] align-middle" />
        Demo guiada · respuesta el mismo día hábil
      </p>
      <h2 className="mt-3 text-[20px] font-semibold tracking-[-0.018em] text-[color:var(--text-primary)] [text-wrap:balance]">
        {title}
      </h2>
      <p className="mt-2 max-w-[58ch] text-[14.5px] leading-[1.6] text-[color:var(--text-secondary)]">
        {body}
      </p>
      <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-3">
        <Button asChild size="sm" className="h-10 rounded-full px-5">
          <Link href="/#contacto">
            Solicitar demo
            <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          </Link>
        </Button>
        <a
          href={DEMO_BOOKING_URL}
          target="_blank"
          rel="noreferrer noopener"
          className="group inline-flex items-center gap-1 text-[13px] font-medium text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
        >
          o agenda 30 minutos directamente
          <ArrowUpRight
            className="h-3 w-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
            weight="bold"
            aria-hidden="true"
          />
        </a>
      </div>
    </aside>
  );
}
