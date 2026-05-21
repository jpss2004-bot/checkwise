#!/usr/bin/env bash
#
# CheckWise demo bootstrap — one command to go from clean checkout
# to a fully-authenticated browser session.
#
# 1. Ensures Docker is running and brings up Postgres via
#    docker-compose.
# 2. Applies Alembic migrations against the running Postgres.
# 3. Loads the demo seed (ada@legalshelf.mx, boss.demo@checkwise.mx,
#    cliente.demo@checkwise.mx + 3 seeded reports).
# 4. Hands off to dev.sh which starts backend + frontend in parallel.
#
# Prereq once:
#   - Docker Desktop installed (started automatically if not running).
#   - apps/api/scripts/dev_setup.sh has been run (creates .venv).
#   - cd apps/web && npm install.
#
# After this script prints "stack up", open
# http://localhost:3000/login and use one of the documented demo
# accounts (see end of dev_seed.py output, or docs/CREDENTIALS.md).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# ── Preflight ──────────────────────────────────────────────────────
if [ ! -d "apps/api/.venv" ]; then
  echo "ERROR: apps/api/.venv not found. Run apps/api/scripts/dev_setup.sh first." >&2
  exit 1
fi
if [ ! -d "apps/web/node_modules" ]; then
  echo "ERROR: frontend deps not installed. Run: cd apps/web && npm install" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker CLI not found. Install Docker Desktop first." >&2
  exit 1
fi

# ── Docker daemon ──────────────────────────────────────────────────
if ! docker info >/dev/null 2>&1; then
  echo "==> Starting Docker Desktop..."
  open -a "Docker Desktop"
  for i in $(seq 1 12); do
    if docker info >/dev/null 2>&1; then
      echo "    daemon ready"
      break
    fi
    sleep 5
  done
  if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker daemon did not start within 60s." >&2
    exit 1
  fi
fi

# ── Postgres ───────────────────────────────────────────────────────
echo "==> Starting Postgres (docker compose up -d postgres)"
docker compose up -d postgres >/dev/null

echo "==> Waiting for Postgres healthcheck"
for i in $(seq 1 20); do
  status=$(docker inspect --format='{{.State.Health.Status}}' checkwise-postgres 2>/dev/null || echo "unknown")
  if [ "$status" = "healthy" ]; then
    echo "    healthy"
    break
  fi
  sleep 2
done
if [ "$status" != "healthy" ]; then
  echo "ERROR: Postgres did not become healthy within 40s." >&2
  exit 1
fi

# ── Migrate + seed ─────────────────────────────────────────────────
echo "==> Applying Alembic migrations"
(cd apps/api && .venv/bin/alembic upgrade head)

echo "==> Loading dev seed"
(cd apps/api && .venv/bin/python scripts/dev_seed.py)

# ── Backend + frontend ─────────────────────────────────────────────
echo
echo "==> Stack ready. Demo accounts:"
echo "    Admin:    ada@legalshelf.mx / demo1234"
echo "    Provider: boss.demo@checkwise.mx / BossDemo!2026"
echo "    Client:   cliente.demo@checkwise.mx / ClienteDemo!2026"
echo
echo "==> Handing off to dev.sh (Ctrl-C stops both processes)..."
echo
exec "$ROOT/dev.sh"
