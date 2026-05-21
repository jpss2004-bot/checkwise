# CheckWise — Mapa Final del Flujo del Sistema

Fecha: 19 de mayo de 2026

## Archivos creados

- `checkwise-final-system-workflow.pdf` — PDF final imprimible en A3 horizontal.
- `checkwise-final-system-workflow.html` — fuente HTML/CSS usado para renderizar el PDF.
- `diagrams/*.svg` — diagramas reutilizables como assets independientes.
- `scripts/build-system-workflow-map.mjs` — script generador.

## Diagramas creados

1. `01-system-overview.svg` — vista general end-to-end.
2. `02-auth-and-entry-flow.svg` — autenticación, entrada y redirects.
3. `03-supplier-upload-flow.svg` — onboarding y upload del proveedor.
4. `04-internal-review-flow.svg` — revisión interna/legal.
5. `05-reporting-flow.svg` — reportes y asistencia IA.
6. `06-data-security-flow.svg` — datos y controles de seguridad.
7. `07-route-api-map.svg` — mapa de rutas a APIs.
8. `08-status-lifecycle.svg` — ciclo de vida de estados.

## Inspección realizada

- Frontend: `apps/web/app/**/*.tsx`, `apps/web/lib/api/*.ts`, session guards y redirects.
- Backend: `apps/api/app/api/v1/*.py`, `apps/api/app/services/*.py`, modelos, constantes y configuración.
- Docs: `API_CONTRACT_MAP.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `REPORTS_ARCHITECTURE.md`, `REPORTS_AUDIT_2026-05-18.md`, `codex-route-workflow-audit/*`, `PROD_AUDIT_2026-05-18.md`.
- Brand: `apps/web/app/globals.css`, `docs/DESIGN_SYSTEM.md`, `apps/web/public/checkwise-logo.png`.

## Supuestos y límites

- El PDF distingue entre implementado, parcial, planeado, requiere validación y faltante recomendado.
- No se afirma producción endurecida. Storage S3/R2, observabilidad, backups, pentest y CORS producción requieren validación real.
- IA/LLM se presenta como asistencia. Si `ANTHROPIC_API_KEY` no existe, el backend usa mock determinístico.
- `POST /api/v1/submissions` se marca como legacy/deprecated; el flujo recomendado es `POST /api/v1/portal/workspaces/{id}/submissions`.
- Provider reports se marca parcial porque la auditoría de rutas documenta bloqueo 403 en la DB actual.

## Workflows inconsistentes o faltantes destacados

- `/activate`: cancelar puede conservar JWT temporal y enviar al portal sin cambio de password.
- `/admin/login`: redirect legacy a `/login` causa double-hop cosmético.
- No existe endpoint final de descarga segura de documentos para cliente/admin.
- No existe backend real para correcciones de workspace/contact requests/notificaciones.
- Exports async de reportes tienen modelo `ReportExport`, pero falta worker/render productivo.
