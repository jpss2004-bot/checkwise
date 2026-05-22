import type { Metadata } from "next";

import {
  LegalDocShell,
  LegalSection,
} from "@/components/checkwise/legal/legal-doc-shell";

export const metadata: Metadata = {
  title: "Aviso de consentimiento · CheckWise",
  description:
    "Aviso de consentimiento informado para compartir tu evidencia REPSE con la empresa contratante a través de CheckWise.",
};

/**
 * /legal/consentimiento — Aviso de Consentimiento Informado.
 *
 * DRAFT (v0-draft). Pendiente de revisión final por Paco/Beko.
 * Cubre específicamente el consentimiento del proveedor para que la
 * empresa contratante reciba y revise su evidencia de cumplimiento
 * REPSE a través de CheckWise.
 */
export default function ConsentimientoPage() {
  return (
    <LegalDocShell
      eyebrow="Documento legal · CheckWise"
      title="Aviso de consentimiento informado"
      effectiveDate="22 de mayo de 2026"
      version="v0-draft"
    >
      <LegalSection heading="1. Propósito de este aviso">
        <p>
          Este aviso describe la información que compartirás con la
          empresa contratante (la “Empresa”) a través de CheckWise y
          recaba tu consentimiento informado para hacerlo. Acompaña al
          Aviso de Privacidad de LegalShelf y a los Términos de Uso de
          la Plataforma, sin sustituirlos.
        </p>
      </LegalSection>

      <LegalSection heading="2. Qué información compartirás">
        <p>
          Al utilizar CheckWise, la Empresa que solicitó tu inscripción
          tendrá acceso a los siguientes elementos:
        </p>
        <ul className="list-disc pl-6">
          <li>
            <strong>Datos de identificación de tu empresa</strong> (razón
            social, RFC, persona moral o física, contrato de referencia
            con la Empresa, datos de contacto operativo).
          </li>
          <li>
            <strong>Documentos de cumplimiento REPSE</strong> que subas a
            la Plataforma: comprobantes fiscales, cédulas, opiniones de
            cumplimiento, constancias de situación fiscal, avisos del
            IMSS, INFONAVIT, STPS y cualquier otro requisito vigente.
          </li>
          <li>
            <strong>Estado de cumplimiento y resultado de las
            revisiones</strong> realizadas por el equipo legal de
            LegalShelf, incluyendo aprobaciones, rechazos, solicitudes
            de aclaración y excepciones legales.
          </li>
          <li>
            <strong>Bitácora de carga</strong>: fechas en que subiste
            cada documento, periodos cubiertos, instituciones emisoras
            y, cuando aplique, la liga de remplazo entre cargas.
          </li>
        </ul>
        <p>
          No compartiremos con la Empresa: tu contraseña, los datos
          internos de auditoría técnica (por ejemplo, huellas criptográficas
          o identificadores de almacenamiento), ni información de otros
          proveedores que también utilicen la Plataforma.
        </p>
      </LegalSection>

      <LegalSection heading="3. Finalidad del intercambio">
        <p>
          La Empresa utilizará la información para evaluar tu
          cumplimiento de las obligaciones derivadas del régimen REPSE,
          gestionar el riesgo asociado a la contratación de servicios
          especializados y conservar evidencia auditable ante las
          autoridades correspondientes (SAT, IMSS, INFONAVIT, STPS) y
          ante cualquier revisión interna o externa.
        </p>
      </LegalSection>

      <LegalSection heading="4. Carácter del consentimiento">
        <p>
          Tu consentimiento es necesario para que CheckWise pueda
          operar tu expediente. Si no otorgas este consentimiento, no
          podremos compartir tu información con la Empresa contratante
          y, por lo tanto, no podremos prestarte el servicio.
        </p>
        <p>
          Puedes revocar este consentimiento en cualquier momento
          siguiendo el procedimiento descrito en el Aviso de
          Privacidad. La revocación no afecta la validez de las
          revisiones ni del intercambio de información ocurridos
          mientras el consentimiento estuvo vigente.
        </p>
      </LegalSection>

      <LegalSection heading="5. Registro de tu aceptación">
        <p>
          Al marcar la casilla correspondiente y continuar al espacio
          de tu proveedor, CheckWise registra los siguientes datos
          para constituir evidencia de tu aceptación:
        </p>
        <ul className="list-disc pl-6">
          <li>Identificador de tu cuenta y de tu espacio en la Plataforma.</li>
          <li>Fecha y hora exactas de la aceptación.</li>
          <li>Versión del paquete legal aceptado.</li>
          <li>
            Dirección IP y agente de usuario del dispositivo con el que
            otorgaste la aceptación.
          </li>
        </ul>
        <p>
          Este registro se conserva como bitácora interna de
          LegalShelf y no se comparte con la Empresa salvo
          requerimiento de autoridad competente.
        </p>
      </LegalSection>

      <LegalSection heading="6. Confirmación">
        <p>
          Al marcar la casilla “Acepto el aviso de privacidad, los
          términos de uso y el aviso de consentimiento” en la pantalla
          de bienvenida, manifiestas que has leído los tres documentos,
          que comprendes los términos en los que se compartirá tu
          información y que otorgas tu consentimiento de manera libre,
          específica e informada.
        </p>
      </LegalSection>
    </LegalDocShell>
  );
}
