#!/usr/bin/env bash
# Persist the SQLite state between GitHub Actions runs on an orphan `data` branch.
#
#   scripts/state.sh pull   # restore state/dailynews.db (fresh DB if the branch doesn't exist yet)
#   scripts/state.sh push   # snapshot it as a single-commit orphan branch (force-push, no history bloat)
#
# If STATE_KEY is set, the DB is encrypted with AES-256 before it leaves the runner. Use this on
# a public repo — otherwise anyone can download your ratings and reading history.
#
# Safety: push refuses to run unless pull succeeded in this job (marker file), so a failed
# decrypt or restore can never overwrite good state with an empty database.
set -euo pipefail

DB="${DAILYNEWS_DB:-state/dailynews.db}"
BRANCH="${STATE_BRANCH:-data}"
MARKER="$(dirname "$DB")/.restored"
ENC_NAME="dailynews.db.enc"
PLAIN_NAME="dailynews.db"

encrypt() { openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:STATE_KEY -in "$1" -out "$2"; }
decrypt() { openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:STATE_KEY -in "$1" -out "$2"; }

pull() {
  mkdir -p "$(dirname "$DB")"
  rm -f "$MARKER"
  if ! git fetch --quiet --depth=1 origin "$BRANCH" 2>/dev/null; then
    echo "state: no '$BRANCH' branch yet — starting fresh"
    touch "$MARKER"; return 0
  fi
  if git cat-file -e "FETCH_HEAD:$ENC_NAME" 2>/dev/null; then
    [[ -n "${STATE_KEY:-}" ]] || { echo "state: branch holds an encrypted DB but STATE_KEY is not set" >&2; exit 1; }
    git show "FETCH_HEAD:$ENC_NAME" > "$DB.enc"
    decrypt "$DB.enc" "$DB" || { echo "state: decrypt failed (wrong STATE_KEY?)" >&2; rm -f "$DB"; exit 1; }
    rm -f "$DB.enc"
  elif git cat-file -e "FETCH_HEAD:$PLAIN_NAME" 2>/dev/null; then
    git show "FETCH_HEAD:$PLAIN_NAME" > "$DB"
  else
    echo "state: '$BRANCH' exists but has no DB — starting fresh"
  fi
  if [[ -f "$DB" ]]; then
    python3 - "$DB" <<'EOF'
import sqlite3, sys
r = sqlite3.connect(sys.argv[1]).execute("PRAGMA integrity_check").fetchone()[0]
sys.exit(0 if r == "ok" else f"state: integrity check failed: {r}")
EOF
    echo "state: restored $(du -h "$DB" | cut -f1)"
  fi
  touch "$MARKER"
}

push() {
  [[ -f "$MARKER" ]] || { echo "state: pull did not succeed in this job — refusing to push" >&2; exit 1; }
  [[ -f "$DB" ]] || { echo "state: no DB to save"; return 0; }
  local file name
  if [[ -n "${STATE_KEY:-}" ]]; then
    file="$DB.enc"; name="$ENC_NAME"; encrypt "$DB" "$file"
  else
    file="$DB"; name="$PLAIN_NAME"
  fi
  export GIT_AUTHOR_NAME="dailynews-bot" GIT_AUTHOR_EMAIL="dailynews-bot@users.noreply.github.com"
  export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
  local blob tree commit
  blob=$(git hash-object -w "$file")
  tree=$(printf '100644 blob %s\t%s\n' "$blob" "$name" | git mktree)
  commit=$(git commit-tree "$tree" -m "state $(date -u +%FT%TZ)")
  git push --quiet --force origin "$commit:refs/heads/$BRANCH"
  echo "state: saved $(du -h "$file" | cut -f1) to '$BRANCH'"
}

case "${1:-}" in
  pull) pull ;;
  push) push ;;
  *) echo "usage: $0 pull|push" >&2; exit 2 ;;
esac
