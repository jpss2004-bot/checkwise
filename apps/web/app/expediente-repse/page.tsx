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
 * /expediente-repse — contratante-intent cluster page.
 *
 * Targets the "expediente REPSE", "documentos REPSE proveedores",
 * "qué documentos pedir a un proveedor REPSE", "expediente auditable"
 * query family — the document-control angle of the contratante wedge.
 * Routes to /validar-proveedores-repse and /software-repse. Evergreen:
 * amounts in UMA, cadences not dates.
 */
export const metadata: Metadata = {
  title: "Expediente REPSE del proveedor: qué debe contener",
  description:
    "Qué documentos debe contener el expediente REPSE de cada proveedor, cómo organizarlo por periodo e institución, cuánto tiempo conservarlo y por qué un expediente auditable —no una carpeta de archivos— es lo que te protege en una inspección.",
  alternates: { canonical: "/expediente-repse" },
  openGraph: {
    title: "Expediente REPSE del proveedor: qué debe contener",
    description:
      "La lista de documentos por proveedor y periodo, cómo organizarlos y por qué un expediente auditable es tu defensa ante una inspección REPSE.",
    url: `${SITE_URL}/expediente-repse`,
    type: "article",
  },
};

const ARTICLE_LD = {
  "@context": "https://schema.org",
  "@type": "Article",
  "@id": `${SITE_URL}/expediente-repse#article`,
  headline: "Expediente REPSE del proveedor: qué debe contener",
  inLanguage: "es-MX",
  datePublished: "2026-06-18",
  dateModified: "2026-06-18",
  author: { "@type": "Organization", name: SITE_NAME, url: SITE_URL },
  publisher: { "@id": `${SITE_URL}/#organization` },
  mainEntityOfPage: `${SITE_URL}/expediente-repse`,
};

const FAQ: readonly ArticleFaqItem[] = [
  {
    question: "¿Qué documentos debe contener el expediente REPSE de un proveedor?",
    answer:
      "Como mínimo: el registro REPSE vigente acorde al servicio, el contrato del servicio especializado, la constancia de situación fiscal, las opiniones de cumplimiento positivas del SAT, IMSS e INFONAVIT, los CFDI de nómina y comprobantes de pago del personal asignado, y las declaraciones de IVA e ISR con sus acuses y los pagos de cuotas obrero-patronales y de vivienda del periodo.",
  },
  {
    question: "¿Cómo se organiza un expediente REPSE auditable?",
    answer:
      "Por proveedor, y dentro de cada proveedor por periodo e institución: cada documento ligado a la obligación que cumple (qué requisito, qué cuatrimestre, ante qué autoridad) y con el historial de los documentos que reemplazó. Una carpeta de archivos sueltos no es un expediente auditable: lo que la autoridad valora es poder seguir la trazabilidad de cada decisión.",
  },
  {
    question: "¿Cuánto tiempo debo conservar el expediente REPSE?",
    answer:
      "La evidencia que respalda la deducción de ISR y el acreditamiento de IVA debe conservarse durante el plazo en que esas operaciones pueden ser revisadas por la autoridad fiscal —en general, al menos cinco años—. En la práctica conviene conservar el expediente completo por todo ese periodo, por proveedor y por cuatrimestre.",
  },
  {
    question: "¿Por qué no basta con guardar los documentos en carpetas?",
    answer:
      "Porque un documento sin contexto no prueba cumplimiento. En una inspección necesitas demostrar qué documento cubre qué obligación, de qué periodo, ante qué institución y quién lo validó. Reconstruir eso desde carpetas compartidas y correos toma semanas; un expediente auditable lo tiene ligado desde el origen.",
  },
  {
    question: "¿Qué hace que un expediente sea 'auditable'?",
    answer:
      "Que cada documento viva ligado a su requisito, periodo e institución, con la decisión de revisión firmada y su historial de reemplazos, de modo que puedas generar en minutos el reporte y el paquete de evidencia que una inspección exige. Es la diferencia entre tener archivos y tener una defensa.",
  },
];

export default function ExpedienteRepsePage() {
  return (
    <MarketingArticleShell
      eyebrow="Control documental"
      title={
        <>
          El expediente REPSE del proveedor:{" "}
          <span className="text-[color:var(--text-teal)]">
            qué debe contener y por qué importa.
          </span>
        </>
      }
      intro="En una inspección REPSE, lo que te defiende no son tus buenas intenciones: es el expediente. Cada proveedor necesita un conjunto de documentos, ordenados por periodo e institución, que demuestre su cumplimiento y el tuyo como contratante. Esto es lo que debe contener y qué lo convierte en auditable."
      breadcrumbName="Expediente REPSE"
      path="/expediente-repse"
    >
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(ARTICLE_LD) }}
      />

      <ArticleSection id="que-es" heading="Qué es el expediente REPSE">
        <p>
          El expediente REPSE es el conjunto de evidencia que una empresa
          contratante reúne y conserva para demostrar que su proveedor de
          servicios especializados cumple, y que ella{" "}
          <Link
            href="/validar-proveedores-repse"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            verificó ese cumplimiento
          </Link>
          . No es un requisito burocrático: es la base que sostiene la
          deducibilidad de tus pagos y tu defensa frente a la{" "}
          <Link
            href="/obligado-solidario-repse"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            responsabilidad solidaria
          </Link>
          .
        </p>
      </ArticleSection>

      <ArticleSection id="que-contiene" heading="Qué debe contener, por proveedor y periodo">
        <ul className="list-disc space-y-2 pl-6">
          <li>Registro REPSE vigente acorde al servicio contratado.</li>
          <li>Contrato del servicio u obra especializada.</li>
          <li>Constancia de situación fiscal del proveedor.</li>
          <li>
            Opiniones de cumplimiento positivas del SAT, IMSS e INFONAVIT.
          </li>
          <li>
            CFDI de nómina y comprobantes de pago del personal asignado al
            servicio.
          </li>
          <li>
            Declaraciones de IVA e ISR con acuse, y pagos de cuotas
            obrero-patronales y de aportaciones de vivienda.
          </li>
          <li>
            Acuses de las informativas cuatrimestrales del proveedor (ICSOE
            ante el IMSS y SISUB ante el INFONAVIT).
          </li>
        </ul>
        <p>
          La clave no es solo tenerlos, sino tenerlos{" "}
          <strong>por cada periodo en que hubo pagos</strong>: el expediente
          se renueva cuatrimestre a cuatrimestre, no una sola vez.
        </p>
      </ArticleSection>

      <ArticleSection id="auditable" heading="De carpeta de archivos a expediente auditable">
        <p>
          Guardar PDFs en carpetas compartidas no es un expediente: es un
          archivo muerto. Lo que una inspección valora —y lo que te ahorra
          semanas de reconstrucción— es la <strong>trazabilidad</strong>:
          cada documento ligado a la obligación que cumple, al periodo y a la
          institución, con la decisión de revisión firmada y el historial de
          los documentos que reemplazó. Eso es lo que convierte un montón de
          archivos en una defensa.
        </p>
      </ArticleSection>

      <ArticleSection id="conservacion" heading="Cuánto conservarlo">
        <p>
          La evidencia que respalda la deducción del ISR y el acreditamiento
          del IVA debe conservarse durante el plazo en que la autoridad puede
          revisar esas operaciones —en general, al menos cinco años—. Conviene
          conservar el expediente completo por todo ese periodo, organizado
          por proveedor y por cuatrimestre, accesible sin depender de la
          memoria de quién guardó qué.
        </p>
      </ArticleSection>

      <ArticleSection id="como" heading="Cómo mantenerlo sin perderse">
        <p>
          Un{" "}
          <Link
            href="/software-repse"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            software de cumplimiento REPSE
          </Link>{" "}
          construye el expediente auditable de forma natural: el proveedor
          carga su evidencia ligada a cada requisito y periodo, la IA detecta
          inconsistencias, un revisor humano firma la decisión y la empresa
          contratante genera el reporte y el paquete de evidencia para una
          inspección en minutos —en PDF, Excel o HTML—. Es exactamente lo que
          hace CheckWise.
        </p>
      </ArticleSection>

      <ArticleFaq items={FAQ} path="/expediente-repse" />

      <ArticleCta
        title="Ten el expediente de cada proveedor listo para auditoría."
        body="Te mostramos en una demo de 30 minutos cómo CheckWise arma el expediente auditable por proveedor y periodo, y genera el paquete de evidencia para una inspección. Con datos de ejemplo, sobre el producto real."
      />
    </MarketingArticleShell>
  );
}
