import type { Metadata } from "next";
import Link from "next/link";

import {
  ArticleCta,
  ArticleFaq,
  type ArticleFaqItem,
  ArticleSection,
  MarketingArticleShell,
} from "@/components/marketing/article-shell";
import { SITE_NAME, SITE_URL } from "@/lib/site";

/**
 * /obligado-solidario-repse — contratante-intent cluster page.
 *
 * Targets the "obligado solidario", "responsabilidad solidaria REPSE",
 * "riesgos de contratar sin REPSE" query family — the fear/pain driver
 * for the company that contracts. Explains the concept and the fiscal
 * and labor consequences, then routes to prevention (/validar... and
 * /software-repse). Evergreen: amounts in UMA, cadences not dates.
 */
export const metadata: Metadata = {
  title: "Obligado solidario REPSE: qué es y cómo evitarlo",
  description:
    "Qué significa ser obligado solidario en la subcontratación especializada, cuándo una empresa contratante responde por las obligaciones de su proveedor, qué consecuencias fiscales y laborales implica y cómo evitar la responsabilidad solidaria con verificación continua.",
  alternates: { canonical: "/obligado-solidario-repse" },
  openGraph: {
    title: "Obligado solidario REPSE: qué es y cómo evitarlo",
    description:
      "Cuándo responde la empresa contratante por su proveedor, qué consecuencias trae y cómo blindarte con verificación documental continua.",
    url: `${SITE_URL}/obligado-solidario-repse`,
    type: "article",
  },
};

const ARTICLE_LD = {
  "@context": "https://schema.org",
  "@type": "Article",
  "@id": `${SITE_URL}/obligado-solidario-repse#article`,
  headline: "Obligado solidario REPSE: qué es y cómo evitarlo",
  inLanguage: "es-MX",
  datePublished: "2026-06-18",
  dateModified: "2026-06-18",
  author: { "@type": "Organization", name: SITE_NAME, url: SITE_URL },
  publisher: { "@id": `${SITE_URL}/#organization` },
  mainEntityOfPage: `${SITE_URL}/obligado-solidario-repse`,
};

const FAQ: readonly ArticleFaqItem[] = [
  {
    question: "¿Qué significa ser obligado solidario en el REPSE?",
    answer:
      "Significa que la empresa que recibe el servicio especializado puede responder, junto con el proveedor, por las obligaciones laborales y de seguridad social de los trabajadores de ese proveedor. Si el proveedor no paga salarios, cuotas al IMSS o aportaciones al INFONAVIT, la autoridad o los trabajadores pueden reclamarle a la empresa beneficiaria del servicio.",
  },
  {
    question: "¿Cuándo se vuelve obligado solidario una empresa contratante?",
    answer:
      "Principalmente cuando contrata servicios especializados con un proveedor sin registro REPSE vigente, o cuando no verifica ni conserva la evidencia de que el proveedor cumple sus obligaciones fiscales y de seguridad social. La falta de verificación es justamente lo que activa el riesgo para el contratante.",
  },
  {
    question: "¿Qué consecuencias tiene la responsabilidad solidaria?",
    answer:
      "Tres frentes: laboral y de seguridad social (responder por salarios y cuotas de los trabajadores del proveedor), fiscal (perder la deducción de ISR y el acreditamiento de IVA de esos pagos) y administrativo (multas de 2,000 a 50,000 veces la UMA por recibir servicios especializados sin registro vigente).",
  },
  {
    question: "¿Cómo se evita ser obligado solidario por REPSE?",
    answer:
      "Verificando que cada proveedor tiene registro REPSE vigente acorde al servicio, conservando la evidencia documental de su cumplimiento por periodo y repitiendo esa verificación de forma continua mientras dure la relación. La defensa del contratante es la evidencia: poder demostrar que verificó en cada periodo.",
  },
  {
    question: "¿La responsabilidad solidaria desaparece si el proveedor tiene REPSE?",
    answer:
      "El registro vigente es la base, pero no basta por sí solo. El contratante debe poder acreditar que verificó el cumplimiento del proveedor —registro, opiniones positivas, pago de cuotas, CFDI de nómina— durante toda la relación. Sin esa evidencia conservada, el registro vigente no protege por completo.",
  },
];

export default function ObligadoSolidarioRepsePage() {
  return (
    <MarketingArticleShell
      eyebrow="Riesgo del contratante"
      title={
        <>
          Obligado solidario REPSE:{" "}
          <span className="text-[color:var(--text-teal)]">
            qué es y cómo dejar de estar expuesto.
          </span>
        </>
      }
      intro="La responsabilidad solidaria es el riesgo que casi nadie ve hasta que lo tiene encima. Cuando contratas servicios especializados, la ley puede hacerte responder por las obligaciones de tu proveedor frente a sus trabajadores y frente al fisco. La buena noticia: es un riesgo que se previene con verificación, no con suerte."
      breadcrumbName="Obligado solidario REPSE"
      path="/obligado-solidario-repse"
    >
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(ARTICLE_LD) }}
      />

      <ArticleSection id="que-es" heading="Qué es la responsabilidad solidaria">
        <p>
          En la subcontratación especializada, la empresa que recibe el
          servicio se beneficia del trabajo de personas que no son sus
          empleados directos. Por eso la ley establece que, bajo ciertas
          condiciones, esa empresa puede responder{" "}
          <strong>solidariamente</strong> por las obligaciones que el
          proveedor tiene con esos trabajadores: salarios, cuotas
          obrero-patronales del IMSS y aportaciones de vivienda al INFONAVIT.
        </p>
        <p>
          &ldquo;Solidaria&rdquo; significa que el trabajador o la autoridad
          pueden cobrarle directamente a la empresa contratante, sin tener
          que agotar primero al proveedor. No es un riesgo teórico: es la
          razón por la que la reforma puso la carga de la verificación sobre
          quien contrata.
        </p>
      </ArticleSection>

      <ArticleSection id="cuando" heading="Cuándo te vuelves obligado solidario">
        <p>
          El detonante más común es contratar a un proveedor{" "}
          <strong>sin registro REPSE vigente</strong> o dejar de verificar
          que sigue cumpliendo. Si el proveedor no tiene registro acorde al
          servicio, no presenta sus informativas o pierde una opinión de
          cumplimiento, y tú no lo detectas, el riesgo se traslada a tu
          empresa. La omisión de verificar es, en sí misma, lo que abre la
          puerta a la responsabilidad solidaria.
        </p>
      </ArticleSection>

      <ArticleSection id="consecuencias" heading="Las tres consecuencias">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Laboral y de seguridad social:</strong> responder por
            salarios y cuotas de los trabajadores del proveedor frente al
            IMSS, el INFONAVIT y los propios trabajadores.
          </li>
          <li>
            <strong>Fiscal:</strong> perder la deducción del ISR y el
            acreditamiento del IVA de los pagos al proveedor incumplido.
          </li>
          <li>
            <strong>Administrativa:</strong> multas de 2,000 a 50,000 veces
            la UMA por recibir servicios especializados sin registro REPSE
            vigente.
          </li>
        </ul>
      </ArticleSection>

      <ArticleSection id="como-evitarlo" heading="Cómo dejar de estar expuesto">
        <p>
          La defensa del contratante es la evidencia. No basta con confiar en
          el proveedor: hay que poder{" "}
          <strong>demostrar que verificaste</strong> su cumplimiento en cada
          periodo. Eso implica{" "}
          <Link
            href="/validar-proveedores-repse"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            validar a cada proveedor
          </Link>{" "}
          —registro vigente, opiniones positivas, pago de cuotas, CFDI de
          nómina— y conservar ese{" "}
          <Link
            href="/expediente-repse"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            expediente por proveedor y periodo
          </Link>
          , de forma continua mientras dure la relación.
        </p>
        <p>
          Sostener eso a mano sobre decenas de proveedores es justo donde
          falla el control. Un{" "}
          <Link
            href="/software-repse"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            software de cumplimiento REPSE
          </Link>{" "}
          detecta los vencimientos y las inconsistencias antes de la fecha
          límite y deja el rastro auditable que necesitas para acreditar que
          cumpliste. Prevención en lugar de exposición.
        </p>
      </ArticleSection>

      <ArticleFaq items={FAQ} path="/obligado-solidario-repse" />

      <ArticleCta
        title="Deja de cargar el riesgo de tus proveedores."
        body="En una demo de 30 minutos te mostramos cómo CheckWise verifica a cada proveedor cada periodo y guarda la evidencia que te protege de la responsabilidad solidaria. Con datos de ejemplo, sobre el producto real."
      />
    </MarketingArticleShell>
  );
}
