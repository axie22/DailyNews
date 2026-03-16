#!/usr/bin/env bash
# setup_cron.sh — Install cron jobs for the ML News pipeline.
#
# Jobs installed:
#   1. Main pipeline  — every 6 hours  (arXiv + HF + RSS → summarize → store)
#   2. X pipeline     — every 24 hours (Twitter/X API, rate-limited)
#
# The jobs call POST /api/pipeline/trigger on the running backend.
# If the backend is unreachable the curl exits non-zero; the log will show it.
#
# Usage:
#   ./scripts/setup_cron.sh              # use defaults (port 8000)
#   BACKEND_PORT=9000 ./scripts/setup_cron.sh

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
BACKEND_PORT="${BACKEND_PORT:-8000}"
BACKEND_URL="http://localhost:${BACKEND_PORT}"
PIPELINE_INTERVAL_HOURS="${PIPELINE_INTERVAL_HOURS:-6}"

# ── Helpers ───────────────────────────────────────────────────────────────────
log() { printf '\033[1;34m[setup_cron]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m[setup_cron]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[setup_cron]\033[0m %s\n' "$*" >&2; }

# ── Log directory ─────────────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"

# ── Build cron expressions ────────────────────────────────────────────────────
# Main pipeline: every N hours on the hour  (default: every 6h → 0,6,12,18)
if [[ "$PIPELINE_INTERVAL_HOURS" -eq 1 ]]; then
    MAIN_CRON="* * * * *"   # every minute — only for testing
elif [[ "$PIPELINE_INTERVAL_HOURS" -le 23 ]]; then
    # Build comma-separated hours: 0, N, 2N, ...
    HOURS=""
    h=0
    while [[ $h -lt 24 ]]; do
        HOURS="${HOURS}${h},"
        h=$((h + PIPELINE_INTERVAL_HOURS))
    done
    HOURS="${HOURS%,}"   # strip trailing comma
    MAIN_CRON="0 ${HOURS} * * *"
else
    MAIN_CRON="0 0 * * *"
fi

X_CRON="0 3 * * *"   # X pipeline: once per day at 03:00 (low-traffic window)

# ── Cron command snippets ─────────────────────────────────────────────────────
MAIN_CMD="curl -sf -X POST ${BACKEND_URL}/api/pipeline/trigger >> ${LOG_DIR}/pipeline_cron.log 2>&1"
X_CMD="curl -sf -X POST ${BACKEND_URL}/api/pipeline/trigger?source=x >> ${LOG_DIR}/x_pipeline_cron.log 2>&1"

MAIN_TAG="# ml-news-main-pipeline"
X_TAG="# ml-news-x-pipeline"

MAIN_ENTRY="${MAIN_CRON} ${MAIN_CMD} ${MAIN_TAG}"
X_ENTRY="${X_CRON} ${X_CMD} ${X_TAG}"

# ── Install / update cron entries ─────────────────────────────────────────────
install_entry() {
    local tag="$1"
    local entry="$2"
    local label="$3"

    # Read existing crontab (or empty string if none)
    local current
    current="$(crontab -l 2>/dev/null || true)"

    if echo "$current" | grep -qF "$tag"; then
        log "Updating existing $label cron entry…"
        # Replace the line that contains the tag
        local updated
        updated="$(echo "$current" | grep -v "$tag")"
        printf '%s\n%s\n' "$updated" "$entry" | crontab -
    else
        log "Adding $label cron entry…"
        printf '%s\n%s\n' "$current" "$entry" | crontab -
    fi
}

install_entry "$MAIN_TAG" "$MAIN_ENTRY" "main pipeline"
install_entry "$X_TAG"    "$X_ENTRY"    "X pipeline"

# ── Show result ───────────────────────────────────────────────────────────────
ok "Cron jobs installed. Current ml-news entries:"
echo ""
crontab -l 2>/dev/null | grep "ml-news" | sed 's/^/  /'
echo ""
ok "Logs will be written to: $LOG_DIR/"
ok "To remove all ml-news cron jobs run:"
echo ""
echo "  crontab -l | grep -v 'ml-news' | crontab -"
echo ""
