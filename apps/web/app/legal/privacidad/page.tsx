import type { Metadata } from "next";

import {
  LegalDocShell,
  LegalSection,
} from "@/components/checkwise/legal/legal-doc-shell";

export const metadata: Metadata = {
  title: "Aviso de privacidad · CheckWise",
  description:
    "Aviso de privacidad de CheckWise (LegalShelf) conforme a la Ley Federal de Protección de Datos Personales en Posesión de los Particulares.",
};

/**
 * /legal/privacidad — Aviso de Privacidad Integral.
 *
 * DRAFT (v0-draft). Pendiente de revisión final por Paco/Beko.
 * Estructurado para cumplir los elementos mínimos del artículo 16 de
 * la LFPDPPP y los lineamientos del INAI para avisos integrales.
 */
export default function PrivacidadPage() {
  return (
    <LegalDocShell
      eyebrow="Documento legal · CheckWise"
      title="Aviso de privacidad integral"
      effectiveDate="22 de mayo de 2026"
      version="v0-draft"
    >
      <LegalSection heading="1. Identidad y domicilio del responsable">
        <p>
          LegalShelf, S.A. de C.V. (en adelante, “LegalShelf” o “el
          Responsable”), con domicilio en la Ciudad de México, opera la
          plataforma CheckWise y es responsable del tratamiento de tus
          datos personales conforme a la Ley Federal de Protección de
          Datos Personales en Posesión de los Particulares (LFPDPPP),
          su Reglamento y los Lineamientos del Aviso de Privacidad
          emitidos por el Instituto Nacional de Transparencia, Acceso a
          la Información y Protección de Datos Personales (INAI).
        </p>
        <p>
          Para cualquier asunto relacionado con la protección de tus
          datos personales puedes contactar al área designada en{" "}
          <a
            href="mailto:privacidad@legalshelf.mx"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            privacidad@legalshelf.mx
          </a>
          .
        </p>
      </LegalSection>

      <LegalSection heading="2. Datos personales que se recaban">
        <p>
          CheckWise recaba los datos personales que tú u otro
          responsable (por ejemplo, la empresa contratante para la que
          actúas como proveedor) nos proporciona directamente al
          registrarte y utilizar la plataforma. Los datos se agrupan en
          las siguientes categorías:
        </p>
        <ul className="list-disc pl-6">
          <li>
            <strong>Datos de identificación</strong>: nombre completo,
            cargo, RFC del proveedor, razón social, domicilio fiscal y
            correo electrónico corporativo.
          </li>
          <li>
            <strong>Datos de contacto</strong>: teléfono, canal preferido
            de comunicación (correo electrónico o mensajería).
          </li>
          <li>
            <strong>Datos derivados del cumplimiento REPSE</strong>:
            comprobantes fiscales, cédulas, opiniones de cumplimiento,
            constancias de situación fiscal, avisos ante el IMSS,
            INFONAVIT y STPS, así como la metadata extraída de los
            archivos (fecha de emisión, periodo cubierto, instituciones
            emisoras y resultado de la revisión).
          </li>
          <li>
            <strong>Datos técnicos de auditoría</strong>: dirección IP,
            agente de usuario, marcas de tiempo de aceptación de
            documentos legales y bitácora de eventos en la plataforma.
          </li>
        </ul>
        <p>
          No se recaban categorías de datos personales sensibles. Si
          algún archivo subido a la plataforma contiene incidentalmente
          datos sensibles (por ejemplo, datos de salud en un acuse
          médico), serán tratados con las mismas medidas de seguridad
          aplicables al resto del expediente.
        </p>
      </LegalSection>

      <LegalSection heading="3. Finalidades del tratamiento">
        <p>
          <strong>Finalidades primarias</strong> (necesarias para la
          relación jurídica y la prestación del servicio):
        </p>
        <ul className="list-disc pl-6">
          <li>
            Operar la plataforma CheckWise y permitir que los
            proveedores registren, suban y consulten su expediente
            REPSE.
          </li>
          <li>
            Compartir el estado de cumplimiento con la empresa
            contratante que solicitó la auditoría del proveedor.
          </li>
          <li>
            Permitir que el equipo legal de LegalShelf revise, apruebe
            o solicite aclaraciones sobre los documentos subidos.
          </li>
          <li>
            Mantener un registro auditable de cambios de estado,
            decisiones de revisión y aceptaciones legales.
          </li>
          <li>
            Cumplir con obligaciones legales, fiscales y regulatorias
            aplicables, incluyendo la conservación de evidencia de
            cumplimiento REPSE.
          </li>
        </ul>
        <p>
          <strong>Finalidades secundarias</strong> (no necesarias pero
          que requieren de tu consentimiento):
        </p>
        <ul className="list-disc pl-6">
          <li>
            Enviarte comunicaciones sobre nuevas funciones, mejoras y
            mejores prácticas de cumplimiento.
          </li>
          <li>
            Realizar estudios estadísticos agregados sobre el desempeño
            de la plataforma y los patrones de cumplimiento.
          </li>
        </ul>
        <p>
          Si no deseas que tus datos sean tratados para alguna de las
          finalidades secundarias puedes escribirnos a{" "}
          <a
            href="mailto:privacidad@legalshelf.mx"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            privacidad@legalshelf.mx
          </a>{" "}
          en cualquier momento. La negativa no será motivo para negarte
          el servicio.
        </p>
      </LegalSection>

      <LegalSection heading="4. Transferencias de datos">
        <p>
          LegalShelf puede transferir tus datos personales a los
          siguientes terceros, exclusivamente para cumplir con las
          finalidades primarias descritas en este aviso:
        </p>
        <ul className="list-disc pl-6">
          <li>
            <strong>Empresa contratante</strong>: la empresa que solicitó
            tu inscripción a CheckWise recibirá el resultado de la
            revisión de tu expediente y la metadata asociada para
            evaluar tu cumplimiento REPSE.
          </li>
          <li>
            <strong>Encargados del tratamiento</strong>: proveedores
            tecnológicos contratados por LegalShelf (alojamiento en
            nube, base de datos administrada, almacenamiento de
            archivos, envío de notificaciones por correo y mensajería)
            que actúan bajo contrato escrito y sujetos a las
            obligaciones del artículo 50 del Reglamento de la LFPDPPP.
          </li>
          <li>
            <strong>Autoridades competentes</strong>: cuando una orden
            de autoridad debidamente fundada lo requiera.
          </li>
        </ul>
        <p>
          Salvo en los supuestos anteriores no se realizan
          transferencias adicionales sin tu consentimiento expreso.
        </p>
      </LegalSection>

      <LegalSection heading="5. Derechos ARCO y revocación del consentimiento">
        <p>
          Puedes ejercer en cualquier momento tus derechos de Acceso,
          Rectificación, Cancelación y Oposición (ARCO), así como
          revocar el consentimiento que nos hayas otorgado, enviando
          una solicitud a{" "}
          <a
            href="mailto:privacidad@legalshelf.mx"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            privacidad@legalshelf.mx
          </a>{" "}
          con la siguiente información:
        </p>
        <ul className="list-disc pl-6">
          <li>Nombre completo y correo electrónico de contacto.</li>
          <li>Descripción clara del derecho que deseas ejercer.</li>
          <li>
            Documento que acredite tu identidad o, en su caso, la
            representación legal de quien actúa por ti.
          </li>
        </ul>
        <p>
          LegalShelf responderá tu solicitud en un plazo máximo de
          veinte días hábiles. La revocación del consentimiento puede
          afectar la prestación del servicio cuando dicho consentimiento
          sea condición indispensable para operar tu expediente REPSE.
        </p>
      </LegalSection>

      <LegalSection heading="6. Medidas de seguridad">
        <p>
          LegalShelf implementa medidas administrativas, técnicas y
          físicas razonables para proteger tus datos personales contra
          daño, pérdida, alteración, destrucción o uso, acceso o
          tratamiento no autorizado. Estas medidas incluyen cifrado en
          tránsito, almacenamiento separado de archivos y metadata,
          control de accesos por rol, bitácora de auditoría inmutable y
          revisiones periódicas de seguridad.
        </p>
      </LegalSection>

      <LegalSection heading="7. Conservación de los datos">
        <p>
          Conservaremos tus datos personales mientras exista una
          relación contractual entre tu empresa proveedora y la empresa
          contratante, así como durante el periodo adicional requerido
          por las disposiciones fiscales y regulatorias aplicables.
          Concluido ese plazo los datos serán bloqueados antes de su
          cancelación definitiva.
        </p>
      </LegalSection>

      <LegalSection heading="8. Cambios al aviso de privacidad">
        <p>
          Cualquier modificación a este aviso será publicada en esta
          misma página y se notificará dentro de la plataforma. Si los
          cambios afectan finalidades primarias o transferencias de
          datos, se te solicitará una nueva aceptación antes de
          continuar usando el servicio.
        </p>
      </LegalSection>

      <LegalSection heading="9. INAI">
        <p>
          Si consideras que tu derecho a la protección de datos
          personales ha sido vulnerado, puedes acudir al Instituto
          Nacional de Transparencia, Acceso a la Información y
          Protección de Datos Personales (
          <a
            href="https://home.inai.org.mx"
            rel="noopener noreferrer"
            target="_blank"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            home.inai.org.mx
          </a>
          ).
        </p>
      </LegalSection>
    </LegalDocShell>
  );
}
