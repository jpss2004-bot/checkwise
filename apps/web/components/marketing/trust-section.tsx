/* eslint-disable @next/next/no-img-element */

/**
 * Client trust strip — sits directly under the hero, mirroring the
 * placement that worked on the old legalshelf.mx/checkwise/repse page.
 *
 * The logos are the official client marks Legal Shelf publishes on its
 * own site today (pulled from its production CDN, trimmed, and
 * self-hosted under /public/clients). All seven ship as white-on-
 * transparent artwork made for a dark surface, so the strip uses the
 * same brand-navy band as the AI-review section — original artwork,
 * no recoloring filters (BIC's knockout mark turns into a blob under
 * any darkening filter). Per-logo heights compensate for the very
 * different aspect ratios so everything reads at one optical size.
 *
 * TODO(confirm): the roster below is taken verbatim from the live old
 * page. Confirm with Héctor which client relationships may be promoted
 * on the CheckWise site specifically (vs. Legal Shelf generally) before
 * any paid campaign points here. The caption credits Legal Shelf — not
 * CheckWise — precisely so the claim stays true in the meantime.
 *
 * Plain <img> (not next/image): tiny pre-sized PNGs, nothing to
 * optimize. Eager on purpose: the strip is effectively above the fold
 * and lazy-loading it only risks a visible pop-in.
 */
const CLIENTS = [
  { name: "Capgemini", src: "/clients/capgemini.png", className: "h-6" },
  { name: "BIC", src: "/clients/bic.png", className: "h-6" },
  { name: "Sekura", src: "/clients/sekura.png", className: "h-7" },
  { name: "Juguetrón", src: "/clients/juguetron.png", className: "h-8" },
  { name: "Benotto", src: "/clients/benotto.png", className: "h-5" },
  { name: "Giormar", src: "/clients/giormar.png", className: "h-9" },
  { name: "Samano Abogados", src: "/clients/samano-abogados.png", className: "h-9" },
] as const;

export function TrustSection() {
  return (
    <section
      aria-label="Empresas que confían en Legal Shelf"
      className="bg-[color:var(--surface-brand)]"
    >
      <div className="mx-auto flex max-w-[1320px] flex-col items-center gap-7 px-5 py-9 lg:flex-row lg:gap-12">
        <p className="shrink-0 text-center font-mono text-[10px] uppercase leading-[1.7] tracking-[0.2em] text-[color:var(--text-inverse-muted)] lg:max-w-[20ch] lg:text-left">
          Confían en Legal Shelf, la firma detrás de CheckWise
        </p>
        <ul className="flex flex-1 flex-wrap items-center justify-center gap-x-12 gap-y-7 lg:justify-between">
          {CLIENTS.map((client) => (
            <li key={client.name} className="flex items-center">
              <img
                src={client.src}
                alt={client.name}
                loading="eager"
                className={`${client.className} w-auto opacity-60 transition-opacity duration-300 hover:opacity-95`}
              />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
