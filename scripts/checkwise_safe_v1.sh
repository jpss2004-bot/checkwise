#!/usr/bin/env bash

set -u

MODE="${1:-help}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BLUE="\033[0;34m"
RESET="\033[0m"

ok() { printf "${GREEN}OK:${RESET} %s\n" "$1"; }
warn() { printf "${YELLOW}WARN:${RESET} %s\n" "$1"; }
fail() { printf "${RED}ERROR:${RESET} %s\n" "$1"; }
info() { printf "${BLUE}INFO:${RESET} %s\n" "$1"; }

require_path() {
  local path="$1"
  if [ ! -e "$path" ]; then
    fail "No encontré: $path"
    fail "Estás en el repo equivocado o falta estructura del proyecto."
    exit 1
  fi
}

check_repo() {
  require_path "$ROOT_DIR/docker-compose.yml"
  require_path "$BACKEND_DIR/pyproject.toml"
  require_path "$BACKEND_DIR/alembic.ini"
  require_path "$FRONTEND_DIR/package.json"
  ok "Repo CheckWise detectado correctamente."
}

choose_python() {
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN="python3.11"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
    warn "No encontré python3.11. Usaré python3."
  else
    fail "No encontré Python."
    exit 1
  fi
}

check_docker_available() {
  if ! command -v docker >/dev/null 2>&1; then
    fail "Docker no está instalado o no está en PATH."
    echo
    echo "Acción requerida:"
    echo "1. Instala Docker Desktop para Mac."
    echo "2. Abre Docker Desktop."
    echo "3. Espera a que esté corriendo."
    echo "4. Vuelve a correr:"
    echo "   ./scripts/checkwise_safe_v1.sh postgres"
    exit 1
  fi

  if ! docker info >/dev/null 2>&1; then
    fail "Docker existe, pero Docker Desktop no está corriendo."
    echo
    echo "Abre Docker Desktop y espera a que termine de iniciar."
    exit 1
  fi

  ok "Docker está instalado y activo."
}

check_node() {
  if ! command -v node >/dev/null 2>&1; then
    fail "No encontré Node.js."
    exit 1
  fi

  if ! command -v npm >/dev/null 2>&1; then
    fail "No encontré npm."
    exit 1
  fi

  ok "Node encontrado: $(node -v)"
  ok "npm encontrado: $(npm -v)"
}

check_port_free() {
  local port="$1"

  if lsof -ti :"$port" >/dev/null 2>&1; then
    warn "El puerto $port está ocupado."
    echo
    echo "No voy a matar procesos automáticamente."
    echo "Para ver qué proceso lo usa:"
    echo "  lsof -i :$port"
    echo
    echo "Si estás seguro de liberarlo:"
    echo "  kill -9 \$(lsof -ti :$port)"
    exit 1
  fi

  ok "Puerto $port libre."
}

backend_deps() {
  check_repo
  choose_python

  cd "$BACKEND_DIR" || exit 1

  if [ ! -d ".venv" ]; then
    info "Creando backend/.venv..."
    "$PYTHON_BIN" -m venv .venv
  else
    ok "backend/.venv ya existe."
  fi

  info "Instalando dependencias backend usando .venv..."
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -e ".[dev]"

  if [ ! -f ".env" ]; then
    if [ -f "$ROOT_DIR/.env.example" ]; then
      cp "$ROOT_DIR/.env.example" ".env"
      ok "Creé backend/.env desde .env.example."
    else
      warn "No encontré .env.example. No creé backend/.env."
    fi
  else
    ok "backend/.env ya existe. No lo sobrescribí."
  fi

  ok "Backend deps listo."
}

frontend_deps() {
  check_repo
  check_node

  cd "$FRONTEND_DIR" || exit 1

  info "Instalando dependencias frontend..."
  npm install

  if [ ! -f ".env.local" ]; then
    if [ -f ".env.local.example" ]; then
      cp ".env.local.example" ".env.local"
      ok "Creé frontend/.env.local desde .env.local.example."
    else
      warn "No encontré frontend/.env.local.example."
    fi
  else
    ok "frontend/.env.local ya existe. No lo sobrescribí."
  fi

  ok "Frontend deps listo."
}

start_postgres() {
  check_repo
  check_docker_available

  cd "$ROOT_DIR" || exit 1

  info "Levantando PostgreSQL..."
  docker compose up -d postgres

  info "Esperando PostgreSQL..."
  local tries=0
  local max_tries=40

  while [ "$tries" -lt "$max_tries" ]; do
    if docker compose exec -T postgres pg_isready >/dev/null 2>&1; then
      ok "PostgreSQL está listo."
      docker compose ps
      return 0
    fi

    tries=$((tries + 1))
    sleep 2
  done

  fail "PostgreSQL no respondió a tiempo."
  echo "Revisa:"
  echo "  docker compose ps"
  echo "  docker compose logs postgres"
  exit 1
}

migrate_db() {
  check_repo

  if [ ! -x "$BACKEND_DIR/.venv/bin/alembic" ]; then
    fail "No encontré Alembic dentro de backend/.venv."
    echo "Primero corre:"
    echo "  ./scripts/checkwise_safe_v1.sh backend-deps"
    exit 1
  fi

  cd "$BACKEND_DIR" || exit 1

  info "Aplicando migraciones con backend/.venv/bin/alembic..."
  .venv/bin/alembic upgrade head

  ok "Migraciones aplicadas."
}

run_backend() {
  check_repo
  check_port_free 8000

  if [ ! -x "$BACKEND_DIR/.venv/bin/uvicorn" ]; then
    fail "No encontré Uvicorn dentro de backend/.venv."
    echo "Primero corre:"
    echo "  ./scripts/checkwise_safe_v1.sh backend-deps"
    exit 1
  fi

  cd "$BACKEND_DIR" || exit 1

  info "Iniciando backend en http://127.0.0.1:8000"
  .venv/bin/uvicorn app.main:app --reload
}

run_frontend() {
  check_repo
  check_port_free 3000

  if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    fail "No encontré frontend/node_modules."
    echo "Primero corre:"
    echo "  ./scripts/checkwise_safe_v1.sh frontend-deps"
    exit 1
  fi

  cd "$FRONTEND_DIR" || exit 1

  info "Iniciando frontend en http://127.0.0.1:3000"
  npm run dev -- --hostname 127.0.0.1
}

verify_api() {
  info "Verificando API..."

  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    ok "Backend /health responde."
  else
    fail "Backend /health no responde."
    echo "Asegúrate de tener backend corriendo:"
    echo "  ./scripts/checkwise_safe_v1.sh backend"
    exit 1
  fi

  if curl -fsS http://127.0.0.1:8000/api/v1/catalogs >/dev/null 2>&1; then
    ok "Backend /api/v1/catalogs responde."
  else
    warn "Backend /api/v1/catalogs no respondió."
  fi

  if curl -fsS http://127.0.0.1:8000/docs >/dev/null 2>&1; then
    ok "Backend /docs responde."
  else
    warn "Backend /docs no respondió."
  fi
}

run_tests() {
  check_repo

  if [ ! -x "$BACKEND_DIR/.venv/bin/pytest" ]; then
    fail "No encontré pytest dentro de backend/.venv."
    echo "Primero corre:"
    echo "  ./scripts/checkwise_safe_v1.sh backend-deps"
    exit 1
  fi

  cd "$BACKEND_DIR" || exit 1
  info "Corriendo ruff..."
  .venv/bin/ruff check .

  info "Corriendo pytest..."
  .venv/bin/pytest

  cd "$FRONTEND_DIR" || exit 1
  info "Corriendo frontend lint..."
  npm run lint

  info "Corriendo frontend typecheck..."
  npm run typecheck

  info "Corriendo frontend build..."
  npm run build

  ok "Tests/verificaciones completas."
}

doctor() {
  check_repo

  echo
  info "Ubicación:"
  echo "$ROOT_DIR"

  echo
  info "Git:"
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    ok "Repo git activo."
    git status --short
  else
    warn "Este directorio no parece ser repo git."
  fi

  echo
  info "Docker:"
  if command -v docker >/dev/null 2>&1; then
    docker --version
    if docker info >/dev/null 2>&1; then
      ok "Docker activo."
      docker compose ps || true
    else
      warn "Docker instalado pero no activo."
    fi
  else
    warn "Docker no encontrado."
  fi

  echo
  info "Backend:"
  [ -d "$BACKEND_DIR/.venv" ] && ok "backend/.venv existe." || warn "backend/.venv falta."
  [ -f "$BACKEND_DIR/.env" ] && ok "backend/.env existe." || warn "backend/.env falta."
  [ -x "$BACKEND_DIR/.venv/bin/alembic" ] && ok "Alembic existe en .venv." || warn "Alembic no existe en .venv."
  [ -x "$BACKEND_DIR/.venv/bin/uvicorn" ] && ok "Uvicorn existe en .venv." || warn "Uvicorn no existe en .venv."

  if [ -f "$BACKEND_DIR/package-lock.json" ] && [ ! -f "$BACKEND_DIR/package.json" ]; then
    warn "Existe backend/package-lock.json sin backend/package.json. Probablemente fue creado accidentalmente por npm desde backend."
    echo "No lo borraré automáticamente."
    echo "Para removerlo del repo de forma segura:"
    echo "  git rm backend/package-lock.json"
    echo "  git commit -m \"Remove accidental backend npm lockfile\""
  fi

  echo
  info "Frontend:"
  [ -d "$FRONTEND_DIR/node_modules" ] && ok "frontend/node_modules existe." || warn "frontend/node_modules falta."
  [ -f "$FRONTEND_DIR/.env.local" ] && ok "frontend/.env.local existe." || warn "frontend/.env.local falta."

  echo
  info "Puertos:"
  if lsof -i :8000 >/dev/null 2>&1; then
    warn "Puerto 8000 ocupado."
    lsof -i :8000
  else
    ok "Puerto 8000 libre."
  fi

  if lsof -i :3000 >/dev/null 2>&1; then
    warn "Puerto 3000 ocupado."
    lsof -i :3000
  else
    ok "Puerto 3000 libre."
  fi
}

help_msg() {
  echo
  echo "CheckWise V1 safe helper"
  echo
  echo "Comandos:"
  echo "  ./scripts/checkwise_safe_v1.sh doctor"
  echo "  ./scripts/checkwise_safe_v1.sh backend-deps"
  echo "  ./scripts/checkwise_safe_v1.sh frontend-deps"
  echo "  ./scripts/checkwise_safe_v1.sh postgres"
  echo "  ./scripts/checkwise_safe_v1.sh migrate"
  echo "  ./scripts/checkwise_safe_v1.sh backend"
  echo "  ./scripts/checkwise_safe_v1.sh frontend"
  echo "  ./scripts/checkwise_safe_v1.sh verify"
  echo "  ./scripts/checkwise_safe_v1.sh test"
  echo
  echo "Orden correcto:"
  echo "  ./scripts/checkwise_safe_v1.sh doctor"
  echo "  ./scripts/checkwise_safe_v1.sh backend-deps"
  echo "  ./scripts/checkwise_safe_v1.sh frontend-deps"
  echo "  ./scripts/checkwise_safe_v1.sh postgres"
  echo "  ./scripts/checkwise_safe_v1.sh migrate"
  echo "  ./scripts/checkwise_safe_v1.sh backend"
  echo
  echo "En otra terminal:"
  echo "  ./scripts/checkwise_safe_v1.sh frontend"
  echo
}

case "$MODE" in
  doctor|status)
    doctor
    ;;
  backend-deps)
    backend_deps
    ;;
  frontend-deps)
    frontend_deps
    ;;
  postgres)
    start_postgres
    ;;
  migrate)
    migrate_db
    ;;
  backend)
    run_backend
    ;;
  frontend)
    run_frontend
    ;;
  verify)
    verify_api
    ;;
  test)
    run_tests
    ;;
  help|--help|-h)
    help_msg
    ;;
  *)
    fail "Comando desconocido: $MODE"
    help_msg
    exit 1
    ;;
esac
