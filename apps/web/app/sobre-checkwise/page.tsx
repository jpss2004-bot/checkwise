import type { Metadata } from "next";
import Link from "next/link";

import {
  ArticleCta,
  ArticleSection,
  MarketingArticleShell,
} from "@/components/marketing/article-shell";
import { SITE_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Sobre CheckWise — Cumplimiento REPSE por Legal Shelf",
  description:
    "CheckWise es la plataforma de cumplimiento REPSE construida por Legal Shelf, firma de abogados especializada en cumplimiento normativo con sede en Ciudad de México.",
  alternates: { canonical: "/sobre-checkwise" },
  openGraph: {
    title: "Sobre CheckWise — Cumplimiento REPSE por Legal Shelf",
    description:
      "Conoce quién está detrás de CheckWise: Legal Shelf, la firma de abogados especializada en REPSE, con sede en Ciudad de México.",
    url: `${SITE_URL}/sobre-checkwise`,
    type: "article",
  },
};

// AboutPage tied to the shared Organization node (#organization, defined
// in the homepage @graph) so search engines connect this page to the
// entity behind the product.
const ABOUT_LD = {
  "@context": "https://schema.org",
  "@type": "AboutPage",
  "@id": `${SITE_URL}/sobre-checkwise#about`,
  inLanguage: "es-MX",
  name: "Sobre CheckWise — Cumplimiento REPSE por Legal Shelf",
  url: `${SITE_URL}/sobre-checkwise`,
  mainEntity: { "@id": `${SITE_URL}/#organization` },
  publisher: { "@id": `${SITE_URL}/#organization` },
};

const LOGOS = [
  "Capgemini",
  "BIC",
  "Sekura",
  "Juguetrón",
  "Benotto",
  "Giormar",
] as const;

export default function SobreCheckWisePage() {
  return (
    <MarketingArticleShell
      eyebrow="Sobre CheckWise"
      title={
        <>
          Cumplimiento REPSE construido por{" "}
          <span className="text-[color:var(--text-teal)]">abogados.</span>
        </>
      }
      intro="CheckWise no nació en un laboratorio de producto. Nació porque Legal Shelf, la firma de abogados detrás de la plataforma, ya manejaba el cumplimiento REPSE de sus clientes de forma manual y vio que el problema de escala era el mismo para todas las empresas que contratan servicios especializados."
      breadcrumbName="Sobre CheckWise"
      path="/sobre-checkwise"
    >
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(ABOUT_LD) }}
      />

      <ArticleSection id="legal-shelf" heading="Legal Shelf">
        <p>
          <Link
            href="https://legalshelf.mx"
            target="_blank"
            rel="noreferrer noopener"
            className="text-[color:var(--text-teal)] underline-offset-2 hover:underline"
          >
            Legal Shelf
          </Link>{" "}
          es una firma de abogados mexicana especializada en cumplimiento
          normativo, con sede en Ciudad de México. Trabaja con empresas de
          manufactura, retail y consumo que tienen redes de proveedores sujetas
          a REPSE, y atiende tanto a las empresas contratantes como a los
          propios prestadores de servicios especializados.
        </p>
        <p>
          La práctica de cumplimiento REPSE de Legal Shelf abarca el registro
          ante la STPS, la gestión de obligaciones recurrentes (ICSOE, SISUB,
          declaraciones patronales, pagos de seguridad social), la preparación
          de expedientes para auditoría y la representación ante inspecciones.
        </p>
      </ArticleSection>

      <ArticleSection id="por-que-checkwise" heading="Por qué existe CheckWise">
        <p>
          La reforma al artículo 13 de la LISR, LSSM y LISSTE de 2021 obligó a
          las empresas a acreditar el cumplimiento de sus proveedores de
          servicios especializados bajo pena de perder la deducción fiscal y
          enfrentar responsabilidad solidaria ante el IMSS y la STPS.
        </p>
        <p>
          El equipo de Legal Shelf pasó los primeros meses post-reforma
          coordinando el cumplimiento de sus clientes con hojas de cálculo,
          carpetas compartidas y correos de seguimiento. Con diez proveedores
          era manejable. Con cincuenta, se volvió inviable: vencimientos
          cruzados, documentos sin contexto, reportes manuales para cada
          inspección.
        </p>
        <p>
          CheckWise es la respuesta a ese problema operativo: un sistema que
          centraliza las 151 obligaciones REPSE por proveedor, automatiza el
          calendario, gestiona la evidencia, incorpora una capa de revisión
          humana firmada y genera el expediente auditable listo para la
          autoridad.
        </p>
      </ArticleSection>

      <ArticleSection id="quienes-confian" heading="Quiénes confían en CheckWise">
        <p>
          Las empresas que operan con CheckWise son, en su mayoría, empresas
          contratantes con portafolios de más de veinte proveedores REPSE —
          manufactura, distribución, servicios de limpieza industrial,
          seguridad y logística especializada.
        </p>
        <ul
          aria-label="Empresas que confían en Legal Shelf"
          className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3"
          role="list"
        >
          {LOGOS.map((name) => (
            <li
              key={name}
              className="flex h-16 items-center justify-center rounded-2xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] font-display text-[15px] font-bold tracking-[-0.01em] text-[hsl(var(--navy-700))]"
            >
              {name}
            </li>
          ))}
        </ul>
      </ArticleSection>

      <ArticleSection id="contacto" heading="Habla con el equipo">
        <p>
          CheckWise es operado por el equipo de Legal Shelf desde Ciudad de
          México. Si tienes preguntas sobre el producto, sobre el REPSE o sobre
          cómo funcionaría para tu empresa, respondemos el mismo día hábil.
        </p>
        <p>
          Para demostraciones, evaluaciones técnicas o preguntas de seguridad,
          usa el formulario de la{" "}
          <Link
            href="/#contacto"
            className="text-[color:var(--text-teal)] underline-offset-2 hover:underline"
          >
            página principal
          </Link>
          .
        </p>
      </ArticleSection>

      <ArticleCta
        title="Ve CheckWise con tus propios proveedores."
        body="Recorremos calendario, expediente, revisión y reportes en una demo de 30 minutos usando datos de ejemplo. Sin video pregrabado. Respuesta el mismo día hábil."
      />
    </MarketingArticleShell>
  );
}
