# Setup Local

## Requisitos

- Docker Desktop o equivalente.
- Python 3.11+.
- Node.js 20+.
- npm.

## Base de datos

```bash
docker compose up -d postgres
docker compose ps
```

La conexión local por defecto es:

```text
postgresql+psycopg://checkwise:checkwise@localhost:5432/checkwise
```

## Backend

```bash
cd backend
python3.11 -m venv .venv  # o cualquier Python 3.11+
source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

URLs:

- API: `http://localhost:8000`
- Healthcheck: `http://localhost:8000/health`
- OpenAPI: `http://localhost:8000/docs`

## Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

URL:

- App: `http://localhost:3000`

## Verificación

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/catalogs
cd backend && pytest
cd frontend && npm run lint && npm run build
```

## Notas

- `backend/storage/` es solo para desarrollo local y está ignorado por git.
- En producción, `STORAGE_BACKEND` debe apuntar a S3/R2/GCS mediante un servicio compatible.
- `.env.example` no contiene secretos reales.
