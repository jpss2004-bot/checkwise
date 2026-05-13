# Roadmap V1

## Fase Actual: V1.2 Provider Portal Foundation

- Página de acceso de proveedor (demo, sin auth de producción).
- Catálogo regulatorio expuesto vía API derivado de
  `C.Árbol Plataforma Proveedores REPSE VF`.
- Expediente Corporativo gated antes del calendario recurrente.
- Calendario REPSE año por mes por institución, con estado por requisito.
- Workspaces de proveedor persistidos en PostgreSQL con `access_token` demo.
- Wizard V1.1 reutilizado en `/portal/upload` con prefill desde el calendario.
- Documentación dedicada en `docs/PROVIDER_PORTAL_FLOW.md`.

## Fase Previa: V1.1 Native Intake Foundation

- Wizard nativo de carga documental.
- PDF-only intake.
- Inspección técnica PDF.
- Señales documentales determinísticas.
- Eventos de validación trazables.
- Soporte contextual WhatsApp preparado por configuración.
- Estrategia documentada de salida progresiva de JotForm.

## Fase Anterior: Foundation

- Monorepo con frontend, backend, DB local y documentación.
- Modelo regulatorio versionable.
- Formulario inicial de carga documental.
- Endpoint de recepción documental.
- Prevalidaciones objetivas iniciales.
- Auditabilidad base.

## Siguiente Fase Recomendada: V1.3 — Auth real + Seed regulatorio

1. Autenticación real (Clerk / Auth0 / Supabase) reemplazando `access_token` demo.
2. Roles: proveedor, cliente, revisor; ownership por workspace.
3. Sembrar `requirements` y `requirement_versions` desde el catálogo
   (`compliance_catalog.py`) hacia PostgreSQL.
4. Persistir `onboarding_completed_at` desde la revisión humana, no del cliente.
5. Reconciliar `period_code` con la taxonomía bimestral (B1–B6) y
   cuatrimestral (Q1–Q3) del Árbol.

## Fase Posterior: Importador Canónico + Vista del Cliente

1. Auditar estructura actual de JotForm y Google Sheets.
2. Crear diccionario de campos fuente.
3. Mapear cada campo a entidades canónicas.
4. Implementar importador idempotente hacia PostgreSQL.
5. Reportar diferencias, duplicados y datos no mapeables.
6. Sembrar `requirements` y `requirement_versions` desde la matriz REPSE 2026.

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
