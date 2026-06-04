import type { Metadata } from "next";

import {
  LegalDocShell,
  LegalSection,
} from "@/components/checkwise/legal/legal-doc-shell";

export const metadata: Metadata = {
  title: "Aviso de consentimiento informado · CheckWise",
  description:
    "Aviso de consentimiento informado para compartir tu evidencia REPSE con la empresa contratante a través de CheckWise.",
};

/**
 * /legal/consentimiento — Aviso de consentimiento informado.
 *
 * v2 (vigente desde 3 de junio de 2026). Copy reproduced verbatim from
 * the legal review of 2026-06-03. The `version` prop matches
 * CURRENT_LEGAL_CONSENT_VERSION on the backend.
 */
export default function ConsentimientoPage() {
  return (
    <LegalDocShell
      eyebrow="Documento legal · CheckWise"
      title="Aviso de consentimiento informado"
      effectiveDate="3 de junio de 2026"
      version="v2"
    >
      <LegalSection heading="1. Propósito de este aviso">
        <p>
          Este aviso describe la información que se compartirá con la empresa
          contratante (la “Empresa”) a través de CheckWise y recaba tu
          consentimiento informado para hacerlo. Acompaña al Aviso de Privacidad
          de LegalShelf y a los Términos de Uso de la Plataforma, sin
          sustituirlos.
        </p>
      </LegalSection>

      <LegalSection heading="2. Qué información se compartirá">
        <p>
          Al utilizar CheckWise, la Empresa que solicitó la inscripción del
          Proveedor tendrá acceso a los siguientes elementos:
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            Datos de identificación de la empresa (razón social, RFC, persona
            moral o física, contrato de referencia con la Empresa, datos de
            contacto operativo).
          </li>
          <li>
            Documentos de cumplimiento REPSE que se subirán a la Plataforma:
            comprobantes fiscales, cédulas, opiniones de cumplimiento,
            constancias de situación fiscal, avisos del IMSS, INFONAVIT, STPS y
            cualquier otro requisito vigente.
          </li>
          <li>
            Estado de cumplimiento y resultado de las revisiones realizadas por
            el equipo legal de LegalShelf, incluyendo aprobaciones, rechazos,
            solicitudes de aclaración y excepciones legales.
          </li>
          <li>
            Bitácora de carga: fechas en que se subió cada documento, periodos
            cubiertos, instituciones emisoras y, cuando aplique, la liga de
            remplazo entre cargas.
          </li>
        </ul>
        <p>
          No se compartirá con la Empresa: contraseña, los datos internos de
          auditoría técnica (por ejemplo, huellas criptográficas o
          identificadores de almacenamiento), ni información de otros
          proveedores que también utilicen la Plataforma.
        </p>
      </LegalSection>

      <LegalSection heading="3. Finalidad del intercambio">
        <p>
          La Empresa utilizará la información para evaluar el cumplimiento de
          las obligaciones derivadas del régimen REPSE, gestionar el riesgo
          asociado a la contratación de servicios especializados y conservar
          evidencia auditable ante las autoridades correspondientes (SAT, IMSS,
          INFONAVIT, STPS) y ante cualquier revisión interna o externa.
        </p>
      </LegalSection>

      <LegalSection heading="4. Carácter del consentimiento">
        <p>
          Tu consentimiento es necesario para que CheckWise pueda operar tu
          expediente. Si no otorgas este consentimiento, no podremos compartir
          tu información con la Empresa contratante y, por lo tanto, no podremos
          prestarte el servicio.
        </p>
        <p>
          Puedes revocar este consentimiento en cualquier momento siguiendo el
          procedimiento descrito en el Aviso de Privacidad. La revocación no
          afecta la validez de las revisiones ni del intercambio de información
          ocurridos mientras el consentimiento estuvo vigente.
        </p>
      </LegalSection>

      <LegalSection heading="5. Registro de aceptación">
        <p>
          Al marcar la casilla correspondiente y continuar al espacio de tu
          proveedor, CheckWise registra los siguientes datos para constituir
          evidencia de tu aceptación:
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>Identificador de cuenta y espacio en la Plataforma.</li>
          <li>Fecha y hora exactas de la aceptación.</li>
          <li>Versión del paquete legal aceptado.</li>
          <li>
            Dirección IP y agente de usuario del dispositivo con el que se
            otorgó la aceptación.
          </li>
        </ul>
        <p>
          Este registro se conserva como bitácora interna de LegalShelf y no se
          comparte con la Empresa salvo requerimiento de autoridad competente.
        </p>
      </LegalSection>

      <LegalSection heading="6. Confirmación">
        <p>
          Al marcar la casilla “Acepto el aviso de privacidad, los términos de
          uso y el aviso de consentimiento” en la pantalla de bienvenida, se
          manifiesta que se han leído los tres documentos, que comprendes los
          términos en los que se compartirá tu información y que otorgas tu
          consentimiento de manera libre, específica e informada.¡
        </p>
      </LegalSection>
    </LegalDocShell>
  );
}
