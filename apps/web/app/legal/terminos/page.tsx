import type { Metadata } from "next";

import {
  LegalDocShell,
  LegalSection,
} from "@/components/checkwise/legal/legal-doc-shell";

export const metadata: Metadata = {
  title: "Términos de uso · CheckWise",
  description:
    "Términos y condiciones de uso de la plataforma CheckWise operada por LegalShelf.",
};

/**
 * /legal/terminos — Términos de Uso.
 *
 * DRAFT (v0-draft). Pendiente de revisión final por Paco/Beko.
 * Estructurado como contrato de adhesión de uso aceptable; redactado
 * para alinearse con la operación REPSE y la naturaleza de servicio
 * de cumplimiento de CheckWise.
 */
export default function TerminosPage() {
  return (
    <LegalDocShell
      eyebrow="Documento legal · CheckWise"
      title="Términos de uso"
      effectiveDate="22 de mayo de 2026"
      version="v0-draft"
    >
      <LegalSection heading="1. Aceptación de los términos">
        <p>
          Los presentes términos de uso (los “Términos”) regulan el
          acceso y uso de la plataforma CheckWise (la “Plataforma”),
          operada por LegalShelf, S.A. de C.V. (“LegalShelf”). Al
          acceder o utilizar la Plataforma aceptas estos Términos y el
          Aviso de Privacidad de LegalShelf.
        </p>
        <p>
          Si no estás de acuerdo con alguno de los Términos, debes
          abstenerte de utilizar la Plataforma.
        </p>
      </LegalSection>

      <LegalSection heading="2. Descripción del servicio">
        <p>
          CheckWise es una plataforma de cumplimiento REPSE diseñada
          para que las empresas proveedoras puedan registrar, subir y
          consultar la evidencia documental requerida por sus
          contrapartes contratantes, y para que el equipo legal de
          LegalShelf revise dicha evidencia.
        </p>
        <p>
          LegalShelf no actúa como autoridad fiscal ni emite
          resoluciones con carácter oficial; la Plataforma es una
          herramienta de gestión documental y auditoría privada.
        </p>
      </LegalSection>

      <LegalSection heading="3. Cuentas y credenciales">
        <p>
          Para usar la Plataforma debes contar con una invitación
          válida y crear una cuenta con credenciales personales. Eres
          responsable de mantener la confidencialidad de tu contraseña
          y de toda actividad realizada bajo tu cuenta. Notifica de
          inmediato a LegalShelf cualquier uso no autorizado a{" "}
          <a
            href="mailto:soporte@legalshelf.mx"
            className="font-medium text-[color:var(--text-brand)] hover:underline"
          >
            soporte@legalshelf.mx
          </a>
          .
        </p>
      </LegalSection>

      <LegalSection heading="4. Uso aceptable">
        <p>Te comprometes a:</p>
        <ul className="list-disc pl-6">
          <li>
            Subir únicamente documentos auténticos y completos que
            correspondan a tu empresa proveedora.
          </li>
          <li>
            No alterar, manipular ni falsificar comprobantes, sellos
            digitales, cédulas o avisos.
          </li>
          <li>
            No intentar acceder a expedientes, datos o sesiones que no
            te correspondan.
          </li>
          <li>
            No usar la Plataforma para fines distintos a la gestión de
            cumplimiento REPSE.
          </li>
          <li>
            No realizar ingeniería inversa, escaneo automatizado no
            autorizado ni intentar evadir los controles de seguridad.
          </li>
        </ul>
      </LegalSection>

      <LegalSection heading="5. Documentos y propiedad intelectual">
        <p>
          Los documentos que subes a la Plataforma siguen siendo
          propiedad de tu empresa proveedora. Otorgas a LegalShelf una
          licencia limitada, no exclusiva, gratuita y revocable
          únicamente para los fines descritos en el Aviso de Privacidad
          (revisar, almacenar, mostrar a la empresa contratante y
          conservar como evidencia auditable).
        </p>
        <p>
          La Plataforma, su código, diseño, marcas, contenidos y
          documentación son propiedad de LegalShelf o de sus
          licenciantes y están protegidos por la legislación de
          propiedad intelectual aplicable.
        </p>
      </LegalSection>

      <LegalSection heading="6. Disponibilidad y soporte">
        <p>
          LegalShelf realizará esfuerzos razonables para mantener la
          Plataforma disponible. Sin embargo, no garantiza un servicio
          ininterrumpido o libre de errores. Podemos suspender el
          acceso para realizar mantenimiento, mejoras o por causas de
          fuerza mayor.
        </p>
      </LegalSection>

      <LegalSection heading="7. Limitación de responsabilidad">
        <p>
          En la máxima medida permitida por la legislación aplicable,
          LegalShelf no será responsable por daños indirectos,
          incidentales, especiales o consecuenciales derivados del uso
          o imposibilidad de uso de la Plataforma, incluyendo pérdida
          de utilidades, oportunidades comerciales o datos.
        </p>
        <p>
          LegalShelf no es responsable por las decisiones que la
          empresa contratante tome con base en la información que tú
          mismo proporcionas a través de la Plataforma.
        </p>
      </LegalSection>

      <LegalSection heading="8. Suspensión y terminación">
        <p>
          LegalShelf puede suspender o cancelar tu acceso si: (i)
          incumples estos Términos, (ii) la empresa contratante
          finaliza su relación contigo, o (iii) se requiere por orden
          de autoridad competente. Conservaremos los datos conforme al
          Aviso de Privacidad y a la legislación aplicable.
        </p>
      </LegalSection>

      <LegalSection heading="9. Modificaciones a los Términos">
        <p>
          Podemos modificar estos Términos para reflejar cambios en la
          Plataforma o en la regulación. Las modificaciones materiales
          se notificarán dentro de la Plataforma con razonable
          anticipación y, cuando aplique, se solicitará una nueva
          aceptación.
        </p>
      </LegalSection>

      <LegalSection heading="10. Legislación aplicable y jurisdicción">
        <p>
          Estos Términos se rigen por las leyes de los Estados Unidos
          Mexicanos. Cualquier controversia será resuelta ante los
          tribunales competentes de la Ciudad de México, renunciando
          las partes a cualquier otro fuero que pudiera corresponderles.
        </p>
      </LegalSection>
    </LegalDocShell>
  );
}
