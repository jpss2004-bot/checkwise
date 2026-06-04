import type { Metadata } from "next";

import {
  LegalDocShell,
  LegalSection,
} from "@/components/checkwise/legal/legal-doc-shell";

export const metadata: Metadata = {
  title: "Política de privacidad · CheckWise",
  description:
    "Política de privacidad de CheckWise (LegalShelf) como encargado del tratamiento, conforme a la Ley Federal de Protección de Datos Personales en Posesión de los Particulares.",
};

const EMAIL_LINK_CLASS =
  "font-medium text-[color:var(--text-brand)] hover:underline";

/**
 * /legal/privacidad — Política de privacidad.
 *
 * v2 (vigente desde 3 de junio de 2026). Copy promoted from the legal
 * review of 2026-06-03, which reframes LegalShelf as *encargado* (no
 * longer *responsable*), updates the regime to "la Ley" + Secretaría
 * Anticorrupción y Buen Gobierno, enumerates sensitive data, and
 * reworks the ARCO flow. Text is reproduced verbatim from the signed
 * document (including its typos) per the integration brief; the
 * `version` prop matches CURRENT_LEGAL_CONSENT_VERSION on the backend.
 */
export default function PrivacidadPage() {
  return (
    <LegalDocShell
      eyebrow="Documento legal · CheckWise"
      title="Política de privacidad"
      effectiveDate="3 de junio de 2026"
      version="v2"
    >
      <LegalSection heading="Identidad y domicilio del Encargado">
        <p>
          LegalShelf, S.A. de C.V. (en adelante, “LegalShelf” o “el
          Encargado”), con domicilio en la Ciudad de México, opera la
          plataforma CheckWise y es encargado del tratamiento de los datos
          personales por cuenta de la persona física o moral de carácter
          privado que lleva a cabo el tratamiento de datos personales (el
          “Responsable”) conforme a la Ley Federal de Protección de Datos
          Personales en Posesión de los Particulares (en adelante, la
          “Ley”), su Reglamento y los Lineamientos emitidos por la
          Secretaría Anticorrupción y Buen Gobierno (en adelante, la
          “Secretaría”)
        </p>
        <p>
          Para cualquier asunto relacionado con la protección de datos
          personales se puede contactar al área designada en{" "}
          <a href="mailto:privacidad@legalshelf.mx" className={EMAIL_LINK_CLASS}>
            privacidad@legalshelf.mx
          </a>
          .
        </p>
      </LegalSection>

      <LegalSection heading="Datos personales remitidos">
        <p>
          CheckWise trata los datos personales que el Responsable le remite
          directamente al registrarse y utilizar la plataforma, así como los
          sustraídos de la documentación cargada. Los datos se agrupan en las
          siguientes categorías:
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Datos de identificación:</strong>
            <ul className="mt-1 list-disc space-y-1 pl-6">
              <li>Nombre completo de los trabajadores</li>
              <li>Cargo de los trabajadores</li>
              <li>RFC de la sociedad</li>
              <li>RFC de los trabajadores</li>
              <li>CURP del trabajador (dato sensible)</li>
              <li>CURP de proveedor persona física (dato sensible)</li>
              <li>Imagen de proveedor persona física (dato sensible)</li>
              <li>
                Fecha de nacimiento de proveedor persona física (dato
                sensible)
              </li>
              <li>Firma de proveedor persona física.</li>
              <li>
                Número de Seguridad Social de trabajadores del proveedor.
              </li>
            </ul>
          </li>
          <li>
            <strong>Datos patriomoniales:</strong>
            <ul className="mt-1 list-disc space-y-1 pl-6">
              <li>
                Cuotas obrero-patronales de trabajadores del proveedor (dato
                sensible)
              </li>
              <li>Salario base de cotización (dato sensible)</li>
              <li>Aportaciones de vivienda (dato sensible)</li>
            </ul>
          </li>
          <li>
            <strong>Datos técnicos de auditoría:</strong>
            <ul className="mt-1 list-disc space-y-1 pl-6">
              <li>Dirección IP</li>
              <li>Agente de usuario</li>
            </ul>
          </li>
        </ul>
      </LegalSection>

      <LegalSection heading="Finalidades del tratamiento">
        <p>
          Los datos personales recabados a través de la plataforma son
          tratados exclusivamente en calidad de encargado, en los términos del
          artículo 3, fracción VI de la Ley, por lo que su tratamiento se
          encuentra en todo momento subordinado a las instrucciones y
          finalidades determinadas por el(los) Responsable(s) de los datos
          personales. En consecuencia, el Encargado no decide sobre el
          tratamiento ni lo utiliza para fines propios, limitándose a fungir
          como intermediario y procesador de la información, sin asumir
          determinación alguna sobre las finalidades, medios o alcance del
          tratamiento. Esto estará sujeto al Aviso de Privacidad del(los)
          Resposable(s), así como al Contrato celebrado entre CheckWise y la
          Empresa Encargada.
        </p>
        <p>
          Como parte de los servicios contratados por la Empresa Contratante
          (como se define más adelante), el Encargado tendrá el siguiente
          alcance con los datos personales:
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            Operar la plataforma CheckWise y permitir que los proveedores
            registren, suban y consulten su expediente REPSE.
          </li>
          <li>
            Permitir que la Empresa Contratante acceda a los documentos
            cargados por sus proveedores y compartir el estado de cumplimiento.
          </li>
          <li>
            Permitir que el equipo legal de LegalShelf revise, apruebe o
            solicite aclaraciones sobre los documentos subidos.
          </li>
        </ul>
        <p>
          Para administración y gestión interna, se llevarán a cabo los
          siguientes controles:
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            Mantener un registro auditable de cambios de estado, decisiones de
            revisión y aceptaciones legales.
          </li>
          <li>
            Enviar comunicaciones sobre nuevas funciones, mejoras y mejores
            prácticas de cumplimiento.
          </li>
          <li>
            Realizar estudios estadísticos agregados sobre el desempeño de la
            plataforma y los patrones de cumplimiento.
          </li>
        </ul>
        <p>
          Si no se desea que los datos sean tratados para alguno de los últimos
          tres puntos, se puede escribir a{" "}
          <a href="mailto:privacidad@legalshelf.mx" className={EMAIL_LINK_CLASS}>
            privacidad@legalshelf.mx
          </a>{" "}
          en cualquier momento. La negativa no será motivo para negarte el
          servicio.
        </p>
      </LegalSection>

      <LegalSection heading="Transferencias de datos">
        <p>
          LegalShelf puede transferir tus datos personales a los siguientes
          terceros, exclusivamente para cumplir con las finalidades primarias
          descritas en este aviso:
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Empresa contratante:</strong> la empresa que solicitó tu
            inscripción a CheckWise recibirá el resultado de la revisión de tu
            expediente y la metadata asociada para evaluar tu cumplimiento
            REPSE. También tendrá acceso a toda la documentación cargada a la
            plataforma.
          </li>
          <li>
            <strong>Autoridades competentes:</strong> cuando una orden de
            autoridad debidamente fundada lo requiera.
          </li>
          <li>
            <strong>Supuestos de la Ley:</strong> según el artículo 36 de la
            Ley, las transferencias nacionales o internacionales de datos se
            pueden llevar a cabo sin el consentimiento del titular cuando:
            <ul className="mt-1 list-disc space-y-1 pl-6">
              <li>Esté previsto en la Ley,</li>
              <li>
                Sea necesaria para la prevención o diagnósitoc médico, o
                cualquier fin médico.
              </li>
              <li>
                Sea precisa para el reconocimiento, ejercicio o defensa de un
                derecho en un proceso judicial.
              </li>
              <li>
                Sea precisa para el mantenimiento o cumplimiento de una
                relación jurídica entre el responsable y la persona titular.
              </li>
            </ul>
          </li>
        </ul>
        <p>
          Salvo en los supuestos anteriores no se realizan transferencias
          adicionales sin tu consentimiento expreso.
        </p>
      </LegalSection>

      <LegalSection heading="Derechos ARCO y revocación del consentimiento">
        <p>
          Los titulares podrán ejercer sus derechos de Acceso, Rectificación,
          Cancelación y Oposición (ARCO), a través de los Responsables y por
          petición directa con ellos para su revisión. Una vez aprobada por el
          Responsable, éste deberá enviar una solicitud a{" "}
          <a href="mailto:privacidad@legalshelf.mx" className={EMAIL_LINK_CLASS}>
            privacidad@legalshelf.mx
          </a>{" "}
          con la siguiente información:
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>Nombre completo de titular.</li>
          <li>Descripción clara del derecho que se desea ejercer.</li>
          <li>
            Documento que acredite la relación del Titular y el Responsable.
          </li>
        </ul>
        <p>
          LegalShelf responderá la solicitud en un plazo máximo de diez días
          hábiles. La revocación del consentimiento puede afectar la prestación
          del servicio cuando dicho consentimiento sea condición indispensable
          para operar el expediente REPSE del proveedor.
        </p>
        <p>
          Como excepción establecida en el Artículo 25º de la Ley, la
          cancelación de datos personales puede no ser ejecutable si se refiere
          a las partes de un contrato privado y son necesarios para su
          desarrollo y cumplimiento, así como si deben ser tratados por
          disposición legal.
        </p>
      </LegalSection>

      <LegalSection heading="Medidas de seguridad">
        <p>
          LegalShelf implementa medidas administrativas, técnicas y físicas
          razonables para proteger los datos personales contra daño, pérdida,
          alteración, destrucción o uso, acceso o tratamiento no autorizado.
          Estas medidas incluyen cifrado en tránsito, almacenamiento separado
          de archivos y metadata, control de accesos por rol, bitácora de
          auditoría inmutable y revisiones periódicas de seguridad.
        </p>
      </LegalSection>

      <LegalSection heading="Conservación de los datos">
        <p>
          Se conservarán los datos personales mientras exista una relación
          contractual entre el proveedor y la empresa contratante, así como
          durante el periodo adicional requerido por las disposiciones fiscales
          y regulatorias aplicables.
        </p>
        <p>
          Concluido ese plazo los datos serán bloqueados antes de su
          cancelación definitiva.
        </p>
      </LegalSection>

      <LegalSection heading="Cambios al aviso de privacidad">
        <p>
          Cualquier modificación a este aviso será publicada en esta misma
          página y se notificará dentro de la plataforma. Si los cambios
          afectan finalidades primarias o transferencias de datos, se te
          solicitará una nueva aceptación antes de continuar usando el
          servicio.
        </p>
      </LegalSection>
    </LegalDocShell>
  );
}
