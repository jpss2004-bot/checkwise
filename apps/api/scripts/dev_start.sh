#!/usr/bin/env bash
#
# Boot the FastAPI backend on port 8000 with auto-reload.
# Stop with Ctrl-C.
#
# Prereq: scripts/dev_setup.sh (one time).

set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
  echo "No .venv found. Run scripts/dev_setup.sh first." >&2
  exit 1
fi

# Free port 8000 if a previous run left a process on it.
if lsof -i :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "Port 8000 was busy. Releasing it..."
  lsof -i :8000 -sTCP:LISTEN -t | xargs kill -TERM
  sleep 1
fi

echo "==> Backend on http://127.0.0.1:8000  (Ctrl-C to stop)"
exec .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
