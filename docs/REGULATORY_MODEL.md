# Modelo Regulatorio REPSE

## Fuente Funcional

La base conceptual proviene de:

- `CheckWise_Matriz_Regulatoria_REPSE_2026.xlsx`
- `C.Árbol Plataforma Proveedores REPSE VF .xlsx` (sheet "Árbol Plataforma")
- Flujo operativo actual JotForm + Sheets + revisión humana/legal + Looker Studio.

### Mapeo Árbol → catálogo de código

`backend/app/core/compliance_catalog.py` encodea el árbol como:

- `OnboardingRequirement` (Expediente Corporativo) por persona moral / física:
  Contrato, Documentación Corporativa, Registro REPSE, Registro Patronal.
- `RecurringRequirement` (Cumplimiento REPSE) por año:
  - IMSS y SAT mensuales (12 meses, cubren el mes anterior).
  - INFONAVIT bimestral: B6 due Ene, B1 due Mar, B2 May, B3 Jul, B4 Sep, B5 Nov.
  - Acuses SISUB / ICSOE cuatrimestrales: due Ene (Q3 año anterior),
    May (Q1 Ene-Abr), Sep (Q2 May-Ago).
  - Acuse declaración anual SAT en Abril.

La versión activa se firma con `CATALOG_VERSION`. Cuando el seed regulatorio
real ingrese a `requirement_versions`, debe inicializar con esta versión.

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
