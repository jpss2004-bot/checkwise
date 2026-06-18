import type { Metadata } from "next";
import Link from "next/link";

import {
  ArticleCta,
  ArticleSection,
  MarketingArticleShell,
} from "@/components/marketing/article-shell";
import { SITE_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Seguridad e infraestructura — CheckWise",
  description:
    "CheckWise protege expedientes legales sensibles con cifrado en tránsito y en reposo, control de acceso por rol, bloqueo por intentos fallidos, trazabilidad completa y backups automatizados.",
  alternates: { canonical: "/seguridad" },
  openGraph: {
    title: "Seguridad e infraestructura — CheckWise",
    description:
      "Cifrado, control de acceso, trazabilidad de auditoría y operaciones de seguridad en la plataforma de cumplimiento REPSE de CheckWise.",
    url: `${SITE_URL}/seguridad`,
    type: "article",
  },
};

// Security/infrastructure page → TechArticle, attributed to the shared
// Organization node (#organization from the homepage @graph).
const SECURITY_LD = {
  "@context": "https://schema.org",
  "@type": "TechArticle",
  "@id": `${SITE_URL}/seguridad#article`,
  headline: "Seguridad e infraestructura — CheckWise",
  inLanguage: "es-MX",
  about: "Seguridad de la plataforma de cumplimiento REPSE CheckWise",
  author: { "@id": `${SITE_URL}/#organization` },
  publisher: { "@id": `${SITE_URL}/#organization` },
  mainEntityOfPage: `${SITE_URL}/seguridad`,
};

export default function SeguridadPage() {
  return (
    <MarketingArticleShell
      eyebrow="Seguridad e infraestructura"
      title={
        <>
          Seguridad diseñada para{" "}
          <span className="text-[color:var(--text-teal)]">
            expedientes legales sensibles.
          </span>
        </>
      }
      intro="CheckWise maneja documentos de cumplimiento con valor jurídico: constancias fiscales, declaraciones patronales y evidencia que puede presentarse ante la STPS o el IMSS. Cada decisión de infraestructura parte de ese hecho."
      breadcrumbName="Seguridad"
      path="/seguridad"
    >
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(SECURITY_LD) }}
      />

      <ArticleSection id="infraestructura" heading="Infraestructura gestionada">
        <p>
          La plataforma corre en tres capas, cada una administrada por un
          proveedor especializado con disponibilidad de nivel empresarial:
        </p>
        <ul>
          <li>
            <strong>Frontend:</strong> desplegado en Vercel con red de borde
            global (CDN), HTTPS forzado en todos los dominios y sin secretos de
            servidor expuestos al navegador.
          </li>
          <li>
            <strong>API:</strong> contenedores gestionados en Render con
            autoescalado, TLS 1.2+ en todas las conexiones y sin acceso directo
            a la base de datos desde el exterior.
          </li>
          <li>
            <strong>Base de datos:</strong> Neon Postgres gestionado, cifrado en
            reposo por defecto, recuperación a cualquier punto en el tiempo
            (PITR) y backups automáticos diarios.
          </li>
        </ul>
      </ArticleSection>

      <ArticleSection id="cifrado" heading="Cifrado y protección de datos">
        <p>
          Los documentos de evidencia (PDFs, imágenes, constancias) se
          almacenan en Cloudflare R2 con cifrado en reposo del lado del servidor
          (SSE). Las URLs de descarga son prefirmadas con expiración corta —
          ningún archivo es accesible sin un token válido.
        </p>
        <p>
          Todo el tráfico entre el navegador y los servidores viaja sobre TLS.
          No se almacenan contraseñas en texto plano: se usa hashing con bcrypt
          y sal única por usuario.
        </p>
      </ArticleSection>

      <ArticleSection id="control-acceso" heading="Control de acceso por rol">
        <p>
          Cada sesión emite un token JWT de corta duración ligado a un rol
          específico. Las rutas de API rechazan peticiones sin token válido o
          con rol insuficiente — no existe escalación silenciosa de privilegios.
        </p>
        <p>Los roles de la plataforma son:</p>
        <ul>
          <li>
            <strong>Cliente admin:</strong> ve y gestiona solo los proveedores
            de su organización.
          </li>
          <li>
            <strong>Proveedor:</strong> accede exclusivamente a sus propios
            requisitos y carga de evidencia.
          </li>
          <li>
            <strong>Revisor CheckWise:</strong> valida documentos en la cola de
            revisión; no puede modificar datos de cliente ni de proveedor fuera
            de esa cola.
          </li>
          <li>
            <strong>Admin de plataforma:</strong> operación interna de Legal
            Shelf; acceso auditado y con doble confirmación para acciones
            destructivas.
          </li>
        </ul>
        <p>
          Tras cinco intentos de contraseña fallidos consecutivos, la cuenta
          queda bloqueada durante 15 minutos. El bloqueo se libera
          automáticamente o mediante acción del administrador.
        </p>
      </ArticleSection>

      <ArticleSection id="trazabilidad" heading="Trazabilidad completa">
        <p>
          Toda acción relevante —cambio de estado, aprobación de documento,
          edición de datos de usuario, acceso a un expediente— queda registrada
          con actor (usuario o sistema), acción, timestamp y dirección IP. Este
          registro es de solo escritura: no puede modificarse retroactivamente.
        </p>
        <p>
          En una inspección de la STPS o el IMSS, el equipo CheckWise puede
          exportar el historial completo de un proveedor — quién cargó cada
          documento, quién lo aprobó y cuándo — en formato PDF o Excel.
        </p>
      </ArticleSection>

      <ArticleSection id="operaciones" heading="Operaciones de seguridad">
        <ul>
          <li>
            Las dependencias de frontend y backend se monitorean con Dependabot;
            las actualizaciones de seguridad se aplican en el ciclo de
            despliegue regular.
          </li>
          <li>
            El código pasa análisis estático con CodeQL en cada cambio antes de
            llegar a producción.
          </li>
          <li>
            Los backups de la base de datos se verifican periódicamente con
            restauraciones de prueba en un entorno aislado.
          </li>
          <li>
            La separación de datos por inquilino (tenant isolation) es
            estructural: las consultas de API filtran por organización antes de
            cualquier otra cláusula. No existe una ruta que devuelva datos
            cruzados entre clientes.
          </li>
        </ul>
      </ArticleSection>

      <ArticleSection id="preguntas" heading="Preguntas de seguridad">
        <p>
          Si tu empresa tiene un proceso de evaluación de proveedores de
          software (vendor risk assessment, cuestionario de seguridad o
          revisión de contrato de procesamiento de datos), escríbenos. El
          equipo de Legal Shelf responde en el mismo día hábil desde CDMX.
        </p>
        <p>
          Para reportar una vulnerabilidad, contáctanos directamente a través
          del formulario de la{" "}
          <Link href="/#contacto" className="text-[color:var(--text-teal)] underline-offset-2 hover:underline">
            página principal
          </Link>
          {' con el asunto "Seguridad".'}
        </p>
      </ArticleSection>

      <ArticleCta
        title="¿Tienes preguntas sobre la seguridad de CheckWise?"
        body="El equipo de Legal Shelf responde evaluaciones de seguridad, cuestionarios de proveedores y preguntas técnicas el mismo día hábil desde CDMX."
      />
    </MarketingArticleShell>
  );
}
