# Modelo de Datos Inicial

## Entidades Principales

| Entidad | Propósito | Notas |
| --- | --- | --- |
| `clients` | Cliente o filial contratante | Aislamiento por cliente. |
| `vendors` | Proveedor REPSE | RFC + cliente evita duplicados por nombre. |
| `contracts` | Relación cliente-proveedor-servicio | No es solo archivo; incluye objeto, vigencia y folio REPSE. |
| `periods` | Ciclos mensuales, bimestrales, cuatrimestrales o eventos | Permite frecuencia variable. |
| `institutions` | SAT, STPS/REPSE, IMSS, INFONAVIT, Interno/Cliente | Catálogo controlado. |
| `requirements` | Requisito regulatorio estable | Código, institución, frecuencia, riesgo. |
| `requirement_versions` | Versión funcional/legal del requisito | Fundamento, aplicabilidad, validación mínima, señales, vigencia. |
| `submissions` | Carga documental recibida | Une cliente, proveedor, contrato, periodo, institución, requisito y estado. |
| `documents` | Metadatos de archivo | Storage key, hash, MIME, tamaño, OCR status. |
| `validations` | Señales automáticas y revisión humana | Resultado, severidad, comentario, escalamiento. |
| `validation_events` | Eventos trazables de intake/prevalidación | Bitácora granular por evento, regla, severidad, confidence y payload. |
| `document_inspections` | Resultado técnico e inteligente del PDF | Estructura PDF, texto, señales detectadas, posible mismatch. |
| `document_status_history` | Historial de estados | Trazabilidad de cambios documentales. |
| `reports` | Salidas ejecutivas | Generación futura desde datos normalizados. |
| `audit_log` | Auditoría transversal | Actor, acción, entidad, antes/después y metadata. |

## Estados Documentales Base

- `pendiente`
- `recibido`
- `pendiente_revision`
- `prevalidado`
- `posible_mismatch`
- `aprobado`
- `rechazado`
- `vencido`
- `no_aplica`
- `requiere_aclaracion`
- `excepcion_legal`

## Relación Mínima de Evidencia

Todo documento debe poder responder:

- ¿De qué cliente es?
- ¿Qué proveedor lo cargó?
- ¿A qué contrato aplica, si aplica?
- ¿Qué periodo cubre?
- ¿Qué institución lo exige?
- ¿Qué requisito/version cumple?
- ¿Dónde está el archivo?
- ¿Qué validaciones existen?
- ¿Cuál es su estado actual?
- ¿Quién lo cambió y cuándo?

## Decisiones V1

- IDs tipo UUID almacenados como `String(36)` para mantener portabilidad en desarrollo y Postgres.
- Campos regulatorios variables viven en `requirement_versions`, no como columnas sueltas.
- `documents.sha256` habilita deduplicación futura.
- `audit_log.metadata` se implementa como columna `metadata` mapeada a atributo `event_metadata` para evitar conflicto interno con SQLAlchemy.
- `validation_events` complementa `validations`: `validations` resume reglas; `validation_events` conserva cronología y payload auditable.
- `document_inspections` concentra señales técnicas/inteligentes sin convertirlas en aprobación legal.
