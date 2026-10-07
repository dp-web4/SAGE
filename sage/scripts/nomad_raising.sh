#!/bin/bash
# Nomad SAGE raising session + snapshot + auto-commit
# Runs a raising session, snapshots state, commits results, pushes to origin.
# Designed to run via cron or manually on Nomad (WSL2, RTX 4060).

set -e

SAGE_DIR="${SAGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PYTHONPATH="$SAGE_DIR"
export PYTHONPATH
PYTHON="python3"

cd "$SAGE_DIR"

echo "[Nomad-Raising] $(date -u +'%Y-%m-%d %H:%M UTC') — Starting raising session"

# Ensure daemon is running and up-to-date (also pulls latest code)
source "$SAGE_DIR/sage/scripts/ensure_daemon.sh"
echo "[Nomad-Raising] Daemon: version=$SAGE_DAEMON_VERSION updated=$SAGE_DAEMON_UPDATED"

# Run the raising session (continue from last session number)
$PYTHON -m sage.raising.scripts.ollama_raising_session --machine nomad -c 2>&1

# Instance directory (switched to gemma4:e2b 2026-06-03; see run_nomad_raising.sh header)
INSTANCE_DIR="sage/instances/nomad-gemma4-e2b"

# Snapshot live state files into git-tracked snapshots/ directory
echo "[Nomad-Raising] Snapshotting state..."
$PYTHON -m sage.scripts.snapshot_state --machine nomad

# Check if there are new results to commit
CHANGED=0

# Check instance dir (sessions + snapshots)
if [ -d "$INSTANCE_DIR" ]; then
    if ! git diff --quiet "$INSTANCE_DIR/" 2>/dev/null; then
        CHANGED=1
    fi
    if [ -n "$(git ls-files --others --exclude-standard "$INSTANCE_DIR/" 2>/dev/null)" ]; then
        CHANGED=1
    fi
fi

if [ "$CHANGED" -eq 0 ]; then
    echo "[Nomad-Raising] No new raising data to commit."
    exit 0
fi

# Read session number from identity snapshot
IDENTITY_FILE="$INSTANCE_DIR/snapshots/identity.json"
if [ ! -f "$IDENTITY_FILE" ]; then
    IDENTITY_FILE="$INSTANCE_DIR/identity.json"
fi

SESSION_NUM=$($PYTHON -c "
import json
with open('$SAGE_DIR/$IDENTITY_FILE') as f:
    print(json.load(f)['identity']['session_count'])
" 2>/dev/null || echo "?")

PHASE=$($PYTHON -c "
import json
with open('$SAGE_DIR/$IDENTITY_FILE') as f:
    print(json.load(f)['development']['phase_name'])
" 2>/dev/null || echo "?")

# --- Dream consolidation (Claude reviews the session) ---
echo "[Nomad-Raising] Running dream consolidation..."
$PYTHON -m sage.raising.scripts.dream_consolidation \
    --instance "$INSTANCE_DIR" \
    --session "$SESSION_NUM" 2>&1 || {
    echo "[Nomad-Raising] Dream consolidation skipped (claude --print not available or timed out)"
}

# Stage instance dir (sessions + snapshots, live state files are gitignored)
git add "$INSTANCE_DIR/" 2>/dev/null || true

git commit -m "[Nomad-Raising] Session $SESSION_NUM ($PHASE) — $(date -u +'%Y-%m-%d %H:%M UTC')

Automated SAGE-Nomad raising session via OllamaIRP
Machine: Nomad (Legion laptop, RTX 4060, WSL2)
Model: Gemma 3 4B (google-gemma family)
Phase: $PHASE
AI-Instance: OllamaIRP (automated)
Human-Supervised: no"

# Push (with rebase to handle race conditions from other machines)
git pull --rebase --quiet 2>/dev/null || true
git push origin main
echo "[Nomad-Raising] Session $SESSION_NUM committed and pushed."
