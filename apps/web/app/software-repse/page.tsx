import type { Metadata } from "next";
import Link from "next/link";

import {
  ArticleCta,
  ArticleSection,
  MarketingArticleShell,
} from "@/components/marketing/article-shell";
import { SITE_URL } from "@/lib/site";

/**
 * /software-repse — commercial intent page.
 *
 * Targets the buyer queries ("software REPSE", "plataforma REPSE",
 * "plataforma de cumplimiento REPSE", "control documental REPSE").
 * Where /repse explains the regulation, this page explains what a
 * compliance platform must solve and maps it to CheckWise — same
 * single conversion path (demo request on the landing).
 */
export const metadata: Metadata = {
  title: "Software de cumplimiento REPSE para empresas y proveedores",
  description:
    "Qué debe resolver un software de cumplimiento REPSE: calendario de obligaciones, expediente auditable por proveedor, revisión documental con IA y validación humana, semáforo de riesgo y reportes para auditoría. Así lo hace CheckWise.",
  alternates: { canonical: "/software-repse" },
  openGraph: {
    title: "Software de cumplimiento REPSE para empresas y proveedores",
    description:
      "Calendario de obligaciones, expediente auditable, revisión documental y reportes de auditoría: qué debe tener una plataforma REPSE y cómo lo resuelve CheckWise.",
    url: `${SITE_URL}/software-repse`,
    type: "article",
  },
};

export default function SoftwareRepsePage() {
  return (
    <MarketingArticleShell
      eyebrow="Plataforma de cumplimiento"
      title={
        <>
          Software de cumplimiento REPSE:{" "}
          <span className="text-[color:var(--text-teal)]">
            qué debe resolver y cómo lo hace CheckWise.
          </span>
        </>
      }
      intro="Cumplir REPSE no falla por desconocimiento de la norma: falla por operación. Decenas de proveedores, cientos de documentos por cuatrimestre y un riesgo fiscal que recae en quien contrata. Esto es lo que una plataforma de cumplimiento REPSE tiene que resolver — empezando por la prevención del riesgo, no solo el seguimiento."
      breadcrumbName="Software de cumplimiento REPSE"
      path="/software-repse"
    >
      <ArticleSection
        id="por-que-no-excel"
        heading="Por qué las hojas de cálculo se quedan cortas"
      >
        <p>
          El control REPSE típico vive en un Excel por proveedor, carpetas
          compartidas y recordatorios de correo. Funciona con tres
          proveedores; se rompe con quince. Los vencimientos son distintos
          por requisito, periodo e institución (
          <Link
            href="/repse"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            renovación trianual, ICSOE, SISUB, opiniones de cumplimiento
          </Link>
          ), los documentos se sustituyen unos a otros, y nadie deja rastro
          de quién revisó qué ni con qué criterio. Cuando llega una
          inspección o una auditoría interna, reconstruir la historia toma
          semanas.
        </p>
      </ArticleSection>

      <ArticleSection
        id="que-debe-tener"
        heading="Qué debe tener una plataforma de cumplimiento REPSE"
      >
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Calendario de obligaciones</strong> por requisito,
            periodo e institución, que muestre qué falta, qué vence y qué
            está en riesgo — antes de la fecha límite, no después.
          </li>
          <li>
            <strong>Expediente digital por proveedor</strong>, con cada
            documento ligado a su obligación y su periodo, y con historial
            de reemplazos cuando llega una versión nueva.
          </li>
          <li>
            <strong>Revisión documental real</strong>, no solo
            almacenamiento: validar que el documento corresponde al
            requisito, al periodo y al proveedor correcto.
          </li>
          <li>
            <strong>Semáforo de riesgo del portafolio</strong>, para que la
            empresa contratante vea de un vistazo qué proveedores están al
            día, en proceso o en riesgo.
          </li>
          <li>
            <strong>Reportes listos para auditoría</strong>: exportables,
            con el estado de cumplimiento y la evidencia detrás de cada
            conclusión.
          </li>
          <li>
            <strong>Registro auditable de decisiones</strong>: quién aprobó,
            cuándo y por qué — porque ante una autoridad, el criterio
            importa tanto como el documento.
          </li>
        </ul>
      </ArticleSection>

      <ArticleSection id="como-lo-hace-checkwise" heading="Cómo lo hace CheckWise">
        <p>
          CheckWise pone a proveedor, empresa contratante y equipo revisor
          sobre <strong>un mismo expediente auditable</strong>. El proveedor
          carga su evidencia con un flujo guiado por requisito y periodo; la
          inteligencia artificial analiza cada documento y detecta
          inconsistencias; y un revisor humano toma la decisión final, que
          queda firmada y registrada. La empresa contratante ve su
          portafolio completo con semáforo de riesgo y genera reportes
          ejecutivos y paquetes de auditoría en PDF, Excel o HTML.
        </p>
        <p>
          La IA asiste; <strong>la decisión legal siempre es humana</strong>.
          CheckWise es una solución de Legal Shelf, construida en Ciudad de
          México por un equipo legal que opera REPSE todos los días.
        </p>
      </ArticleSection>

      <ArticleSection id="para-quien" heading="Para quién es">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Empresas contratantes</strong> que reciben servicios
            especializados y necesitan blindar la deducibilidad y el
            acreditamiento de sus pagos con evidencia continua.
          </li>
          <li>
            <strong>Proveedores registrados en el REPSE</strong> que
            atienden a varios clientes y quieren entregar su evidencia una
            sola vez, bien, y a tiempo.
          </li>
          <li>
            <strong>Equipos legales y de cumplimiento</strong> que hoy
            sostienen el control en hojas de cálculo y necesitan
            trazabilidad de cada decisión.
          </li>
        </ul>
      </ArticleSection>

      <ArticleCta
        title="Compara tu control actual contra CheckWise en 30 minutos."
        body="Te mostramos el calendario de obligaciones, el expediente auditable y los reportes con datos de ejemplo, sobre el producto real. Respondemos el mismo día hábil."
      />
    </MarketingArticleShell>
  );
}
