#!/usr/bin/env bash
# Start BizzCheckup for local development: double-click this file (Git Bash),
# or run ./start.sh in a terminal. Every step is skipped when already done, so
# the second start is fast.
#
#   1. virtual environment + libraries (re-installed only when requirements change),
#      and headless Chromium for the browser checks (once per Playwright version)
#   2. .env with a fresh secret key (first run only)
#   3. PostgreSQL + Redis in Docker (if Docker is running; otherwise SQLite)
#   4. Tailwind CSS: download once, then rebuild automatically while you work
#   5. database migrations
#   6. Celery worker (only when Redis is available)
#   7. Django development server
#
# Stop everything with Ctrl+C. Use another port with: PORT=8001 ./start.sh

set -euo pipefail
cd "$(dirname "$0")"

RUN_DIR=".run"   # log files and markers (ignored by git)
mkdir -p "$RUN_DIR"
PIDS=()

# --- helpers ------------------------------------------------------------------

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
info() { printf '    %s\n' "$1"; }
warn() { printf '    \033[1;33m! %s\033[0m\n' "$1"; }

pause_before_exit() {
  # A double-clicked window closes immediately; keep it open so messages can be read.
  if [ -t 0 ]; then read -rp $'\nPress Enter to close this window...' _ || true; fi
}

fail() {
  printf '\n\033[1;31mX %s\033[0m\n' "$1"
  pause_before_exit
  exit 1
}

kill_tree() {
  # Stop a background program AND anything it started (Django's auto-reloader
  # runs the server in a child process). Windows needs taskkill for that.
  local pid="$1"
  if [ -r "/proc/$pid/winpid" ] && command -v taskkill >/dev/null 2>&1; then
    taskkill //T //F //PID "$(cat "/proc/$pid/winpid")" >/dev/null 2>&1 || true
  else
    pkill -TERM -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null || true
  fi
}

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] && kill_tree "$pid"
  done
}
trap cleanup EXIT
trap 'echo; info "Stopping..."; exit 0' INT TERM

port_in_use() {
  "$PY" -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', int(sys.argv[1]))) == 0 else 1)" "$1"
}

env_value() { grep -E "^$1=" .env | tail -n1 | cut -d= -f2-; }

# --- 1. Python and the virtual environment --------------------------------------

step "Checking Python"
SYSTEM_PY=""
for candidate in python3 python py; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys; sys.exit(sys.version_info < (3, 12))" 2>/dev/null; then
    SYSTEM_PY="$candidate"; break
  fi
done
[ -n "$SYSTEM_PY" ] || fail "Python 3.12 or newer is required: https://www.python.org/downloads/"
info "$("$SYSTEM_PY" --version)"

if [ ! -d .venv ]; then
  step "Creating the virtual environment (.venv)"
  "$SYSTEM_PY" -m venv .venv
fi

if [ -x .venv/Scripts/python.exe ]; then
  PY=".venv/Scripts/python.exe"; BIN=".venv/Scripts"   # Windows
else
  PY=".venv/bin/python"; BIN=".venv/bin"               # macOS / Linux
fi

REQ_HASH="$(cat requirements/*.txt | "$PY" -c "import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())")"
if [ "$(cat "$RUN_DIR/requirements.sha" 2>/dev/null || true)" != "$REQ_HASH" ]; then
  step "Installing libraries (requirements/dev.txt)"
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" -m pip install --quiet -r requirements/dev.txt
  echo "$REQ_HASH" > "$RUN_DIR/requirements.sha"
else
  info "Libraries are up to date."
fi

PW_VERSION="$("$PY" -c "from importlib.metadata import version; print(version('playwright'))")"
if [ "$(cat "$RUN_DIR/playwright.version" 2>/dev/null || true)" != "$PW_VERSION" ]; then
  step "Installing headless Chromium for the browser checks (one-time, ~150 MB)"
  "$PY" -m playwright install --only-shell chromium
  echo "$PW_VERSION" > "$RUN_DIR/playwright.version"
fi

# --- 2. .env -------------------------------------------------------------------

if [ ! -f .env ]; then
  step "Creating .env from .env.example"
  SECRET="$("$PY" -c "import secrets; print(secrets.token_urlsafe(50))")"
  sed "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$SECRET|" .env.example > .env
  info "A new secret key was generated. Edit .env to add PSI_API_KEY later."
fi

# --- 3. Docker services (PostgreSQL + Redis) ------------------------------------

step "Checking Docker"
REDIS_READY=false
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  info "Starting PostgreSQL and Redis..."
  docker compose up -d --wait postgres redis >/dev/null || fail "Docker services didn't start. See: docker compose logs"
  info "PostgreSQL and Redis are running."
  REDIS_READY=true
  if [[ "$(env_value DATABASE_URL)" == sqlite* ]]; then
    warn ".env uses SQLite. To use PostgreSQL set:"
    warn "DATABASE_URL=postgres://bizzcheckup:bizzcheckup@localhost:5432/bizzcheckup"
  fi
else
  warn "Docker isn't running, so PostgreSQL, Redis and the worker are skipped."
  warn "Pages work; check-ups need Docker (install Docker Desktop and start it)."
  if [[ "$(env_value DATABASE_URL)" != sqlite* ]]; then
    info "Switching .env to SQLite so the site can still start."
    sed -i.bak "s|^DATABASE_URL=.*|DATABASE_URL=sqlite:///db.sqlite3|" .env && rm -f .env.bak
  fi
fi

# --- 4. Tailwind CSS -------------------------------------------------------------

step "Preparing CSS"
TAILWIND=".bin/tailwindcss"
[ -f "$TAILWIND.exe" ] && TAILWIND="$TAILWIND.exe"
if [ ! -f "$TAILWIND" ]; then
  "$PY" scripts/get_tailwind.py
  TAILWIND=".bin/tailwindcss"; [ -f "$TAILWIND.exe" ] && TAILWIND="$TAILWIND.exe"
fi
"$TAILWIND" -i frontend/tailwind.css -o static/css/app.css --minify >/dev/null 2>&1 || fail "CSS build failed."
"$TAILWIND" -i frontend/tailwind.css -o static/css/app.css --watch >"$RUN_DIR/tailwind.log" 2>&1 &
PIDS+=($!)
info "CSS built; it rebuilds automatically when you edit templates (log: $RUN_DIR/tailwind.log)."

# --- 5. Database -----------------------------------------------------------------

step "Updating the database"
"$PY" manage.py migrate --noinput -v 0 || fail "Migrations failed (is the database running?)."
info "Database is up to date."

# --- 6. Celery worker -------------------------------------------------------------

if [ "$REDIS_READY" = true ]; then
  step "Starting the background worker"
  # --pool=solo: Celery's default process pool doesn't work on Windows.
  "$BIN/celery" -A config worker --loglevel=info --pool=solo >"$RUN_DIR/worker.log" 2>&1 &
  PIDS+=($!)
  info "Worker running (log: $RUN_DIR/worker.log)."
fi

# --- 7. Web server -----------------------------------------------------------------

PORT="${PORT:-8000}"
while port_in_use "$PORT"; do
  warn "Port $PORT is busy, trying $((PORT + 1))."
  PORT=$((PORT + 1))
done

step "Starting BizzCheckup"
info "Website:     http://127.0.0.1:$PORT/"
info "Style guide: http://127.0.0.1:$PORT/styleguide/"
info "Admin:       http://127.0.0.1:$PORT/admin/  (create a login: $PY manage.py createsuperuser)"
info "Press Ctrl+C to stop."
echo

"$PY" manage.py runserver "127.0.0.1:$PORT" &
PIDS+=($!)
wait "$!" || true
pause_before_exit
