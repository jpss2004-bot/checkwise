#!/usr/bin/env bash
#
# Boot the whole CheckWise stack locally — backend + frontend in
# parallel. Ctrl-C once cleans up both processes.
#
# Prereq once: apps/api/scripts/dev_setup.sh and (cd apps/web && npm install).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$ROOT/apps/api/.venv" ]; then
  echo "Backend not set up. Run apps/api/scripts/dev_setup.sh first." >&2
  exit 1
fi
if [ ! -d "$ROOT/apps/web/node_modules" ]; then
  echo "Frontend deps not installed. Run: cd apps/web && npm install" >&2
  exit 1
fi

# Release ports if a prior run is still holding them.
for port in 8000 3000; do
  if lsof -i :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "Releasing port $port..."
    lsof -i :$port -sTCP:LISTEN -t | xargs kill -TERM
    sleep 1
  fi
done

cleanup() {
  echo
  echo "==> Stopping CheckWise stack..."
  if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill -TERM "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "${FRONTEND_PID:-}" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill -TERM "$FRONTEND_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
  echo "Done."
}
trap cleanup EXIT INT TERM

echo "==> Starting backend on http://127.0.0.1:8000"
(
  cd "$ROOT/apps/api"
  exec .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 \
    2>&1 | sed -e 's/^/[backend] /'
) &
BACKEND_PID=$!

echo "==> Starting frontend on http://localhost:3000"
(
  cd "$ROOT/apps/web"
  exec npm run dev 2>&1 | sed -e 's/^/[frontend] /'
) &
FRONTEND_PID=$!

echo
echo "  Backend:  http://127.0.0.1:8000/docs"
echo "  Frontend: http://localhost:3000/"
echo
echo "  Reviewer login → http://localhost:3000/admin/login"
echo "    ada@legalshelf.mx / demo1234"
echo
echo "Press Ctrl-C to stop both."

wait
