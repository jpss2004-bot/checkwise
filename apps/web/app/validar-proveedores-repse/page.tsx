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
 * /validar-proveedores-repse — contratante-intent cluster page.
 *
 * Targets the "cómo validar / verificar proveedores REPSE", "verificar
 * vigencia REPSE", "validación de proveedores" query family — the core
 * wedge: the obligation falls on the company that contracts. Funnels to
 * /software-repse (automation) and reinforces /repse and the other
 * cluster pages. Evergreen: amounts in UMA, cadences not dates.
 */
export const metadata: Metadata = {
  title: "Cómo validar a tus proveedores REPSE",
  description:
    "Guía práctica para empresas contratantes: cómo verificar que un proveedor tiene su registro REPSE vigente, qué evidencia documental reunir por periodo y con qué frecuencia repetir la validación para no perder deducibilidad ni volverte obligado solidario.",
  alternates: { canonical: "/validar-proveedores-repse" },
  openGraph: {
    title: "Cómo validar a tus proveedores REPSE — guía para contratantes",
    description:
      "Verifica la vigencia del registro, reúne la evidencia por periodo y repite la validación de forma continua. La guía del contratante para no volverse obligado solidario.",
    url: `${SITE_URL}/validar-proveedores-repse`,
    type: "article",
  },
};

const ARTICLE_LD = {
  "@context": "https://schema.org",
  "@type": "Article",
  "@id": `${SITE_URL}/validar-proveedores-repse#article`,
  headline: "Cómo validar a tus proveedores REPSE",
  inLanguage: "es-MX",
  datePublished: "2026-06-18",
  dateModified: "2026-06-18",
  author: { "@type": "Organization", name: SITE_NAME, url: SITE_URL },
  publisher: { "@id": `${SITE_URL}/#organization` },
  mainEntityOfPage: `${SITE_URL}/validar-proveedores-repse`,
};

const FAQ: readonly ArticleFaqItem[] = [
  {
    question: "¿Cómo sé si mi proveedor tiene su REPSE vigente?",
    answer:
      "Consultando el padrón público de la STPS con el número de registro o el RFC del proveedor: ahí aparece el estatus del registro y las actividades autorizadas. La validación no termina ahí: además de que el registro exista, debe estar vigente y amparar precisamente el servicio que te presta.",
  },
  {
    question: "¿Dónde se consulta el padrón REPSE?",
    answer:
      "En el portal oficial de la STPS (repse.stps.gob.mx), que publica el registro de prestadoras de servicios especializados. Es la fuente para confirmar que el registro existe y está activo; la evidencia de cumplimiento fiscal y de seguridad social (opiniones, CFDI, declaraciones) la entrega el propio proveedor.",
  },
  {
    question: "¿Cada cuánto debo validar a un proveedor REPSE?",
    answer:
      "De forma continua mientras dure la relación, no solo al contratar. Como mínimo conviene revisar la vigencia del registro y la evidencia documental cada periodo en que existan pagos —la cadencia natural es cuatrimestral, ligada a ICSOE y SISUB— y siempre antes de deducir o acreditar un CFDI del proveedor.",
  },
  {
    question: "¿Qué pasa si no valido a mis proveedores REPSE?",
    answer:
      "Quien recibe servicios especializados de un proveedor sin registro vigente se expone a multas de 2,000 a 50,000 veces la UMA, a perder la deducción de ISR y el acreditamiento de IVA sobre esos pagos, y a responsabilidad solidaria frente a los trabajadores del proveedor. La obligación de verificar y conservar evidencia recae sobre la empresa contratante.",
  },
  {
    question: "¿Basta con pedir el registro REPSE una vez al firmar el contrato?",
    answer:
      "No. Un proveedor que cumplía al firmar puede dejar de cumplir meses después: no renovar a tiempo, perder una opinión de cumplimiento positiva o dejar de presentar sus informativas. Por eso la validación es un control recurrente por periodo, no un trámite único de alta.",
  },
  {
    question: "¿Puedo automatizar la validación de mis proveedores?",
    answer:
      "Sí. Una plataforma de cumplimiento REPSE centraliza el calendario de obligaciones por proveedor, recibe y revisa la evidencia, marca con un semáforo de riesgo lo que está al día, en proceso o vencido, y genera el expediente auditable. Es la diferencia entre validar a mano sobre hojas de cálculo y prevenir el riesgo de forma sistemática.",
  },
];

export default function ValidarProveedoresRepsePage() {
  return (
    <MarketingArticleShell
      eyebrow="Guía para contratantes"
      title={
        <>
          Cómo validar a tus proveedores REPSE{" "}
          <span className="text-[color:var(--text-teal)]">
            sin volverte obligado solidario.
          </span>
        </>
      }
      intro="Si tu empresa recibe servicios especializados, la ley te obliga a verificar que cada proveedor cumple con el REPSE y a conservar la evidencia. No es un trámite del proveedor: es tu responsabilidad como contratante, y de ella dependen la deducibilidad de tus pagos y tu exposición a multas. Esta es la forma práctica de hacerlo bien."
      breadcrumbName="Cómo validar proveedores REPSE"
      path="/validar-proveedores-repse"
    >
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(ARTICLE_LD) }}
      />

      <ArticleSection id="por-que-tu" heading="Por qué la validación es tu responsabilidad">
        <p>
          La reforma en materia de subcontratación dejó claro que el riesgo
          se comparte. La legislación fiscal condiciona la{" "}
          <strong>deducción del ISR y el acreditamiento del IVA</strong> de
          los servicios especializados a que el contratante verifique que su
          proveedor tiene registro REPSE vigente y a que conserve la
          evidencia documental de su cumplimiento. Si no lo haces, el gasto
          deja de ser deducible y puedes responder solidariamente por las
          obligaciones laborales y de seguridad social del proveedor.
        </p>
        <p>
          Dicho de otro modo: el proveedor se registra y opera, pero quien
          contrata es quien pierde dinero y asume el riesgo si algo falla.
          Por eso conviene tratar la validación como un control propio y
          continuo, no como un favor que le pides al proveedor.
        </p>
      </ArticleSection>

      <ArticleSection id="paso-1" heading="Paso 1: verifica el registro REPSE vigente">
        <p>
          Empieza por lo básico: confirma en el{" "}
          <Link
            href="https://repse.stps.gob.mx/"
            target="_blank"
            rel="noreferrer noopener"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            padrón público de la STPS
          </Link>{" "}
          que el registro del proveedor existe y está activo. Pero no te
          quedes en el sí/no: revisa que el registro{" "}
          <strong>ampare el servicio específico</strong> que te presta y que
          no esté por vencer. El{" "}
          <Link
            href="/repse"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            registro REPSE
          </Link>{" "}
          tiene vigencia de tres años y puede cancelarse antes si el
          proveedor deja de cumplir.
        </p>
      </ArticleSection>

      <ArticleSection id="paso-2" heading="Paso 2: reúne la evidencia documental del periodo">
        <p>
          El registro vigente es necesario, pero no suficiente. Para blindar
          la deducibilidad necesitas un{" "}
          <Link
            href="/expediente-repse"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            expediente por proveedor y por periodo
          </Link>{" "}
          que incluya, como mínimo:
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>Registro REPSE vigente acorde al servicio contratado.</li>
          <li>Contrato del servicio especializado.</li>
          <li>Constancia de situación fiscal del proveedor.</li>
          <li>Opiniones de cumplimiento positivas del SAT, IMSS e INFONAVIT.</li>
          <li>
            CFDI de nómina y comprobantes de pago del personal asignado al
            servicio.
          </li>
          <li>
            Declaraciones de IVA e ISR con acuse y pagos de cuotas
            obrero-patronales y de vivienda.
          </li>
        </ul>
      </ArticleSection>

      <ArticleSection id="paso-3" heading="Paso 3: repite la validación cada periodo">
        <p>
          Aquí es donde la mayoría de las empresas tropieza. La verificación{" "}
          <strong>no se hace una vez</strong>: se repite mientras existan
          pagos al proveedor. La cadencia natural es cuatrimestral, alineada
          con las informativas ICSOE (IMSS) y SISUB (INFONAVIT) que el
          proveedor debe presentar en enero, mayo y septiembre. Antes de
          deducir o acreditar cualquier CFDI, el expediente de ese periodo
          debe estar completo.
        </p>
      </ArticleSection>

      <ArticleSection id="errores" heading="Errores comunes al validar proveedores">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            Validar solo al firmar y no volver a revisar durante la relación.
          </li>
          <li>
            Confirmar que el registro existe, pero no que ampara el servicio
            contratado ni que sigue vigente.
          </li>
          <li>
            Guardar documentos sueltos en carpetas y correos, sin ligarlos a
            su periodo e institución — imposible de auditar después.
          </li>
          <li>
            No detectar a tiempo un vencimiento o una opinión de cumplimiento
            que pasó a negativa.
          </li>
        </ul>
      </ArticleSection>

      <ArticleSection id="automatizar" heading="Cómo automatizar la validación">
        <p>
          Validar a mano funciona con tres proveedores; con quince se vuelve
          imposible sostenerlo cada cuatrimestre. Un{" "}
          <Link
            href="/software-repse"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            software de cumplimiento REPSE
          </Link>{" "}
          centraliza el calendario de obligaciones por proveedor, recibe y
          revisa la evidencia con apoyo de IA y validación humana, muestra un
          semáforo de riesgo del portafolio y genera el expediente auditable
          listo para una inspección. Es pasar de reaccionar a prevenir — y es
          exactamente lo que hace CheckWise.
        </p>
      </ArticleSection>

      <ArticleFaq items={FAQ} path="/validar-proveedores-repse" />

      <ArticleCta
        title="Valida a todos tus proveedores REPSE desde un solo lugar."
        body="Te mostramos en una demo de 30 minutos cómo CheckWise verifica vigencias, reúne la evidencia por periodo y prende el semáforo de riesgo antes de que llegue una multa. Con datos de ejemplo, sobre el producto real."
      />
    </MarketingArticleShell>
  );
}
