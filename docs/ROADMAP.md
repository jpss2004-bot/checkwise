# Roadmap V1

## Fase Actual: Foundation

- Monorepo con frontend, backend, DB local y documentación.
- Modelo regulatorio versionable.
- Formulario inicial de carga documental.
- Endpoint de recepción documental.
- Prevalidaciones objetivas iniciales.
- Auditabilidad base.

## Siguiente Fase Recomendada: Importador Canónico

1. Auditar estructura actual de JotForm y Google Sheets.
2. Crear diccionario de campos fuente.
3. Mapear cada campo a entidades canónicas.
4. Implementar importador idempotente hacia PostgreSQL.
5. Reportar diferencias, duplicados y datos no mapeables.

## Fases Posteriores

- Semilla completa de requisitos desde la matriz regulatoria.
- Portal de proveedores con secciones por tipo de carga.
- Cola de trabajos para OCR, hash, deduplicación y alertas.
- Módulo de revisión humana/legal con motivos estandarizados.
- Reporte mensual desde datos normalizados.
- Integración con storage S3-compatible.
- Autenticación, roles y permisos por cliente/proveedor/revisor.

## Criterio de No Sobreconstrucción

Cada fase debe dejar una pieza operable y verificable. Las integraciones futuras deben colgar del modelo canónico, no duplicar lógica regulatoria en formularios o dashboards.
