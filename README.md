# CheckWise V1

Base técnica inicial para CheckWise, una plataforma de cumplimiento documental REPSE para México. Esta fase crea el monorepo deployable para migrar gradualmente desde JotForm + Google Sheets + revisión humana/legal + Looker Studio hacia una fuente canónica en PostgreSQL.

## Estructura

- `frontend/`: Next.js + TypeScript + Tailwind CSS + componentes estilo shadcn/ui.
- `backend/`: FastAPI + SQLAlchemy + Alembic + OpenAPI.
- `docs/`: arquitectura, setup, modelo de datos, modelo regulatorio y roadmap.
- `docker-compose.yml`: PostgreSQL local.
- `.env.example`: variables base para entorno local/deployment.
- `AGENTS.md`: reglas para futuros agentes Codex.

## Arranque rápido

1. Base de datos local:

```bash
docker compose up -d postgres
```

2. Backend:

```bash
cd backend
python3.11 -m venv .venv  # o cualquier Python 3.11+
source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

3. Frontend:

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

## Verificación

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/catalogs
cd backend && pytest
cd frontend && npm run lint && npm run build
```

## Alcance V1 de esta fase

Listo:

- Modelo inicial para clientes, proveedores, contratos, periodos, instituciones, requisitos versionados, submissions, documentos, validaciones, historial de estados, reportes y auditoría.
- Formulario inicial de carga documental con campos REPSE mínimos.
- Endpoint backend para recibir carga documental, guardar archivo fuera de la DB, calcular hash y registrar prevalidaciones objetivas.
- Catálogos base para estados, instituciones, tipos de carga y validaciones.
- Documentación técnica para continuar con importadores JotForm/Sheets, validaciones avanzadas, dashboards y portal.

Pendiente para siguientes fases:

- Importador JotForm/Google Sheets hacia PostgreSQL.
- Semilla completa de `requirements` desde la matriz regulatoria.
- OCR, extracción estructurada y revisión legal asistida.
- Portal multirol de proveedores/clientes/revisores.
- Reportes ejecutivos generados desde datos normalizados.
