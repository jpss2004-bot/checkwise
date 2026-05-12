# Document Intelligence Strategy

## Principio

CheckWise no debe ser un bucket de archivos. Cada PDF debe producir señales útiles para revisión y trazabilidad, pero sin aprobar automáticamente.

## Orden de Capas

1. Validación determinística de archivo.
2. Inspección técnica PDF.
3. Extracción de texto/metadata.
4. Clasificación documental determinística.
5. Detección de posibles anomalías.
6. Revisión humana.

## Señales V1.1

Implementadas de forma determinística:

- Institución probable.
- Tipo documental probable.
- RFCs encontrados.
- Fechas encontradas.
- Menciones de periodo.
- Confianza simple de match contra requisito.
- Razón de posible mismatch.
- Códigos de anomalía.

## Límites

- No hay OCR real todavía.
- No hay IA generativa tomando decisiones.
- No hay aprobación/rechazo legal automático.
- La clasificación actual es una señal inicial por keywords, no un dictamen.

## Siguiente Evolución

- Worker asíncrono para OCR y extracción enriquecida.
- Normalización de RFC/razón social contra `vendors`.
- Match de periodo contra `periods`.
- Comparación de actividad REPSE contra contrato.
- Cola interna de revisión con explicación de señales y evidencia.
