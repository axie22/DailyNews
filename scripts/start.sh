#!/usr/bin/env bash
# start.sh — Bring the full ML News stack online.
#
# What this does, in order:
#   1. Copies .env.example → .env if .env is missing
#   2. docker compose up -d  (postgres + ollama + frontend)
#   3. Waits for postgres to pass its healthcheck
#   4. Pulls qwen3:4b into Ollama if not already present
#   5. Installs/syncs backend Python deps (uv)
#   6. Runs Alembic migrations (alembic upgrade head)
#   7. Starts the FastAPI backend  (uvicorn, hot-reload)
#
# Usage:
#   ./scripts/start.sh
#
# Suggested alias (add to ~/.zshrc or ~/.bashrc):
#   alias mlnews='~/path/to/DailyNews/scripts/start.sh'

set -euo pipefail

# ── Locate project root ────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
LOG_DIR="$PROJECT_ROOT/logs"

# ── Colour helpers ────────────────────────────────────────────────────────────
log()  { printf '\033[1;34m[mlnews]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[mlnews]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[mlnews]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[mlnews]\033[0m %s\n' "$*" >&2; }
step() { printf '\n\033[1;37m━━━ %s ━━━\033[0m\n' "$*"; }

# ── Cleanup: kill background processes on exit ─────────────────────────────────
PIDS=()
cleanup() {
    if [[ ${#PIDS[@]} -gt 0 ]]; then
        echo ""
        log "Shutting down background processes..."
        for pid in "${PIDS[@]}"; do
            kill "$pid" 2>/dev/null || true
        done
    fi
}
trap cleanup EXIT INT TERM

# ─────────────────────────────────────────────────────────────────────────────
step "1 / 7  Environment"
# ─────────────────────────────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"

ENV_FILE="$BACKEND_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    warn ".env not found — copying from .env.example"
    cp "$BACKEND_DIR/.env.example" "$ENV_FILE"
    warn "Edit $ENV_FILE before running if you need custom settings."
else
    ok ".env already exists"
fi

# ─────────────────────────────────────────────────────────────────────────────
step "2 / 7  Docker Compose (postgres + ollama + frontend)"
# ─────────────────────────────────────────────────────────────────────────────
if ! docker info &>/dev/null; then
    err "Docker is not running. Start Docker Desktop and try again."
    exit 1
fi
cd "$PROJECT_ROOT"

# Start infra + frontend containers; backend runs locally via uvicorn for hot-reload
RUNNING=$(docker compose ps --services --filter status=running 2>/dev/null || true)

for svc in postgres ollama frontend; do
    if echo "$RUNNING" | grep -q "^${svc}$"; then
        ok "$svc already running"
    else
        log "Starting $svc..."
        docker compose up -d --no-deps "$svc"
    fi
done

# ─────────────────────────────────────────────────────────────────────────────
step "3 / 7  Waiting for postgres healthcheck"
# ─────────────────────────────────────────────────────────────────────────────
MAX_WAIT=60
WAITED=0
until docker compose exec -T postgres pg_isready -U mlnews -q 2>/dev/null; do
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        err "Postgres did not become ready within ${MAX_WAIT}s. Check docker compose logs postgres"
        exit 1
    fi
    printf '.'
    sleep 2
    WAITED=$((WAITED + 2))
done
echo ""
ok "Postgres is ready"

# ─────────────────────────────────────────────────────────────────────────────
step "4 / 7  Ollama model (qwen3:4b)"
# ─────────────────────────────────────────────────────────────────────────────
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:4b}"

# Wait briefly for ollama HTTP server to come up before checking models
sleep 3

if docker compose exec -T ollama ollama list 2>/dev/null | grep -q "${OLLAMA_MODEL%%:*}"; then
    ok "Model $OLLAMA_MODEL already present"
else
    log "Pulling $OLLAMA_MODEL (this may take a few minutes on first run)..."
    docker compose exec -T ollama ollama pull "$OLLAMA_MODEL"
    ok "Model pulled"
fi

# ─────────────────────────────────────────────────────────────────────────────
step "5 / 7  Backend Python deps"
# ─────────────────────────────────────────────────────────────────────────────
cd "$BACKEND_DIR"

if command -v uv &>/dev/null; then
    log "uv sync..."
    uv sync --quiet
else
    warn "uv not found — falling back to pip install"
    pip install -e . --quiet
fi
ok "Dependencies up to date"

# ─────────────────────────────────────────────────────────────────────────────
step "6 / 7  Database migrations"
# ─────────────────────────────────────────────────────────────────────────────

# Source the .env so alembic can read DATABASE_URL
set -o allexport
# shellcheck source=/dev/null
source "$ENV_FILE"
set +o allexport

log "Running alembic upgrade head..."
uv run alembic upgrade head
ok "Migrations applied"

# ─────────────────────────────────────────────────────────────────────────────
step "7 / 7  Starting services"
# ─────────────────────────────────────────────────────────────────────────────
cd "$BACKEND_DIR"

BACKEND_LOG="$LOG_DIR/backend.log"

# Kill any process already holding port 8000
EXISTING_PID=$(lsof -ti tcp:8000 2>/dev/null || true)
if [[ -n "$EXISTING_PID" ]]; then
    warn "Port 8000 in use (PID $EXISTING_PID) — killing..."
    kill "$EXISTING_PID" 2>/dev/null || true
    sleep 1
fi

log "Starting backend → http://localhost:8000  (log: $BACKEND_LOG)"

if command -v uv &>/dev/null; then
    uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 \
        >> "$BACKEND_LOG" 2>&1 &
else
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 \
        >> "$BACKEND_LOG" 2>&1 &
fi
BACKEND_PID=$!
PIDS+=($BACKEND_PID)

# Wait for backend to accept connections
MAX_WAIT=30
WAITED=0
until curl -sf http://localhost:8000/api/health &>/dev/null; do
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        err "Backend did not start within ${MAX_WAIT}s. Check $BACKEND_LOG"
        exit 1
    fi
    printf '.'
    sleep 1
    WAITED=$((WAITED + 1))
done
echo ""
ok "Backend is up"

log "Waiting for frontend (npm install + next dev can take ~60s on first run)..."
MAX_WAIT=120
WAITED=0
until curl -sf http://localhost:3000 &>/dev/null; do
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        warn "Frontend not ready after ${MAX_WAIT}s — it may still be installing deps."
        warn "Check: docker compose logs frontend"
        break
    fi
    printf '.'
    sleep 2
    WAITED=$((WAITED + 2))
done
echo ""
ok "Frontend is up"

# ─────────────────────────────────────────────────────────────────────────────
echo ""
ok "Stack is running. Press Ctrl+C to stop."
echo ""
printf '  %-20s %s\n' "Frontend:"       "http://localhost:3000"
printf '  %-20s %s\n' "Backend API:"    "http://localhost:8000"
printf '  %-20s %s\n' "Swagger UI:"     "http://localhost:8000/docs"
printf '  %-20s %s\n' "Backend log:"    "$LOG_DIR/backend.log"
printf '  %-20s %s\n' "Cron log:"       "$LOG_DIR/pipeline_cron.log"
echo ""
echo "  Trigger pipeline manually:"
echo "    curl -X POST http://localhost:8000/api/pipeline/trigger"
echo ""

# Block until Ctrl+C
wait "${PIDS[@]}"
