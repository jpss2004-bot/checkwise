# CheckWise V1.2

Base técnica de CheckWise, una plataforma de cumplimiento documental REPSE para México. Esta fase mueve el producto de un wizard suelto a un portal de proveedor: acceso, expediente inicial, calendario REPSE recurrente y carga prellenada — todo trazable contra el catálogo regulatorio derivado de `C.Árbol Plataforma Proveedores REPSE VF`.

V1.2 agrega:

- `/` Acceso de proveedor (demo, sin autenticación de producción).
- `/portal/onboarding` Expediente Corporativo gated por persona moral / física.
- `/portal/dashboard` Calendario REPSE 2026 mensual / bimestral / cuatrimestral / anual.
- `/portal/upload` Wizard V1.1 reutilizado, prellenado desde el calendario.
- Endpoints `/api/v1/compliance/*` y `/api/v1/portal/*`.
- Tabla `provider_workspaces` y migración `0003`.

## Estructura

- `frontend/`: Next.js + TypeScript + Tailwind CSS + componentes estilo shadcn/ui.
- `backend/`: FastAPI + SQLAlchemy + Alembic + OpenAPI.
- `docs/`: arquitectura, setup, modelo de datos, modelo regulatorio y roadmap.
- `docker-compose.yml`: PostgreSQL local.
- `.env.example`: variables base para entorno local/deployment.
- `AGENTS.md`: reglas para futuros agentes Codex.

## Arranque rápido para demo local

Desde el repo:

```bash
cd /Users/josepablosamano/Desktop/Personal/legalshelf/checkwise/CheckWise
./scripts/checkwise_safe_v1.sh doctor
./scripts/checkwise_safe_v1.sh backend-deps
./scripts/checkwise_safe_v1.sh frontend-deps
```

Si Docker Desktop/PostgreSQL está disponible y se quiere correr la demo con persistencia real:

```bash
./scripts/checkwise_safe_v1.sh postgres
./scripts/checkwise_safe_v1.sh migrate
```

Docker es necesario para la demo completa con PostgreSQL local. Los tests de backend usan SQLite en memoria y pueden correr sin Docker.

Terminal 1:

```bash
./scripts/checkwise_safe_v1.sh backend
```

Terminal 2:

```bash
./scripts/checkwise_safe_v1.sh frontend
```

URLs de demo:

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000`
- FastAPI docs: `http://127.0.0.1:8000/docs`

## Verificación

```bash
./scripts/checkwise_safe_v1.sh verify
cd backend && .venv/bin/ruff check . && .venv/bin/pytest
cd frontend && npm run lint && npm run typecheck && npm run build
```

## Demo preparada

- Guía: `docs/DEMO_GUIDE.md`
- Portal flow: `docs/PROVIDER_PORTAL_FLOW.md`
- PDF ficticio: `demo_assets/sample_documents/checkwise_demo_opinion_sat.pdf`
- Screenshots reales: `demo_assets/screenshots/`
- Regenerar PDFs de demo: `python3 tools/generate_demo_assets.py`

## Alcance V1 de esta fase

Listo:

- Modelo inicial para clientes, proveedores, contratos, periodos, instituciones, requisitos versionados, submissions, documentos, validaciones, historial de estados, reportes y auditoría.
- Wizard inicial de carga documental con campos REPSE mínimos.
- Endpoint backend para recibir carga documental, guardar archivo fuera de la DB, calcular hash y registrar prevalidaciones objetivas.
- Validación PDF-only con inspección técnica y eventos trazables.
- Catálogos base para estados, instituciones, tipos de carga y validaciones.
- Documentación técnica para continuar con importadores JotForm/Sheets, validaciones avanzadas, dashboards y portal.

Pendiente para siguientes fases:

- Importador JotForm/Google Sheets hacia PostgreSQL.
- Semilla completa de `requirements` desde la matriz regulatoria.
- OCR, extracción estructurada y revisión legal asistida.
- Portal multirol de proveedores/clientes/revisores.
- Reportes ejecutivos generados desde datos normalizados.
