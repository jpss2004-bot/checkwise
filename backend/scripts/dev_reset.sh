#!/usr/bin/env bash
#
# Nuke the local SQLite DB and start over from migrations + seed.
# Does NOT touch your .env or .venv.

set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Removing local checkwise.db"
rm -f checkwise.db

echo "==> Re-applying migrations"
.venv/bin/alembic upgrade head

echo "==> Re-loading dev seed"
.venv/bin/python scripts/dev_seed.py
