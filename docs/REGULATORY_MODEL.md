# Modelo Regulatorio REPSE

## Fuente Funcional

La base conceptual proviene de:

- `CheckWise_Matriz_Regulatoria_REPSE_2026.xlsx`
- `C.Árbol Plataforma Proveedores REPSE VF .xlsx`
- Flujo operativo actual JotForm + Sheets + revisión humana/legal + Looker Studio.

## Requisito Versionable

Un requisito no es una columna fija. Es una regla documentada y versionable con:

- Código (`REQ-...`).
- Institución.
- Tipo de carga.
- Frecuencia.
- Documento o requisito.
- Fundamento legal.
- Aplicabilidad.
- Validación mínima.
- Señales automáticas.
- Revisión humana requerida.
- Riesgo.
- Estado si falta.
- Regla temporal o vencimiento.
- Vigencia de la versión.

## Tipos de Carga Base

- Alta inicial.
- Contrato.
- Mensual.
- Cuatrimestral.
- Renovación.
- Evento / excepción.

## Instituciones Base

- STPS / REPSE.
- SAT.
- IMSS.
- INFONAVIT.
- Interno / Cliente.

## Validaciones Iniciales

La arquitectura queda preparada para:

- Archivo existe.
- Tipo de archivo permitido.
- Tamaño máximo.
- Hash SHA-256.
- Estructura PDF básica.
- PDF bloqueado/corrupto.
- Texto legible o posible escaneo.
- Señales documentales determinísticas.
- Proveedor coincide.
- Periodo coincide.
- Requisito correcto.
- Duplicado por hash.
- Documento vencido.
- Requiere revisión humana.

## Regla de Aprobación

Los requisitos críticos o con criterio legal/fiscal nunca deben aprobarse únicamente por automatización. La automatización puede marcar `prevalidado`, `posible_mismatch`, `rechazado` técnico o `requiere_aclaracion`; la aprobación final requiere actor humano autorizado.
