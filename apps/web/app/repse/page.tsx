import type { Metadata } from "next";
import Link from "next/link";

import {
  ArticleCta,
  ArticleSection,
  MarketingArticleShell,
} from "@/components/marketing/article-shell";
import { SITE_NAME, SITE_URL } from "@/lib/site";

/**
 * /repse — informational pillar page.
 *
 * Targets the high-volume informational queries around the registry
 * itself ("qué es REPSE", "obligaciones REPSE", "multas REPSE",
 * "documentos REPSE proveedores") and funnels readers to the demo CTA.
 * Facts are kept evergreen on purpose: amounts in UMA (never pesos),
 * cadences ("cada tres años", "cuatrimestral") instead of dates, and
 * no claims about pending reforms.
 */
export const metadata: Metadata = {
  title: "Qué es el REPSE: registro, obligaciones y sanciones",
  description:
    "Guía clara del REPSE: qué es, quién debe registrarse ante la STPS, qué obligaciones implica (renovación, ICSOE, SISUB), qué debe verificar la empresa contratante y qué sanciones existen por incumplir.",
  alternates: { canonical: "/repse" },
  openGraph: {
    title: "Qué es el REPSE: registro, obligaciones y sanciones",
    description:
      "Quién debe registrarse en el REPSE, qué obligaciones implica y qué debe verificar la empresa contratante. Guía práctica de CheckWise.",
    url: `${SITE_URL}/repse`,
    type: "article",
  },
};

const ARTICLE_LD = {
  "@context": "https://schema.org",
  "@type": "Article",
  "@id": `${SITE_URL}/repse#article`,
  headline: "Qué es el REPSE: registro, obligaciones y sanciones",
  inLanguage: "es-MX",
  datePublished: "2026-06-12",
  dateModified: "2026-06-12",
  author: { "@type": "Organization", name: SITE_NAME, url: SITE_URL },
  publisher: { "@id": `${SITE_URL}/#organization` },
  mainEntityOfPage: `${SITE_URL}/repse`,
};

export default function RepsePage() {
  return (
    <MarketingArticleShell
      eyebrow="Guía REPSE"
      title={
        <>
          Qué es el REPSE y cómo cumplir:{" "}
          <span className="text-[color:var(--text-teal)]">
            guía para proveedores y empresas contratantes.
          </span>
        </>
      }
      intro="El REPSE es el registro obligatorio para prestar servicios especializados en México. Aquí explicamos quién debe inscribirse, qué obligaciones siguen después del registro, qué debe verificar la empresa que contrata y qué riesgos existen cuando algo falla."
      breadcrumbName="Qué es el REPSE"
      path="/repse"
    >
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(ARTICLE_LD) }}
      />

      <ArticleSection id="que-es" heading="¿Qué es el REPSE?">
        <p>
          El REPSE — Registro de Prestadoras de Servicios Especializados u
          Obras Especializadas — es el padrón público que administra la
          Secretaría del Trabajo y Previsión Social (STPS). Nació con la
          reforma en materia de subcontratación de 2021, que prohibió la
          subcontratación de personal y la sustituyó por un esquema acotado:
          solo se pueden subcontratar <strong>servicios especializados u
          obras especializadas</strong>, y solo con empresas inscritas en
          este registro.
        </p>
        <p>
          En la práctica, el REPSE convirtió el cumplimiento en un asunto de
          dos partes: el proveedor debe registrarse y mantenerse al
          corriente, y la empresa que lo contrata debe{" "}
          <strong>verificarlo y documentarlo de forma continua</strong>,
          porque las consecuencias fiscales y laborales del incumplimiento
          recaen también sobre ella.
        </p>
      </ArticleSection>

      <ArticleSection id="quien-debe-registrarse" heading="¿Quién debe registrarse?">
        <p>
          Debe inscribirse en el REPSE toda persona física o moral que ponga
          trabajadores propios a disposición de un tercero para ejecutar
          servicios u obras especializadas: actividades que{" "}
          <strong>no forman parte del objeto social ni de la actividad
          económica preponderante</strong> de la empresa que las recibe.
          Ejemplos típicos: limpieza, seguridad, mantenimiento, comedores
          industriales, logística especializada, servicios de TI, obra civil
          especializada.
        </p>
        <p>
          El registro se solicita en línea ante la STPS acreditando, entre
          otras cosas, estar al corriente en obligaciones fiscales y de
          seguridad social. Una vez otorgado,{" "}
          <strong>no es permanente</strong>: debe renovarse cada tres años y
          puede cancelarse si la empresa deja de cumplir.
        </p>
      </ArticleSection>

      <ArticleSection
        id="obligaciones-proveedor"
        heading="Obligaciones del proveedor registrado"
      >
        <p>
          Obtener el registro es el inicio, no el final. Un proveedor
          registrado debe, de forma permanente:
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Mantener el registro vigente</strong> y renovarlo cada
            tres años ante la STPS.
          </li>
          <li>
            <strong>Presentar la ICSOE</strong> (Informativa de Contratos de
            Servicios u Obras Especializadas) ante el IMSS cada cuatrimestre,
            en enero, mayo y septiembre.
          </li>
          <li>
            <strong>Presentar el SISUB</strong> (Sistema de Información de
            Subcontratación) ante el INFONAVIT con la misma periodicidad
            cuatrimestral.
          </li>
          <li>
            <strong>Mantenerse al corriente</strong> en obligaciones
            fiscales (SAT), de seguridad social (IMSS) y de vivienda
            (INFONAVIT), incluidas las opiniones de cumplimiento positivas.
          </li>
          <li>
            <strong>Entregar a cada cliente</strong> la evidencia documental
            que la ley obliga al contratante a recabar: CFDI de nómina,
            pagos de cuotas, declaraciones de impuestos, entre otros.
          </li>
          <li>
            <strong>Informar a la STPS</strong> las modificaciones relevantes
            a su situación (razón social, actividades registradas, etcétera).
          </li>
        </ul>
      </ArticleSection>

      <ArticleSection
        id="obligaciones-contratante"
        heading="Qué debe verificar la empresa contratante"
      >
        <p>
          La legislación fiscal condiciona la deducción del ISR y el
          acreditamiento del IVA de los servicios especializados a que el
          contratante <strong>verifique y conserve evidencia</strong> del
          cumplimiento de su proveedor. Un expediente sano por proveedor y
          por periodo incluye, como mínimo:
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>Registro REPSE vigente y acorde al servicio contratado.</li>
          <li>Contrato del servicio especializado.</li>
          <li>Constancia de situación fiscal del proveedor.</li>
          <li>
            Opiniones de cumplimiento del SAT, IMSS e INFONAVIT.
          </li>
          <li>
            CFDI de nómina y comprobantes de pago de salarios del personal
            asignado al servicio.
          </li>
          <li>
            Declaraciones de IVA e ISR con su acuse, y pagos de cuotas
            obrero-patronales y aportaciones de vivienda.
          </li>
        </ul>
        <p>
          El punto que más empresas subestiman: esta verificación{" "}
          <strong>se repite durante toda la vigencia del contrato</strong>.
          Un proveedor que cumplía al firmar puede dejar de cumplir seis
          meses después, y el riesgo fiscal corre por cuenta del contratante
          que no lo detectó.
        </p>
      </ArticleSection>

      <ArticleSection id="sanciones" heading="Multas y riesgos por incumplir">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Multas administrativas:</strong> prestar o recibir
            servicios especializados sin registro REPSE vigente se sanciona
            con multas de 2,000 a 50,000 veces la UMA.
          </li>
          <li>
            <strong>Efectos fiscales:</strong> los pagos al proveedor
            incumplido pierden la deducción para ISR y el acreditamiento del
            IVA.
          </li>
          <li>
            <strong>Responsabilidad solidaria:</strong> si el proveedor
            incumple sus obligaciones laborales y de seguridad social, la
            empresa beneficiaria puede responder frente a los trabajadores.
          </li>
          <li>
            <strong>Esquemas simulados:</strong> utilizar subcontratación
            simulada de personal puede constituir defraudación fiscal con
            consecuencias penales.
          </li>
        </ul>
      </ArticleSection>

      <ArticleSection
        id="control-documental"
        heading="Cómo llevar el control sin perderse"
      >
        <p>
          El reto operativo del REPSE no es entender las reglas: es
          sostenerlas mes tras mes sobre decenas de proveedores, cada uno
          con sus propios vencimientos, periodos e instituciones. Las hojas
          de cálculo y el correo fallan justo donde más duele — nadie ve a
          tiempo qué venció, qué falta o qué documento quedó obsoleto.
        </p>
        <p>
          Para eso existe el{" "}
          <Link
            href="/software-repse"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            software de cumplimiento REPSE
          </Link>
          : un calendario de obligaciones por requisito, periodo e
          institución, un expediente auditable por proveedor, revisión
          documental con apoyo de IA y validación humana, y reportes listos
          para una inspección. Es la diferencia entre dar seguimiento y
          hacer prevención de riesgos REPSE — y es exactamente lo que hace
          CheckWise.
        </p>
      </ArticleSection>

      <ArticleCta
        title="Ve tu operación REPSE completa en una demo guiada."
        body="Recorremos el calendario de obligaciones, el expediente del proveedor, la revisión documental y los reportes con datos de ejemplo — sobre el producto real, sin video pregrabado."
      />
    </MarketingArticleShell>
  );
}
