/**
 * Landing-page FAQ. Single source of truth: the visible accordion in
 * `components/marketing/faq-section.tsx` and the FAQPage JSON-LD in
 * `app/page.tsx` both render these exact strings, so the structured
 * data can never drift from what the user actually sees (a Google
 * rich-results requirement).
 *
 * Answers are plain text — no JSX — because they are serialized
 * verbatim into `acceptedAnswer.text`. Keep each answer self-contained
 * and factual; regulatory amounts are expressed in UMA, never pesos,
 * so the copy doesn't go stale when the UMA value changes each year.
 */
export type FaqItem = {
  readonly question: string;
  readonly answer: string;
};

export const FAQ_ITEMS: readonly FaqItem[] = [
  {
    question: "¿Qué es el REPSE?",
    answer:
      "El REPSE (Registro de Prestadoras de Servicios Especializados u Obras Especializadas) es el padrón público de la Secretaría del Trabajo y Previsión Social (STPS) creado por la reforma en materia de subcontratación de 2021. Toda empresa que presta servicios especializados u obras especializadas con personal propio a un tercero debe estar inscrita en él para operar legalmente en México.",
  },
  {
    question: "¿Quién está obligado a registrarse en el REPSE?",
    answer:
      "Cualquier persona física o moral que ponga trabajadores propios a disposición de un cliente para ejecutar servicios u obras especializadas, es decir, actividades que no forman parte del objeto social ni de la actividad económica preponderante de ese cliente. Sin un registro REPSE vigente, la empresa contratante no puede deducir ni acreditar fiscalmente los pagos por esos servicios.",
  },
  {
    question: "¿Qué obligaciones tiene un proveedor registrado en el REPSE?",
    answer:
      "Además de mantener su registro vigente y renovarlo cada tres años, el proveedor debe presentar las informativas cuatrimestrales ICSOE (ante el IMSS) y SISUB (ante el INFONAVIT) en enero, mayo y septiembre, mantenerse al corriente en sus obligaciones fiscales, de seguridad social y de vivienda, y entregar a sus clientes la evidencia documental de cumplimiento que la ley les exige recabar.",
  },
  {
    question:
      "¿Qué documentos debe revisar una empresa que contrata servicios especializados?",
    answer:
      "Como mínimo: el registro REPSE vigente del proveedor, su constancia de situación fiscal, las opiniones de cumplimiento del SAT, IMSS e INFONAVIT, los CFDI y comprobantes de pago de nómina del personal asignado, las declaraciones de IVA e ISR y los pagos de cuotas obrero-patronales. Esta revisión debe repetirse de forma periódica durante toda la relación, no solo al firmar el contrato.",
  },
  {
    question: "¿Qué riesgos corre una empresa si su proveedor incumple REPSE?",
    answer:
      "Recibir servicios especializados de un proveedor sin registro vigente puede implicar multas de 2,000 a 50,000 veces la UMA, la pérdida de la deducción para ISR y del acreditamiento de IVA sobre esos pagos, y responsabilidad solidaria frente a los trabajadores del proveedor. Por eso la empresa contratante necesita evidencia documental continua, no una verificación única al inicio.",
  },
  {
    question: "¿Qué es una plataforma de cumplimiento REPSE?",
    answer:
      "Es un software que centraliza el control documental de la subcontratación especializada: calendario de obligaciones por requisito y periodo, expediente digital por proveedor, revisión de documentos, semáforo de riesgo y reportes listos para auditoría. CheckWise es una plataforma de cumplimiento REPSE construida en México por el equipo de Legal Shelf.",
  },
  {
    question: "¿Cómo previene CheckWise las multas y la responsabilidad solidaria?",
    answer:
      "Anticipándose: el calendario de obligaciones y el semáforo del portafolio detectan documentos faltantes, vencidos o inconsistentes antes de la fecha límite, cuando todavía se pueden corregir. La prevención REPSE consiste en eso — encontrar el riesgo en tu operación antes de que lo encuentre la autoridad, en lugar de reaccionar cuando la multa ya existe.",
  },
  {
    question: "¿Cómo ayuda CheckWise en una auditoría o inspección REPSE?",
    answer:
      "Cada documento vive ligado a su requisito, periodo e institución, con la decisión de revisión firmada y su historial de reemplazos. Ante una auditoría REPSE, generas el reporte ejecutivo y el paquete de evidencia en PDF, Excel o HTML directamente del expediente — sin reconstruir meses de correos y carpetas compartidas.",
  },
  {
    question: "¿CheckWise sustituye al abogado o emite resoluciones legales?",
    answer:
      "No. CheckWise es una plataforma de control documental: organiza la evidencia, la analiza con apoyo de inteligencia artificial y la valida con revisión humana, dejando un registro auditable de cada decisión. No emite resoluciones legales ni garantiza el cumplimiento automático; la decisión legal siempre la toma una persona.",
  },
  {
    question: "¿Cómo puedo ver CheckWise funcionando?",
    answer:
      "Solicita una demo guiada desde esta misma página. Recorremos el calendario de obligaciones, el expediente del proveedor, la revisión documental y los reportes con datos de ejemplo, y respondemos el mismo día hábil desde Ciudad de México.",
  },
];
