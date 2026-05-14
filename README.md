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

Primera vez:

```bash
bash backend/scripts/dev_setup.sh   # crea .venv, instala deps, corre alembic
cd frontend && npm install && cd ..
```

Arrancar todo el stack (backend en :8000, frontend en :3000):

```bash
bash dev.sh
```

O en dos terminales:

```bash
# Terminal 1
bash backend/scripts/dev_start.sh

# Terminal 2
cd frontend && npm run dev
```

URLs de demo:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- FastAPI docs: `http://localhost:8000/docs`

Reset de DB (borra SQLite local, re-corre migraciones, vuelve a seedear):

```bash
bash backend/scripts/dev_reset.sh
```

## Verificación

```bash
cd backend && .venv/bin/ruff check . && .venv/bin/pytest -q
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```

## Demo preparada

- Guía: `docs/DEMO_GUIDE.md`
- Portal flow: `docs/PROVIDER_PORTAL_FLOW.md`
- Screenshots reales: `demo_assets/screenshots/`
- Regenerar assets de demo: `python3 scripts/reports/generate_demo_assets.py`

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
