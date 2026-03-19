#!/usr/bin/env bash
# Manually trigger all scrapers (main + X) and show progress.
# Usage: ./scrape.sh

set -euo pipefail

API="http://localhost:8000/api/pipeline"

# Check backend is reachable
if ! curl -sf "$API/status" > /dev/null 2>&1; then
  echo "Backend not reachable at $API. Starting containers..."
  docker compose up -d
  echo "Waiting for backend to be ready..."
  for i in $(seq 1 30); do
    if curl -sf "$API/status" > /dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  if ! curl -sf "$API/status" > /dev/null 2>&1; then
    echo "ERROR: Backend did not start in time."
    exit 1
  fi
fi

echo "Triggering main pipeline (arXiv, HF, RSS)..."
curl -sf -X POST "$API/trigger" | python3 -m json.tool

echo "Triggering X pipeline..."
curl -sf -X POST "$API/trigger-x" | python3 -m json.tool

echo ""
echo "Pipelines running in background. Polling status..."
echo ""

while true; do
  status=$(curl -sf "$API/status" 2>/dev/null) || { echo "Lost connection"; exit 1; }
  phase=$(echo "$status" | python3 -c "import sys,json; print(json.load(sys.stdin)['phase'])")

  if [ "$phase" = "idle" ]; then
    # Brief pause — pipeline may not have started yet
    sleep 2
    status=$(curl -sf "$API/status" 2>/dev/null)
    phase=$(echo "$status" | python3 -c "import sys,json; print(json.load(sys.stdin)['phase'])")
    if [ "$phase" = "idle" ]; then
      echo "$status" | python3 -c "
import sys, json
s = json.load(sys.stdin)
sc = s['scrape']
sm = s['summarization']
rc = s['recommendation']
un = s.get('unsummarized_count', 0)
print(f'Done! Scraped {sc[\"articles_fetched\"]} articles, stored {sc[\"articles_stored\"]} new.')
print(f'Summarized {sm[\"done\"]}/{sm[\"total\"]} (failures: {sm[\"failures\"]})')
print(f'Recommended: {rc[\"recommended\"]} top picks')
if un > 0:
    print(f'Note: {un} articles still unsummarized')
if s['recent_errors']:
    print(f'Errors: {\", \".join(s[\"recent_errors\"][:3])}')
"
      break
    fi
  fi

  echo "$status" | python3 -c "
import sys, json
s = json.load(sys.stdin)
phase = s['phase']
sm = s['summarization']
elapsed = s.get('elapsed_s') or 0
eta = s.get('eta_s')
parts = [f'Phase: {phase}', f'Elapsed: {int(elapsed)}s']
if sm['total'] > 0:
    parts.append(f'Summarized: {sm[\"done\"]}/{sm[\"total\"]}')
if eta and eta > 0:
    parts.append(f'ETA: {int(eta)}s')
print(' | '.join(parts))
"
  sleep 5
done
