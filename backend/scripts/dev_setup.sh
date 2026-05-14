#!/usr/bin/env bash
#
# One-time backend setup. Idempotent — safe to re-run.
#
#   1. Creates ./.venv if missing.
#   2. Installs/refreshes deps from pyproject.toml.
#   3. Ensures backend/.env exists with sqlite defaults.
#   4. Runs Alembic migrations to head.
#   5. Loads the dev demo seed.
#
# After this finishes, run scripts/dev_start.sh.

set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
  echo "==> Creating .venv (Python 3.11+)"
  python3 -m venv .venv
fi

echo "==> Installing backend deps"
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e ".[dev]"
.venv/bin/pip install --quiet bcrypt "pyjwt>=2.8"

if [ ! -f ".env" ]; then
  echo "==> Writing default backend/.env (sqlite + local storage)"
  cat > .env <<'EOF'
CHECKWISE_ENV=local
DATABASE_URL=sqlite+pysqlite:///./checkwise.db
LOCAL_STORAGE_PATH=./storage
STORAGE_BACKEND=local
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
AUTH_JWT_SECRET=checkwise-local-dev-secret-not-for-production-please-change
AUTH_JWT_ALGORITHM=HS256
AUTH_JWT_EXPIRES_MINUTES=1440
EOF
fi

mkdir -p storage

echo "==> Applying Alembic migrations"
.venv/bin/alembic upgrade head

echo "==> Loading dev seed"
.venv/bin/python scripts/dev_seed.py

echo
echo "Backend setup complete."
echo "  start backend: cd backend && scripts/dev_start.sh"
echo "  start frontend: cd frontend && npm run dev"
