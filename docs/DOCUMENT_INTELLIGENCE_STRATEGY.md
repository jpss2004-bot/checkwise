# Document Intelligence Strategy

## Principio

CheckWise no debe ser un bucket de archivos. Cada PDF debe producir señales útiles para revisión, trazabilidad y reporteo, pero sin aprobar automáticamente.

La base de datos de CheckWise debe ser la fuente de verdad. Google Sheets, Excel o cualquier archivo tabular deben funcionar como puentes de exportación, QA o migración, no como el modelo canónico de cumplimiento.

## Objetivo V2.4

Cuando un proveedor suba un documento, CheckWise debe:

1. Identificar el tipo real de documento y compararlo contra el requisito esperado.
2. Extraer campos documentales relevantes, no solo metadata técnica del archivo.
3. Guardar cada campo extraído con valor, confianza, método, evidencia y estado de revisión.
4. Marcar inconsistencias objetivas como `posible_mismatch` o `requiere_aclaracion`.
5. Enviar el resultado a revisión humana antes de cualquier aprobación legal.
6. Exportar una vista ordenada a Google Sheets o Excel cuando se necesite operar fuera del producto.

## Orden de Capas

1. Validación determinística de archivo.
2. Inspección técnica PDF.
3. Extracción de texto/OCR.
4. Clasificación documental.
5. Extracción estructurada por regla documental.
6. Comparación contra el contexto esperado.
7. Validaciones con confianza y evidencia.
8. Revisión humana.
9. Exportación tabular.

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

## Campos Extraídos

La extracción enriquecida debe vivir en una tabla propia, no escondida en `document_inspections.raw_metadata`.

Propuesta de entidades:

- `document_extraction_runs`: una ejecución por documento, modelo/reglas usados, estado, costos, errores y timestamps.
- `document_extracted_fields`: un registro por campo extraído, ligado a documento, submission, requisito y run.
- `document_export_batches`: lote de exportación a Google Sheets, Excel o CSV.
- `document_export_rows`: relación entre campos/submissions y filas exportadas.

Campos mínimos para `document_extracted_fields`:

- `field_key`: clave del rulebook, por ejemplo `vendor_rfc`, `main_date`, `period_key`, `folio_repse`.
- `field_label`: etiqueta humana del campo en el momento de extracción.
- `value_text`: valor normalizado.
- `raw_value_text`: valor tal como aparece o fue inferido.
- `confidence`: número de 0 a 1.
- `extraction_method`: `pdf_text`, `ocr`, `ai_assisted`, `deterministic`, `human_review`.
- `evidence`: JSON con página, fragmento corto, bounding boxes si existen, o razón de inferencia.
- `review_status`: `pending`, `accepted`, `corrected`, `rejected`.
- `reviewed_by`, `reviewed_at`, `review_note`.

## Comparaciones Esperadas

Cada extracción debe compararse contra el contexto de la carga:

- Cliente esperado contra razón social/RFC detectado.
- Proveedor esperado contra RFC detectado.
- Institución esperada contra institución detectada.
- Requisito esperado contra tipo documental detectado.
- Periodo esperado contra fechas o periodos visibles.
- Contrato/REPSE esperado contra folio, actividad, vigencia o participantes.

La salida de comparación debe crear `validation_events` y, cuando aplique, cambiar el estado inicial a `posible_mismatch` o `requiere_aclaracion`.

## Pipeline Propuesto

1. El endpoint de upload guarda el PDF y crea `Submission`, `Document`, `DocumentInspection` y eventos actuales.
2. Se agenda un job `document_extraction_requested`.
3. El worker extrae texto; si no hay texto suficiente, corre OCR.
4. El worker selecciona una plantilla desde `metadata_rules.py` usando `requirement_code` o clasificación.
5. El worker llama al extractor estructurado con salida JSON estricta.
6. El backend valida el JSON contra la plantilla esperada.
7. Se persisten campos, evidencia y eventos de validación.
8. Se recalcula el estado de revisión si hay mismatch.
9. La UI de reviewer muestra campos extraídos, evidencia y acciones de corrección.
10. Un exportador genera filas para Google Sheets, Excel o CSV desde los datos ya revisados o marcados como pendientes.

## Exportación

Orden recomendado:

1. CSV/XLSX local desde PostgreSQL para QA y demos.
2. Google Sheets append/update con idempotencia por `document_id + field_key`.
3. Exportaciones programadas por cliente/proveedor/periodo.

Cada fila exportada debe incluir:

- IDs canónicos: `client_id`, `vendor_id`, `contract_id`, `submission_id`, `document_id`.
- Contexto: cliente, proveedor, RFC, institución, requisito, periodo.
- Archivo: nombre, hash, storage key, page count.
- Extracción: campo, valor, confianza, método, estado de revisión.
- Mismatch: códigos, razón y estado documental.
- Auditoría: timestamps, reviewer, export batch.

## Límites

- No hay OCR real todavía.
- No hay extracción estructurada persistida todavía.
- No hay IA generativa tomando decisiones legales.
- No hay aprobación/rechazo legal automático.
- La clasificación actual es una señal inicial por keywords, no un dictamen.

## Siguiente Evolución

- Worker asíncrono para OCR y extracción enriquecida.
- Tablas persistentes para runs y campos extraídos.
- Normalización de RFC/razón social contra `vendors`.
- Match de periodo contra `periods`.
- Comparación de actividad REPSE contra contrato.
- Cola interna de revisión con explicación de señales y evidencia.
- Exportación CSV/XLSX local y después Google Sheets.
